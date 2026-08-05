# -*- coding: utf-8 -*-
"""
排班管理 v5.0 —— 餐饮专业版
- 餐饮班次：早班/中班/晚班/全天/休息
- 周视图排班表（7天 × 员工）
- 批量排班功能
"""
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QComboBox, QDialog, QFormLayout, QMessageBox, QFrame)
from gui.calendar_widget import ModernDateEdit
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor
from database.db_manager import get_connection
from utils.app_context import get_app_context as _ctx
from gui.theme import COLOR, FONT_SIZE, TABLE_STYLE, COMBO_STYLE, primary_btn
from utils.logger import logger

import re

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")

SHIFT_TYPES = ["早班(08:00-16:00)", "中班(12:00-20:00)", "晚班(16:00-00:00)", "全天(08:00-20:00)", "休息"]

SHIFT_COLORS = {
    "早班": COLOR['success'],
    "中班": COLOR['warning'],
    "晚班": COLOR['info'],
    "全天": COLOR['primary'],
    "休息": COLOR['text_muted'],
}


def parse_shift_time(shift_type):
    if not shift_type or "休息" in shift_type:
        return "", ""
    m = re.search(r'[（(](\d{2}:\d{2})\s*[-~–]\s*(\d{2}:\d{2})[）)]', shift_type)
    if m:
        return m.group(1), m.group(2)
    return "", ""


class ShiftDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量排班")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"QDialog {{ background: {COLOR['bg_card']}; }}")
        layout = QFormLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(28, 24, 28, 20)

        self.cmb_emp = QComboBox()
        self.cmb_emp.setStyleSheet(COMBO_STYLE)
        self.cmb_emp.setFixedHeight(40)
        self.load_employees()
        layout.addRow("员工：", self.cmb_emp)

        self.date_start = ModernDateEdit()
        self.date_start.setDate(QDate.currentDate())
        self.date_start.setFixedHeight(40)
        layout.addRow("开始日期：", self.date_start)

        self.date_end = ModernDateEdit()
        self.date_end.setDate(QDate.currentDate().addDays(6))
        self.date_end.setFixedHeight(40)
        layout.addRow("结束日期：", self.date_end)

        self.cmb_shift = QComboBox()
        self.cmb_shift.addItems(SHIFT_TYPES)
        self.cmb_shift.setStyleSheet(COMBO_STYLE)
        self.cmb_shift.setFixedHeight(40)
        layout.addRow("班次：", self.cmb_shift)

        btn_save = QPushButton("批量设置")
        btn_save.setStyleSheet(primary_btn)
        btn_save.setFixedHeight(38)
        btn_save.clicked.connect(self.save)
        layout.addRow(btn_save)

        self.setLayout(layout)

    def load_employees(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT id, name FROM employees WHERE status='在职' AND (is_system_user=0 OR is_system_user IS NULL)")
        else:
            cursor.execute("SELECT id, name FROM employees WHERE status='在职' AND (store_id=? OR store_id IS NULL) AND (is_system_user=0 OR is_system_user IS NULL)", (_sid,))
        for row in cursor.fetchall():
            self.cmb_emp.addItem(row["name"], row["id"])
        conn.close()

    def save(self):
        eid = self.cmb_emp.currentData()
        if not eid:
            QMessageBox.warning(self, "提示", "请选择员工")
            return
        shift_type = self.cmb_shift.currentText()
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()

        current = self.date_start.date()
        end = self.date_end.date()
        count = 0
        start_t, end_t = parse_shift_time(shift_type)
        while current <= end:
            date_str = current.toString("yyyy-MM-dd")
            cursor.execute("""INSERT OR REPLACE INTO shifts (employee_id, shift_date, shift_type, start_time, end_time, store_id)
                              VALUES (?,?,?,?,?,?)""",
                           (eid, date_str, shift_type, start_t, end_t, _sid))
            count += 1
            current = current.addDays(1)
        conn.commit()
        _sync_cloud()
        QMessageBox.information(self, "成功", f"已为 {self.cmb_emp.currentText()} 设置 {count} 天排班")
        self.accept()


class ShiftWidget(QWidget):
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
        btn_add = QPushButton("+ 批量排班")
        btn_add.setStyleSheet(primary_btn)
        btn_add.setFixedHeight(36)
        btn_add.clicked.connect(self.add_shift)
        toolbar.addWidget(btn_add)

        toolbar.addWidget(QLabel("选择日期："))
        self.date_week = ModernDateEdit()
        self.date_week.setDate(QDate.currentDate())
        self.date_week.dateChanged.connect(self.load_data)
        toolbar.addWidget(self.date_week)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.week_label = QLabel("")
        self.week_label.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: 600; color: {COLOR['text_primary']};")
        layout.addWidget(self.week_label)

        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def load_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()

        base = self.date_week.date()
        monday = base.addDays(-(base.dayOfWeek() - 1))
        sunday = monday.addDays(6)
        self.week_label.setText(f"排班周期：{monday.toString('yyyy-MM-dd')} ~ {sunday.toString('yyyy-MM-dd')}")

        if _all:
            cursor.execute("SELECT id, name FROM employees WHERE status='在职' AND (is_system_user=0 OR is_system_user IS NULL) ORDER BY name")
        else:
            cursor.execute("SELECT id, name FROM employees WHERE status='在职' AND (store_id=? OR store_id IS NULL) AND (is_system_user=0 OR is_system_user IS NULL) ORDER BY name", (_sid,))
        emps = cursor.fetchall()

        dates = [monday.addDays(i).toString("yyyy-MM-dd") for i in range(7)]
        date_labels = [monday.addDays(i).toString("MM/dd\nddd") for i in range(7)]

        shifts = {}
        if _all:
            cursor.execute("SELECT employee_id, shift_date, shift_type FROM shifts WHERE shift_date BETWEEN ? AND ?",
                         (dates[0], dates[6]))
        else:
            cursor.execute("SELECT employee_id, shift_date, shift_type FROM shifts WHERE shift_date BETWEEN ? AND ? AND (store_id=? OR store_id IS NULL)",
                         (dates[0], dates[6], _sid))
        for row in cursor.fetchall():
            shifts[(row["employee_id"], row["shift_date"])] = row["shift_type"]
        conn.close()

        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["员工"] + date_labels)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setStretchLastSection(False)

        self.table.setRowCount(len(emps))
        for i, emp in enumerate(emps):
            name_item = QTableWidgetItem(emp["name"])
            name_item.setTextAlignment(Qt.AlignCenter)
            name_item.setFont(self.font())
            self.table.setItem(i, 0, name_item)
            for j, ds in enumerate(dates):
                shift_type = shifts.get((emp["id"], ds), "-")
                item = QTableWidgetItem(shift_type)
                item.setTextAlignment(Qt.AlignCenter)
                for key, color in SHIFT_COLORS.items():
                    if key in shift_type:
                        item.setForeground(QColor(color))
                        break
                self.table.setItem(i, j + 1, item)

    def add_shift(self):
        dlg = ShiftDialog(self)
        if dlg.exec_():
            self.load_data()
