# -*- coding: utf-8 -*-
"""
门店管理 v5.0 —— 餐饮专业版
- 门店信息CRUD：名称、地址、电话、负责人、营业时间、状态
- 门店状态：正常、停业、装修中
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QFrame)
from PyQt5.QtCore import Qt
from database.db_manager import get_connection, _safe_sql_identifier
from gui.theme import COLOR, RADIUS, FONT_SIZE, DLG_STYLE, TABLE_STYLE, COMBO_STYLE, primary_btn, make_table_button
from utils.logger import logger

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")


class StoreDialog(QDialog):
    def __init__(self, parent=None, store_data=None):
        super().__init__(parent)
        self.store_data = store_data
        self.setWindowTitle("编辑门店" if store_data else "新建门店")
        self.resize(560, 520)
        self.setMinimumSize(500, 460)
        self.setStyleSheet(DLG_STYLE)
        self.init_ui()
        if store_data:
            self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(18)

        title = QLabel("编辑门店" if self.store_data else "新建门店")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLOR['border']}; max-height: 1px;")
        layout.addWidget(line)

        form = QFormLayout()
        form.setSpacing(18)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("请输入门店名称（必填）")
        self.txt_name.setFixedHeight(40)
        form.addRow("门店名称 *：", self.txt_name)

        self.txt_address = QLineEdit()
        self.txt_address.setPlaceholderText("请输入门店地址")
        self.txt_address.setFixedHeight(40)
        form.addRow("地    址：", self.txt_address)

        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("请输入联系电话")
        self.txt_phone.setFixedHeight(40)
        form.addRow("电    话：", self.txt_phone)

        self.txt_manager = QLineEdit()
        self.txt_manager.setPlaceholderText("请输入负责人")
        self.txt_manager.setFixedHeight(40)
        form.addRow("负 责 人：", self.txt_manager)

        self.txt_hours = QLineEdit()
        self.txt_hours.setPlaceholderText("如：09:00-22:00")
        self.txt_hours.setFixedHeight(40)
        form.addRow("营业时间：", self.txt_hours)

        self.cmb_status = QComboBox()
        self.cmb_status.setStyleSheet(COMBO_STYLE)
        self.cmb_status.addItems(["正常", "停业", "装修中"])
        self.cmb_status.setFixedHeight(40)
        form.addRow("状    态：", self.cmb_status)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注信息（可选）")
        self.txt_remark.setFixedHeight(40)
        form.addRow("备    注：", self.txt_remark)

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

    def load_data(self):
        self.txt_name.setText(self.store_data["name"])
        self.txt_address.setText(self.store_data.get("address", "") or "")
        self.txt_phone.setText(self.store_data.get("phone", "") or "")
        self.txt_manager.setText(self.store_data.get("manager", "") or "")
        self.txt_hours.setText(self.store_data.get("business_hours", "") or "09:00-22:00")
        self.cmb_status.setCurrentText(self.store_data.get("status", "正常"))
        self.txt_remark.setText(self.store_data.get("remark", "") or "")

    def save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入门店名称")
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            if self.store_data:
                cursor.execute("""UPDATE stores SET name=?,address=?,phone=?,manager=?,business_hours=?,status=?,remark=? WHERE id=?""",
                    (name, self.txt_address.text(), self.txt_phone.text(), self.txt_manager.text(),
                     self.txt_hours.text(), self.cmb_status.currentText(), self.txt_remark.text(), self.store_data["id"]))
            else:
                cursor.execute("""INSERT INTO stores (name,address,phone,manager,business_hours,status,remark) VALUES (?,?,?,?,?,?,?)""",
                    (name, self.txt_address.text(), self.txt_phone.text(), self.txt_manager.text(),
                     self.txt_hours.text(), self.cmb_status.currentText(), self.txt_remark.text()))
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")


class StoreWidget(QWidget):
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
        btn_add = QPushButton("+ 新建门店")
        btn_add.setStyleSheet(primary_btn)
        btn_add.setFixedHeight(36)
        btn_add.clicked.connect(self.add)
        toolbar.addWidget(btn_add)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["序号", "门店名称", "地址", "电话", "负责人", "状态", "创建时间", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 60)
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
        cursor.execute("SELECT * FROM stores ORDER BY id")
        rows = cursor.fetchall()
        conn.close()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci1 = QTableWidgetItem(d["name"])
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(d.get("address", "") or "")
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci2)
            _ci3 = QTableWidgetItem(d.get("phone", "") or "")
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, _ci3)
            _ci4 = QTableWidgetItem(d.get("manager", "") or "")
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, _ci4)
            status_item = QTableWidgetItem(d.get("status", "正常"))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, status_item)
            _ci5 = QTableWidgetItem(d.get("created_at", "") or "")
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 6, _ci5)

            btn_widget = QWidget()
            btn_widget.setObjectName("btnCell")
            btn_widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
            btn_h = QHBoxLayout(btn_widget)
            btn_h.setContentsMargins(0, 0, 0, 0)
            btn_h.setSpacing(4)
            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            sid = d["id"]
            btn_edit.clicked.connect(lambda checked, sid=sid: self.edit(sid))
            btn_del.clicked.connect(lambda checked, sid=sid: self.delete_store(sid))
            btn_h.addStretch()
            btn_h.addWidget(btn_edit)
            btn_h.addWidget(btn_del)
            btn_h.addStretch()
            self.table.setCellWidget(i, 7, btn_widget)

    def add(self):
        dlg = StoreDialog(self)
        if dlg.exec_():
            self.load_data()

    def edit(self, sid):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stores WHERE id=?", (sid,))
        row = dict(cursor.fetchone())
        conn.close()
        dlg = StoreDialog(self, row)
        if dlg.exec_():
            self.load_data()

    def delete_store(self, sid):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM stores WHERE id=?", (sid,))
        row = cursor.fetchone()
        name = row["name"] if row else f"ID={sid}"
        conn.close()
        reply = QMessageBox.question(self, "确认删除",
                                     f"确定要删除门店「{name}」吗？\n此操作不可恢复。",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = get_connection()
            cursor = conn.cursor()
            # 解除所有引用该门店的外键关系（置为NULL），避免FOREIGN KEY约束报错
            ref_tables = ["employees", "purchases", "daily_revenue", "finance_records",
                          "attendance", "salary_records", "reimbursements",
                          "ingredients", "dishes", "suppliers", "shifts"]
            for tbl in ref_tables:
                try:
                    cursor.execute(f"UPDATE {_safe_sql_identifier(tbl)} SET store_id=NULL WHERE store_id=?", (sid,))
                except Exception:
                    pass
            cursor.execute("DELETE FROM stores WHERE id=?", (sid,))
            conn.commit()
            conn.close()
            _sync_cloud()
            self.load_data()
