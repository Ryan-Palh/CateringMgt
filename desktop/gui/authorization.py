# -*- coding: utf-8 -*-
"""
授权管理模块 v5.0 — 餐饮专业版
功能：
  Tab1 用户管理：用户CRUD + 门店分配 + 按门店Tab权限面板 + 启用/禁用/删除/重置密码
  Tab2 门店授权：门店授权查看（只读，编辑需到用户管理）
  Tab3 员工授权：本地员工角色 / 系统角色 / 职位 / 所属门店 / 功能权限设置

权限键与 main_window NAV_GROUPS 一致，共15项导航权限。
"""
import json
import time

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QLineEdit, QComboBox,
    QMessageBox, QCheckBox, QGroupBox, QGridLayout, QTabWidget,
    QFrame, QScrollArea, QSpinBox, QSplitter
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from database.db_manager import get_connection
from gui.theme import (
    COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
    DLG_STYLE, BTN_PRIMARY, BTN_SUCCESS, BTN_DANGER,
    COMPACT_TABLE_STYLE, TABLE_BTN_EDIT, TABLE_BTN_DELETE, TABLE_BTN_VIEW, make_table_button
)
from utils.auth_manager import (
    get_auth, User, UserList,
    PRESET_ROLES, ROLE_DISPLAY, ADMIN_ROLES,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STORE_MANAGER,
    ROLE_SUPERVISOR, ROLE_EMPLOYEE,
)
from utils.app_context import get_app_context as _ctx
from utils.logger import logger
from utils.nutstore_sync import get_sync as _get_sync

def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception:
        pass


# ========== 导航权限定义（与 main_window NAV_GROUPS 一致） ==========

TAB_PERMISSIONS = [
    ("dashboard",     "工作台"),
    ("revenue",       "营业额"),
    ("purchase",      "进销存管理"),
    ("table_mgt",     "桌台管理"),
    ("finance",       "收支管理"),
    ("employee",      "员工管理"),
    ("shifts",        "排班管理"),
    ("attendance",    "考勤管理"),
    ("salary",        "工资管理"),
    ("reimbursement", "报销管理"),
    ("approval",      "审批中心"),
    ("cost_calc",     "成本核算"),
    ("reports",       "报表中心"),
    ("store_manager", "门店管理"),
    ("authorization", "授权管理"),
]

TAB_KEY_SET = {k for k, _ in TAB_PERMISSIONS}


# ========== 用户新增/编辑对话框 ==========

