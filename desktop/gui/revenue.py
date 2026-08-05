# -*- coding: utf-8 -*-
"""
营收管理 v5.0 —— 餐饮专业版
- 按渠道/套餐/类型记录每日营业额
- 多渠道营收对比（堂食/外卖/包间等）
- 日报/月报/年报营收统计与趋势分析
"""
import logging
from datetime import date, datetime, timedelta
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QFrame, QSpinBox,
                             QDoubleSpinBox, QTabWidget, QFileDialog)
from gui.calendar_widget import ModernDateEdit, ModernMonthEdit
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QDoubleValidator
from database.db_manager import get_connection
from gui.theme import (COLOR, DLG_STYLE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
                       primary_btn, success_btn, danger_btn, make_table_button,
                       TABLE_BTN_EDIT, TABLE_BTN_DELETE, TABLE_BTN_VIEW)
from utils.data_io import export_to_excel
from utils.app_context import get_app_context as _ctx
from utils.nutstore_sync import get_sync as _get_sync
from utils.logger import logger

_logger = logging.getLogger(__name__)

# ============================================================
# 云同步
# ============================================================
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")

# ============================================================
# 对话框按钮样式
# ============================================================
def _dlg_btn_save():
    return f"background: {COLOR['primary']}; color: #fff; border: none; border-radius: 4px; padding: 10px 36px; font-size: 13px; font-weight: bold;"

def _dlg_btn_cancel():
    return f"background: {COLOR['bg_card']}; color: {COLOR['text_primary']}; border: 1px solid {COLOR['border']}; border-radius: 4px; padding: 10px 36px; font-size: 13px;"


