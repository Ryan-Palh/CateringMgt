# -*- coding: utf-8 -*-
"""
员工管理 v5.0 —— 餐饮专业版
- 餐饮岗位：店长、厨师长、炒锅、切配、打荷、传菜、迎宾、收银、采购等
- 部门：前厅、后厨、吧台、管理
- 支持搜索、导入CSV、导出Excel
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox)
from gui.calendar_widget import ModernDateEdit
from PyQt5.QtCore import Qt, QDate
from database.db_manager import get_connection
from gui.theme import COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE, primary_btn, make_table_button
from utils.data_io import export_to_excel, import_from_csv
from utils.validators import check_duplicate_employee
from utils.app_context import get_app_context as _ctx
from utils.logger import logger

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")

RESTAURANT_POSITIONS = ["", "店长", "前厅经理", "厨师长", "炒锅", "切配", "打荷",
                        "面点师", "传菜员", "服务员", "迎宾", "收银员", "吧台", "采购", "保洁", "会计"]


class EmployeeDialog(QDialog):
    def __init__(self, parent=None, emp_data=None):
        super().__init__(parent)
        self.emp_data = emp_data
        self.setWindowTitle("编辑员工" if emp_data else "添加员工")
        self.resize(580, 560)
        self.setMinimumSize(520, 500)
        self.setStyleSheet(f"""
            QDialog {{ background: {COLOR['bg_card']}; }}
            QLabel {{ color: {COLOR['text_primary']}; }}
        """)
        self.init_ui()
        if emp_data:
            self.load_data()

    def init_ui(self):
        layout = QFormLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 20)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("请输入姓名")
        self.txt_name.setStyleSheet(INPUT_STYLE)
        self.txt_name.setFixedHeight(40)
        layout.addRow("姓名 *：", self.txt_name)

        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("请输入手机号")
        self.txt_phone.setStyleSheet(INPUT_STYLE)
        self.txt_phone.setFixedHeight(40)
        layout.addRow("手机号：", self.txt_phone)

        self.cmb_dept = QComboBox()
        self.cmb_dept.setStyleSheet(COMBO_STYLE)
        self.cmb_dept.setFixedHeight(40)
        layout.addRow("部门：", self.cmb_dept)

        self.cmb_pos = QComboBox()
        self.cmb_pos.setStyleSheet(COMBO_STYLE)
        self.cmb_pos.addItems(RESTAURANT_POSITIONS)
        self.cmb_pos.setFixedHeight(40)
        layout.addRow("岗位：", self.cmb_pos)

        self.txt_salary = QLineEdit()
        self.txt_salary.setPlaceholderText("基本工资")
        self.txt_salary.setStyleSheet(INPUT_STYLE)
        self.txt_salary.setFixedHeight(40)
        layout.addRow("基本工资：", self.txt_salary)

        self.date_hire = ModernDateEdit()
        self.date_hire.setDate(QDate.currentDate())
        self.date_hire.setFixedHeight(40)
        layout.addRow("入职日期：", self.date_hire)

        self.cmb_status = QComboBox()
        self.cmb_status.setStyleSheet(COMBO_STYLE)
        self.cmb_status.addItems(["在职", "离职", "试用期", "休假"])
        self.cmb_status.setFixedHeight(40)
        layout.addRow("状态：", self.cmb_status)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注信息")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(40)
        layout.addRow("备注：", self.txt_remark)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存")
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
        self.load_depts()

    def load_depts(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM departments ORDER BY id")
        self.cmb_dept.clear()
        self.cmb_dept.addItem("", None)
        for d in cursor.fetchall():
            self.cmb_dept.addItem(d["name"], d["id"])
        conn.close()

    def load_data(self):
        self.txt_name.setText(self.emp_data["name"])
        self.txt_phone.setText(self.emp_data.get("phone", ""))
        idx = self.cmb_dept.findText(self.emp_data.get("department_name", ""))
        if idx >= 0:
            self.cmb_dept.setCurrentIndex(idx)
        self.cmb_pos.setCurrentText(self.emp_data.get("position", ""))
        self.txt_salary.setText(str(self.emp_data.get("base_salary", 0)))
        if self.emp_data.get("hire_date"):
            self.date_hire.setDate(QDate.fromString(self.emp_data["hire_date"], "yyyy-MM-dd"))
        self.cmb_status.setCurrentText(self.emp_data.get("status", "在职"))
        self.txt_remark.setText(self.emp_data.get("remark", ""))

    def save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入员工姓名")
            return
        phone = self.txt_phone.text().strip()
        exclude_id = self.emp_data["id"] if self.emp_data else None
        ok, msg = check_duplicate_employee(name, phone, exclude_id)
        if not ok:
            QMessageBox.warning(self, "重复提示", msg)
            return
        _sid, _ = _ctx().get_store_filter()
        try:
            salary_val = float(self.txt_salary.text() or "0")
        except ValueError:
            QMessageBox.warning(self, "提示", "基本工资格式错误")
            return
        conn = get_connection()
        cursor = conn.cursor()
        dept_id = self.cmb_dept.currentData()
        if self.emp_data:
            cursor.execute("""UPDATE employees SET name=?,phone=?,department_id=?,position=?,
                base_salary=?,hire_date=?,status=?,remark=? WHERE id=?""",
                (name, self.txt_phone.text(), dept_id, self.cmb_pos.currentText(),
                 salary_val, self.date_hire.date().toString("yyyy-MM-dd"),
                 self.cmb_status.currentText(), self.txt_remark.text(), self.emp_data["id"]))
        else:
            cursor.execute("""INSERT INTO employees (name,phone,department_id,position,base_salary,hire_date,status,remark,store_id)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (name, self.txt_phone.text(), dept_id, self.cmb_pos.currentText(),
                 salary_val, self.date_hire.date().toString("yyyy-MM-dd"),
                 self.cmb_status.currentText(), self.txt_remark.text(), _sid))
        conn.commit()
        conn.close()
        _sync_cloud()
        self.accept()


class EmployeeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self.init_ui()
        # load_data() 延迟到首次切换时调用（懒加载）

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        btn_add = QPushButton("+ 添加员工")
        btn_add.setStyleSheet(primary_btn)
        btn_add.setFixedHeight(36)
        btn_add.clicked.connect(self.add)
        toolbar.addWidget(btn_add)

        btn_import = QPushButton("导入CSV")
        btn_import.setFixedHeight(36)
        btn_import.clicked.connect(self.import_data)
        toolbar.addWidget(btn_import)

        btn_export = QPushButton("导出Excel")
        btn_export.setFixedHeight(36)
        btn_export.clicked.connect(self.export_data)
        toolbar.addWidget(btn_export)

        toolbar.addStretch()

        toolbar.addWidget(QLabel("搜索："))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("姓名/手机号/岗位")
        self.txt_search.setFixedWidth(200)
        self.txt_search.setStyleSheet(INPUT_STYLE)
        self.txt_search.textChanged.connect(lambda: self.load_data())
        toolbar.addWidget(self.txt_search)
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["序号", "姓名", "手机号", "部门", "岗位", "基本工资", "入职日期", "状态", "操作"])
        self.table.setColumnWidth(0, 50)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
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
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        search_text = self.txt_search.text().strip() if hasattr(self, 'txt_search') else ""
        search_where = ""
        search_params = []
        if search_text:
            search_where = " AND (e.name LIKE ? OR e.phone LIKE ? OR e.position LIKE ?)"
            search_params = [f"%{search_text}%"] * 3
        if _all:
            cursor.execute(f"""SELECT e.*, d.name as dept_name FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE (e.is_system_user = 0 OR e.is_system_user IS NULL){search_where} ORDER BY e.id""", search_params)
        else:
            cursor.execute(f"""SELECT e.*, d.name as dept_name FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE (e.store_id=? OR e.store_id IS NULL) AND (e.is_system_user = 0 OR e.is_system_user IS NULL){search_where} ORDER BY e.id""",
                [_sid] + search_params)
        rows = cursor.fetchall()
        conn.close()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            sn_item = QTableWidgetItem(str(i + 1))
            sn_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn_item)
            _ci1 = QTableWidgetItem(d["name"])
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(d.get("phone", ""))
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci2)
            _ci3 = QTableWidgetItem(d.get("dept_name", ""))
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, _ci3)
            _ci4 = QTableWidgetItem(d.get("position", ""))
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, _ci4)
            salary_item = QTableWidgetItem(f"¥{d.get('base_salary',0):.2f}")
            salary_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, salary_item)
            _ci5 = QTableWidgetItem(d.get("hire_date", ""))
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 6, _ci5)
            status_item = QTableWidgetItem(d.get("status", ""))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 7, status_item)

            widget = QWidget()
            widget.setObjectName("btnCell")
            widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
            hl = QHBoxLayout(widget)
            hl.setContentsMargins(0, 0, 0, 0)
            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            eid = d["id"]
            btn_edit.clicked.connect(lambda checked, eid=eid: self.edit(eid))
            btn_del.clicked.connect(lambda checked, eid=eid: self.delete_employee(eid))
            hl.addStretch()
            hl.addWidget(btn_edit)
            hl.addWidget(btn_del)
            hl.addStretch()
            self.table.setCellWidget(i, 8, widget)

    def add(self):
        dlg = EmployeeDialog(self)
        if dlg.exec_():
            self.load_data()

    def export_data(self):
        _sid, _ = _ctx().get_store_filter()
        export_to_excel("employees", self, _sid)

    def import_data(self):
        ok, skip = import_from_csv("employees", self)
        if ok > 0:
            self.load_data()

    def edit(self, eid):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT e.*, d.name as department_name FROM employees e
            LEFT JOIN departments d ON e.department_id = d.id WHERE e.id=?""", (eid,))
        row = dict(cursor.fetchone())
        conn.close()
        dlg = EmployeeDialog(self, row)
        if dlg.exec_():
            self.load_data()

    def delete_employee(self, eid):
        reply = QMessageBox.question(self, "确认删除", "确定要删除该员工吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM employees WHERE id=?", (eid,))
        conn.commit()
        conn.close()
        _sync_cloud()
        self.load_data()