class AddEditUserDialog(QDialog):
    """用户新增/编辑：用户名/密码/显示名/角色 + 门店分配 + 按门店Tab权限面板"""

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.user = user  # User 对象 or None
        self.is_edit = user is not None
        self.setWindowTitle("编辑用户" if self.is_edit else "新增用户")
        self.setMinimumSize(640, 600)
        self.setStyleSheet(DLG_STYLE)

        self._store_checks = {}     # {store_id_str: QCheckBox}
        self._perm_checks = {}      # {(store_id_str, tab_key): QCheckBox}

        layout = QVBoxLayout(self)
        title = QLabel("编辑用户" if self.is_edit else "新增用户")
        title.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: bold; color: {COLOR['primary']};")
        layout.addWidget(title)

        # ---- 基本信息区 ----
        info_group = QGroupBox("基本信息")
        info_form = QFormLayout(info_group)
        info_form.setLabelAlignment(Qt.AlignRight)

        self.username_edit = QLineEdit()
        self.username_edit.setStyleSheet(INPUT_STYLE)
        self.username_edit.setPlaceholderText("登录用户名")
        if self.is_edit:
            self.username_edit.setText(user.username)
            self.username_edit.setReadOnly(True)
        info_form.addRow("用户名 *:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setStyleSheet(INPUT_STYLE)
        self.password_edit.setPlaceholderText("密码（编辑时留空表示不修改）")
        self.password_edit.setEchoMode(QLineEdit.Password)
        info_form.addRow("密码:", self.password_edit)

        self.display_edit = QLineEdit()
        self.display_edit.setStyleSheet(INPUT_STYLE)
        self.display_edit.setPlaceholderText("显示名称")
        if self.is_edit:
            self.display_edit.setText(user.displayName or "")
        info_form.addRow("显示名称:", self.display_edit)

        self.role_combo = QComboBox()
        self.role_combo.setStyleSheet(COMBO_STYLE)
        for role_key, role_name in PRESET_ROLES:
            self.role_combo.addItem(role_name, role_key)
        if self.is_edit:
            idx = self.role_combo.findData(user.role)
            if idx >= 0:
                self.role_combo.setCurrentIndex(idx)
        info_form.addRow("角色:", self.role_combo)

        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True if not self.is_edit else user.enabled)
        info_form.addRow("状态:", self.enabled_check)

        layout.addWidget(info_group)

        # ---- 门店分配 + 按门店Tab权限 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)

        store_group = QGroupBox("门店分配 & 功能权限")
        store_lay = QVBoxLayout(store_group)

        # 全选/全不选门店
        btn_row = QHBoxLayout()
        btn_select_all = QPushButton("全选门店")
        btn_select_all.setStyleSheet(BTN_PRIMARY)
        btn_select_all.clicked.connect(self._select_all_stores)
        btn_deselect_all = QPushButton("全不选门店")
        btn_deselect_all.setStyleSheet(BTN_DANGER)
        btn_deselect_all.clicked.connect(self._deselect_all_stores)
        btn_row.addWidget(btn_select_all)
        btn_row.addWidget(btn_deselect_all)
        btn_row.addStretch()
        store_lay.addLayout(btn_row)

        # 加载门店列表
        conn = get_connection()
        stores = []
        try:
            stores = conn.execute("SELECT id, name FROM stores ORDER BY id").fetchall()
        finally:
            conn.close()

        if not stores:
            store_lay.addWidget(QLabel("（无门店，请先在门店管理中添加）"))
        else:
            for s in stores:
                sid_str = str(s["id"])
                # 门店复选框
                store_cb = QCheckBox(f"🏪 {s['name']}")
                store_cb.setStyleSheet(f"font-size: {FONT_SIZE['md']}px; font-weight: bold; color: {COLOR['text']};")
                self._store_checks[sid_str] = store_cb
                store_lay.addWidget(store_cb)

                # 该门店的Tab权限面板
                perm_frame = QFrame()
                perm_frame.setStyleSheet(f"""
                    QFrame {{
                        background: {COLOR['bg_card']};
                        border-radius: {RADIUS['sm']}px;
                        padding: 4px 8px;
                        margin-left: 24px;
                    }}
                """)
                perm_lay = QGridLayout(perm_frame)
                perm_lay.setContentsMargins(12, 4, 12, 4)

                for col, (tab_key, tab_name) in enumerate(TAB_PERMISSIONS):
                    cb = QCheckBox(tab_name)
                    cb.setStyleSheet(f"font-size: {FONT_SIZE['sm']}px;")
                    self._perm_checks[(sid_str, tab_key)] = cb
                    row = col // 3
                    c = col % 3
                    perm_lay.addWidget(cb, row, c)

                # 快捷：全选/全不选该门店权限
                quick_row = QHBoxLayout()
                btn_all = QPushButton("全选权限")
                btn_all.setFixedWidth(70)
                btn_all.setStyleSheet(TABLE_BTN_VIEW)
                btn_all.clicked.connect(lambda _, f=perm_frame: self._toggle_store_perms(f, True))
                btn_none = QPushButton("全不选权限")
                btn_none.setFixedWidth(80)
                btn_none.setStyleSheet(TABLE_BTN_DELETE)
                btn_none.clicked.connect(lambda _, f=perm_frame: self._toggle_store_perms(f, False))
                quick_row.addWidget(btn_all)
                quick_row.addWidget(btn_none)
                quick_row.addStretch()

                perm_container = QWidget()
                perm_container.setLayout(quick_row)
                store_lay.addWidget(perm_container)
                store_lay.addWidget(perm_frame)

        inner_lay.addWidget(store_group)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        # ---- 按钮 ----
        btn_lay = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(BTN_SUCCESS)
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(BTN_DANGER)
        btn_cancel.clicked.connect(self.reject)
        btn_lay.addStretch()
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_cancel)
        layout.addLayout(btn_lay)

        if self.is_edit:
            self._load_user_data()

    def _select_all_stores(self):
        for cb in self._store_checks.values():
            cb.setChecked(True)

    def _deselect_all_stores(self):
        for cb in self._store_checks.values():
            cb.setChecked(False)

    def _toggle_store_perms(self, frame, checked):
        """切换某个门店权限面板的全选/全不选"""
        for (sid_str, _), cb in self._perm_checks.items():
            # 通过 parent 层级判断是否属于该 frame
            if cb.parent() == frame:
                cb.setChecked(checked)

    def _load_user_data(self):
        """加载已有用户的门店分配和权限"""
        u = self.user
        # 门店分配
        for sid_str in u.allowedStores:
            sid_str = str(sid_str)
            if sid_str in self._store_checks:
                self._store_checks[sid_str].setChecked(True)

        # 按门店Tab权限
        store_perms = u.storeTabPermissions or {}
        for sid_str, tab_keys in store_perms.items():
            sid_str = str(sid_str)
            for tab_key in tab_keys:
                key = (sid_str, tab_key)
                if key in self._perm_checks:
                    self._perm_checks[key].setChecked(True)

    def _save(self):
        username = self.username_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "提示", "请输入用户名")
            return

        display_name = self.display_edit.text().strip() or username
        role = self.role_combo.currentData()
        enabled = self.enabled_check.isChecked()

        # 收集门店分配
        allowed_stores = []
        for sid_str, cb in self._store_checks.items():
            if cb.isChecked():
                allowed_stores.append(sid_str)

        # 收集按门店Tab权限
        store_tab_perms = {}
        for (sid_str, tab_key), cb in self._perm_checks.items():
            if cb.isChecked():
                if sid_str not in store_tab_perms:
                    store_tab_perms[sid_str] = []
                store_tab_perms[sid_str].append(tab_key)

        # 超级管理员拥有全部权限
        if role in ADMIN_ROLES:
            allowed_stores = list(self._store_checks.keys())
            for sid_str in allowed_stores:
                store_tab_perms[sid_str] = [k for k, _ in TAB_PERMISSIONS]

        auth = get_auth()
        try:
            user_list = auth._fetch_users()
            if user_list is None:
                user_list = UserList()

            if self.is_edit:
                # 更新已有用户
                for u in user_list.users:
                    if u.username == username:
                        u.displayName = display_name
                        u.role = role
                        u.enabled = enabled
                        u.allowedStores = allowed_stores
                        u.storeTabPermissions = store_tab_perms
                        u.visibleTabs = self._collect_visible_tabs(store_tab_perms)
                        # 密码
                        new_pwd = self.password_edit.text()
                        if new_pwd.strip():
                            u.passwordHash = auth.hash_password(new_pwd)
                        break
            else:
                # 检查重复
                for u in user_list.users:
                    if u.username == username:
                        QMessageBox.warning(self, "提示", "用户名已存在")
                        return
                new_pwd = self.password_edit.text().strip()
                if not new_pwd:
                    QMessageBox.warning(self, "提示", "请输入密码")
                    return
                new_user = User(
                    username=username,
                    password_hash=auth.hash_password(new_pwd),
                    display_name=display_name,
                    role=role,
                    allowed_stores=allowed_stores,
                    visible_tabs=self._collect_visible_tabs(store_tab_perms),
                    store_tab_permissions=store_tab_perms,
                    enabled=enabled,
                )
                user_list.users.append(new_user)

            user_list.updatedAt = int(time.time() * 1000)
            if auth._push_users(user_list):
                QMessageBox.information(self, "成功", "用户已保存")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "同步到云端失败")
        except Exception as e:
            logger.error(f"AddEditUserDialog _save: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"保存失败: {e}")

    def _collect_visible_tabs(self, store_tab_perms):
        """从门店权限中汇总可见Tab（并集）"""
        visible = set()
        for tab_keys in store_tab_perms.values():
            visible.update(tab_keys)
        return list(visible)


# ========== 重置密码对话框 ==========

class ResetPasswordDialog(QDialog):
    """重置密码"""

    def __init__(self, username, parent=None):
        super().__init__(parent)
        self.username = username
        self.setWindowTitle("重置密码")
        self.setMinimumWidth(360)
        self.setStyleSheet(DLG_STYLE)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"重置用户「{username}」的密码"))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setStyleSheet(INPUT_STYLE)
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        form.addRow("新密码 *:", self.pwd_edit)

        self.pwd2_edit = QLineEdit()
        self.pwd2_edit.setStyleSheet(INPUT_STYLE)
        self.pwd2_edit.setEchoMode(QLineEdit.Password)
        form.addRow("确认密码 *:", self.pwd2_edit)

        layout.addLayout(form)

        btn_lay = QHBoxLayout()
        btn_save = QPushButton("确认")
        btn_save.setStyleSheet(BTN_SUCCESS)
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(BTN_DANGER)
        btn_cancel.clicked.connect(self.reject)
        btn_lay.addStretch()
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_cancel)
        layout.addLayout(btn_lay)

    def _save(self):
        pwd = self.pwd_edit.text().strip()
        pwd2 = self.pwd2_edit.text().strip()
        if not pwd:
            QMessageBox.warning(self, "提示", "请输入新密码")
            return
        if pwd != pwd2:
            QMessageBox.warning(self, "提示", "两次密码不一致")
            return

        auth = get_auth()
        try:
            user_list = auth._fetch_users()
            if user_list is None:
                QMessageBox.warning(self, "错误", "无法获取用户列表")
                return
            for u in user_list.users:
                if u.username == self.username:
                    u.passwordHash = auth.hash_password(pwd)
                    break
            user_list.updatedAt = int(time.time() * 1000)
            if auth._push_users(user_list):
                QMessageBox.information(self, "成功", "密码已重置")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "同步失败")
        except Exception as e:
            logger.error(f"ResetPasswordDialog _save: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"重置失败: {e}")


# ========== 用户管理Widget ==========

class UserManagementWidget(QWidget):
    """用户管理：用户列表 + 新增/编辑/删除/启用禁用/重置密码"""

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # 工具栏
        toolbar = QHBoxLayout()
        title = QLabel("用户管理")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: bold; color: {COLOR['text']};")
        toolbar.addWidget(title)
        toolbar.addStretch()

        btn_add = QPushButton("新增用户")
        btn_add.setStyleSheet(BTN_PRIMARY)
        btn_add.clicked.connect(self._add_user)
        toolbar.addWidget(btn_add)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(BTN_PRIMARY)
        btn_refresh.clicked.connect(self._load_users)
        toolbar.addWidget(btn_refresh)

        layout.addLayout(toolbar)

        # 表格
        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["用户名", "显示名", "角色", "门店数", "状态", "创建时间", "操作"])
        header = self.table.horizontalHeader()
        widths = [100, 100, 80, 60, 60, 120, 200]
        for i, w in enumerate(widths):
            header.resizeSection(i, w)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.table)
        # 不在 init 中加载，延迟到 load_data() 调用时
        self._loaded = False

    def _load_users(self):
        auth = get_auth()
        try:
            user_list = auth._fetch_users()
            if user_list is None:
                QMessageBox.warning(self, "提示", "无法获取用户列表，请检查网络")
                self.table.setRowCount(0)
                return

            self.table.setRowCount(len(user_list.users))
            for i, u in enumerate(user_list.users):
                role_name = ROLE_DISPLAY.get(u.role, u.role)
                store_count = len(u.allowedStores) if u.allowedStores else 0
                status = "启用" if u.enabled else "禁用"
                created = time.strftime("%Y-%m-%d %H:%M", time.localtime(u.createdAt / 1000)) if u.createdAt else ""

                vals = [u.username, u.displayName or "", role_name, str(store_count), status, created]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignCenter)
                    if j == 4:
                        item.setForeground(QColor(COLOR['success'] if u.enabled else COLOR['danger']))
                    self.table.setItem(i, j, item)

                # 操作按钮
                cell = QWidget()
                cl = QHBoxLayout(cell)
                cl.setContentsMargins(2, 2, 2, 2)

                btn_edit = QPushButton("编辑")
                btn_edit.setFixedWidth(42)
                btn_edit.setStyleSheet(TABLE_BTN_EDIT)
                btn_edit.clicked.connect(lambda _, uu=u: self._edit_user(uu))
                cl.addWidget(btn_edit)

                btn_pwd = QPushButton("重置密码")
                btn_pwd.setFixedWidth(68)
                btn_pwd.setStyleSheet(TABLE_BTN_EDIT)
                btn_pwd.clicked.connect(lambda _, un=u.username: self._reset_pwd(un))
                cl.addWidget(btn_pwd)

                if u.enabled:
                    btn_toggle = QPushButton("禁用")
                    btn_toggle.setFixedWidth(42)
                    btn_toggle.setStyleSheet(TABLE_BTN_DELETE)
                    btn_toggle.clicked.connect(lambda _, un=u.username: self._toggle_user(un, False))
                else:
                    btn_toggle = QPushButton("启用")
                    btn_toggle.setFixedWidth(42)
                    btn_toggle.setStyleSheet(TABLE_BTN_VIEW)
                    btn_toggle.clicked.connect(lambda _, un=u.username: self._toggle_user(un, True))
                cl.addWidget(btn_toggle)

                btn_del = QPushButton("删除")
                btn_del.setFixedWidth(42)
                btn_del.setStyleSheet(TABLE_BTN_DELETE)
                btn_del.clicked.connect(lambda _, un=u.username: self._delete_user(un))
                cl.addWidget(btn_del)

                self.table.setCellWidget(i, 6, cell)

        except Exception as e:
            logger.error(f"UserManagementWidget _load_users: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"加载失败: {e}")

    def _add_user(self):
        dlg = AddEditUserDialog(parent=self)
        if dlg.exec_():
            self._load_users()

    def _edit_user(self, user):
        dlg = AddEditUserDialog(user=user, parent=self)
        if dlg.exec_():
            self._load_users()

    def _reset_pwd(self, username):
        dlg = ResetPasswordDialog(username, self)
        dlg.exec_()

    def _toggle_user(self, username, enable):
        auth = get_auth()
        try:
            user_list = auth._fetch_users()
            if user_list is None:
                return
            for u in user_list.users:
                if u.username == username:
                    u.enabled = enable
                    break
            user_list.updatedAt = int(time.time() * 1000)
            auth._push_users(user_list)
            self._load_users()
        except Exception as e:
            logger.error(f"UserManagementWidget _toggle_user: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"操作失败: {e}")

    def _delete_user(self, username):
        ctx = _ctx()
        if ctx.current_username == username:
            QMessageBox.warning(self, "提示", "不能删除当前登录用户")
            return

        reply = QMessageBox.question(
            self, "确认删除", f"确认删除用户「{username}」？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        auth = get_auth()
        try:
            user_list = auth._fetch_users()
            if user_list is None:
                return
            user_list.users = [u for u in user_list.users if u.username != username]
            user_list.updatedAt = int(time.time() * 1000)
            auth._push_users(user_list)
            self._load_users()
            QMessageBox.information(self, "成功", "用户已删除")
        except Exception as e:
            logger.error(f"UserManagementWidget _delete_user: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"删除失败: {e}")


# ========== 门店授权查看Widget ==========

class StoreAuthWidget(QWidget):
    """门店授权查看（只读，编辑需到用户管理）"""

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        toolbar = QHBoxLayout()
        title = QLabel("门店授权")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: bold; color: {COLOR['text']};")
        toolbar.addWidget(title)
        toolbar.addStretch()

        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(BTN_PRIMARY)
        btn_refresh.clicked.connect(self._load)
        toolbar.addWidget(btn_refresh)

        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["门店", "授权用户", "角色", "功能权限"])
        header = self.table.horizontalHeader()
        widths = [120, 100, 80, 400]
        for i, w in enumerate(widths):
            header.resizeSection(i, w)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.table)
        # 不在 init 中加载，延迟到 load_data() 调用时
        self._loaded = False

    def _load(self):
        if not self._loaded:
            self._loaded = True
        auth = get_auth()
        conn = get_connection()
        user_list = auth._fetch_users()
        if user_list is None:
            self.table.setRowCount(0)
            return

        stores = conn.execute("SELECT id, name FROM stores ORDER BY id").fetchall()
        self.table.setRowCount(len(stores))

        for i, s in enumerate(stores):
            sid_str = str(s["id"])
            authorized = [u for u in user_list.users if sid_str in (u.allowedStores or [])]

            if authorized:
                names = ", ".join(u.displayName or u.username for u in authorized)
                roles = ", ".join(ROLE_DISPLAY.get(u.role, u.role) for u in authorized)
                perms_set = set()
                for u in authorized:
                    sp = u.storeTabPermissions or {}
                    for tab_keys in sp.get(sid_str, []):
                        perms_set.add(tab_keys)
                perm_names = ", ".join(
                    tab_name for tab_key, tab_name in TAB_PERMISSIONS if tab_key in perms_set
                )
            else:
                names = "（无）"
                roles = "—"
                perm_names = "—"

            vals = [s["name"], names, roles, perm_names]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignCenter if j < 3 else Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(i, j, item)

        conn.close()
class EmployeeAuthDialog(QDialog):
    """员工授权设置：系统角色 / 职位 / 所属门店 / 功能权限"""

    def __init__(self, employee_id, parent=None):
        super().__init__(parent)
        self.employee_id = employee_id
        self.setWindowTitle("员工授权")
        self.setMinimumWidth(480)
        self.setStyleSheet(DLG_STYLE)

        self._perm_checks = {}

        layout = QVBoxLayout(self)
        title = QLabel("员工授权设置")
        title.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: bold; color: {COLOR['primary']};")
        layout.addWidget(title)

        conn = get_connection()
        emp_info = None
        try:
            emp_info = conn.execute(
                "SELECT name, position, role, store_id, permissions FROM employees WHERE id=?",
                (employee_id,)
            ).fetchone()
        finally:
            conn.close()

        if emp_info:
            info = QLabel(f"员工: {emp_info['name']}  |  岗位: {emp_info['position'] or '未设置'}")
            info.setStyleSheet(f"color: {COLOR['text_secondary']}; padding: 4px 0;")
            layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.role_combo = QComboBox()
        self.role_combo.setStyleSheet(COMBO_STYLE)
        for role_key, role_name in PRESET_ROLES:
            self.role_combo.addItem(role_name, role_key)
        if emp_info:
            idx = self.role_combo.findData(emp_info["role"] or ROLE_EMPLOYEE)
            if idx >= 0:
                self.role_combo.setCurrentIndex(idx)
        form.addRow("系统角色:", self.role_combo)

        self.store_combo = QComboBox()
        self.store_combo.setStyleSheet(COMBO_STYLE)
        conn = get_connection()
        stores = conn.execute("SELECT id, name FROM stores ORDER BY id").fetchall()
        for s in stores:
            self.store_combo.addItem(s["name"], s["id"])
        idx = -1
        if emp_info and emp_info["store_id"]:
            idx = self.store_combo.findData(emp_info["store_id"])
            if idx >= 0:
                self.store_combo.setCurrentIndex(idx)
        conn.close()
        form.addRow("所属门店:", self.store_combo)

        layout.addLayout(form)

        # 功能权限
        perm_group = QGroupBox("功能权限")
        perm_lay = QGridLayout(perm_group)
        for col, (tab_key, tab_name) in enumerate(TAB_PERMISSIONS):
            cb = QCheckBox(tab_name)
            self._perm_checks[tab_key] = cb
            row = col // 3
            c = col % 3
            perm_lay.addWidget(cb, row, c)

        # 加载已有权限
        if emp_info:
            perms_str = emp_info["permissions"] or ""
            if perms_str:
                try:
                    perms = json.loads(perms_str) if perms_str.startswith("[") else perms_str.split(",")
                    for p in perms:
                        p = p.strip()
                        if p in self._perm_checks:
                            self._perm_checks[p].setChecked(True)
                except (json.JSONDecodeError, TypeError):
                    pass

        layout.addWidget(perm_group)

        # 快捷按钮
        quick_row = QHBoxLayout()
        btn_all = QPushButton("全选")
        btn_all.setStyleSheet(BTN_PRIMARY)
        btn_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self._perm_checks.values()])
        btn_none = QPushButton("全不选")
        btn_none.setStyleSheet(BTN_DANGER)
        btn_none.clicked.connect(lambda: [cb.setChecked(False) for cb in self._perm_checks.values()])
        quick_row.addWidget(btn_all)
        quick_row.addWidget(btn_none)
        quick_row.addStretch()
        layout.addLayout(quick_row)

        # 保存/取消
        btn_lay = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(BTN_SUCCESS)
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(BTN_DANGER)
        btn_cancel.clicked.connect(self.reject)
        btn_lay.addStretch()
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_cancel)
        layout.addLayout(btn_lay)

    def _save(self):
        role = self.role_combo.currentData()
        store_id = self.store_combo.currentData()
        perms = [k for k, cb in self._perm_checks.items() if cb.isChecked()]
        perms_json = json.dumps(perms, ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE employees SET role=?, store_id=?, permissions=? WHERE id=?",
                (role, store_id, perms_json, self.employee_id)
            )
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", "员工授权已保存")
            self.accept()
        except Exception as e:
            logger.error(f"EmployeeAuthDialog _save: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"保存失败: {e}")


# ========== 员工授权Widget ==========

class EmployeeAuthWidget(QWidget):
    """员工授权：本地员工角色 / 权限列表"""

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        toolbar = QHBoxLayout()
        title = QLabel("员工授权")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: bold; color: {COLOR['text']};")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setStyleSheet(INPUT_STYLE)
        self.search_edit.setPlaceholderText("搜索员工姓名...")
        self.search_edit.setFixedWidth(200)
        self.search_edit.textChanged.connect(self._load)
        toolbar.addWidget(self.search_edit)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(BTN_PRIMARY)
        btn_refresh.clicked.connect(self._load)
        toolbar.addWidget(btn_refresh)

        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["员工", "岗位", "系统角色", "所属门店", "功能权限", "操作"])
        header = self.table.horizontalHeader()
        widths = [80, 70, 80, 100, 300, 80]
        for i, w in enumerate(widths):
            header.resizeSection(i, w)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.table)
        # 不在 init 中加载，延迟到 load_data() 调用时
        self._loaded = False
    def _load(self):
        if not self._loaded:
            self._loaded = True
        keyword = self.search_edit.text().strip()
        conn = get_connection()
        try:
            if keyword:
                rows = conn.execute(
                    """SELECT e.id, e.name, e.position, e.role, e.permissions,
                       s.name as store_name
               FROM employees e LEFT JOIN stores s ON e.store_id = s.id
               WHERE e.name LIKE ? ORDER BY e.name""",
                    (f"%{keyword}%",)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT e.id, e.name, e.position, e.role, e.permissions,
                       s.name as store_name
               FROM employees e LEFT JOIN stores s ON e.store_id = s.id
               ORDER BY e.name"""
                ).fetchall()

            self.table.setRowCount(len(rows))
            for i, r in enumerate(rows):
                d = dict(r)
                role_name = ROLE_DISPLAY.get(d.get("role", ""), d.get("role", "") or "员工")
                perms_str = d.get("permissions", "") or ""
                perm_names = ""
                if perms_str:
                    try:
                        perms = json.loads(perms_str) if perms_str.startswith("[") else perms_str.split(",")
                        perm_names = ", ".join(
                            tab_name for tab_key, tab_name in TAB_PERMISSIONS
                            if tab_key.strip() in [p.strip() for p in perms]
                        )
                    except (json.JSONDecodeError, TypeError):
                        pass

                vals = [
                    d.get("name", ""),
                    d.get("position", "") or "",
                    role_name,
                    d.get("store_name", "") or "未分配",
                    perm_names or "—",
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignCenter if j < 4 else Qt.AlignLeft | Qt.AlignVCenter)
                    self.table.setItem(i, j, item)

                btn = QPushButton("授权")
                btn.setFixedWidth(56)
                btn.setStyleSheet(TABLE_BTN_EDIT)
                btn.clicked.connect(lambda _, eid=d["id"]: self._edit_auth(eid))
                self.table.setCellWidget(i, 5, btn)
        except Exception as e:
            logger.error(f"EmployeeAuthWidget _load: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"加载失败: {e}")
        conn.close()
        conn.close()

    def _edit_auth(self, emp_id):
        dlg = EmployeeAuthDialog(emp_id, self)
        if dlg.exec_():
            self._load()


# ========== 授权管理主界面 ==========

class AuthorizationWidget(QWidget):
    """授权管理主界面：3个Tab"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabBar::tab {{
                background: {COLOR['bg_card']};
                color: {COLOR['text_secondary']};
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: {RADIUS['sm']}px;
                border-top-right-radius: {RADIUS['sm']}px;
                font-size: {FONT_SIZE['md']}px;
            }}
            QTabBar::tab:selected {{
                background: {COLOR['primary']};
                color: white;
            }}
        """)

        self._user_tab = UserManagementWidget()
        self._store_tab = StoreAuthWidget()
        self._emp_tab = EmployeeAuthWidget()

        tabs.addTab(self._user_tab, "用户管理")
        tabs.addTab(self._store_tab, "门店授权")
        tabs.addTab(self._emp_tab, "员工授权")

        layout.addWidget(tabs)

    def load_data(self):
        """统一刷新入口（导航切换时调用）"""
        try:
            self._user_tab._load_users()
        except Exception:
            pass
        try:
            self._store_tab._load()
        except Exception:
            pass
        try:
            self._emp_tab._load()
        except Exception:
            pass