# ============================================================
# 营收记录编辑对话框
# ============================================================
class RevenueDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("编辑营收记录" if data else "新增营收记录")
        self.resize(640, 640)
        self.setMinimumSize(580, 580)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()
        if data:
            self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("编辑营收记录" if self.data else "新增营收记录")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self.dt_date = ModernDateEdit()
        self.dt_date.setDate(QDate.currentDate())
        self.dt_date.setFixedHeight(36)
        form.addRow("日期 *：", self.dt_date)

        self.cmb_channel = QComboBox()
        self.cmb_channel.setStyleSheet(COMBO_STYLE)
        self.cmb_channel.setFixedHeight(36)
        self._load_channels()
        form.addRow("渠道：", self.cmb_channel)

        self.cmb_package = QComboBox()
        self.cmb_package.setStyleSheet(COMBO_STYLE)
        self.cmb_package.setFixedHeight(36)
        self.cmb_package.setEditable(True)
        self._load_packages()
        form.addRow("套餐/类型：", self.cmb_package)

        self.cmb_package_type = QComboBox()
        self.cmb_package_type.setStyleSheet(COMBO_STYLE)
        self.cmb_package_type.setFixedHeight(36)
        self._load_package_types()
        form.addRow("分类：", self.cmb_package_type)

        self.sp_amount = QDoubleSpinBox()
        self.sp_amount.setRange(0, 9999999)
        self.sp_amount.setDecimals(2)
        self.sp_amount.setPrefix("¥ ")
        self.sp_amount.setFixedHeight(36)
        form.addRow("金额 *：", self.sp_amount)

        self.sp_order_count = QSpinBox()
        self.sp_order_count.setRange(0, 99999)
        self.sp_order_count.setFixedHeight(36)
        form.addRow("订单数：", self.sp_order_count)

        self.sp_cash = QDoubleSpinBox()
        self.sp_cash.setRange(0, 9999999)
        self.sp_cash.setDecimals(2)
        self.sp_cash.setPrefix("¥ ")
        self.sp_cash.setFixedHeight(36)
        form.addRow("现金：", self.sp_cash)

        self.sp_card = QDoubleSpinBox()
        self.sp_card.setRange(0, 9999999)
        self.sp_card.setDecimals(2)
        self.sp_card.setPrefix("¥ ")
        self.sp_card.setFixedHeight(36)
        form.addRow("刷卡：", self.sp_card)

        self.sp_online = QDoubleSpinBox()
        self.sp_online.setRange(0, 9999999)
        self.sp_online.setDecimals(2)
        self.sp_online.setPrefix("¥ ")
        self.sp_online.setFixedHeight(36)
        form.addRow("线上：", self.sp_online)

        self.sp_dining = QSpinBox()
        self.sp_dining.setRange(0, 99999)
        self.sp_dining.setFixedHeight(36)
        form.addRow("堂食人数：", self.sp_dining)

        self.sp_takeout = QSpinBox()
        self.sp_takeout.setRange(0, 99999)
        self.sp_takeout.setFixedHeight(36)
        form.addRow("外卖单数：", self.sp_takeout)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(36)
        form.addRow("备  注：", self.txt_remark)

        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(_dlg_btn_cancel())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(_dlg_btn_save())
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_channels(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT channel_name FROM revenue_channels ORDER BY sort_order, id")
        rows = cursor.fetchall()
        conn.close()
        self.cmb_channel.clear()
        default_channels = ["堂食", "外卖", "包间", "其他"]
        existing = {dict(r)['channel_name'] for r in rows}
        for ch in default_channels:
            if ch not in existing:
                self.cmb_channel.addItem(ch)
        for r in rows:
            self.cmb_channel.addItem(dict(r)['channel_name'])

    def _load_packages(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT package_name FROM revenue_packages ORDER BY package_name")
        rows = cursor.fetchall()
        conn.close()
        self.cmb_package.clear()
        self.cmb_package.addItem("")
        for r in rows:
            self.cmb_package.addItem(dict(r)['package_name'])

    def _load_package_types(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT type_name FROM revenue_package_types ORDER BY type_name")
        rows = cursor.fetchall()
        conn.close()
        self.cmb_package_type.clear()
        self.cmb_package_type.addItem("")
        for r in rows:
            self.cmb_package_type.addItem(dict(r)['type_name'])

    def _load_data(self):
        self.dt_date.setDate(QDate.fromString(self.data['record_date'], 'yyyy-MM-dd'))
        self.cmb_channel.setCurrentText(self.data.get('channel', '') or '')
        self.cmb_package.setCurrentText(self.data.get('package_name', '') or '')
        self.cmb_package_type.setCurrentText(self.data.get('package_type', '') or '')
        self.sp_amount.setValue(self.data.get('amount', 0) or 0)
        self.sp_order_count.setValue(self.data.get('order_count', 0) or 0)
        self.sp_cash.setValue(self.data.get('cash_amount', 0) or 0)
        self.sp_card.setValue(self.data.get('card_amount', 0) or 0)
        self.sp_online.setValue(self.data.get('online_amount', 0) or 0)
        self.sp_dining.setValue(self.data.get('dining_count', 0) or 0)
        self.sp_takeout.setValue(self.data.get('takeout_count', 0) or 0)
        self.txt_remark.setText(self.data.get('remark', '') or '')

    def _save(self):
        record_date = self.dt_date.date().toString('yyyy-MM-dd')
        amount = self.sp_amount.value()
        if amount <= 0:
            QMessageBox.warning(self, "提示", "请输入金额")
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            if self.data:
                cursor.execute("""UPDATE daily_revenue SET record_date=?,channel=?,package_name=?,package_type=?,
                                  amount=?,order_count=?,cash_amount=?,card_amount=?,online_amount=?,
                                  dining_count=?,takeout_count=?,remark=?,operator=?
                                  WHERE id=?""",
                               (record_date, self.cmb_channel.currentText(),
                                self.cmb_package.currentText(), self.cmb_package_type.currentText(),
                                amount, self.sp_order_count.value(),
                                self.sp_cash.value(), self.sp_card.value(), self.sp_online.value(),
                                self.sp_dining.value(), self.sp_takeout.value(),
                                self.txt_remark.text(), _ctx().current_user or '系统',
                                self.data['id']))
            else:
                cursor.execute("""INSERT INTO daily_revenue (record_date,channel,package_name,package_type,
                                  amount,order_count,cash_amount,card_amount,online_amount,
                                  dining_count,takeout_count,operator,remark)
                                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (record_date, self.cmb_channel.currentText(),
                                self.cmb_package.currentText(), self.cmb_package_type.currentText(),
                                amount, self.sp_order_count.value(),
                                self.sp_cash.value(), self.sp_card.value(), self.sp_online.value(),
                                self.sp_dining.value(), self.sp_takeout.value(),
                                _ctx().current_user or '系统', self.txt_remark.text()))
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")


# ============================================================
# 营收管理主界面
# ============================================================
class RevenueWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"QTabWidget::pane {{ border: none; }}")

        self.tab_daily = QWidget()
        self._build_daily_tab()
        self.tabs.addTab(self.tab_daily, "每日营收")

        self.tab_monthly = QWidget()
        self._build_monthly_tab()
        self.tabs.addTab(self.tab_monthly, "月度汇总")

        self.tab_channel = QWidget()
        self._build_channel_tab()
        self.tabs.addTab(self.tab_channel, "渠道分析")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self._loaded_tabs = {0: True}
        self._load_daily()

    def _on_tab_changed(self, index):
        if index in self._loaded_tabs:
            return
        loaders = {0: self._load_daily, 1: self._load_monthly, 2: self._load_channel}
        if index in loaders:
            loaders[index]()
            self._loaded_tabs[index] = True

    # ========== 每日营收 ==========
    def _build_daily_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ 新增记录")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_revenue)
        toolbar.addWidget(btn_add)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("日期："))
        self.daily_date = ModernDateEdit()
        self.daily_date.setDate(QDate.currentDate())
        self.daily_date.setFixedWidth(160)
        toolbar.addWidget(self.daily_date)
        btn_query = QPushButton("查询")
        btn_query.setStyleSheet(primary_btn)
        btn_query.clicked.connect(self._load_daily)
        toolbar.addWidget(btn_query)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.daily_table, "每日营收"))
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.daily_summary = QLabel()
        self.daily_summary.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR['primary']}; padding: 8px;")
        layout.addWidget(self.daily_summary)

        self.daily_table = QTableWidget()
        self.daily_table.setColumnCount(12)
        self.daily_table.setHorizontalHeaderLabels(["序号", "日期", "渠道", "套餐", "分类", "金额", "订单数", "现金", "刷卡", "线上", "堂食人数", "操作"])
        self.daily_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.daily_table.setStyleSheet(TABLE_STYLE)
        self.daily_table.verticalHeader().setVisible(False)
        self.daily_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.daily_table)
        self.tab_daily.setLayout(layout)

    def _load_daily(self):
        dt = self.daily_date.date().toString('yyyy-MM-dd')
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT * FROM daily_revenue WHERE record_date = ? ORDER BY id""", (dt,))
        rows = cursor.fetchall()
        conn.close()
        total_amount = sum(dict(r).get('amount', 0) or 0 for r in rows)
        self.daily_summary.setText(f"  {dt}  共 {len(rows)} 条记录，合计：¥ {total_amount:,.2f}")
        self.daily_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.daily_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.daily_table.setItem(i, 1, QTableWidgetItem(d['record_date']))
            self.daily_table.setItem(i, 2, QTableWidgetItem(d.get('channel', '') or ''))
            self.daily_table.setItem(i, 3, QTableWidgetItem(d.get('package_name', '') or ''))
            self.daily_table.setItem(i, 4, QTableWidgetItem(d.get('package_type', '') or ''))
            amt = d.get('amount', 0) or 0
            amt_item = QTableWidgetItem(f"{amt:,.2f}")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.daily_table.setItem(i, 5, amt_item)
            self.daily_table.setItem(i, 6, QTableWidgetItem(str(d.get('order_count', 0) or 0)))
            self.daily_table.setItem(i, 7, QTableWidgetItem(f"{d.get('cash_amount', 0) or 0:,.2f}"))
            self.daily_table.setItem(i, 8, QTableWidgetItem(f"{d.get('card_amount', 0) or 0:,.2f}"))
            self.daily_table.setItem(i, 9, QTableWidgetItem(f"{d.get('online_amount', 0) or 0:,.2f}"))
            self.daily_table.setItem(i, 10, QTableWidgetItem(str(d.get('dining_count', 0) or 0)))
            btn_edit = QPushButton("编辑")
            btn_edit.setStyleSheet(TABLE_BTN_EDIT)
            btn_edit.clicked.connect(lambda checked, rd=d: self._edit_revenue(rd))
            self.daily_table.setCellWidget(i, 11, btn_edit)

    def _add_revenue(self):
        dlg = RevenueDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._load_daily()
            self._loaded_tabs.pop(1, None)
            self._loaded_tabs.pop(2, None)

    def _edit_revenue(self, data):
        dlg = RevenueDialog(self, data)
        if dlg.exec_() == QDialog.Accepted:
            self._load_daily()
            self._loaded_tabs.pop(1, None)
            self._loaded_tabs.pop(2, None)

    # ========== 月度汇总 ==========
    def _build_monthly_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("月份："))
        self.month_picker = ModernMonthEdit()
        self.month_picker.setFixedWidth(180)
        toolbar.addWidget(self.month_picker)
        toolbar.addStretch()
        btn_query = QPushButton("查询")
        btn_query.setStyleSheet(primary_btn)
        btn_query.clicked.connect(self._load_monthly)
        toolbar.addWidget(btn_query)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.monthly_table, "月度营收汇总"))
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.monthly_summary = QLabel()
        self.monthly_summary.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR['primary']}; padding: 8px;")
        layout.addWidget(self.monthly_summary)

        self.monthly_table = QTableWidget()
        self.monthly_table.setColumnCount(8)
        self.monthly_table.setHorizontalHeaderLabels(["日期", "堂食", "外卖", "包间", "其他", "合计", "订单数", "堂食人数"])
        self.monthly_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.monthly_table.setStyleSheet(TABLE_STYLE)
        self.monthly_table.verticalHeader().setVisible(False)
        self.monthly_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.monthly_table)
        self.tab_monthly.setLayout(layout)

    def _load_monthly(self):
        month_str = self.month_picker.date().toString('yyyy-MM')
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT record_date, channel,
                                 SUM(amount) as total, SUM(order_count) as orders,
                                 SUM(dining_count) as dining
                          FROM daily_revenue
                          WHERE record_date LIKE ?
                          GROUP BY record_date, channel
                          ORDER BY record_date""", (f"{month_str}%",))
        rows = cursor.fetchall()
        conn.close()
        daily_data = {}
        for r in rows:
            d = dict(r)
            dt = d['record_date']
            if dt not in daily_data:
                daily_data[dt] = {'堂食': 0, '外卖': 0, '包间': 0, '其他': 0, 'orders': 0, 'dining': 0}
            ch = d['channel'] or '其他'
            if ch not in daily_data[dt]:
                daily_data[dt][ch] = 0
            daily_data[dt][ch] += (d['total'] or 0)
            daily_data[dt]['orders'] += (d['orders'] or 0)
            daily_data[dt]['dining'] += (d['dining'] or 0)
        sorted_dates = sorted(daily_data.keys())
        grand_total = 0
        self.monthly_table.setRowCount(len(sorted_dates))
        for i, dt in enumerate(sorted_dates):
            dd = daily_data[dt]
            self.monthly_table.setItem(i, 0, QTableWidgetItem(dt))
            self.monthly_table.setItem(i, 1, QTableWidgetItem(f"{dd['堂食']:,.0f}"))
            self.monthly_table.setItem(i, 2, QTableWidgetItem(f"{dd['外卖']:,.0f}"))
            self.monthly_table.setItem(i, 3, QTableWidgetItem(f"{dd['包间']:,.0f}"))
            self.monthly_table.setItem(i, 4, QTableWidgetItem(f"{dd['其他']:,.0f}"))
            day_total = sum(dd.get(ch, 0) for ch in ['堂食', '外卖', '包间', '其他'])
            grand_total += day_total
            self.monthly_table.setItem(i, 5, QTableWidgetItem(f"{day_total:,.0f}"))
            self.monthly_table.setItem(i, 6, QTableWidgetItem(str(dd['orders'])))
            self.monthly_table.setItem(i, 7, QTableWidgetItem(str(dd['dining'])))
        self.monthly_summary.setText(f"  {month_str}  共 {len(sorted_dates)} 天，月合计：¥ {grand_total:,.2f}")

    # ========== 渠道分析 ==========
    def _build_channel_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("月份："))
        self.ch_month_picker = ModernMonthEdit()
        self.ch_month_picker.setFixedWidth(180)
        toolbar.addWidget(self.ch_month_picker)
        toolbar.addStretch()
        btn_query = QPushButton("查询")
        btn_query.setStyleSheet(primary_btn)
        btn_query.clicked.connect(self._load_channel)
        toolbar.addWidget(btn_query)
        layout.addLayout(toolbar)

        self.channel_table = QTableWidget()
        self.channel_table.setColumnCount(6)
        self.channel_table.setHorizontalHeaderLabels(["渠道", "金额", "占比", "订单数", "堂食人数", "外卖单数"])
        self.channel_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.channel_table.setStyleSheet(TABLE_STYLE)
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.channel_table)
        self.tab_channel.setLayout(layout)

    def _load_channel(self):
        month_str = self.ch_month_picker.date().toString('yyyy-MM')
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT channel, SUM(amount) as total, SUM(order_count) as orders,
                                 SUM(dining_count) as dining, SUM(takeout_count) as takeout
                          FROM daily_revenue
                          WHERE record_date LIKE ?
                          GROUP BY channel
                          ORDER BY total DESC""", (f"{month_str}%",))
        rows = cursor.fetchall()
        conn.close()
        grand_total = sum((dict(r)['total'] or 0) for r in rows)
        self.channel_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            ch = d['channel'] or '未分类'
            total = d['total'] or 0
            pct = f"{total / grand_total * 100:.1f}%" if grand_total > 0 else "0%"
            self.channel_table.setItem(i, 0, QTableWidgetItem(ch))
            amt_item = QTableWidgetItem(f"{total:,.2f}")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.channel_table.setItem(i, 1, amt_item)
            self.channel_table.setItem(i, 2, QTableWidgetItem(pct))
            self.channel_table.setItem(i, 3, QTableWidgetItem(str(d['orders'] or 0)))
            self.channel_table.setItem(i, 4, QTableWidgetItem(str(d['dining'] or 0)))
            self.channel_table.setItem(i, 5, QTableWidgetItem(str(d['takeout'] or 0)))

    def _export_table(self, table, name):
        path, _ = QFileDialog.getSaveFileName(self, "导出", f"{name}_{date.today().strftime('%Y%m%d')}.xlsx",
                                               "Excel (*.xlsx)")
        if path:
            export_to_excel(table, path)
            QMessageBox.information(self, "提示", f"已导出到：{path}")