# -*- coding: utf-8 -*-
"""
登录对话框 v4.0 —— 现代化重构
优化点：
- 全新视觉设计：渐变品牌区 + 精致表单卡片
- 密码显示/隐藏切换
- 优化错误提示样式
- 修复 OutlinedLineEdit 标签定位bug
- 增加输入框前置图标
- 登录按钮加载状态优化
- 记住密码逻辑修复（仅记住账号，不自动填充密码）
"""
import threading

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QMessageBox, QFrame,
                             QCheckBox, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, QEvent, QObject, pyqtSignal
from PyQt5.QtGui import QFont, QFontMetrics, QIcon, QPixmap
import os, sys

from database.db_manager import get_connection
from utils.auth_manager import get_auth
from utils.logger import logger
from gui.theme import COLOR, RADIUS, FONT_SIZE

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")

# ═══════════════════════════════════════════
# 复用样式常量
# ═══════════════════════════════════════════

_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {COLOR['primary']};
        color: {COLOR['text_white']};
        border: none;
        border-radius: {RADIUS['md']}px;
        font-size: {FONT_SIZE['lg']}px;
        font-weight: 600;
        padding: 12px;
    }}
    QPushButton:hover {{
        background-color: {COLOR['primary_hover']};
    }}
    QPushButton:pressed {{
        background-color: {COLOR['primary_pressed']};
    }}
    QPushButton:disabled {{
        background-color: {COLOR['border_dark']};
        color: {COLOR['text_muted']};
    }}
"""

_BTN_LINK = f"""
    QPushButton {{
        color: {COLOR['primary']};
        font-size: {FONT_SIZE['sm']}px;
        border: none;
        background: transparent;
        padding: 4px 0;
    }}
    QPushButton:hover {{
        color: {COLOR['primary_hover']};
        text-decoration: underline;
    }}
