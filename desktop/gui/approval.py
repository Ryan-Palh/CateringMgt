# -*- coding: utf-8 -*-
"""
审批中心 v5.0 —— 餐饮专业版
- 待审批列表 + 审批历史
- 通过/拒绝 + 审批意见
- 报销通过自动创建财务记录
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QTextEdit, QDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from database.db_manager import get_connection
from utils.auth_manager import ADMIN_ROLES
from utils.app_context import get_app_context as _ctx
from gui.theme import COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, make_table_button
from datetime import datetime
from utils.logger import logger

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")


class ApprovalWidget(QWidget):
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

        lbl_pending = QLabel("待审批事项")
        lbl_pending.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: 600; color: {COLOR['text_primary']};")
        layout.addWidget(lbl_pending)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["序号", "类型", "申请单号", "申请人", "金额/说明", "提交时间", "操作"])
        self.table.setColumnWidth(0, 60)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        lbl_history = QLabel("审批历史")
        lbl_history.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: 600; color: {COLOR['text_primary']}; margin-top: 8px;")
        layout.addWidget(lbl_history)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(["序号", "类型", "申请人", "结果", "审批意见", "审批时间"])
        self.history_table.setColumnWidth(0, 60)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setStyleSheet(TABLE_STYLE)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.verticalHeader().setDefaultSectionSize(48)
        layout.addWidget(self.history_table)

        self.setLayout(layout)

    def load_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        is_admin = self.current_user["role"] in ADMIN_ROLES
        _sid, _all = _ctx().get_store_filter()

        # 待审批
        if is_admin:
            if _all:
                cursor.execute("""SELECT a.*, e.name as applicant_name, r.title, r.amount
                                  FROM approvals a
                                  LEFT JOIN employees e ON a.applicant_id = e.id
                                  LEFT JOIN reimbursements r ON a.biz_type='报销' AND a.biz_id = r.id
                                  WHERE a.status='待审批' ORDER BY a.id DESC""")
            else:
                cursor.execute("""SELECT a.*, e.name as applicant_name, r.title, r.amount
                                  FROM approvals a LEFT JOIN employees e ON a.applicant_id = e.id
                                  LEFT JOIN reimbursements r ON a.biz_type='报销' AND a.biz_id = r.id
                                  WHERE a.status='待审批' AND (a.store_id=? OR a.store_id IS NULL) ORDER BY a.id DESC""", (_sid,))
        else:
            if _all:
                cursor.execute("""SELECT a.*, e.name as applicant_name, r.title, r.amount
                                  FROM approvals a LEFT JOIN employees e ON a.applicant_id = e.id
                                  LEFT JOIN reimbursements r ON a.biz_type='报销' AND a.biz_id = r.id
                                  WHERE a.approver_id=? AND a.status='待审批' ORDER BY a.id DESC""", (self.current_user["id"],))
            else:
                cursor.execute("""SELECT a.*, e.name as applicant_name, r.title, r.amount
                                  FROM approvals a LEFT JOIN employees e ON a.applicant_id = e.id
                                  LEFT JOIN reimbursements r ON a.biz_type='报销' AND a.biz_id = r.id
                                  WHERE a.approver_id=? AND a.status='待审批' AND (a.store_id=? OR a.store_id IS NULL)
                                  ORDER BY a.id DESC""", (self.current_user["id"], _sid))

        rows = cursor.fetchall()
        self.table.setRowCount(len(rows))
        if not rows:
            self.table.setRowCount(1)
            empty = QTableWidgetItem("暂无待审批事项")
            empty.setTextAlignment(Qt.AlignCenter)
            self.table.setSpan(0, 0, 1, 7)
            self.table.setItem(0, 0, empty)
        for i, row in enumerate(rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci1 = QTableWidgetItem(r.get("biz_type", ""))
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(f"#{r.get('biz_id', '')}")
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci2)
            _ci3 = QTableWidgetItem(r.get("applicant_name", ""))
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, _ci3)
            title_text = r.get("title", "") or ""
            if r.get("amount"):
                title_text = f"¥{r['amount']:.2f} {title_text}"
            _ci4 = QTableWidgetItem(str(title_text))
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, _ci4)
            _ci5 = QTableWidgetItem(r.get("created_at", ""))
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, _ci5)

            btn_widget = QWidget()
            btn_widget.setObjectName("btnCell")
            btn_widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
            hl = QHBoxLayout(btn_widget)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            btn_pass = make_table_button("通过", "view")
            btn_reject = make_table_button("拒绝", "delete")
            aid = r["id"]
            biz_type = r["biz_type"]
            biz_id = r["biz_id"]
            btn_pass.clicked.connect(lambda checked, aid=aid, bt=biz_type, bi=biz_id: self.approve(aid, bt, bi, "已通过"))
            btn_reject.clicked.connect(lambda checked, aid=aid, bt=biz_type, bi=biz_id: self.approve(aid, bt, bi, "已拒绝"))
            hl.addStretch()
            hl.addWidget(btn_pass)
            hl.addWidget(btn_reject)
            hl.addStretch()
            self.table.setCellWidget(i, 6, btn_widget)

        # 审批历史
        if is_admin:
            if _all:
                cursor.execute("""SELECT a.*, e.name as applicant_name FROM approvals a
                                  LEFT JOIN employees e ON a.applicant_id = e.id
                                  WHERE a.status!='待审批' ORDER BY a.updated_at DESC LIMIT 50""")
            else:
                cursor.execute("""SELECT a.*, e.name as applicant_name FROM approvals a
                                  LEFT JOIN employees e ON a.applicant_id = e.id
                                  WHERE a.status!='待审批' AND (a.store_id=? OR a.store_id IS NULL)
                                  ORDER BY a.updated_at DESC LIMIT 50""", (_sid,))
        else:
            if _all:
                cursor.execute("""SELECT a.*, e.name as applicant_name FROM approvals a
                                  LEFT JOIN employees e ON a.applicant_id = e.id
                                  WHERE (a.approver_id=? OR a.applicant_id=?) AND a.status!='待审批'
                                  ORDER BY a.updated_at DESC LIMIT 50""", (self.current_user["id"], self.current_user["id"]))
            else:
                cursor.execute("""SELECT a.*, e.name as applicant_name FROM approvals a
                                  LEFT JOIN employees e ON a.applicant_id = e.id
                                  WHERE (a.approver_id=? OR a.applicant_id=?) AND a.status!='待审批'
                                  AND (a.store_id=? OR a.store_id IS NULL)
                                  ORDER BY a.updated_at DESC LIMIT 50""", (self.current_user["id"], self.current_user["id"], _sid))
        hist_rows = cursor.fetchall()
        conn.close()

        self.history_table.setRowCount(len(hist_rows))
        for i, row in enumerate(hist_rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(i, 0, sn)
            _ci6 = QTableWidgetItem(r.get("biz_type", ""))
            _ci6.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(i, 1, _ci6)
            _ci7 = QTableWidgetItem(r.get("applicant_name", ""))
            _ci7.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(i, 2, _ci7)
            status_item = QTableWidgetItem(r.get("status", ""))
            status_item.setTextAlignment(Qt.AlignCenter)
            if r.get("status") == "已通过":
                status_item.setForeground(QColor(COLOR['success']))
            elif r.get("status") == "已拒绝":
                status_item.setForeground(QColor(COLOR['danger']))
            self.history_table.setItem(i, 3, status_item)
            _ci8 = QTableWidgetItem(r.get("comment", ""))
            _ci8.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(i, 4, _ci8)
            _ci9 = QTableWidgetItem(r.get("updated_at", ""))
            _ci9.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(i, 5, _ci9)

    def approve(self, approval_id, biz_type, biz_id, status):
        dlg = QDialog(self)
        dlg.setWindowTitle("审批确认")
        dlg.resize(500, 380)
        dlg.setMinimumSize(460, 340)
        dlg.setStyleSheet(f"QDialog {{ background: {COLOR['bg_card']}; }}")
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        action = "通过" if status == "已通过" else "拒绝"
        color = COLOR['success'] if status == "已通过" else COLOR['danger']
        label = QLabel(f"确定{action}此申请？")
        label.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: 600; color: {color};")
        layout.addWidget(label)

        layout.addWidget(QLabel("审批意见："))
        txt_comment = QTextEdit()
        txt_comment.setPlaceholderText("可选填写审批意见...")
        txt_comment.setFixedHeight(80)
        layout.addWidget(txt_comment)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确认提交")
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {color}; color: {COLOR['text_white']};
                border: none; border-radius: {RADIUS['md']}px;
                padding: 8px 20px; font-size: {FONT_SIZE['base']}px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {COLOR['danger_hover'] if status != '已通过' else COLOR['success_hover']}; }}
        """)
        btn_ok.setFixedHeight(38)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(38)
        btn_cancel.clicked.connect(dlg.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        dlg.setLayout(layout)

        if dlg.exec_():
            conn = get_connection()
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""UPDATE approvals SET status=?, approver_id=?, comment=?, updated_at=? WHERE id=?""",
                           (status, self.current_user["id"], txt_comment.toPlainText(), now, approval_id))

            if biz_type == "报销":
                cursor.execute("UPDATE reimbursements SET status=?, approve_date=? WHERE id=?", (status, now[:10], biz_id))
                if status == "已通过":
                    cursor.execute("SELECT amount, employee_id FROM reimbursements WHERE id=?", (biz_id,))
                    row = cursor.fetchone()
                    if row:
                        cursor.execute("SELECT name FROM employees WHERE id=?", (row["employee_id"],))
                        emp_row = cursor.fetchone()
                        emp_name = emp_row["name"] if emp_row else "未知"
                        from utils.data_linkage import auto_finance_from_reimbursement
                        from utils.app_context import get_app_context
                        op = get_app_context().current_username or ""
                        auto_finance_from_reimbursement(biz_id, row["amount"], emp_name, op)

            conn.commit()
            conn.close()
            _sync_cloud()
            self.load_data()
