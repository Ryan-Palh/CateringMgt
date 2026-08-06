# -*- coding: utf-8 -*-
"""
营业额配置管理 v5.0 —— 渠道列表 + 融合管理对话框（套餐/类型）
餐饮专业化：堂食、外卖平台、团购渠道等营收渠道配置
"""
import os
import sys
import logging

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QLineEdit, QMessageBox, QInputDialog,
                             QWidget, QComboBox, QFormLayout, QDialogButtonBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon

from database.db_manager import get_connection, _safe_sql_identifier
from gui.theme import (COLOR, COMPACT_TABLE_STYLE, DLG_STYLE,
                       primary_btn, success_btn, make_table_button,
                       INPUT_STYLE, COMBO_STYLE)
from utils.app_context import get_app_context as _ctx
from utils.nutstore_sync import get_sync

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)




def _sync_cloud():
    try:
        get_sync().trigger_sync()
    except Exception as e:
        _logger.debug(f"云同步失败: {e}")


def _migrate_channel_name_columns():
    """旧库兼容：为 revenue_packages / revenue_package_types 补 channel_name 列"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        for table in ("revenue_packages", "revenue_package_types"):
            try:
                cursor.execute(f"PRAGMA table_info({_safe_sql_identifier(table)})")
                cols = {row[1] for row in cursor.fetchall()}
                if "channel_name" not in cols:
                    cursor.execute(
                        f"ALTER TABLE {_safe_sql_identifier(table)} ADD COLUMN channel_name TEXT DEFAULT ''")
                    conn.commit()
                    _sync_cloud()
            except Exception as e:
                _logger.debug(f"迁移 {table}.channel_name 失败: {e}")
    finally:
        conn.close()


def create_revenue_config_tables():
    """确保营收配置表存在（db_manager 已建，此处仅做兼容迁移）"""
    _migrate_channel_name_columns()


# ═══════════════════════════════════════════════════════════
# 融合管理对话框：套餐（表格）+ 类型（下拉）
# ═══════════════════════════════════════════════════════════
class ChannelManageDialog(QDialog):
    """管理指定渠道下的套餐和类型"""

    def __init__(self, parent=None, channel_name=""):
        super().__init__(parent)
        self.channel_name = channel_name
        self.setWindowTitle(f"{channel_name} · 套餐/类型管理")
        self.resize(520, 420)
        self.setMinimumSize(420, 320)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()
        self._load_packages()
        self._load_type_combo()

    def _build_ui(self):
        main = QVBoxLayout()
        main.setContentsMargins(16, 12, 16, 12)
        main.setSpacing(10)

        # 提示
        hint = QLabel(f"渠道：<b>{self.channel_name}</b> · 在此管理该渠道下的套餐及类型")
        hint.setStyleSheet(f"color: {COLOR['text_secondary']}; font-size: 12px; padding: 2px 0;")
        main.addWidget(hint)

        # 套餐输入行：套餐名 + 类型下拉 + 添加按钮
        pkg_row = QHBoxLayout()
        pkg_row.setSpacing(6)
        self.edit_pkg_name = QLineEdit()
        self.edit_pkg_name.setPlaceholderText("套餐名称")
        self.edit_pkg_name.setStyleSheet(INPUT_STYLE)
        self.edit_pkg_name.returnPressed.connect(self._add_package)
        pkg_row.addWidget(self.edit_pkg_name, 3)

        self.cmb_pkg_type = QComboBox()
        self.cmb_pkg_type.setEditable(True)
        self.cmb_pkg_type.lineEdit().setPlaceholderText("类型")
        self.cmb_pkg_type.setFixedWidth(130)
        self.cmb_pkg_type.activated.connect(self._on_type_activated)
        # 光标置左
        self.cmb_pkg_type.currentTextChanged.connect(
            lambda t: QTimer.singleShot(0, lambda: self.cmb_pkg_type.lineEdit().setCursorPosition(0)))
        self.cmb_pkg_type.setStyleSheet(
            COMBO_STYLE + "QComboBox QLineEdit { border: none; background: transparent; }")
        pkg_row.addWidget(self.cmb_pkg_type)

        btn_pkg = QPushButton("添加套餐")
        btn_pkg.setStyleSheet(primary_btn)
        btn_pkg.clicked.connect(self._add_package)
        pkg_row.addWidget(btn_pkg)
        main.addLayout(pkg_row)

        # 套餐表格
        self.pkg_table = QTableWidget()
        self.pkg_table.setColumnCount(4)
        self.pkg_table.setHorizontalHeaderLabels(["序号", "套餐名称", "类型", "操作"])
        self.pkg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.pkg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.pkg_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.pkg_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.pkg_table.setColumnWidth(0, 50)
        self.pkg_table.setColumnWidth(2, 100)
        self.pkg_table.setColumnWidth(3, 120)
        self.pkg_table.setStyleSheet(COMPACT_TABLE_STYLE)
        self.pkg_table.verticalHeader().setVisible(False)
        self.pkg_table.verticalHeader().setDefaultSectionSize(44)
        self.pkg_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.pkg_table.setSelectionBehavior(QTableWidget.SelectRows)
        main.addWidget(self.pkg_table)

        self.setLayout(main)

    # ── 类型操作 ──
    def _on_type_activated(self, index):
        """选中「＋ 添加类型」时弹出输入框"""
        if self.cmb_pkg_type.currentText() == "＋ 添加类型":
            new_type, ok = QInputDialog.getText(self, "添加类型", "请输入新类型名称：")
            if ok and new_type.strip():
                pkg_type = new_type.strip()
                _sid, _ = _ctx().get_store_filter()
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM revenue_package_types "
                    "WHERE type_name=? AND channel_name=? AND (store_id=? OR store_id IS NULL)",
                    (pkg_type, self.channel_name, _sid))
                if cursor.fetchone():
                    QMessageBox.information(self, "提示", f"类型「{pkg_type}」已存在")
                else:
                    cursor.execute(
                        "INSERT INTO revenue_package_types "
                        "(type_name, channel_name, store_id) VALUES (?,?,?)",
                        (pkg_type, self.channel_name, _sid))
                    conn.commit()
                    conn.close()
                    _sync_cloud()
                    QMessageBox.information(self, "成功", f"类型「{pkg_type}」已添加")
                self._load_type_combo()
                self.cmb_pkg_type.setCurrentText(pkg_type)
            else:
                self.cmb_pkg_type.setCurrentIndex(-1)

    # ── 套餐操作 ──
    def _add_package(self):
        name = self.edit_pkg_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入套餐名称")
            return
        pkg_type = self.cmb_pkg_type.currentText().strip()
        if pkg_type == "＋ 添加类型":
            pkg_type = ""
        _sid, _ = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        # 如果是新类型，同步持久化
        if pkg_type:
            cursor.execute(
                "SELECT id FROM revenue_package_types "
                "WHERE type_name=? AND channel_name=? AND (store_id=? OR store_id IS NULL)",
                (pkg_type, self.channel_name, _sid))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO revenue_package_types "
                    "(type_name, channel_name, store_id) VALUES (?,?,?)",
                    (pkg_type, self.channel_name, _sid))
        cursor.execute(
            "INSERT INTO revenue_packages "
            "(package_name, channel_name, type_name, store_id) VALUES (?,?,?,?)",
            (name, self.channel_name, pkg_type, _sid))
        conn.commit()
        _sync_cloud()
        self.edit_pkg_name.clear()
        self._load_packages()
        self._load_type_combo()

    def _load_packages(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute(
                "SELECT id, package_name, type_name FROM revenue_packages "
                "WHERE channel_name=? ORDER BY id",
                (self.channel_name,))
        else:
            cursor.execute(
                "SELECT id, package_name, type_name FROM revenue_packages "
                "WHERE channel_name=? AND (store_id=? OR store_id IS NULL) ORDER BY id",
                (self.channel_name, _sid))
        rows = cursor.fetchall()
        conn.close()

        self.pkg_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.pkg_table.setItem(i, 0, sn)
            _ci1 = QTableWidgetItem(r["package_name"])
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.pkg_table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(r["type_name"] if r["type_name"] else "")
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.pkg_table.setItem(i, 2, _ci2)

            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            rid = r["id"]
            pkg_name = r["package_name"]
            pkg_type = r["type_name"] if r["type_name"] else ""
            btn_edit.clicked.connect(
                lambda checked, rid=rid, pn=pkg_name, pt=pkg_type: self._edit_pkg(rid, pn, pt))
            btn_del.clicked.connect(lambda checked, rid=rid: self._del_pkg(rid))

            wrapper = QWidget()
            wrapper.setStyleSheet("background: transparent; border: none;")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(4)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_edit)
            wl.addWidget(btn_del)
            self.pkg_table.setCellWidget(i, 3, wrapper)

    def _load_type_combo(self):
        """从数据库加载类型到下拉框"""
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute(
                "SELECT DISTINCT type_name FROM revenue_package_types "
                "WHERE type_name != '' AND channel_name=? ORDER BY id",
                (self.channel_name,))
        else:
            cursor.execute(
                "SELECT DISTINCT type_name FROM revenue_package_types "
                "WHERE type_name != '' AND channel_name=? "
                "AND (store_id=? OR store_id IS NULL) ORDER BY id",
                (self.channel_name, _sid))
        rows = cursor.fetchall()
        conn.close()

        cur = self.cmb_pkg_type.currentText()
        self.cmb_pkg_type.blockSignals(True)
        self.cmb_pkg_type.clear()
        for r in rows:
            self.cmb_pkg_type.addItem(r["type_name"])
        self.cmb_pkg_type.insertSeparator(self.cmb_pkg_type.count())
        self.cmb_pkg_type.addItem("＋ 添加类型")
        if cur and cur != "＋ 添加类型":
            self.cmb_pkg_type.setCurrentText(cur)
        self.cmb_pkg_type.blockSignals(False)

    def _edit_pkg(self, rid, old_name, old_type):
        """编辑套餐名称和类型"""
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑套餐")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet(DLG_STYLE)
        layout = QFormLayout(dlg)

        edit_name = QLineEdit(old_name)
        edit_name.setStyleSheet(INPUT_STYLE)

        edit_type = QComboBox()
        edit_type.setEditable(True)
        edit_type.lineEdit().setPlaceholderText("类型")
        # 加载已有类型
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute(
                "SELECT DISTINCT type_name FROM revenue_package_types "
                "WHERE type_name != '' AND channel_name=? ORDER BY id",
                (self.channel_name,))
        else:
            cursor.execute(
                "SELECT DISTINCT type_name FROM revenue_package_types "
                "WHERE type_name != '' AND channel_name=? "
                "AND (store_id=? OR store_id IS NULL) ORDER BY id",
                (self.channel_name, _sid))
        for r in cursor.fetchall():
            edit_type.addItem(r["type_name"])
        conn.close()
        edit_type.insertSeparator(edit_type.count())
        edit_type.addItem("＋ 添加类型")
        if old_type:
            idx = edit_type.findText(old_type)
            if idx >= 0:
                edit_type.setCurrentIndex(idx)
            else:
                edit_type.setCurrentText(old_type)
        edit_type.setStyleSheet(
            COMBO_STYLE + "QComboBox QLineEdit { border: none; background: transparent; }")

        layout.addRow("套餐名：", edit_name)
        layout.addRow("类型：", edit_type)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setStyleSheet(primary_btn)
        btns.button(QDialogButtonBox.Cancel).setStyleSheet(success_btn)
        layout.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        if dlg.exec_() != QDialog.Accepted:
            return
        new_name = edit_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "提示", "套餐名不能为空")
            return
        new_type = edit_type.currentText().strip()
        if new_type == "＋ 添加类型":
            new_type = ""

        _sid, _ = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        if new_type:
            cursor.execute(
                "SELECT id FROM revenue_package_types "
                "WHERE type_name=? AND channel_name=? AND (store_id=? OR store_id IS NULL)",
                (new_type, self.channel_name, _sid))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO revenue_package_types "
                    "(type_name, channel_name, store_id) VALUES (?,?,?)",
                    (new_type, self.channel_name, _sid))
        cursor.execute(
            "UPDATE revenue_packages SET package_name=?, type_name=? WHERE id=?",
            (new_name, new_type, rid))
        conn.commit()
        conn.close()
        self._load_packages()
        self._load_type_combo()
        _sync_cloud()

    def _del_pkg(self, rid):
        reply = QMessageBox.question(self, "确认", "确定删除该套餐吗？")
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM revenue_packages WHERE id=?", (rid,))
        conn.commit()
        conn.close()
        self._load_packages()
        _sync_cloud()


# ═══════════════════════════════════════════════════════════
# 主配置对话框：渠道列表
# ═══════════════════════════════════════════════════════════
class RevenueConfigDialog(QDialog):
    """营业额渠道配置对话框"""

    def __init__(self, parent=None):
        try:
            super().__init__(parent)
            _migrate_channel_name_columns()
            self._set_window_icon()
            self.setWindowTitle("营业额配置")
            self.resize(600, 460)
            self.setMinimumSize(480, 380)
            self.setStyleSheet(DLG_STYLE)
            self._build_ui()
            self._load_channels()
        except Exception as e:
            import traceback as _tb
            _log_dir = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                        else os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(_log_dir, "crash_config.log")
            with open(log_path, "w", encoding="utf-8") as f:
                _tb.print_exc(file=f)
            QMessageBox.critical(parent, "配置错误",
                                 f"初始化配置窗口失败：\n{e}\n\n详细日志：{log_path}")
            raise

    def _set_window_icon(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "app_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(
                getattr(sys, "_MEIPASS",
                        os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                        else "."),
                "assets", "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # 标题
        title = QLabel("营收渠道配置")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {COLOR['primary']}; padding: 2px 0;")
        layout.addWidget(title)

        # 添加渠道行
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("渠道名称："))
        self.edit_channel = QLineEdit()
        self.edit_channel.setPlaceholderText("输入渠道名称，回车添加")
        self.edit_channel.setStyleSheet(INPUT_STYLE)
        self.edit_channel.returnPressed.connect(self._add_channel)
        row.addWidget(self.edit_channel)
        btn_add = QPushButton("添加渠道")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_channel)
        row.addWidget(btn_add)
        layout.addLayout(row)

        # 渠道列表表格
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["渠道名称", "套餐/类型管理", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(2, 130)
        self.table.setStyleSheet(COMPACT_TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # 关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet(success_btn)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self.setLayout(layout)

    def _add_channel(self):
        name = self.edit_channel.text().strip()
        if not name:
            return
        _sid, _ = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO revenue_channels (channel_name, store_id) VALUES (?,?)",
                (name, _sid))
            conn.commit()
            _sync_cloud()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"添加失败：{e}")
        finally:
                conn.close()
        self.edit_channel.clear()
        self._load_channels()
        try:
            from utils.channel_sync import upload_channels
            upload_channels(get_connection())
        except Exception:
            pass

    def _load_channels(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT id, channel_name FROM revenue_channels ORDER BY sort_order, id")
        else:
            cursor.execute(
                "SELECT id, channel_name FROM revenue_channels "
                "WHERE store_id=? OR store_id IS NULL ORDER BY sort_order, id",
                (_sid,))
        rows = cursor.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            ch_name = r["channel_name"]
            ch_item = QTableWidgetItem(ch_name)
            ch_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, ch_item)

            # 套餐/类型管理按钮
            btn_mgr = QPushButton("管理套餐/类型")
            btn_mgr.setStyleSheet(
                f"background:{COLOR['primary_light']}; color:{COLOR['primary']}; "
                f"border:none; border-radius:4px; padding:4px 14px; "
                f"font-size:12px; font-weight:500;")
            btn_mgr.setCursor(Qt.PointingHandCursor)
            btn_mgr.clicked.connect(
                lambda checked, ch=ch_name: ChannelManageDialog(self, ch).exec_())
            mgr_wrapper = QWidget()
            mgr_wrapper.setStyleSheet("background: transparent; border: none;")
            mgr_wl = QHBoxLayout(mgr_wrapper)
            mgr_wl.setContentsMargins(0, 0, 0, 0)
            mgr_wl.setAlignment(Qt.AlignCenter)
            mgr_wl.addWidget(btn_mgr)
            self.table.setCellWidget(i, 1, mgr_wrapper)

            # 编辑/删除按钮
            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            rid = r["id"]
            btn_edit.clicked.connect(lambda checked, ch=ch_name: self._edit_channel(ch))
            btn_del.clicked.connect(lambda checked, rid=rid: self._del_channel(rid))
            wrapper = QWidget()
            wrapper.setStyleSheet("background: transparent; border: none;")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(4)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_edit)
            wl.addWidget(btn_del)
            self.table.setCellWidget(i, 2, wrapper)

    def _edit_channel(self, old_name):
        new_name, ok = QInputDialog.getText(self, "编辑渠道", "渠道名称：", text=old_name)
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name == old_name:
                return
            _sid, _all = _ctx().get_store_filter()
            conn = get_connection()
            cursor = conn.cursor()
            try:
                if _all:
                    cursor.execute("UPDATE revenue_channels SET channel_name=? WHERE channel_name=?",
                                   (new_name, old_name))
                    cursor.execute("UPDATE revenue_packages SET channel_name=? WHERE channel_name=?",
                                   (new_name, old_name))
                    cursor.execute("UPDATE revenue_package_types SET channel_name=? WHERE channel_name=?",
                                   (new_name, old_name))
                else:
                    cursor.execute(
                        "UPDATE revenue_channels SET channel_name=? "
                        "WHERE channel_name=? AND (store_id=? OR store_id IS NULL)",
                        (new_name, old_name, _sid))
                    cursor.execute(
                        "UPDATE revenue_packages SET channel_name=? "
                        "WHERE channel_name=? AND (store_id=? OR store_id IS NULL)",
                        (new_name, old_name, _sid))
                    cursor.execute(
                        "UPDATE revenue_package_types SET channel_name=? "
                        "WHERE channel_name=? AND (store_id=? OR store_id IS NULL)",
                        (new_name, old_name, _sid))
                conn.commit()
                _sync_cloud()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"修改失败：{e}")
            finally:
                conn.close()
            self._load_channels()
        try:
            from utils.channel_sync import upload_channels
            upload_channels(get_connection())
        except Exception:
            pass

    def _del_channel(self, rid):
        reply = QMessageBox.question(
            self, "确认",
            "确定删除该渠道吗？\n该渠道下的所有套餐和类型也将一并删除。")
        if reply != QMessageBox.Yes:
            return
        _sid, _all = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        # 先查出渠道名称，用于级联删除
        if _all:
            cursor.execute("SELECT channel_name FROM revenue_channels WHERE id=?", (rid,))
        else:
            cursor.execute(
                "SELECT channel_name FROM revenue_channels "
                "WHERE id=? AND (store_id=? OR store_id IS NULL)",
                (rid, _sid))
        row = cursor.fetchone()
        if row:
            ch_name = row["channel_name"]
            if _all:
                cursor.execute("DELETE FROM revenue_packages WHERE channel_name=?", (ch_name,))
                cursor.execute("DELETE FROM revenue_package_types WHERE channel_name=?", (ch_name,))
            else:
                cursor.execute(
                    "DELETE FROM revenue_packages "
                    "WHERE channel_name=? AND (store_id=? OR store_id IS NULL)",
                    (ch_name, _sid))
                cursor.execute(
                    "DELETE FROM revenue_package_types "
                    "WHERE channel_name=? AND (store_id=? OR store_id IS NULL)",
                    (ch_name, _sid))
        cursor.execute("DELETE FROM revenue_channels WHERE id=?", (rid,))
        conn.commit()
        try:
            from utils.channel_sync import upload_channels
            upload_channels(get_connection())
        except Exception:
            pass
        conn.close()
        self._load_channels()
        _sync_cloud()
