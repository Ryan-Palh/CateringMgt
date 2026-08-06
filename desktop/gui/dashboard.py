# -*- coding: utf-8 -*-
"""
工作台 v5.0 —— 餐饮专业版 Dashboard
- 餐饮核心指标：今日营业额、客单价、翻台率、在岗人数
- 低库存预警、待办事项、本月经营概览
- 快捷操作：录入营业额、采购进货、提交报销、打卡考勤
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QFrame, QPushButton, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt, pyqtSignal
from utils.font_utils import make_font

from database.db_manager import get_connection
from utils.helpers import format_money, get_today
from utils.app_context import get_app_context as _ctx
from utils.nutstore_sync import get_sync
from gui.theme import COLOR, RADIUS, FONT_SIZE, TABLE_STYLE
from utils.validators import get_low_stock_items
from utils.data_io import full_backup, full_restore
from utils.logger import logger


class StatCard(QFrame):
    """统计卡片 —— 渐变色背景 + 白色文字"""
    # 每张卡片对应的渐变色对 (起始色, 结束色)
    GRADIENTS = {
        "#5B6CFF": ("#667EEA", "#764BA2"),  # 蓝紫
        "#06B6D4": ("#0891B2", "#06B6D4"),  # 青色
        "#F59E0B": ("#F59E0B", "#EF4444"),  # 橙红
        "#A78BFA": ("#8B5CF6", "#EC4899"),  # 紫粉
    }

    def __init__(self, title, value, color, extra="", icon=""):
        super().__init__()
        self.setObjectName("statCard")
        self._color = color
        grad_start, grad_end = self.GRADIENTS.get(color, (color, color))
        self.setMinimumHeight(120)
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background-color: {grad_start};
                border-radius: {RADIUS['lg']}px;
                border: none;
            }}
        """)
        # 用paintEvent绘制渐变
        self._grad_start = grad_start
        self._grad_end = grad_end
        self._radius = RADIUS['lg']

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(f"font-size: 20px; background: transparent; color: white;")
            top.addWidget(icon_lbl)
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"color: rgba(255,255,255,0.85); font-size: {FONT_SIZE['sm']}px; font-weight: 500; background: transparent;")
        top.addWidget(self.lbl_title)
        top.addStretch()
        layout.addLayout(top)

        self.lbl_value = QLabel(value)
        self.lbl_value.setFont(make_font(28, bold=True))
        self.lbl_value.setStyleSheet(f"color: white; background: transparent;")
        layout.addWidget(self.lbl_value)

        self.lbl_extra = QLabel(extra)
        self.lbl_extra.setStyleSheet(f"color: rgba(255,255,255,0.7); font-size: {FONT_SIZE['xs']}px; background: transparent;")
        layout.addWidget(self.lbl_extra)

        layout.addStretch()
        self.setLayout(layout)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QLinearGradient, QColor
        from PyQt5.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor(self._grad_start))
        grad.setColorAt(1, QColor(self._grad_end))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self._radius, self._radius)
        # 子控件需要设置透明背景以显示渐变
        super().paintEvent(event)


