# -*- coding: utf-8 -*-
"""
收支管理 v5.0 —— 餐饮专业版
- 餐饮收支类别：营业额、外卖结算、食材采购、工资、房租、水电燃气等
- 收入/支出记录、月度汇总、净收入统计
- 按类别/说明搜索、按月份/类型筛选
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QTextEdit, QFrame)
from gui.calendar_widget import ModernDateEdit
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QDoubleValidator
from database.db_manager import get_connection
from gui.theme import (COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
                       primary_btn, BTN_SUCCESS, BTN_DANGER, make_table_button)
from utils.data_io import export_to_excel
from utils.app_context import get_app_context as _ctx
from utils.logger import logger

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")

INCOME_CATEGORIES = ["堂食营业额", "外卖平台结算", "外带打包", "会员充值", "包间服务费", "酒水销售", "其他收入"]
EXPENSE_CATEGORIES = ["食材采购", "酒水采购", "工资", "房租", "物业费",
                      "水费", "电费", "燃气费", "外卖平台佣金", "包装耗材",
                      "餐具耗材", "设备维修", "营销推广", "保洁服务",
                      "垃圾排污费", "办公用品", "交通费", "培训费",
                      "员工福利", "保险", "税费", "证照年审", "其他支出"]
ACCOUNTS = ["现金", "微信", "支付宝", "银行卡", "对公账户"]


class FinanceDialog(QDialog):
    def __init__(self, parent=None, record_type="支出", data=None):
        super().__init__(parent)
        self.record_type = record_type
        self.data = data
        self.setWindowTitle(f"编辑{record_type}" if data else f"新增{record_type}")
        self.resize(560, 580)
        self.setMinimumSize(500, 520)
        self.setStyleSheet(f"QDialog {{ background: {COLOR['bg_card']}; }}")
        self.init_ui()
        if data:
            self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 24, 30, 20)
        layout.setSpacing(16)

        title = QLabel(f"{'编辑' if self.data else '新增'} {self.record_type}")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.date_record = ModernDateEdit()
        self.date_record.setDate(QDate.currentDate())
        self.date_record.setFixedHeight(40)
        form.addRow("日期 *：", self.date_record)

        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["收入", "支出"])
        self.cmb_type.setCurrentText(self.record_type)
        self.cmb_type.currentTextChanged.connect(self.on_type_changed)
        self.cmb_type.setStyleSheet(COMBO_STYLE)
        self.cmb_type.setFixedHeight(40)
        form.addRow("类型：", self.cmb_type)

        self.cmb_category = QComboBox()
        self.cmb_category.addItems(INCOME_CATEGORIES if self.record_type == "收入" else EXPENSE_CATEGORIES)
        self.cmb_category.setStyleSheet(COMBO_STYLE)
        self.cmb_category.setFixedHeight(40)
        form.addRow("类别 *：", self.cmb_category)

        self.spin_amount = QLineEdit()
        self.spin_amount.setPlaceholderText("¥ 0.00")
        self.spin_amount.setValidator(QDoubleValidator(0.01, 9999999, 2))
        self.spin_amount.setStyleSheet(INPUT_STYLE)
        self.spin_amount.setFixedHeight(40)
        form.addRow("金额 *：", self.spin_amount)

        self.cmb_account = QComboBox()
        self.cmb_account.addItems(ACCOUNTS)
        self.cmb_account.setStyleSheet(COMBO_STYLE)
        self.cmb_account.setFixedHeight(40)
        form.addRow("支付方式：", self.cmb_account)

        self.txt_operator = QLineEdit()
        self.txt_operator.setPlaceholderText("经办人姓名")
        self.txt_operator.setStyleSheet(INPUT_STYLE)
        self.txt_operator.setFixedHeight(40)
        form.addRow("经办人：", self.txt_operator)

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText("收支说明，如用途、事由等...")
        self.txt_desc.setFixedHeight(80)
        form.addRow("说明：", self.txt_desc)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注信息（可选）")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(40)
        form.addRow("备注：", self.txt_remark)

        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(38)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(primary_btn)
        btn_save.setFixedHeight(38)
        btn_save.clicked.connect(self.save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def on_type_changed(self, new_type):
        self.cmb_category.clear()
        self.cmb_category.addItems(INCOME_CATEGORIES if new_type == "收入" else EXPENSE_CATEGORIES)

    def load_data(self):
        self.date_record.setDate(QDate.fromString(self.data["record_date"], "yyyy-MM-dd"))
        self.cmb_type.setCurrentText(self.data["record_type"])
        self.cmb_category.setCurrentText(self.data.get("category", ""))
        self.spin_amount.setText(f'{self.data["amount"]:.2f}')
        idx = self.cmb_account.findText(self.data.get("account", ""))
        if idx >= 0:
            self.cmb_account.setCurrentIndex(idx)
        self.txt_operator.setText(self.data.get("operator", ""))
        self.txt_desc.setPlainText(self.data.get("description", ""))
        self.txt_remark.setText(self.data.get("remark", ""))

    def save(self):
        record_date = self.date_record.date().toString("yyyy-MM-dd")
        rtype = self.cmb_type.currentText()
        category = self.cmb_category.currentText()
        try:
            amount = float(self.spin_amount.text() or "0")
        except ValueError:
            QMessageBox.warning(self, "提示", "金额格式错误")
            return
        if not category:
            QMessageBox.warning(self, "提示", "请选择类别")
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            if self.data:
                cursor.execute("""UPDATE finance_records SET record_date=?, record_type=?, category=?,
                                  amount=?, account=?, operator=?, description=?, remark=? WHERE id=?""",
                               (record_date, rtype, category, amount,
                                self.cmb_account.currentText(), self.txt_operator.text(),
                                self.txt_desc.toPlainText(), self.txt_remark.text(), self.data["id"]))
            else:
                _sid, _ = _ctx().get_store_filter()
                cursor.execute("""INSERT INTO finance_records
                                  (record_date, record_type, category, amount, account, operator, description, remark, store_id)
                                  VALUES (?,?,?,?,?,?,?,?,?)""",
                               (record_date, rtype, category, amount,
                                self.cmb_account.currentText(), self.txt_operator.text(),
                                self.txt_desc.toPlainText(), self.txt_remark.text(), _sid))
            conn.commit()
            _sync_cloud()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存失败：{e}")
        self.accept()


class FinanceWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self.init_ui()
        # load_data() 延迟到首次切换时调用（懒加载）

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        btn_income = QPushButton("＋ 新增收入")
        btn_income.setStyleSheet(BTN_SUCCESS)
        btn_income.setFixedHeight(36)
        btn_income.clicked.connect(lambda: self.add_record("收入"))
        toolbar.addWidget(btn_income)

        btn_expense = QPushButton("－ 新增支出")
        btn_expense.setStyleSheet(BTN_DANGER)
        btn_expense.setFixedHeight(36)
        btn_expense.clicked.connect(lambda: self.add_record("支出"))
        toolbar.addWidget(btn_expense)

        btn_export = QPushButton("导出Excel")
        btn_export.setFixedHeight(36)
        btn_export.clicked.connect(self.export_data)
        toolbar.addWidget(btn_export)

        toolbar.addStretch()

        toolbar.addWidget(QLabel("搜索："))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("类别/说明/经办人")
        self.txt_search.setFixedWidth(160)
        self.txt_search.setStyleSheet(INPUT_STYLE)
        self.txt_search.textChanged.connect(lambda: self.load_data())
        toolbar.addWidget(self.txt_search)

        toolbar.addWidget(QLabel("类型："))
        self.cmb_filter = QComboBox()
        self.cmb_filter.setStyleSheet(COMBO_STYLE)
        self.cmb_filter.setFixedHeight(36)
        self.cmb_filter.addItems(["全部", "收入", "支出"])
        self.cmb_filter.currentTextChanged.connect(lambda: self.load_data())
        toolbar.addWidget(self.cmb_filter)

        toolbar.addWidget(QLabel("月份："))
        self.cmb_month = QComboBox()
        self.cmb_month.setStyleSheet(COMBO_STYLE)
        self.cmb_month.setFixedHeight(36)
        today = QDate.currentDate()
        for m in range(1, 13):
            self.cmb_month.addItem(f"{today.year()}年{m:02d}月", f"{today.year()}-{m:02d}")
        self.cmb_month.setCurrentIndex(today.month() - 1)
        self.cmb_month.currentIndexChanged.connect(self.load_data)
        toolbar.addWidget(self.cmb_month)

        layout.addLayout(toolbar)

        # 汇总统计
        summary_bar = QHBoxLayout()
        summary_bar.setSpacing(16)
        self.lbl_income = QLabel("收入合计：¥ 0.00")
        self.lbl_income.setStyleSheet(f"color: {COLOR['success']}; font-size: {FONT_SIZE['lg']}px; font-weight: 600; padding: 8px 16px; background: {COLOR['bg_card']}; border-radius: {RADIUS['md']}px;")
        self.lbl_expense = QLabel("支出合计：¥ 0.00")
        self.lbl_expense.setStyleSheet(f"color: {COLOR['danger']}; font-size: {FONT_SIZE['lg']}px; font-weight: 600; padding: 8px 16px; background: {COLOR['bg_card']}; border-radius: {RADIUS['md']}px;")
        self.lbl_net = QLabel("净收入：¥ 0.00")
        self.lbl_net.setStyleSheet(f"color: {COLOR['primary']}; font-size: {FONT_SIZE['lg']}px; font-weight: 600; padding: 8px 16px; background: {COLOR['bg_card']}; border-radius: {RADIUS['md']}px;")
        summary_bar.addWidget(self.lbl_income)
        summary_bar.addWidget(self.lbl_expense)
        summary_bar.addWidget(self.lbl_net)
        summary_bar.addStretch()
        layout.addLayout(summary_bar)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["序号", "日期", "类型", "类别", "金额", "支付方式", "经办人", "说明", "操作"])
        self.table.setColumnWidth(0, 60)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_data(self):
        filter_type = self.cmb_filter.currentText()
        month_str = self.cmb_month.currentData()
        search_text = self.txt_search.text().strip() if hasattr(self, 'txt_search') else ""

        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()

        where = " WHERE f.record_date LIKE ?"
        params = [f"{month_str}%"]
        if not _all:
            where += " AND (f.store_id=? OR f.store_id IS NULL)"
            params.append(_sid)
        if filter_type != "全部":
            where += " AND f.record_type=?"
            params.append(filter_type)
        if search_text:
            where += " AND (f.category LIKE ? OR f.description LIKE ? OR f.operator LIKE ?)"
            params.extend([f"%{search_text}%", f"%{search_text}%", f"%{search_text}%"])

        cursor.execute(f"""SELECT f.* FROM finance_records f{where} ORDER BY f.record_date DESC, f.id DESC""", params)
        rows = cursor.fetchall()

        cursor.execute(f"""SELECT record_type, COALESCE(SUM(amount),0) as total FROM finance_records f{where}
                          GROUP BY record_type""", params)
        stats = {r["record_type"]: r["total"] for r in cursor.fetchall()}
        total_income = stats.get("收入", 0)
        total_expense = stats.get("支出", 0)
        net = total_income - total_expense

        self.lbl_income.setText(f"收入合计：¥ {total_income:.2f}")
        self.lbl_expense.setText(f"支出合计：¥ {total_expense:.2f}")
        net_color = COLOR['success'] if net >= 0 else COLOR['danger']
        self.lbl_net.setText(f"净收入：¥ {net:.2f}")
        self.lbl_net.setStyleSheet(f"color: {net_color}; font-size: {FONT_SIZE['lg']}px; font-weight: 600; padding: 8px 16px; background: {COLOR['bg_card']}; border-radius: {RADIUS['md']}px;")

        conn.close()

        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci1 = QTableWidgetItem(r["record_date"])
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci1)

            type_item = QTableWidgetItem(r["record_type"])
            type_item.setTextAlignment(Qt.AlignCenter)
            if r["record_type"] == "收入":
                type_item.setForeground(QColor(COLOR['success']))
            else:
                type_item.setForeground(QColor(COLOR['danger']))
            self.table.setItem(i, 2, type_item)

            _ci2 = QTableWidgetItem(r.get("category", ""))
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, _ci2)
            amt_item = QTableWidgetItem(f"¥{r['amount']:.2f}")
            amt_item.setTextAlignment(Qt.AlignCenter)
            if r["record_type"] == "收入":
                amt_item.setForeground(QColor(COLOR['success']))
            else:
                amt_item.setForeground(QColor(COLOR['danger']))
            self.table.setItem(i, 4, amt_item)
            _ci3 = QTableWidgetItem(r.get("account", ""))
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, _ci3)
            _ci4 = QTableWidgetItem(r.get("operator", ""))
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 6, _ci4)
            _ci5 = QTableWidgetItem(r.get("description", ""))
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 7, _ci5)

            btn_widget = QWidget()
            btn_widget.setObjectName("btnCell")
            btn_widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
            hl = QHBoxLayout(btn_widget)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            rid = r["id"]
            btn_edit.clicked.connect(lambda checked, rid=rid: self.edit_record(rid))
            btn_del.clicked.connect(lambda checked, rid=rid: self.delete_record(rid))
            hl.addStretch()
            hl.addWidget(btn_edit)
            hl.addWidget(btn_del)
            hl.addStretch()
            self.table.setCellWidget(i, 8, btn_widget)

    def add_record(self, rtype):
        dlg = FinanceDialog(self, rtype)
        if dlg.exec_():
            self.load_data()

    def export_data(self):
        _sid, _ = _ctx().get_store_filter()
        export_to_excel("finance_records", self, _sid)

    def edit_record(self, record_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM finance_records WHERE id=?", (record_id,))
        row = dict(cursor.fetchone())
        conn.close()
        dlg = FinanceDialog(self, row["record_type"], row)
        if dlg.exec_():
            self.load_data()

    def delete_record(self, record_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT record_date, record_type, amount FROM finance_records WHERE id=?", (record_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return
        r = dict(row)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除这条记录吗？\n\n日期：{r['record_date']}\n类型：{r['record_type']}\n金额：¥{r['amount']:.2f}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM finance_records WHERE id=?", (record_id,))
            conn.commit()
            _sync_cloud()
            self.load_data()
