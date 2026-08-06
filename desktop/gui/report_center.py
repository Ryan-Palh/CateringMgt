# -*- coding: utf-8 -*-
"""
报表中心 v5.0 —— 餐饮专业版
- 日报/周报/月报/收支汇总/菜品销量排行
- 摘要卡片 + 详细数据表
- 支持CSV导出
"""
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QComboBox, QMessageBox, QFrame, QFileDialog)
from gui.calendar_widget import ModernDateEdit
from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QColor
from database.db_manager import get_connection
from utils.app_context import get_app_context as _ctx
from utils.helpers import format_money
from gui.theme import COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, COMBO_STYLE, primary_btn, success_btn
from utils.logger import logger

import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

# 中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


class ReportWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        toolbar.addWidget(QLabel("报表类型："))

        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["日报", "周报", "月报", "菜品销量排行", "收支汇总"])
        self.cmb_type.setStyleSheet(COMBO_STYLE)
        self.cmb_type.setFixedWidth(150)
        self.cmb_type.currentTextChanged.connect(self.on_type_changed)
        toolbar.addWidget(self.cmb_type)

        self.date_from = ModernDateEdit()
        self.date_from.setDate(QDate.currentDate())
        self.date_from.setFixedWidth(160)
        toolbar.addWidget(QLabel("日期："))
        toolbar.addWidget(self.date_from)

        self.date_to = ModernDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setFixedWidth(160)
        toolbar.addWidget(QLabel("至"))
        toolbar.addWidget(self.date_to)

        btn_query = QPushButton("查询")
        btn_query.setStyleSheet(primary_btn)
        btn_query.setFixedHeight(36)
        btn_query.clicked.connect(self.load_report)
        toolbar.addWidget(btn_query)

        btn_export = QPushButton("导出CSV")
        btn_export.setStyleSheet(success_btn)
        btn_export.setFixedHeight(36)
        btn_export.clicked.connect(self.export_report)
        toolbar.addWidget(btn_export)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 摘要卡片
        self.summary_frame = QFrame()
        self.summary_layout = QHBoxLayout(self.summary_frame)
        self.summary_layout.setSpacing(16)
        layout.addWidget(self.summary_frame)

        # 图表区域
        self.chart_frame = QFrame()
        self.chart_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR['bg_card']};
                border-radius: {RADIUS['xl']}px;
                border: 1px solid {COLOR['border_light']};
            }}
        """)
        self.chart_layout = QVBoxLayout(self.chart_frame)
        self.chart_layout.setContentsMargins(16, 12, 16, 12)
        self.chart_layout.setSpacing(8)
        self.chart_frame.setVisible(False)
        layout.addWidget(self.chart_frame)

        # 报表内容
        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.setLayout(layout)
        self.on_type_changed("日报")

    def on_type_changed(self, rtype):
        now = QDate.currentDate()
        if rtype == "日报":
            self.date_from.setDate(now)
            self.date_to.setDate(now)
        elif rtype == "周报":
            monday = now.addDays(-(now.dayOfWeek() - 1))
            self.date_from.setDate(monday)
            self.date_to.setDate(monday.addDays(6))
        elif rtype == "月报":
            self.date_from.setDate(QDate(now.year(), now.month(), 1))
            last_day = QDate(now.year(), now.month(), 1).addMonths(1).addDays(-1)
            self.date_to.setDate(last_day)
        self.load_report()

    def _make_summary_card(self, label, value, color):
        card = QFrame()
        card.setObjectName("statCard")
        card.setMinimumHeight(72)
        card.setStyleSheet(f"""
            QFrame#statCard {{
                background: {COLOR['bg_card']};
                border: 1px solid {COLOR['border']};
                border-left: 4px solid {color};
                border-radius: {RADIUS['lg']}px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 10, 16, 10)
        cl.setSpacing(2)
        vl = QLabel(value)
        vl.setStyleSheet(f"font-size: {FONT_SIZE['3xl']}px; font-weight: 700; color: {color};")
        tl = QLabel(label)
        tl.setStyleSheet(f"font-size: {FONT_SIZE['sm']}px; color: {COLOR['text_muted']};")
        cl.addWidget(vl)
        cl.addWidget(tl)
        return card

    def _render_chart(self, rtype):
        """根据报表类型生成图表"""
        # 清除旧图表
        for i in reversed(range(self.chart_layout.count())):
            w = self.chart_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        data = getattr(self, "_chart_data", {})
        if not data:
            self.chart_frame.setVisible(False)
            return

        fig = Figure(figsize=(8, 3.5), dpi=100)
        fig.patch.set_facecolor('white')

        if rtype in ("日报", "周报", "月报"):
            # 柱状图：营业额 vs 支出 vs 净利润
            ax = fig.add_subplot(111)
            labels = ['营业额', '采购支出', '工资+报销', '净利润']
            values = data.get('values', [0, 0, 0, 0])
            colors = ['#5B6CFF', '#F59E0B', '#EF4444', '#10B981']
            bars = ax.bar(labels, values, color=colors, width=0.5, edgecolor='white', linewidth=0.5)
            ax.set_title('经营收支对比', fontsize=13, fontweight='bold', color='#0F172A')
            ax.set_ylabel('金额 (元)', fontsize=10)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.yaxis.grid(True, linestyle='--', alpha=0.3)
            # 在柱子上显示数值
            for bar, val in zip(bars, values):
                if val != 0:
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                            f'{val:.0f}', ha='center', va='bottom', fontsize=9, color='#374151')

        elif rtype == "收支汇总":
            # 饼图：各类别收支占比
            ax = fig.add_subplot(111)
            categories = data.get('categories', [])
            incomes = data.get('incomes', [])
            if categories and incomes:
                filtered = [(c, i) for c, i in zip(categories, incomes) if i > 0]
                if filtered:
                    cats, incs = zip(*filtered)
                    colors = ['#5B6CFF', '#06B6D4', '#F59E0B', '#A78BFA', '#10B981', '#EC4899']
                    ax.pie(incs, labels=cats, autopct='%1.1f%%', colors=colors[:len(cats)],
                           startangle=90, textprops={'fontsize': 10})
                    ax.set_title('各类别收入占比', fontsize=13, fontweight='bold', color='#0F172A')
                else:
                    self.chart_frame.setVisible(False)
                    return
            else:
                self.chart_frame.setVisible(False)
                return

        elif rtype == "菜品销量排行":
            # 水平柱状图：菜品售价排行Top10
            ax = fig.add_subplot(111)
            names = data.get('names', [])
            prices = data.get('prices', [])
            if names and prices:
                top_n = min(10, len(names))
                names = names[:top_n][::-1]
                prices = prices[:top_n][::-1]
                colors = ['#5B6CFF'] * len(names)
                bars = ax.barh(names, prices, color=colors, height=0.6, edgecolor='white')
                ax.set_title('菜品售价排行 Top{}'.format(top_n), fontsize=13, fontweight='bold', color='#0F172A')
                ax.set_xlabel('售价 (元)', fontsize=10)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.xaxis.grid(True, linestyle='--', alpha=0.3)
                for bar, val in zip(bars, prices):
                    ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                            f' ¥{val:.0f}', ha='left', va='center', fontsize=9, color='#374151')
            else:
                self.chart_frame.setVisible(False)
                return

        fig.tight_layout()
        canvas = FigureCanvas(fig)
        self.chart_layout.addWidget(canvas)
        self.chart_frame.setVisible(True)

    def load_data(self):
        """统一刷新入口（导航切换时调用）"""
        try:
            self.load_report()
        except Exception as e:
            logger.error(f"ReportWidget load_data: {e}", exc_info=True)

    def load_report(self):
        rtype = self.cmb_type.currentText()
        d1 = self.date_from.date().toString("yyyy-MM-dd")
        d2 = self.date_to.date().toString("yyyy-MM-dd")

        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()

        for i in reversed(range(self.summary_layout.count())):
            self.summary_layout.itemAt(i).widget().setParent(None)

        # 清除旧图表
        for i in reversed(range(self.chart_layout.count())):
            w = self.chart_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        self._chart_data = {}

        if rtype in ("日报", "周报", "月报"):
            self._load_period_report(cursor, _sid, _all, d1, d2)
        elif rtype == "菜品销量排行":
            self._load_dish_ranking(cursor, _sid, _all, d1, d2)
        elif rtype == "收支汇总":
            self._load_finance_summary(cursor, _sid, _all, d1, d2)

        conn.close()

        # 生成图表
        self._render_chart(rtype)

    def _load_period_report(self, cursor, _sid, _all, d1, d2):
        if _all:
            cursor.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM daily_revenue WHERE record_date BETWEEN ? AND ?", (d1, d2))
        else:
            cursor.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM daily_revenue WHERE record_date BETWEEN ? AND ? AND (store_id=? OR store_id IS NULL)", (d1, d2, _sid))
        total_rev, rev_days = cursor.fetchone()

        if _all:
            cursor.execute("SELECT COALESCE(SUM(total_amount),0), COUNT(*) FROM purchases WHERE purchase_date BETWEEN ? AND ?", (d1, d2))
        else:
            cursor.execute("SELECT COALESCE(SUM(total_amount),0), COUNT(*) FROM purchases WHERE purchase_date BETWEEN ? AND ? AND (store_id=? OR store_id IS NULL)", (d1, d2, _sid))
        total_purchase, purchase_count = cursor.fetchone()

        if _all:
            cursor.execute("SELECT COALESCE(SUM(actual_salary),0) FROM salary_records WHERE year=? AND month=? AND status='已发放'",
                       (int(d1[:4]), int(d1[5:7])))
        else:
            cursor.execute("SELECT COALESCE(SUM(actual_salary),0) FROM salary_records WHERE year=? AND month=? AND status='已发放' AND (store_id=? OR store_id IS NULL)",
                       (int(d1[:4]), int(d1[5:7]), _sid))
        total_salary = cursor.fetchone()[0] or 0

        if _all:
            cursor.execute("SELECT COALESCE(SUM(amount),0) FROM reimbursements WHERE status='已通过' AND submit_date BETWEEN ? AND ?", (d1, d2))
        else:
            cursor.execute("SELECT COALESCE(SUM(amount),0) FROM reimbursements WHERE status='已通过' AND submit_date BETWEEN ? AND ? AND (store_id=? OR store_id IS NULL)", (d1, d2, _sid))
        total_reimb = cursor.fetchone()[0] or 0

        total_expense = total_purchase + total_salary + total_reimb
        profit = total_rev - total_expense

        for label, value, color in [
            ("营业额", f"¥{format_money(total_rev)}", COLOR['primary']),
            ("采购支出", f"¥{format_money(total_purchase)}", COLOR['warning']),
            ("工资+报销", f"¥{format_money(total_salary + total_reimb)}", COLOR['danger']),
            ("净利润", f"¥{format_money(profit)}", COLOR['success'] if profit >= 0 else COLOR['danger']),
        ]:
            self.summary_layout.addWidget(self._make_summary_card(label, value, color))

        self._chart_data = {
            'values': [total_rev, total_purchase, total_salary + total_reimb, profit],
        }

        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["指标", "数值", "说明"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        rows = [
            ("营业天数", str(rev_days), f"{d1} ~ {d2}"),
            ("营业额", f"¥{format_money(total_rev)}", ""),
            ("采购批次", str(purchase_count), ""),
            ("采购支出", f"¥{format_money(total_purchase)}", ""),
            ("工资支出", f"¥{format_money(total_salary)}", ""),
            ("报销支出", f"¥{format_money(total_reimb)}", ""),
            ("总支出", f"¥{format_money(total_expense)}", ""),
            ("净利润", f"¥{format_money(profit)}", "盈利" if profit >= 0 else "亏损"),
        ]
        self.table.setRowCount(len(rows))
        for i, (a, b, c) in enumerate(rows):
            _ci1 = QTableWidgetItem(a)
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, _ci1)
            val_item = QTableWidgetItem(b)
            val_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, val_item)
            _ci2 = QTableWidgetItem(c)
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci2)

    def _load_dish_ranking(self, cursor, _sid, _all, d1, d2):
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["排名", "菜品名称", "分类", "售价"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        if _all:
            cursor.execute("SELECT name, category, selling_price FROM dishes ORDER BY selling_price DESC")
        else:
            cursor.execute("SELECT name, category, selling_price FROM dishes WHERE (store_id=? OR store_id IS NULL) ORDER BY selling_price DESC", (_sid,))
        rows = cursor.fetchall()
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci3 = QTableWidgetItem(row["name"])
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci3)
            _ci4 = QTableWidgetItem(row["category"] or "")
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci4)
            price = QTableWidgetItem(f"¥{format_money(row['selling_price'])}")
            price.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, price)

        self._chart_data = {
            'names': [r["name"] for r in rows],
            'prices': [r["selling_price"] for r in rows],
        }

    def _load_finance_summary(self, cursor, _sid, _all, d1, d2):
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["类别", "收入", "支出", "净额"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        if _all:
            cursor.execute("""SELECT category, 
                          COALESCE(SUM(CASE WHEN record_type='收入' THEN amount ELSE 0 END),0),
                          COALESCE(SUM(CASE WHEN record_type='支出' THEN amount ELSE 0 END),0)
                          FROM finance_records WHERE record_date BETWEEN ? AND ?
                          GROUP BY category ORDER BY category""", (d1, d2))
        else:
            cursor.execute("""SELECT category, 
                          COALESCE(SUM(CASE WHEN record_type='收入' THEN amount ELSE 0 END),0),
                          COALESCE(SUM(CASE WHEN record_type='支出' THEN amount ELSE 0 END),0)
                          FROM finance_records WHERE record_date BETWEEN ? AND ? AND (store_id=? OR store_id IS NULL)
                          GROUP BY category ORDER BY category""", (d1, d2, _sid))
        rows = cursor.fetchall()
        self.table.setRowCount(len(rows))
        total_in = total_out = 0
        for i, row in enumerate(rows):
            net = row[1] - row[2]
            total_in += row[1]
            total_out += row[2]
            _ci5 = QTableWidgetItem(row[0] or "其他")
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, _ci5)
            _ci6 = QTableWidgetItem(f"¥{format_money(row[1])}")
            _ci6.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci6)
            _ci7 = QTableWidgetItem(f"¥{format_money(row[2])}")
            _ci7.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci7)
            net_item = QTableWidgetItem(f"¥{format_money(net)}")
            net_item.setTextAlignment(Qt.AlignCenter)
            net_item.setForeground(QColor(COLOR['success'] if net >= 0 else COLOR['danger']))
            self.table.setItem(i, 3, net_item)

        self.table.setRowCount(len(rows) + 1)
        _ci8 = QTableWidgetItem("合计")
        _ci8.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(len(rows), 0, _ci8)
        for col, val in [(1, total_in), (2, total_out), (3, total_in - total_out)]:
            item = QTableWidgetItem(f"¥{format_money(val)}")
            item.setTextAlignment(Qt.AlignCenter)
            from PyQt5.QtGui import QFont
            f = item.font()
            f.setBold(True)
            item.setFont(f)
            self.table.setItem(len(rows), col, item)

        self._chart_data = {
            'categories': [row[0] or "其他" for row in rows],
            'incomes': [row[1] for row in rows],
        }

    def export_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出报表", "", "CSV文件 (*.csv)")
        if not path:
            return
        with open(path, 'w', encoding='utf-8-sig') as f:
            headers = [self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())]
            f.write(",".join(headers) + "\n")
            for r in range(self.table.rowCount()):
                row = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(self.table.columnCount())]
                f.write(",".join(row) + "\n")
        QMessageBox.information(self, "导出成功", f"已导出到: {path}")