"""

_INPUT_LABEL_STYLE = f"font-size: {FONT_SIZE['sm']}px; color: {COLOR['text_secondary']}; margin-bottom: 6px; font-weight: 500;"


# ═══════════════════════════════════════════
# 自定义组件：带图标的输入框
# ═══════════════════════════════════════════

class IconLineEdit(QFrame):
    """带前置图标的输入框组件
    支持：前置图标、密码显隐切换、聚焦高亮、错误状态
    """
    def __init__(self, placeholder="", icon_text="", is_password=False, parent=None):
        super().__init__(parent)
        self._icon_text = icon_text
        self._is_password = is_password
        self._show_password = False
        self._has_error = False
        self.setFixedHeight(48)
        self.setStyleSheet("background: transparent;")

        # 背景边框
        self._border_frame = QFrame(self)
        self._border_frame.setObjectName("inputBorder")
        self._update_border_style()

        # 内部布局
        inner_layout = QHBoxLayout(self._border_frame)
        inner_layout.setContentsMargins(14, 0, 8, 0)
        inner_layout.setSpacing(8)

        # 前置图标
        if icon_text:
            self._icon_label = QLabel(icon_text)
            self._icon_label.setStyleSheet(f"""
                font-size: 16px;
                color: {COLOR['text_muted']};
                background: transparent;
            """)
            inner_layout.addWidget(self._icon_label)

        # 输入框
        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        if is_password:
            self.input.setEchoMode(QLineEdit.Password)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                background: transparent;
                font-size: {FONT_SIZE['base']}px;
                color: {COLOR['text_primary']};
                padding: 0;
            }}
            QLineEdit:focus {{
                border: none;
                background: transparent;
            }}
        """)
        self.input.installEventFilter(self)
        inner_layout.addWidget(self.input, 1)

        # 密码显隐按钮
        if is_password:
            self._toggle_btn = QPushButton("👁")
            self._toggle_btn.setFixedSize(28, 28)
            self._toggle_btn.setCursor(Qt.PointingHandCursor)
            self._toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    font-size: 14px;
                    color: {COLOR['text_muted']};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: {COLOR['bg_hover']};
                    color: {COLOR['text_secondary']};
                }}
            """)
            self._toggle_btn.clicked.connect(self._toggle_password)
            inner_layout.addWidget(self._toggle_btn)

    def _update_border_style(self):
        if self._has_error:
            border_color = COLOR['danger']
            bg_color = COLOR['danger_light']
        else:
            border_color = COLOR['border']
            bg_color = COLOR['bg_card']
        self._border_frame.setStyleSheet(f"""
            QFrame#inputBorder {{
                background-color: {bg_color};
                border: 1.5px solid {border_color};
                border-radius: {RADIUS['md']}px;
            }}
        """)

    def _toggle_password(self):
        self._show_password = not self._show_password
        if self._show_password:
            self.input.setEchoMode(QLineEdit.Normal)
            self._toggle_btn.setText("🙈")
        else:
            self.input.setEchoMode(QLineEdit.Password)
            self._toggle_btn.setText("👁")

    def set_error(self, has_error):
        """设置错误状态"""
        self._has_error = has_error
        self._update_border_style()

    def text(self):
        return self.input.text()

    def setText(self, text):
        self.input.setText(text)

    def setFocus(self):
        self.input.setFocus()

    def eventFilter(self, obj, event):
        if obj == self.input:
            if event.type() == QEvent.FocusIn:
                if not self._has_error:
                    self._border_frame.setStyleSheet(f"""
                        QFrame#inputBorder {{
                            background-color: {COLOR['bg_card']};
                            border: 2px solid {COLOR['primary']};
                            border-radius: {RADIUS['md']}px;
                        }}
                    """)
                    if self._icon_text and hasattr(self, '_icon_label'):
                        self._icon_label.setStyleSheet(f"""
                            font-size: 16px;
                            color: {COLOR['primary']};
                            background: transparent;
                        """)
            elif event.type() == QEvent.FocusOut:
                self._update_border_style()
                if self._icon_text and hasattr(self, '_icon_label'):
                    self._icon_label.setStyleSheet(f"""
                        font-size: 16px;
                        color: {COLOR['text_muted']};
                        background: transparent;
                    """)
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._border_frame.setGeometry(0, 0, self.width(), self.height())


# ═══════════════════════════════════════════
# 注册对话框
# ═══════════════════════════════════════════

class RegisterDialog(QDialog):
    """注册对话框 v4.0"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered_username = None
        self._result = {}
        self._poll_timer = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("注册新账号")
        self.resize(460, 580)
        self.setStyleSheet(f"QDialog {{ background-color: {COLOR['bg_card']}; }}")

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 36, 40, 28)
        layout.setSpacing(0)

        # 标题
        title = QLabel("注册新账号")
        title.setStyleSheet(f"font-size: {FONT_SIZE['3xl']}px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        subtitle = QLabel("创建您的管理账号，开启智能餐饮管理")
        subtitle.setStyleSheet(f"font-size: {FONT_SIZE['sm']}px; color: {COLOR['text_muted']}; margin-top: 6px; margin-bottom: 32px;")
        layout.addWidget(subtitle)

        # 账号
        lbl_u = QLabel("账号")
        lbl_u.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_u)
        self.txt_user_widget = IconLineEdit("请输入登录账号", "👤")
        self.txt_username = self.txt_user_widget.input
        layout.addWidget(self.txt_user_widget)
        layout.addSpacing(18)

        # 姓名
        lbl_n = QLabel("姓名（选填）")
        lbl_n.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_n)
        self.txt_display_widget = IconLineEdit("请输入显示名称", "📝")
        self.txt_display = self.txt_display_widget.input
        layout.addWidget(self.txt_display_widget)
        layout.addSpacing(18)

        # 密码
        lbl_p = QLabel("密码")
        lbl_p.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_p)
        self.txt_pwd_widget = IconLineEdit("请输入密码（至少6位）", "🔒", is_password=True)
        self.txt_password = self.txt_pwd_widget.input
        layout.addWidget(self.txt_pwd_widget)
        layout.addSpacing(18)

        # 确认密码
        lbl_cp = QLabel("确认密码")
        lbl_cp.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_cp)
        self.txt_confirm_widget = IconLineEdit("请再次输入密码", "🔒", is_password=True)
        self.txt_confirm = self.txt_confirm_widget.input
        layout.addWidget(self.txt_confirm_widget)

        # 错误提示
        layout.addSpacing(16)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"""
            color: {COLOR['danger']};
            font-size: {FONT_SIZE['sm']}px;
            background: {COLOR['danger_light']};
            padding: 8px 12px;
            border-radius: {RADIUS['sm']}px;
        """)
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        # 注册按钮
        layout.addSpacing(20)
        self.btn_register = QPushButton("注  册")
        self.btn_register.setFixedHeight(46)
        self.btn_register.setCursor(Qt.PointingHandCursor)
        self.btn_register.setStyleSheet(_BTN_PRIMARY)
        self.btn_register.clicked.connect(self.do_register)
        layout.addWidget(self.btn_register)

        layout.addStretch()
        self.setLayout(layout)

    def do_register(self):
        username = self.txt_username.text().strip()
        display_name = self.txt_display.text().strip()
        password = self.txt_password.text()
        confirm = self.txt_confirm.text()

        # 清除之前的错误状态
        self.txt_user_widget.set_error(False)
        self.txt_pwd_widget.set_error(False)
        self.txt_confirm_widget.set_error(False)

        if not username:
            self.show_error("请输入账号")
            self.txt_user_widget.set_error(True)
            self.txt_user_widget.setFocus()
            return
        if len(username) < 2:
            self.show_error("账号至少2个字符")
            self.txt_user_widget.set_error(True)
            self.txt_user_widget.setFocus()
            return
        if not password:
            self.show_error("请输入密码")
            self.txt_pwd_widget.set_error(True)
            self.txt_pwd_widget.setFocus()
            return
        if len(password) < 6:
            self.show_error("密码至少6位")
            self.txt_pwd_widget.set_error(True)
            self.txt_pwd_widget.setFocus()
            return
        if password != confirm:
            self.show_error("两次密码输入不一致")
            self.txt_confirm_widget.set_error(True)
            self.txt_confirm_widget.setFocus()
            return

        self.lbl_error.setVisible(False)
        self.btn_register.setEnabled(False)
        self.btn_register.setText("注册中...")

        self._result = {}

        def thread_func():
            try:
                auth = get_auth()
                if not auth.is_connected:
                    self._result = {"error": "无法连接云端，请检查网络"}
                    return
                success, msg = auth.register(username, password, display_name)
                if success:
                    self._result = {"success": username}
                else:
                    self._result = {"error": msg}
            except Exception as e:
                self._result = {"error": f"注册异常：{e}"}

        t = threading.Thread(target=thread_func, daemon=True)
        t.start()

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._check_register_result)
        self._poll_timer.start(200)

    def _check_register_result(self):
        if not self._result:
            return
        self._poll_timer.stop()
        if "success" in self._result:
            self.registered_username = self._result["success"]
            QMessageBox.information(self, "注册成功",
                                    f"账号 '{self.registered_username}' 注册成功，请登录")
            self.accept()
        else:
            self.show_error(self._result.get("error", "注册失败"))
            self.btn_register.setEnabled(True)
            self.btn_register.setText("注  册")

    def show_error(self, msg):
        self.lbl_error.setText(msg)
        self.lbl_error.setVisible(True)


