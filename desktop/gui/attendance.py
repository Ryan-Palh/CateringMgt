# -*- coding: utf-8 -*-
"""
考勤管理 v5.0 —— 餐饮专业版
- 签到/签退（含位置信息）
- 月度考勤记录、迟到统计
- 按门店过滤
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QComboBox, QMessageBox)
from PyQt5.QtCore import Qt, QDate, QTime
from PyQt5.QtGui import QColor
from utils.font_utils import make_font

from database.db_manager import get_connection
from utils.app_context import get_app_context as _ctx
from gui.theme import COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, COMBO_STYLE, BTN_SUCCESS, BTN_DANGER
from utils.helpers import get_today
from utils.location_helper import get_current_location
from utils.logger import logger

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")


class AttendanceWidget(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.init_ui()
        # load_data() 延迟到首次切换时调用（懒加载）

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        btn_checkin = QPushButton("📍 签到")
        btn_checkin.setStyleSheet(BTN_SUCCESS)
        btn_checkin.setFixedHeight(36)
        btn_checkin.clicked.connect(self.do_checkin)
        toolbar.addWidget(btn_checkin)

        btn_checkout = QPushButton("📤 签退")
        btn_checkout.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR['warning']}; color: {COLOR['text_white']};
                border: none; border-radius: {RADIUS['md']}px;
                padding: 8px 20px; font-size: {FONT_SIZE['base']}px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {COLOR['warning_hover']}; }}
        """)
        btn_checkout.setFixedHeight(36)
        btn_checkout.clicked.connect(self.do_checkout)
        toolbar.addWidget(btn_checkout)

        toolbar.addStretch()

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

        # 汇总
        self.lbl_summary = QLabel()
        self.lbl_summary.setStyleSheet(f"color: {COLOR['text_secondary']}; font-size: {FONT_SIZE['sm']}px; padding: 4px 0;")
        layout.addWidget(self.lbl_summary)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["序号", "员工", "部门", "日期", "签到", "签退", "状态", "打卡位置", "备注"])
        self.table.setColumnWidth(0, 60)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def do_checkin(self):
        conn = get_connection()
        cursor = conn.cursor()
        today = get_today()
        now = QTime.currentTime().toString("HH:mm:ss")

        if not self.current_user or not self.current_user.get("id"):
            QMessageBox.warning(self, "提示", "无法识别当前用户，请重新登录")
        conn.close()
        return

        emp_id = self.current_user["id"]
        emp_name = self.current_user.get("name", "")
        cursor.execute("SELECT status FROM employees WHERE id=?", (emp_id,))
        emp_row = cursor.fetchone()
        if not emp_row or emp_row["status"] != "在职":
            QMessageBox.warning(self, "提示", "当前用户未关联在职员工")
            conn.close()
            return

        cursor.execute("SELECT id FROM attendance WHERE employee_id=? AND record_date=?", (emp_id, today))
        if cursor.fetchone():
            QMessageBox.warning(self, "提示", "今天已签到")
            conn.close()
            return

        _sid, _ = _ctx().get_store_filter()
        location_info = get_current_location()
        try:
            cursor.execute("INSERT INTO attendance (employee_id, record_date, check_in, store_id, check_in_location, check_in_lat, check_in_lon) VALUES (?,?,?,?,?,?,?)",
                           (emp_id, today, now, _sid, location_info.get('address', ''), location_info.get('lat', ''), location_info.get('lon', '')))
            conn.commit()
            _sync_cloud()
            loc_str = f"\n📍 位置: {location_info.get('address', '未知')}" if location_info.get('address') else ""
            QMessageBox.information(self, "签到成功", f"{emp_name} 于 {now} 签到成功{loc_str}")
        except Exception as e:
            QMessageBox.warning(self, "提示", f"签到失败：{e}")
        conn.close()
        self.load_data()

    def do_checkout(self):
        conn = get_connection()
        cursor = conn.cursor()
        today = get_today()
        now = QTime.currentTime().toString("HH:mm:ss")

        if not self.current_user or not self.current_user.get("id"):
            QMessageBox.warning(self, "提示", "无法识别当前用户，请重新登录")
        conn.close()
        return

        emp_id = self.current_user["id"]
        emp_name = self.current_user.get("name", "")

        _sid, _all = _ctx().get_store_filter()
        location_info = get_current_location()
        if _all:
            cursor.execute("UPDATE attendance SET check_out=?, check_out_location=?, check_out_lat=?, check_out_lon=? WHERE employee_id=? AND record_date=?",
                           (now, location_info.get('address', ''), location_info.get('lat', ''), location_info.get('lon', ''), emp_id, today))
        else:
            cursor.execute("UPDATE attendance SET check_out=?, check_out_location=?, check_out_lat=?, check_out_lon=? WHERE employee_id=? AND record_date=? AND store_id=?",
                           (now, location_info.get('address', ''), location_info.get('lat', ''), location_info.get('lon', ''), emp_id, today, _sid))
        if cursor.rowcount > 0:
            conn.commit()
            _sync_cloud()
            loc_str = f"\n📍 位置: {location_info.get('address', '未知')}" if location_info.get('address') else ""
            QMessageBox.information(self, "签退成功", f"{emp_name} 于 {now} 签退成功{loc_str}")
        else:
            QMessageBox.warning(self, "提示", "请先签到")
        conn.close()
        self.load_data()

    def load_data(self):
        month_str = self.cmb_month.currentData()
        if not month_str:
            return

        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("""SELECT a.*, e.name as emp_name, d.name as dept_name
                              FROM attendance a
                              JOIN employees e ON a.employee_id = e.id
                              LEFT JOIN departments d ON e.department_id = d.id
                              WHERE a.record_date LIKE ? ORDER BY a.record_date DESC, e.name""",
                           (f"{month_str}%",))
        else:
            cursor.execute("""SELECT a.*, e.name as emp_name, d.name as dept_name
                              FROM attendance a
                              JOIN employees e ON a.employee_id = e.id
                              LEFT JOIN departments d ON e.department_id = d.id
                              WHERE a.record_date LIKE ? AND (a.store_id=? OR a.store_id IS NULL)
                              ORDER BY a.record_date DESC, e.name""",
                           (f"{month_str}%", _sid))
        rows = cursor.fetchall()

        self.table.setRowCount(len(rows))
        normal_count = 0
        late_count = 0
        for i, row in enumerate(rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci1 = QTableWidgetItem(r.get("emp_name", ""))
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(r.get("dept_name", ""))
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci2)
            _ci3 = QTableWidgetItem(r.get("record_date", ""))
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, _ci3)
            _ci4 = QTableWidgetItem(r.get("check_in", "")[:5] if r.get("check_in") else "")
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, _ci4)
            _ci5 = QTableWidgetItem(r.get("check_out", "")[:5] if r.get("check_out") else "")
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, _ci5)

            status = r.get("status", "正常")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "迟到":
                status_item.setForeground(QColor(COLOR['danger']))
                late_count += 1
            else:
                normal_count += 1
            self.table.setItem(i, 6, status_item)

            loc_display = r.get("check_in_location", "") or ""
            if r.get("check_out_location"):
                loc_display += f" → {r['check_out_location']}"
            _ci6 = QTableWidgetItem(loc_display)
            _ci6.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 7, _ci6)
            _ci7 = QTableWidgetItem(r.get("remark", ""))
            _ci7.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 8, _ci7)

        conn.close()
        self.lbl_summary.setText(f"本月记录 {len(rows)} 条 | 正常 {normal_count} 次 | 迟到 {late_count} 次")