class WarningCard(QFrame):
    """预警卡片 —— 渐变色背景 + 预警数量 + 可点击查看详情"""
    YELLOW_GRAD = ("#F59E0B", "#EF4444")  # 黄色预警: 橙→红
    RED_GRAD = ("#DC2626", "#991B1B")      # 红色预警: 深红→暗红

    clicked = pyqtSignal()

    def __init__(self, title="库存预警"):
        super().__init__()
        self.setObjectName("warningCard")
        self._grad_start = self.YELLOW_GRAD[0]
        self._grad_end = self.YELLOW_GRAD[1]
        self._radius = RADIUS['lg']
        self.setMinimumHeight(90)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#warningCard {{
                border-radius: {RADIUS['lg']}px;
                border: none;
            }}
        """)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon_lbl = QLabel("⚠")
        icon_lbl.setStyleSheet("font-size: 18px; background: transparent; color: white;")
        top.addWidget(icon_lbl)
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"font-size: {FONT_SIZE['sm']}px; font-weight: 500; color: rgba(255,255,255,0.85); background: transparent;")
        top.addWidget(self.lbl_title)
        top.addStretch()
        layout.addLayout(top)

        self.lbl_count = QLabel("0")
        self.lbl_count.setFont(make_font(26, bold=True))
        self.lbl_count.setStyleSheet("color: white; background: transparent;")
        layout.addWidget(self.lbl_count)

        self.lbl_hint = QLabel("项预警 · 点击查看详情")
        self.lbl_hint.setStyleSheet(f"font-size: {FONT_SIZE['xs']}px; color: rgba(255,255,255,0.7); background: transparent;")
        layout.addWidget(self.lbl_hint)

        layout.addStretch()
        self.setLayout(layout)

    def set_count(self, count):
        self.lbl_count.setText(str(count))

    def set_level(self, level):
        if level == "red":
            self._grad_start, self._grad_end = self.RED_GRAD
        else:
            self._grad_start, self._grad_end = self.YELLOW_GRAD
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QLinearGradient, QColor
        from PyQt5.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor(self._grad_start))
        grad.setColorAt(1, QColor(self._grad_end))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self._radius, self._radius)
        super().paintEvent(event)


class DashboardWidget(QWidget):
    def __init__(self, user):
        super().__init__()
        self.current_user = user
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ===== 顶部：欢迎 + 数据操作 =====
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        title = QLabel(f"欢迎回来，{self.current_user['name']}")
        title.setStyleSheet(f"font-size: {FONT_SIZE['2xl']}px; font-weight: 700; color: {COLOR['text_primary']};")
        top_row.addWidget(title)
        top_row.addStretch()

        for text, cb, hover_color in [
            ("  手动备份  ", self.manual_backup, COLOR['primary']),
            ("  导出数据  ", self.export_data, COLOR['accent']),
            ("  恢复数据  ", self.restore_data, COLOR['warning']),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR['bg_card']};
                    border: 1px solid {COLOR['border']};
                    border-radius: {RADIUS['md']}px;
                    padding: 8px 18px;
                    font-size: {FONT_SIZE['base']}px;
                    color: {COLOR['text_secondary']};
                }}
                QPushButton:hover {{
                    border-color: {hover_color};
                    color: {hover_color};
                    background-color: {COLOR['bg_page']};
                }}
            """)
            btn.clicked.connect(cb)
            top_row.addWidget(btn)

        layout.addLayout(top_row)

        # ===== 统计卡片（4列） =====
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)

        self.card_revenue = StatCard("今日营业额", "加载中...", COLOR['primary'], icon="💰")
        self.card_avg = StatCard("今日客单价", "加载中...", COLOR['accent'], icon="🍽")
        self.card_approval = StatCard("待审批事项", "加载中...", COLOR['warning'], icon="📋")
        self.card_employee = StatCard("在岗员工", "加载中...", COLOR['chart_5'], icon="👥")

        for card in [self.card_revenue, self.card_avg, self.card_approval, self.card_employee]:
            cards_layout.addWidget(card, 1)
        layout.addLayout(cards_layout)

        # ===== 快捷操作 =====
        ops_layout = QHBoxLayout()
        ops_layout.setSpacing(16)

        for text, cb, clr in [
            ("  录入营业额", self.open_revenue, COLOR['primary']),
            ("  采购进货", self.open_purchase, COLOR['accent']),
            ("  提交报销", self.open_reimb, COLOR['warning']),
            ("  打卡考勤", self.open_attendance, COLOR['info']),
        ]:
            btn = QPushButton(text)
            btn.setMinimumHeight(48)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR['bg_card']};
                    border: 1px solid {COLOR['border_light']};
                    border-radius: {RADIUS['lg']}px;
                    font-size: {FONT_SIZE['lg']}px;
                    color: {clr}; font-weight: 500;
                }}
                QPushButton:hover {{
                    border-color: {clr};
                    background-color: {COLOR['bg_page']};
                }}
            """)
            btn.clicked.connect(cb)
            ops_layout.addWidget(btn, 1)

        layout.addLayout(ops_layout)

        # ===== 预警卡片（并排） =====
        warning_layout = QHBoxLayout()
        warning_layout.setSpacing(16)

        self.stock_warning_frame = WarningCard("库存预警")
        self.stock_warning_frame.setVisible(False)
        self.stock_warning_frame.clicked.connect(self._show_stock_warning_detail)
        warning_layout.addWidget(self.stock_warning_frame, 1)

        self.expiry_warning_frame = WarningCard("过期预警")
        self.expiry_warning_frame.setVisible(False)
        self.expiry_warning_frame.clicked.connect(self._show_expiry_warning_detail)
        warning_layout.addWidget(self.expiry_warning_frame, 1)

        layout.addLayout(warning_layout)

        # ===== 下半部分：待办 + 概览 =====
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(16)

        # 待办事项
        todo_frame = QFrame()
        todo_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR['bg_card']};
                border-radius: {RADIUS['xl']}px;
                border: 1px solid {COLOR['border_light']};
            }}
        """)
        todo_layout = QVBoxLayout(todo_frame)
        todo_layout.setContentsMargins(0, 0, 0, 0)
        todo_layout.setSpacing(0)

        todo_header = QFrame()
        todo_header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR['primary']};
                border-top-left-radius: {RADIUS['xl']}px;
                border-top-right-radius: {RADIUS['xl']}px;
            }}
        """)
        todo_header.setMinimumHeight(44)
        th_layout = QHBoxLayout(todo_header)
        th_layout.setContentsMargins(20, 8, 20, 8)
        todo_title = QLabel("待办事项")
        todo_title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: 700; color: white;")
        th_layout.addWidget(todo_title)
        th_layout.addStretch()
        todo_layout.addWidget(todo_header)

        todo_body = QWidget()
        tb_layout = QVBoxLayout(todo_body)
        tb_layout.setContentsMargins(20, 12, 20, 16)
        tb_layout.setSpacing(8)

        self.todo_table = QTableWidget()
        self.todo_table.setColumnCount(3)
        self.todo_table.setHorizontalHeaderLabels(["类型", "内容", "日期"])
        self.todo_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.todo_table.horizontalHeader().setStretchLastSection(False)
        self.todo_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.todo_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.todo_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.todo_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.todo_table.verticalHeader().setVisible(False)
        self.todo_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.todo_table.verticalHeader().setDefaultSectionSize(38)
        self.todo_table.setMinimumHeight(180)
        self.todo_table.setStyleSheet(TABLE_STYLE)
        tb_layout.addWidget(self.todo_table, 1)

        # 本月概览
        overview_frame = QFrame()
        overview_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR['bg_card']};
                border-radius: {RADIUS['xl']}px;
                border: 1px solid {COLOR['border_light']};
            }}
        """)
        overview_layout = QVBoxLayout(overview_frame)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(0)

        overview_header = QFrame()
        overview_header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR['accent']};
                border-top-left-radius: {RADIUS['xl']}px;
                border-top-right-radius: {RADIUS['xl']}px;
            }}
        """)
        overview_header.setMinimumHeight(44)
        oh_layout = QHBoxLayout(overview_header)
        oh_layout.setContentsMargins(20, 8, 20, 8)
        overview_title = QLabel("本月经营概览")
        overview_title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: 700; color: white;")
        oh_layout.addWidget(overview_title)
        oh_layout.addStretch()
        overview_layout.addWidget(overview_header)

        overview_body = QWidget()
        ob_layout = QVBoxLayout(overview_body)
        ob_layout.setContentsMargins(20, 12, 20, 16)
        ob_layout.setSpacing(8)

        self.overview_table = QTableWidget()
        self.overview_table.setColumnCount(2)
        self.overview_table.setHorizontalHeaderLabels(["指标", "数值"])
        self.overview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.overview_table.horizontalHeader().setStretchLastSection(False)
        self.overview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.overview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.overview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.overview_table.verticalHeader().setVisible(False)
        self.overview_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.overview_table.verticalHeader().setDefaultSectionSize(38)
        self.overview_table.setMinimumHeight(180)
        self.overview_table.setStyleSheet(TABLE_STYLE)
        ob_layout.addWidget(self.overview_table, 1)

        todo_layout.addWidget(todo_body)
        bottom_layout.addWidget(todo_frame, 3)
        overview_layout.addWidget(overview_body)
        bottom_layout.addWidget(overview_frame, 2)
        layout.addLayout(bottom_layout, 1)

        self.setLayout(layout)

    def _show_stock_warning_detail(self):
        """库存预警详情对话框"""
        items = getattr(self, "_stock_warning_items", [])
        if not items:
            return
        dlg = QMessageBox(self)
        dlg.setWindowTitle("库存预警详情")
        dlg.setIcon(QMessageBox.Warning)
        lines = []
        for it in items:
            mark = "🔴" if it["level"] == "red" else "🟡"
            lines.append(f"{mark} {it['name']} — 当前库存: {it['stock']:.1f}{it.get('unit', '')}")
        dlg.setText(f"共 {len(items)} 项库存预警：\n\n" + "\n".join(lines))
        dlg.exec_()

    def _show_expiry_warning_detail(self):
        """过期预警详情对话框"""
        items = getattr(self, "_expiry_warning_items", [])
        if not items:
            return
        dlg = QMessageBox(self)
        dlg.setWindowTitle("过期预警详情")
        dlg.setIcon(QMessageBox.Warning)
        lines = []
        for it in items:
            mark = "🔴" if it["level"] == "red" else "🟡"
            lines.append(f"{mark} {it['text']}")
        dlg.setText(f"共 {len(items)} 项过期预警：\n\n" + "\n".join(lines))
        dlg.exec_()

    def load_data(self):
        self.refresh_data()

    def refresh_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        today = get_today()
        month = today[:7]
        _sid, _all = _ctx().get_store_filter()

        def q(sql, params):
            if _all:
                # 全部门店：去掉 store_id 条件和对应参数
                clean_sql = sql.replace(" AND (store_id=? OR store_id IS NULL)", "")
                # params 是元组，最后一个参数是 store_id，去掉它
                if isinstance(params, tuple) and len(params) > 1:
                    params = params[:-1]
                elif isinstance(params, tuple) and len(params) == 1:
                    params = ()
                return cursor.execute(clean_sql, params).fetchone()
            return cursor.execute(sql, params).fetchone()

        # 今日营业额
        row = q("SELECT COALESCE(SUM(amount),0), COALESCE(SUM(order_count),0) FROM daily_revenue WHERE record_date=? AND (store_id=? OR store_id IS NULL)", (today, _sid))
        today_revenue = row[0] if row else 0
        today_orders = row[1] if row and len(row) > 1 else 0
        self.card_revenue.lbl_value.setText(f"¥{format_money(today_revenue)}")
        self.card_revenue.lbl_extra.setText(f"订单数：{today_orders}")

        # 客单价
        avg = today_revenue / today_orders if today_orders and today_orders > 0 else 0
        self.card_avg.lbl_value.setText(f"¥{format_money(avg)}")
        self.card_avg.lbl_extra.setText(f"订单：{today_orders} 单")

        # 待审批
        row = q("SELECT COUNT(*) FROM approvals WHERE status='待审批' AND (store_id=? OR store_id IS NULL)", (_sid,))
        self.card_approval.lbl_value.setText(str(row[0] if row else 0))

        # 在岗员工
        row = q("SELECT COUNT(*) FROM employees WHERE status='在职' AND (store_id=? OR store_id IS NULL)", (_sid,))
        self.card_employee.lbl_value.setText(str(row[0] if row else 0))

        # 低库存预警（基于交易记录计算当前库存）
        from datetime import date
        low_items = []
        if _all:
            cursor.execute("SELECT id, name, unit FROM ingredients")
        else:
            cursor.execute(
                "SELECT id, name, unit FROM ingredients "
                "WHERE store_id=? OR store_id IS NULL", (_sid,))
        ing_rows = [dict(r) for r in cursor.fetchall()]
        for ing in ing_rows:
            ing_id = ing["id"]
            if _all:
                cursor.execute(
                    "SELECT COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END),0) - "
                    "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END),0) as ti, "
                    "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END),0) as tout "
                    "FROM purchase_items pi JOIN purchases p ON pi.purchase_id=p.id "
                    "WHERE pi.ingredient_id=?", (ing_id,))
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END),0) - "
                    "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END),0) as ti, "
                    "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END),0) as tout "
                    "FROM purchase_items pi JOIN purchases p ON pi.purchase_id=p.id "
                    "WHERE pi.ingredient_id=? AND (p.store_id=? OR p.store_id IS NULL)",
                    (ing_id, _sid))
            sr = cursor.fetchone()
            if sr:
                d = dict(sr)
                stock = d["ti"] - d["tout"]
                if stock < 0:
                    stock = 0
                if stock < 10:
                    level = "red" if stock < 5 else "yellow"
                    low_items.append({"name": ing["name"], "stock": stock, "unit": ing.get("unit", ""), "level": level})
        self._stock_warning_items = low_items
        if low_items:
            self.stock_warning_frame.set_count(len(low_items))
            has_red = any(it["level"] == "red" for it in low_items)
            self.stock_warning_frame.set_level("red" if has_red else "yellow")
            self.stock_warning_frame.setVisible(True)
        else:
            self.stock_warning_frame.setVisible(False)

        # 过期预警（检查最近进货中有生产日期+保质期的产品）
        today = date.today()
        expiry_items = []
        if _all:
            cursor.execute(
                "SELECT pi.ingredient_id, pi.production_date, i.name, i.expiry_months, i.expiry_days, i.unit "
                "FROM purchase_items pi JOIN ingredients i ON pi.ingredient_id = i.id "
                "JOIN purchases p ON pi.purchase_id = p.id "
                "WHERE pi.production_date IS NOT NULL AND pi.production_date != '' "
                "AND (i.expiry_months > 0 OR i.expiry_days > 0) "
                "GROUP BY pi.ingredient_id ORDER BY pi.production_date DESC")
        else:
            cursor.execute(
                "SELECT pi.ingredient_id, pi.production_date, i.name, i.expiry_months, i.expiry_days, i.unit "
                "FROM purchase_items pi JOIN ingredients i ON pi.ingredient_id = i.id "
                "JOIN purchases p ON pi.purchase_id = p.id "
                "WHERE pi.production_date IS NOT NULL AND pi.production_date != '' "
                "AND (i.expiry_months > 0 OR i.expiry_days > 0) "
                "AND (p.store_id=? OR p.store_id IS NULL) "
                "GROUP BY pi.ingredient_id ORDER BY pi.production_date DESC",
                (_sid,))
        from datetime import datetime, timedelta
        for r in cursor.fetchall():
            d = dict(r)
            try:
                pd = datetime.strptime(d["production_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError, KeyError):
                continue
            exp_date = pd
            if d.get("expiry_months", 0) > 0:
                y, m = pd.year, pd.month + d["expiry_months"]
                while m > 12:
                    y += 1
                    m -= 12
                import calendar
                d_last = calendar.monthrange(y, m)[1]
                exp_date = date(y, m, min(d_last, pd.day))
            if d.get("expiry_days", 0) > 0:
                exp_date = exp_date + timedelta(days=d["expiry_days"])
            diff = (exp_date - today).days
            if diff <= 30:  # 30天内过期或已过期
                level = "red" if diff <= 15 else "yellow"
                if diff < 0:
                    expiry_items.append({"text": f"{d['name']}(已过期{-diff}天)", "level": level})
                elif diff == 0:
                    expiry_items.append({"text": f"{d['name']}(今天过期)", "level": level})
                else:
                    expiry_items.append({"text": f"{d['name']}(剩{diff}天)", "level": level})
        self._expiry_warning_items = expiry_items
        if expiry_items:
            self.expiry_warning_frame.set_count(len(expiry_items))
            has_red = any(it["level"] == "red" for it in expiry_items)
            self.expiry_warning_frame.set_level("red" if has_red else "yellow")
            self.expiry_warning_frame.setVisible(True)
        else:
            self.expiry_warning_frame.setVisible(False)

        # 待办事项
        self.todo_table.setRowCount(0)
        if _all:
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN a.biz_type='报销' THEN (SELECT title FROM reimbursements WHERE id=a.biz_id)
                        WHEN a.biz_type='请假' THEN (SELECT reason FROM leave_records WHERE id=a.biz_id)
                        ELSE a.biz_type
                    END as title,
                    a.biz_type as description,
                    a.created_at
                FROM approvals a
                WHERE a.status='待审批'
                ORDER BY a.created_at DESC
                LIMIT 10
            """)
        else:
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN a.biz_type='报销' THEN (SELECT title FROM reimbursements WHERE id=a.biz_id)
                        WHEN a.biz_type='请假' THEN (SELECT reason FROM leave_records WHERE id=a.biz_id)
                        ELSE a.biz_type
                    END as title,
                    a.biz_type as description,
                    a.created_at
                FROM approvals a
                WHERE a.status='待审批' AND (a.store_id=? OR a.store_id IS NULL)
                ORDER BY a.created_at DESC
                LIMIT 10
            """, (_sid,))
        rows = cursor.fetchall()
        if rows:
            self.todo_table.setRowCount(len(rows))
            for i, (title, reason, ctime) in enumerate(rows):
                _ci1 = QTableWidgetItem("审批")
                _ci1.setTextAlignment(Qt.AlignCenter)
                self.todo_table.setItem(i, 0, _ci1)
                _ci2 = QTableWidgetItem((title or '')[:30])
                _ci2.setTextAlignment(Qt.AlignCenter)
                self.todo_table.setItem(i, 1, _ci2)
                _ci3 = QTableWidgetItem(ctime[:10] if ctime else "")
                _ci3.setTextAlignment(Qt.AlignCenter)
                self.todo_table.setItem(i, 2, _ci3)
        else:
            self.todo_table.setRowCount(1)
            empty = QTableWidgetItem("暂无待办事项")
            empty.setTextAlignment(Qt.AlignCenter)
            self.todo_table.setSpan(0, 0, 1, 3)
            self.todo_table.setItem(0, 0, empty)

        # 本月概览
        self.overview_table.setRowCount(0)
        overview_data = []

        row = q("SELECT COALESCE(SUM(amount),0) FROM daily_revenue WHERE record_date LIKE ? AND (store_id=? OR store_id IS NULL)", (f"{month}%", _sid))
        overview_data.append(("本月总营业额", f"¥{format_money(row[0] if row else 0)}"))

        row = q("SELECT COALESCE(SUM(total_amount),0) FROM purchases WHERE purchase_date LIKE ? AND (store_id=? OR store_id IS NULL)", (f"{month}%", _sid))
        overview_data.append(("本月进货成本", f"¥{format_money(row[0] if row else 0)}"))

        row = q("SELECT COALESCE(SUM(amount),0) FROM reimbursements WHERE created_at LIKE ? AND status='已通过' AND (store_id=? OR store_id IS NULL)", (f"{month}%", _sid))
        overview_data.append(("本月报销支出", f"¥{format_money(row[0] if row else 0)}"))

        row = q("SELECT COUNT(*) FROM attendance WHERE record_date LIKE ? AND (store_id=? OR store_id IS NULL)", (f"{month}%", _sid))
        overview_data.append(("本月打卡次数", str(row[0] if row else 0)))

        row = q("SELECT COALESCE(SUM(CASE WHEN record_type='收入' THEN amount ELSE 0 END),0), COALESCE(SUM(CASE WHEN record_type='支出' THEN amount ELSE 0 END),0) FROM finance_records WHERE record_date LIKE ? AND (store_id=? OR store_id IS NULL)", (f"{month}%", _sid))
        if row:
            net = row[0] - row[1]
            overview_data.append(("本月净收支", f"¥{format_money(net)}"))

        self.overview_table.setRowCount(len(overview_data))
        for i, (label, val) in enumerate(overview_data):
            _ci4 = QTableWidgetItem(label)
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.overview_table.setItem(i, 0, _ci4)
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignCenter)
            self.overview_table.setItem(i, 1, item)

        conn.close()

    def _nav_to(self, tab_key):
        p = self.window()
        if hasattr(p, 'tab_key_to_idx') and tab_key in p.tab_key_to_idx:
            idx = p.tab_key_to_idx[tab_key]
            p.nav.setCurrentRow(idx)

    def open_purchase(self):
        self._nav_to("purchase")

    def open_revenue(self):
        self._nav_to("revenue")

    def open_reimb(self):
        self._nav_to("reimbursement")

    def open_attendance(self):
        self._nav_to("attendance")

    def manual_backup(self):
        sync = get_sync()
        if not sync.is_connected:
            QMessageBox.warning(self, "备份失败", "无法连接到坚果云，请检查网络")
            return
        ok, msg = sync.upload_db()
        QMessageBox.information(self, "备份成功" if ok else "备份失败", msg)

    def export_data(self):
        full_backup(self)

    def restore_data(self):
        reply = QMessageBox.question(
            self, "恢复数据",
            "恢复操作将覆盖当前所有数据。\n建议先执行「导出数据」备份当前数据。\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if full_restore(self):
                self.refresh_data()