# ═══════════════════════════════════════════
# 忘记密码对话框
# ═══════════════════════════════════════════

class ForgotPasswordDialog(QDialog):
    """忘记密码对话框 v4.0 —— 账号 + 显示姓名验证后重置密码"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = {}
        self._poll_timer = None
        self._verified = False
        self._username = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("找回密码")
        self.resize(460, 540)
        self.setStyleSheet(f"QDialog {{ background-color: {COLOR['bg_card']}; }}")

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 36, 40, 28)
        layout.setSpacing(0)

        # 标题
        title = QLabel("找回密码")
        title.setStyleSheet(f"font-size: {FONT_SIZE['3xl']}px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        subtitle = QLabel("请输入您的账号和注册姓名进行身份验证")
        subtitle.setStyleSheet(f"font-size: {FONT_SIZE['sm']}px; color: {COLOR['text_muted']}; margin-top: 6px; margin-bottom: 32px;")
        layout.addWidget(subtitle)

        # 账号
        lbl_u = QLabel("账号")
        lbl_u.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_u)
        self.txt_user_widget = IconLineEdit("请输入您的登录账号", "👤")
        self.txt_username = self.txt_user_widget.input
        layout.addWidget(self.txt_user_widget)
        layout.addSpacing(18)

        # 注册姓名
        lbl_d = QLabel("注册姓名")
        lbl_d.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_d)
        self.txt_name_widget = IconLineEdit("请输入注册时的姓名", "📝")
        self.txt_displayname = self.txt_name_widget.input
        layout.addWidget(self.txt_name_widget)
        layout.addSpacing(18)

        # 新密码
        lbl_p = QLabel("新密码")
        lbl_p.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_p)
        self.txt_newpwd_widget = IconLineEdit("请输入新密码（至少6位）", "🔒", is_password=True)
        self.txt_newpwd = self.txt_newpwd_widget.input
        self.txt_newpwd_widget.setEnabled(False)
        self.txt_newpwd_widget.setStyleSheet(f"""
            QFrame#inputBorder {{
                background-color: {COLOR['bg_surface']};
                border: 1.5px solid {COLOR['border']};
                border-radius: {RADIUS['md']}px;
            }}
        """)
        layout.addWidget(self.txt_newpwd_widget)
        layout.addSpacing(18)

        # 确认新密码
        lbl_c = QLabel("确认新密码")
        lbl_c.setStyleSheet(_INPUT_LABEL_STYLE)
        layout.addWidget(lbl_c)
        self.txt_confirm_widget = IconLineEdit("请再次输入新密码", "🔒", is_password=True)
        self.txt_confirm = self.txt_confirm_widget.input
        self.txt_confirm_widget.setEnabled(False)
        self.txt_confirm_widget.setStyleSheet(f"""
            QFrame#inputBorder {{
                background-color: {COLOR['bg_surface']};
                border: 1.5px solid {COLOR['border']};
                border-radius: {RADIUS['md']}px;
            }}
        """)
        layout.addWidget(self.txt_confirm_widget)

        # 错误/成功提示
        layout.addSpacing(16)
        self.lbl_msg = QLabel("")
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        self.lbl_msg.setVisible(False)
        layout.addWidget(self.lbl_msg)

        # 提交按钮
        layout.addSpacing(20)
        self.btn_submit = QPushButton("验证身份")
        self.btn_submit.setFixedHeight(46)
        self.btn_submit.setCursor(Qt.PointingHandCursor)
        self.btn_submit.setStyleSheet(_BTN_PRIMARY)
        self.btn_submit.clicked.connect(self.do_submit)
        layout.addWidget(self.btn_submit)

        layout.addStretch()
        self.setLayout(layout)

    def _set_msg(self, msg, msg_type="error"):
        """设置提示消息
        Args:
            msg: 消息内容
            msg_type: error/success/info
        """
        type_styles = {
            "error": f"color: {COLOR['danger']}; background: {COLOR['danger_light']};",
            "success": f"color: {COLOR['success']}; background: {COLOR['success_light']};",
            "info": f"color: {COLOR['info']}; background: {COLOR['info_light']};",
        }
        style = type_styles.get(msg_type, type_styles["error"])
        self.lbl_msg.setStyleSheet(f"""
            {style}
            font-size: {FONT_SIZE['sm']}px;
            padding: 8px 12px;
            border-radius: {RADIUS['sm']}px;
        """)
        self.lbl_msg.setText(msg)
        self.lbl_msg.setVisible(True)

    def do_submit(self):
        if not self._verified:
            # 验证身份阶段
            username = self.txt_username.text().strip()
            displayname = self.txt_displayname.text().strip()

            self.txt_user_widget.set_error(False)
            self.txt_name_widget.set_error(False)

            if not username:
                self._set_msg("请输入账号", "error")
                self.txt_user_widget.set_error(True)
                self.txt_user_widget.setFocus()
                return
            if not displayname:
                self._set_msg("请输入注册姓名", "error")
                self.txt_name_widget.set_error(True)
                self.txt_name_widget.setFocus()
                return

            self.lbl_msg.setVisible(False)
            self.btn_submit.setEnabled(False)
            self.btn_submit.setText("验证中...")
            self._result = {}

            def thread_func():
                try:
                    auth = get_auth()
                    users = auth.get_all_users()
                    found = None
                    for u in users:
                        if u.username == username:
                            found = u
                            break
                    if found is None:
                        self._result = {"error": "账号不存在"}
                    elif not found.enabled:
                        self._result = {"error": "账号已被禁用，无法重置密码"}
                    elif found.displayName != displayname:
                        self._result = {"error": "注册姓名不匹配，身份验证失败"}
                    else:
                        self._result = {"verified": username}
                except Exception as e:
                    self._result = {"error": f"验证异常：{e}"}

            t = threading.Thread(target=thread_func, daemon=True)
            t.start()
            self._poll_timer = QTimer()
            self._poll_timer.timeout.connect(self._check_verify_result)
            self._poll_timer.start(200)
        else:
            # 重置密码阶段
            newpwd = self.txt_newpwd.text()
            confirm = self.txt_confirm.text()

            self.txt_newpwd_widget.set_error(False)
            self.txt_confirm_widget.set_error(False)

            if not newpwd:
                self._set_msg("请输入新密码", "error")
                self.txt_newpwd_widget.set_error(True)
                self.txt_newpwd_widget.setFocus()
                return
            if len(newpwd) < 6:
                self._set_msg("密码至少6位", "error")
                self.txt_newpwd_widget.set_error(True)
                self.txt_newpwd_widget.setFocus()
                return
            if newpwd != confirm:
                self._set_msg("两次密码输入不一致", "error")
                self.txt_confirm_widget.set_error(True)
                self.txt_confirm_widget.setFocus()
                return

            self.lbl_msg.setVisible(False)
            self.btn_submit.setEnabled(False)
            self.btn_submit.setText("重置中...")
            self._result = {}

            def thread_func():
                try:
                    auth = get_auth()
                    success, msg = auth.reset_password(self._username, newpwd)
                    if success:
                        self._result = {"success": True}
                    else:
                        self._result = {"error": msg}
                except Exception as e:
                    self._result = {"error": f"重置异常：{e}"}

            t = threading.Thread(target=thread_func, daemon=True)
            t.start()
            self._poll_timer = QTimer()
            self._poll_timer.timeout.connect(self._check_reset_result)
            self._poll_timer.start(200)

    def _check_verify_result(self):
        if not self._result:
            return
        self._poll_timer.stop()
        if "error" in self._result:
            self._set_msg(self._result["error"], "error")
            self.btn_submit.setEnabled(True)
            self.btn_submit.setText("验证身份")
        else:
            self._verified = True
            self._username = self._result["verified"]
            # 启用密码输入框
            self.txt_username.setEnabled(False)
            self.txt_displayname.setEnabled(False)
            self.txt_newpwd_widget.setEnabled(True)
            self.txt_newpwd_widget._update_border_style()
            self.txt_confirm_widget.setEnabled(True)
            self.txt_confirm_widget._update_border_style()
            self.btn_submit.setEnabled(True)
            self.btn_submit.setText("重置密码")
            self._set_msg("✓ 身份验证通过，请设置新密码", "success")
            self.txt_newpwd_widget.setFocus()

    def _check_reset_result(self):
        if not self._result:
            return
        self._poll_timer.stop()
        if "success" in self._result:
            QMessageBox.information(self, "成功", "密码已重置，请使用新密码登录")
            self.accept()
        else:
            self._set_msg(self._result.get("error", "重置失败"), "error")
            self.btn_submit.setEnabled(True)
            self.btn_submit.setText("重置密码")


# ═══════════════════════════════════════════
# 主登录对话框
# ═══════════════════════════════════════════

class _CloudCheckSignal(QObject):
    """跨线程信号：网络检查完成"""
    def __init__(self, parent=None):
        super().__init__(parent)
    done = pyqtSignal(bool)


class LoginDialog(QDialog):
    """登录对话框 v4.0 —— 现代化设计"""
    def __init__(self):
        super().__init__()
        self.current_user = None
        self.current_session = None
        self._login_result = {}
        self._poll_timer = None
        self._drag_pos = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("餐饮综合管理系统")
        self.resize(900, 560)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 设置窗口图标
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(os.path.dirname(sys.executable), 'assets', 'app_icon.ico')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), 'assets', 'app_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 加载云同步状态图标
        # 修正 frozen 模式下的 assets 路径（PNG 在 _internal/assets/ 中）
        if getattr(sys, 'frozen', False):
            assets_dir = os.path.join(sys._MEIPASS, 'assets')
        else:
            assets_dir = os.path.dirname(icon_path)
        self._cloud_icons = {}
        _sz = 24
        for _name in ['cloud_connected', 'cloud_disconnected', 'cloud_connecting', 'cloud_neutral']:
            _p = os.path.join(assets_dir, f'{_name}.png')
            if os.path.isfile(_p):
                self._cloud_icons[_name] = QPixmap(_p).scaled(_sz, _sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # 外层容器（阴影效果）
        outer = QFrame(self)
        outer.setObjectName("outerFrame")
        outer.setStyleSheet(f"""
            #outerFrame {{
                background: {COLOR['bg_card']};
                border-radius: {RADIUS['xl']}px;
                border: 1px solid {COLOR['border']};
            }}
        """)
        outer.setGeometry(0, 0, 900, 560)

        # 主布局：左右分栏
        main_layout = QHBoxLayout(outer)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== 左侧品牌展示区 =====
        brand_panel = QFrame()
        brand_panel.setFixedWidth(400)
        brand_panel.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0.8, y2:1,
                    stop:0 {COLOR['sidebar_bg']},
                    stop:0.4 {COLOR['primary']},
                    stop:1 {COLOR['accent']});
                border-top-left-radius: {RADIUS['xl']}px;
                border-bottom-left-radius: {RADIUS['xl']}px;
            }}
        """)

        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(48, 48, 48, 48)
        brand_layout.setSpacing(0)

        # 品牌名称（一排）
        brand_title = QLabel("餐饮综合管理系统")
        brand_title.setStyleSheet(f"""
            font-size: 30px;
            font-weight: 700;
            color: white;
            background: transparent;
        """)
        brand_title.setAlignment(Qt.AlignLeft)
        brand_layout.addWidget(brand_title)

        # 测量标题宽度和英文字体
        title_width = QFontMetrics(brand_title.font()).horizontalAdvance("餐饮综合管理系统")
        brand_en_font = QFont()
        brand_en_font.setPixelSize(13)

        brand_layout.addSpacing(14)

        # 横线分割（与标题等宽）
        brand_divider = QFrame()
        brand_divider.setFixedHeight(2)
        brand_divider.setFixedWidth(title_width)
        brand_divider.setStyleSheet("background: rgba(255,255,255,0.35); border: none;")
        brand_layout.addWidget(brand_divider)

        brand_layout.addSpacing(14)

        # 英文副标题（与标题等宽，左右对齐）
        brand_en_text = "Catering Management System"
        en_natural = QFontMetrics(brand_en_font).horizontalAdvance(brand_en_text)
        extra_spacing = max(0, (title_width - en_natural) / (len(brand_en_text) - 1))

        brand_en = QLabel(brand_en_text)
        brand_en.setFixedWidth(title_width)
        brand_en.setStyleSheet(f"""
            font-size: 13px;
            color: rgba(255, 255, 255, 0.65);
            background: transparent;
            letter-spacing: {extra_spacing:.1f}px;
        """)
        brand_en.setAlignment(Qt.AlignLeft)
        brand_layout.addWidget(brand_en)

        brand_layout.addSpacing(16)

        # 品牌副标题
        brand_subtitle = QLabel("一站式餐饮门店管理解决方案\n进销存 · 财务 · 人事 · 报表")
        brand_subtitle.setStyleSheet(f"""
            font-size: {FONT_SIZE['base']}px;
            color: rgba(255, 255, 255, 0.8);
            background: transparent;
            line-height: 1.6;
        """)
        brand_subtitle.setAlignment(Qt.AlignLeft)
        brand_layout.addWidget(brand_subtitle)

        brand_layout.addStretch()

        # 底部特性列表
        features = [
            ("📊", "数据可视化报表"),
            ("💰", "智能成本核算"),
            ("👥", "员工排班考勤"),
        ]
        for icon, text in features:
            feat_layout = QHBoxLayout()
            feat_layout.setSpacing(12)
            feat_icon = QLabel(icon)
            feat_icon.setStyleSheet("font-size: 18px; background: transparent;")
            feat_text = QLabel(text)
            feat_text.setStyleSheet(f"""
                font-size: {FONT_SIZE['sm']}px;
                color: rgba(255, 255, 255, 0.9);
                background: transparent;
            """)
            feat_layout.addWidget(feat_icon)
            feat_layout.addWidget(feat_text)
            feat_layout.addStretch()
            brand_layout.addLayout(feat_layout)
            brand_layout.addSpacing(12)

        main_layout.addWidget(brand_panel)

        # ===== 右侧登录表单区 =====
        form_panel = QFrame()
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(60, 40, 60, 40)
        form_layout.setSpacing(0)

        # 关闭按钮
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLOR['text_muted']};
                border: none;
                font-size: 14px;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                color: {COLOR['text_primary']};
                background: {COLOR['bg_hover']};
            }}
        """)
        btn_close.clicked.connect(self.reject)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(btn_close)
        form_layout.addLayout(close_row)

        form_layout.addSpacing(20)

        # 欢迎标题
        welcome_title = QLabel("欢迎回来")
        welcome_title.setStyleSheet(f"""
            font-size: {FONT_SIZE['4xl']}px;
            font-weight: 700;
            color: {COLOR['text_primary']};
        """)
        form_layout.addWidget(welcome_title)

        form_layout.addSpacing(8)

        welcome_sub = QLabel("请登录您的账号继续使用")
        welcome_sub.setStyleSheet(f"""
            font-size: {FONT_SIZE['base']}px;
            color: {COLOR['text_muted']};
        """)
        form_layout.addWidget(welcome_sub)

        form_layout.addSpacing(36)

        # 账号输入
        lbl_user = QLabel("账号")
        lbl_user.setStyleSheet(_INPUT_LABEL_STYLE)
        form_layout.addWidget(lbl_user)
        self.txt_user_widget = IconLineEdit("请输入用户名", "👤")
        self.txt_user = self.txt_user_widget.input
        form_layout.addWidget(self.txt_user_widget)

        form_layout.addSpacing(20)

        # 密码输入
        lbl_pwd = QLabel("密码")
        lbl_pwd.setStyleSheet(_INPUT_LABEL_STYLE)
        form_layout.addWidget(lbl_pwd)
        self.txt_pwd_widget = IconLineEdit("请输入密码", "🔒", is_password=True)
        self.txt_pwd = self.txt_pwd_widget.input
        form_layout.addWidget(self.txt_pwd_widget)

        form_layout.addSpacing(16)

        # 记住账号 + 忘记密码
        options_row = QHBoxLayout()
        self.chk_remember = QCheckBox("记住密码")
        self.chk_remember.setStyleSheet(f"""
            QCheckBox {{
                color: {COLOR['text_secondary']};
                font-size: {FONT_SIZE['sm']}px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1.5px solid {COLOR['border_dark']};
                border-radius: 3px;
                background: {COLOR['bg_card']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR['primary']};
                border-color: {COLOR['primary']};
            }}
            QCheckBox::indicator:hover {{
                border-color: {COLOR['primary']};
            }}
        """)
        options_row.addWidget(self.chk_remember)
        options_row.addStretch()

        btn_forgot = QPushButton("忘记密码？")
        btn_forgot.setCursor(Qt.PointingHandCursor)
        btn_forgot.setStyleSheet(_BTN_LINK)
        btn_forgot.clicked.connect(self.open_forgot_password)
        options_row.addWidget(btn_forgot)
        form_layout.addLayout(options_row)

        form_layout.addSpacing(12)

        # 错误提示
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"""
            color: {COLOR['danger']};
            font-size: {FONT_SIZE['sm']}px;
            background: {COLOR['danger_light']};
            padding: 10px 14px;
            border-radius: {RADIUS['sm']}px;
        """)
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setVisible(False)
        form_layout.addWidget(self.lbl_error)

        form_layout.addSpacing(24)

        # 登录按钮
        self.btn_login = QPushButton("登  录")
        self.btn_login.setFixedHeight(46)
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLOR['primary']}, stop:1 {COLOR['accent']});
                color: {COLOR['text_white']};
                border: none;
                border-radius: {RADIUS['md']}px;
                font-size: {FONT_SIZE['lg']}px;
                font-weight: 600;
                padding: 12px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLOR['primary_hover']}, stop:1 {COLOR['accent_hover']});
            }}
            QPushButton:disabled {{
                background: {COLOR['border_dark']};
                color: {COLOR['text_muted']};
            }}
        """)
        self.btn_login.clicked.connect(self.do_login)
        self.btn_login.setEnabled(False)  # 检查网络前禁用登录
        form_layout.addWidget(self.btn_login)

        form_layout.addSpacing(20)

        # 注册链接
        register_row = QHBoxLayout()
        register_row.addStretch()
        register_text = QLabel("还没有账号？")
        register_text.setStyleSheet(f"color: {COLOR['text_muted']}; font-size: {FONT_SIZE['sm']}px;")
        register_row.addWidget(register_text)
        btn_register = QPushButton("立即注册")
        btn_register.setCursor(Qt.PointingHandCursor)
        btn_register.setStyleSheet(_BTN_LINK)
        btn_register.clicked.connect(self.open_register)
        register_row.addWidget(btn_register)
        register_row.addStretch()
        form_layout.addLayout(register_row)

        form_layout.addStretch()

        # 云端状态
        cloud_row = QHBoxLayout()
        cloud_row.addStretch()
        self.lbl_cloud_icon = QLabel()
        if 'cloud_connecting' in self._cloud_icons:
            self.lbl_cloud_icon.setPixmap(self._cloud_icons['cloud_connecting'])
        elif 'cloud_neutral' in self._cloud_icons:
            self.lbl_cloud_icon.setPixmap(self._cloud_icons['cloud_neutral'])
        self.lbl_cloud_icon.setFixedSize(24, 24)
        self.lbl_cloud_icon.setStyleSheet("background: transparent;")
        cloud_row.addWidget(self.lbl_cloud_icon)
        self.lbl_cloud = QLabel("正在检查云端连接...")
        self.lbl_cloud.setStyleSheet(f"font-size: {FONT_SIZE['xs']}px; color: {COLOR['warning']}; background: transparent;")
        cloud_row.addWidget(self.lbl_cloud)
        cloud_row.addStretch()
        form_layout.addLayout(cloud_row)

        main_layout.addWidget(form_panel, 1)

        # 回车登录
        self.txt_pwd.returnPressed.connect(self.btn_login.click)
        self.txt_user.returnPressed.connect(self.txt_pwd_widget.setFocus)

        self.setLayout(main_layout)

        # 加载记住的账号
        self._load_remembered()
        # 云端检查：先显示检查动画，1.5秒后显示结果
        self._cloud_check_dots = 0
        self._cloud_check_timer = QTimer()
        self._cloud_check_timer.timeout.connect(self._animate_cloud_check)
        self._cloud_check_timer.start(400)
        QTimer.singleShot(1500, self._check_cloud)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        outer = self.findChild(QFrame, "outerFrame")
        if outer:
            outer.setGeometry(0, 0, self.width(), self.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.globalPos() - self._drag_pos)
            self._drag_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _load_remembered(self):
        """加载记住的账号和密码"""
        try:
            auth = get_auth()
            history = auth.get_login_history()
            if history:
                username = history[0]
                self.txt_user_widget.setText(username)
                # 检查是否有保存的密码
                pwd = auth.get_remembered_password(username)
                if pwd:
                    self.txt_pwd_widget.setText(pwd)
                    self.chk_remember.setChecked(True)
                else:
                    self.chk_remember.setChecked(False)
                    self.txt_pwd_widget.setFocus()
        except Exception as e:
            logger.error(f"loadRemembered error: {e}")

    def _animate_cloud_check(self):
        """云端检查中的省略号动画"""
        self._cloud_check_dots = (self._cloud_check_dots + 1) % 4
        dots = "." * self._cloud_check_dots
        self.lbl_cloud.setText(f"正在检查云端连接{dots}")

    def _check_cloud(self):
        """检查云端连接状态——用 socket 检测网络"""
        if hasattr(self, '_cloud_check_timer'):
            self._cloud_check_timer.stop()

        # 创建跨线程信号（仅首次）
        if not hasattr(self, '_cloud_signal'):
            self._cloud_signal = _CloudCheckSignal()
            self._cloud_signal.done.connect(self._on_cloud_check_done)

        def _do_check():
            import socket
            net_ok = False
            for host, port in [("www.baidu.com", 443), ("www.qq.com", 443)]:
                try:
                    s = socket.create_connection((host, port), timeout=3)
                    s.close()
                    net_ok = True
                    break
                except Exception:
                    continue
            self._cloud_signal.done.emit(net_ok)

        import threading
        t = threading.Thread(target=_do_check, daemon=True)
        t.start()

    def _on_cloud_check_done(self, net_ok):
        """网络检查完成回调"""
        if net_ok:
            if 'cloud_connected' in self._cloud_icons:
                self.lbl_cloud_icon.setPixmap(self._cloud_icons['cloud_connected'])
            self.lbl_cloud.setText("云端同步已连接")
            self.lbl_cloud.setStyleSheet(f"font-size: {FONT_SIZE['xs']}px; color: {COLOR['success']}; background: transparent;")
            self.btn_login.setEnabled(True)
        else:
            if 'cloud_disconnected' in self._cloud_icons:
                self.lbl_cloud_icon.setPixmap(self._cloud_icons['cloud_disconnected'])
            self.lbl_cloud.setText("网络连接失败，请检查网络")
            self.lbl_cloud.setStyleSheet(f"font-size: {FONT_SIZE['xs']}px; color: {COLOR['danger']}; background: transparent;")
            self.btn_login.setEnabled(False)

    def open_register(self):
        dlg = RegisterDialog(self)
        dlg.exec_()
        if dlg.registered_username:
            self.txt_user.setText(dlg.registered_username)
            self.txt_pwd_widget.setFocus()

    def open_forgot_password(self):
        dlg = ForgotPasswordDialog(self)
        dlg.exec_()

    def do_login(self):
        username = self.txt_user.text().strip()
        password = self.txt_pwd.text()

        # 清除错误状态
        self.txt_user_widget.set_error(False)
        self.txt_pwd_widget.set_error(False)

        if not username:
            self.show_error("请输入账号")
            self.txt_user_widget.set_error(True)
            self.txt_user_widget.setFocus()
            return
        if not password:
            self.show_error("请输入密码")
            self.txt_pwd_widget.set_error(True)
            self.txt_pwd_widget.setFocus()
            return

        self.lbl_error.setVisible(False)
        self.btn_login.setEnabled(False)
        self.btn_login.setText("登录中...")

        self._login_result = {}

        def thread_func():
            try:
                auth = get_auth()
                session, err_msg = auth.login(username, password)
                if session is not None:
                    self._login_result = {"session": session, "username": username,
                                          "password": password}
                else:
                    self._login_result = {"error": err_msg or "登录失败"}
            except Exception as e:
                self._login_result = {"error": f"登录异常：{e}"}

        t = threading.Thread(target=thread_func, daemon=True)
        t.start()

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._check_login_result)
        self._poll_timer.start(200)

    def _check_login_result(self):
        if not self._login_result:
            return
        self._poll_timer.stop()

        if "error" in self._login_result:
            self.btn_login.setText("登  录")
            self.show_error(self._login_result["error"])
            # 密码错误时高亮密码框
            if "密码" in self._login_result["error"] or "错误" in self._login_result["error"]:
                self.txt_pwd_widget.set_error(True)
                self.txt_pwd_widget.setFocus()
            else:
                self.txt_user_widget.set_error(True)
                self.txt_user_widget.setFocus()
            self._check_cloud()
            return

        session = self._login_result["session"]
        username = self._login_result["username"]
        password = self._login_result["password"]

        auth = get_auth()
        if self.chk_remember.isChecked():
            auth.save_remembered_password(username, password)
        else:
            auth.clear_remembered_password(username)

        user_id = self._get_or_create_local_user(session)

        role_map = {"ADMIN": "管理员", "MANAGER": "经理", "CLERK": "员工"}
        self.current_user = {
            "id": user_id,
            "name": session.displayName or session.username,
            "username": session.username,
            "role": session.role,
            "position": role_map.get(session.role, session.role),
            "allowedStores": session.allowedStores,
            "visibleTabs": session.visibleTabs,
        }
        self.current_session = session

        self.btn_login.setText("登录成功 ✓")
        QTimer.singleShot(400, self.accept)

    def _get_or_create_local_user(self, session):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM employees WHERE username=?",
                           (session.username,))
            row = cursor.fetchone()
            if row:
                user_id = row["id"]
            else:
                role_map = {"ADMIN": "管理员", "MANAGER": "经理", "CLERK": "员工"}
            # 云端用户本地不存储真实密码，使用占位哈希表示"云端认证"
                from database.db_manager import _hash_password
                cloud_placeholder = _hash_password("__CLOUD_AUTH_ONLY__" + session.username)
            # 获取第一个门店作为默认门店
                cursor.execute("SELECT id FROM stores ORDER BY id LIMIT 1")
                store_row = cursor.fetchone()
                default_store_id = store_row["id"] if store_row else None
                cursor.execute(
                    "INSERT INTO employees (name, username, password, role, position, "
                    "hire_date, is_system_user, store_id) "
                    "VALUES (?, ?, ?, ?, ?, date('now'), 1, ?)",
                    (session.displayName or session.username, session.username,
                     cloud_placeholder, session.role, role_map.get(session.role, "员工"),
                     default_store_id)
                )
                conn.commit()
                _sync_cloud()
                user_id = cursor.lastrowid
            return user_id
        except Exception as e:
            logger.error(f"getOrCreateLocalUser error: {e}")
            return 0
        finally:
            conn.close()

    def show_error(self, msg):
        self.lbl_error.setText(msg)
        self.lbl_error.setVisible(True)
