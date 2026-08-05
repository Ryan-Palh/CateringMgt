# -*- coding: utf-8 -*-
"""
报销管理 v5.0 —— 餐饮专业版
- 餐饮报销类别：食材采购、办公用品、交通费、设备维修、水电燃气、员工福利等
- 提交报销自动创建审批记录
- 按角色/门店过滤
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QTextEdit)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDoubleValidator, QColor
from database.db_manager import get_connection
from gui.theme import COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, COMBO_STYLE, INPUT_STYLE, primary_btn, make_table_button
from utils.helpers import generate_order_no
from utils.auth_manager import ADMIN_ROLES
from utils.app_context import get_app_context as _ctx
from utils.logger import logger

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")

REIMB_CATEGORIES = ["", "食材采购", "酒水采购", "包装耗材", "餐具耗材", "设备维修", "水电燃气费", "房租物业", "营销推广", "办公用品", "交通费", "培训费", "员工福利", "税费保险", "其他"]


class ReimbursementDialog(QDialog):
    def __init__(self, parent=None, user=None, data=None):
        super().__init__(parent)
        self.user = user
        self.data = data
        self.setWindowTitle("编辑报销" if data else "提交报销")
        self.resize(560, 520)
        self.setMinimumSize(500, 460)
        self.setStyleSheet(f"QDialog {{ background: {COLOR['bg_card']}; }}")
        self.init_ui()
        if data:
            self.load_data()

    def init_ui(self):
        layout = QFormLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 20)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("报销事由")
        self.txt_title.setStyleSheet(INPUT_STYLE)
        self.txt_title.setFixedHeight(40)
        layout.addRow("标题 *：", self.txt_title)

        self.cmb_category = QComboBox()
        self.cmb_category.setStyleSheet(COMBO_STYLE)
        self.cmb_category.addItems(REIMB_CATEGORIES)
        self.cmb_category.setFixedHeight(40)
        layout.addRow("类别：", self.cmb_category)

        self.spin_amount = QLineEdit()
        self.spin_amount.setPlaceholderText("¥ 0.00")
        self.spin_amount.setValidator(QDoubleValidator(0, 999999, 2))
        self.spin_amount.setStyleSheet(INPUT_STYLE)
        self.spin_amount.setFixedHeight(40)
        layout.addRow("金额 *：", self.spin_amount)

        self.txt_desc = QTextEdit()
        self.txt_desc.setFixedHeight(80)
        self.txt_desc.setPlaceholderText("详细说明...")
        layout.addRow("说明：", self.txt_desc)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(40)
        layout.addRow("备注：", self.txt_remark)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("提交")
        btn_save.setStyleSheet(primary_btn)
        btn_save.setFixedHeight(38)
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(38)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addRow(btn_layout)
        self.setLayout(layout)

    def load_data(self):
        self.txt_title.setText(self.data.get("title", ""))
        self.cmb_category.setCurrentText(self.data.get("category", ""))
        self.spin_amount.setText(f"{self.data.get('amount', 0):.2f}")
        self.txt_desc.setPlainText(self.data.get("description", ""))
        self.txt_remark.setText(self.data.get("remark", ""))

    def save(self):
        title = self.txt_title.text().strip()
        try:
            amount = float(self.spin_amount.text() or "0")
        except ValueError:
            QMessageBox.warning(self, "提示", "金额格式错误")
            return
        if not title:
            QMessageBox.warning(self, "提示", "请输入报销事由")
            return
        if amount <= 0:
            QMessageBox.warning(self, "提示", "请输入报销金额")
            return

        conn = get_connection()
        cursor = conn.cursor()
        if self.data:
            cursor.execute("""UPDATE reimbursements SET title=?,category=?,amount=?,description=?,remark=? WHERE id=?""",
                           (title, self.cmb_category.currentText(), amount,
                            self.txt_desc.toPlainText(), self.txt_remark.text(), self.data["id"]))
        else:
            reimb_no = generate_order_no("BX")
            cursor.execute("""INSERT INTO reimbursements (reimb_no, employee_id, title, category, amount, description, status, submit_date)
                              VALUES (?,?,?,?,?,?,'待审批',date('now','localtime'))""",
                           (reimb_no, self.user["id"], title, self.cmb_category.currentText(),
                            amount, self.txt_desc.toPlainText()))
            reimb_id = cursor.lastrowid
            _sid_app, _ = _ctx().get_store_filter()
            cursor.execute("""INSERT INTO approvals (biz_type, biz_id, applicant_id, status, store_id, title, amount)
                              VALUES ('报销', ?, ?, '待审批', ?, ?, ?)""",
                           (reimb_id, self.user["id"], _sid_app, title, amount))

        conn.commit()
        _sync_cloud()
        self.accept()


class ReimbursementWidget(QWidget):
    def __init__(self, user):
        super().__init__()
        self.current_user = user
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self.init_ui()
        # load_data() 延迟到首次切换时调用（懒加载）

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        btn_add = QPushButton("＋ 提交报销")
        btn_add.setStyleSheet(primary_btn)
        btn_add.setFixedHeight(36)
        btn_add.clicked.connect(self.add_reimb)
        toolbar.addWidget(btn_add)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["序号", "单号", "标题", "类别", "金额", "状态", "提交日期", "备注"])
        self.table.setColumnWidth(0, 60)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def load_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        is_admin = self.current_user.get("role") in ADMIN_ROLES
        _sid, _all = _ctx().get_store_filter()
        if is_admin:
            if _all:
                cursor.execute("SELECT * FROM reimbursements ORDER BY id DESC")
            else:
                cursor.execute("SELECT * FROM reimbursements WHERE (store_id=? OR store_id IS NULL) ORDER BY id DESC", (_sid,))
        else:
            if _all:
                cursor.execute("SELECT * FROM reimbursements WHERE employee_id=? ORDER BY id DESC", (self.current_user["id"],))
            else:
                cursor.execute("SELECT * FROM reimbursements WHERE employee_id=? AND (store_id=? OR store_id IS NULL) ORDER BY id DESC", (self.current_user["id"], _sid))
        rows = cursor.fetchall()
        conn.close()
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci1 = QTableWidgetItem(r.get("reimb_no", ""))
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(r.get("title", ""))
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci2)
            _ci3 = QTableWidgetItem(r.get("category", ""))
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, _ci3)
            amt = QTableWidgetItem(f"¥{r['amount']:.2f}")
            amt.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, amt)

            status = r.get("status", "")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "待审批":
                status_item.setForeground(QColor(COLOR['warning']))
            elif status == "已通过":
                status_item.setForeground(QColor(COLOR['success']))
            elif status == "已拒绝":
                status_item.setForeground(QColor(COLOR['danger']))
            self.table.setItem(i, 5, status_item)
            _ci4 = QTableWidgetItem(r.get("submit_date", ""))
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 6, _ci4)
            _ci5 = QTableWidgetItem(r.get("remark", ""))
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 7, _ci5)

    def add_reimb(self):
        dlg = ReimbursementDialog(self, self.current_user)
        if dlg.exec_():
            self.load_data()
