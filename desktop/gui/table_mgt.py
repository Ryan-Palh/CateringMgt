# -*- coding: utf-8 -*-
"""
桌台管理 v5.0 —— 餐饮专业版
- 桌台状态总览卡片（总数/空闲/占用/预定）
- 快捷切换桌台状态
- 区域管理、容量设置
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QLineEdit, QComboBox, QDialog, QFormLayout, QSpinBox,
                             QMessageBox, QFrame)
from database.db_manager import get_connection
from utils.app_context import get_app_context as _ctx
from gui.theme import COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE, primary_btn, make_table_button
from utils.logger import logger

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")


class TableDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("编辑桌台" if data else "添加桌台")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"QDialog {{ background: {COLOR['bg_card']}; }}")
        layout = QFormLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(28, 24, 28, 20)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("如：A1、大厅-3号桌")
        self.txt_name.setStyleSheet(INPUT_STYLE)
        self.txt_name.setFixedHeight(40)
        layout.addRow("桌台名称 *：", self.txt_name)

        self.txt_area = QLineEdit()
        self.txt_area.setPlaceholderText("如：大厅、包间A区、露台")
        self.txt_area.setStyleSheet(INPUT_STYLE)
        self.txt_area.setFixedHeight(40)
        layout.addRow("区域：", self.txt_area)

        self.spin_cap = QSpinBox()
        self.spin_cap.setButtonSymbols(QSpinBox.NoButtons)
        self.spin_cap.setRange(1, 30)
        self.spin_cap.setStyleSheet(INPUT_STYLE)
        self.spin_cap.setFixedHeight(40)
        layout.addRow("容纳人数：", self.spin_cap)

        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["空闲", "占用", "预定", "清洁中"])
        self.cmb_status.setStyleSheet(COMBO_STYLE)
        self.cmb_status.setFixedHeight(40)
        layout.addRow("状态：", self.cmb_status)

        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(primary_btn)
        btn_save.setFixedHeight(38)
        btn_save.clicked.connect(self.save)
        layout.addRow(btn_save)

        if data:
            self.txt_name.setText(data.get("name", ""))
            self.txt_area.setText(data.get("area", ""))
            self.spin_cap.setValue(data.get("capacity", 4))
            idx = self.cmb_status.findText(data.get("status", "空闲"))
            if idx >= 0:
                self.cmb_status.setCurrentIndex(idx)

        self.setLayout(layout)

    def save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入桌台名称")
            return
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if self.data:
            cursor.execute("""UPDATE dining_tables SET name=?,area=?,capacity=?,status=? WHERE id=?""",
                          (name, self.txt_area.text(), self.spin_cap.value(), self.cmb_status.currentText(), self.data["id"]))
        else:
            cursor.execute("""INSERT INTO dining_tables (name,area,capacity,status,store_id) VALUES (?,?,?,?,?)""",
                          (name, self.txt_area.text(), self.spin_cap.value(), self.cmb_status.currentText(), _sid))
        conn.commit()
        conn.close()
        _sync_cloud()
        self.accept()


class TableWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self.init_ui()
        # load_data() 延迟到首次切换时调用（懒加载）

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 概览卡片
        self.cards_frame = QFrame()
        self.cards_layout = QHBoxLayout(self.cards_frame)
        self.cards_layout.setSpacing(16)
        layout.addWidget(self.cards_frame)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        btn_add = QPushButton("+ 添加桌台")
        btn_add.setStyleSheet(primary_btn)
        btn_add.setFixedHeight(36)
        btn_add.clicked.connect(self.add_table)
        toolbar.addWidget(btn_add)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["序号", "桌台名称", "区域", "容量", "状态", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 100)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def _make_card(self, label, value, color):
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
        vl.setStyleSheet(f"font-size: {FONT_SIZE['4xl']}px; font-weight: 700; color: {color};")
        tl = QLabel(label)
        tl.setStyleSheet(f"font-size: {FONT_SIZE['sm']}px; color: {COLOR['text_muted']};")
        cl.addWidget(vl)
        cl.addWidget(tl)
        return card

    def load_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT * FROM dining_tables ORDER BY area, id")
        else:
            cursor.execute("SELECT * FROM dining_tables WHERE store_id=? OR store_id IS NULL ORDER BY area, id", (_sid,))
        rows = cursor.fetchall()
        conn.close()

        total = len(rows)
        free = sum(1 for r in rows if r["status"] == "空闲")
        busy = sum(1 for r in rows if r["status"] == "占用")
        booked = sum(1 for r in rows if r["status"] == "预定")

        for i in reversed(range(self.cards_layout.count())):
            self.cards_layout.itemAt(i).widget().setParent(None)

        for label, value, color in [
            ("总桌台", str(total), COLOR['info']),
            ("空闲", str(free), COLOR['success']),
            ("占用", str(busy), COLOR['danger']),
            ("预定", str(booked), COLOR['warning']),
        ]:
            self.cards_layout.addWidget(self._make_card(label, value, color))

        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            d = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci1 = QTableWidgetItem(d["name"])
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(d.get("area", "") or "")
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci2)
            cap = QTableWidgetItem(f"{d['capacity']}人")
            cap.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, cap)
            _ci3 = QTableWidgetItem(d.get("status", "空闲"))
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, _ci3)

            btn_widget = QWidget()
            btn_widget.setObjectName("btnCell")
            btn_widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(4)

            if d["status"] != "空闲":
                btn_free = make_table_button("空闲", "edit")
                btn_free.clicked.connect(lambda checked, r=d: self.quick_status(r, "空闲"))
                btn_layout.addWidget(btn_free)
            if d["status"] != "占用":
                btn_busy = make_table_button("占用", "delete")
                btn_busy.clicked.connect(lambda checked, r=d: self.quick_status(r, "占用"))
                btn_layout.addWidget(btn_busy)

            btn_edit = make_table_button("编辑", "edit")
            btn_edit.clicked.connect(lambda checked, r=d: self.edit_table(r))
            btn_layout.addWidget(btn_edit)

            btn_del = make_table_button("删除", "delete")
            btn_del.clicked.connect(lambda checked, r=d: self.delete_table(r))
            btn_layout.addWidget(btn_del)

            self.table.setCellWidget(i, 5, btn_widget)

    def add_table(self):
        dlg = TableDialog(self)
        if dlg.exec_():
            self.load_data()

    def edit_table(self, row):
        dlg = TableDialog(self, row)
        if dlg.exec_():
            self.load_data()

    def delete_table(self, row):
        reply = QMessageBox.question(self, "确认删除", f"确定删除桌台「{row['name']}」吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dining_tables WHERE id=?", (row["id"],))
            conn.commit()
            conn.close()
            _sync_cloud()
            self.load_data()

    def quick_status(self, row, status):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE dining_tables SET status=? WHERE id=?", (status, row["id"]))
        conn.commit()
        conn.close()
        _sync_cloud()
        self.load_data()
