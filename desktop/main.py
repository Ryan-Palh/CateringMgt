# -*- coding: utf-8 -*-
"""
餐饮综合管理系统 v5.0 - 餐饮专业版主入口
启动流程：高DPI适配 → 闪屏窗口 → 全局主题 → 数据库初始化 → 坚果云同步 → 登录 → 主窗口
优化：重模块延迟导入，闪屏立即响应
"""
import sys
import os
import traceback
import threading

# ===== 全局异常钩子：崩溃时写日志 + 弹窗提示用户 =====
_crash_dialog_shown = False

def _global_excepthook(exc_type, exc_value, exc_tb):
    global _crash_dialog_shown
    if _crash_dialog_shown:
        return
    _crash_dialog_shown = True

    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    try:
        from utils.logger import logger
        logger.critical("未捕获异常导致崩溃:\n" + tb_str)
    except Exception:
        if getattr(sys, 'frozen', False):
            _log_dir = os.path.join(os.path.dirname(sys.executable), "data", "logs")
        else:
            _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs")
        os.makedirs(_log_dir, exist_ok=True)
        with open(os.path.join(_log_dir, "crash.log"), "a", encoding="utf-8") as f:
            f.write(tb_str + "\n")

    try:
        from PyQt5.QtWidgets import QMessageBox, QApplication
        app = QApplication.instance()
        if app:
            short_msg = str(exc_value)[:200] if exc_value else str(exc_type.__name__)
            QMessageBox.critical(None, "程序异常",
                f"程序遇到错误，即将退出。\n\n错误类型: {exc_type.__name__}\n错误信息: {short_msg}\n\n详细信息已记录到日志，请联系技术支持。")
    except Exception:
        pass

    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _global_excepthook

def _threading_excepthook(args):
    tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_tb))
    try:
        from utils.logger import logger
        logger.error(f"子线程异常 (thread={args.thread.name}):\n{tb_str}")
    except Exception:
        pass

threading.excepthook = _threading_excepthook

# 修复 Qt 平台插件路径
if getattr(sys, 'frozen', False):
    base = os.path.dirname(sys.executable)
    plugin_path = os.path.join(base, '_internal', 'PyQt5', 'Qt5', 'plugins')
else:
    try:
        import PyQt5
        plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins')
        if not os.path.isdir(plugin_path):
            from PyQt5.QtCore import QLibraryInfo
            plugin_path = QLibraryInfo.location(QLibraryInfo.PluginsPath)
    except Exception:
        plugin_path = None

if plugin_path and os.path.isdir(plugin_path):
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont, QIcon

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 应用图标
    if getattr(sys, 'frozen', False):
        _icon_path = os.path.join(os.path.dirname(sys.executable), 'assets', 'app_icon.ico')
    else:
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'app_icon.ico')
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    font = QFont()
    font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Arial"])
    font.setPointSize(10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    # ===== 延迟导入重模块 =====
    from gui.theme import apply_global_theme
    apply_global_theme(app)
    # 初始化数据库
    try:
        from database.db_manager import init_database, seed_default_data
        init_database()
        seed_default_data()
    except Exception as e:
        from utils.logger import logger
        logger.error(f"数据库初始化失败: {e}")

    # 坚果云同步（子线程，不阻塞）
    from utils.nutstore_sync import get_sync
    from utils.logger import logger
    sync = get_sync()
    if sync.is_connected:
        def _bg_sync():
            try:
                sync_result = sync.sync_on_login()
                logger.info(f"登录前同步结果: {sync_result}")
                from database.db_manager import migrate_database
                migrate_database()
            except Exception as e:
                logger.warning(f"登录前同步失败: {e}")
            sync.start_auto_sync()
            logger.info("坚果云自动同步已启动")
        threading.Thread(target=_bg_sync, daemon=True).start()
    else:
        logger.warning("坚果云未连接，将在后台重试")

    from gui.login_dialog import LoginDialog
    login = LoginDialog()
    logger.debug("登录对话框已创建，等待用户操作...")
    result = login.exec_()
    logger.debug(f"登录对话框返回: {result}")
    if result == LoginDialog.Accepted:
        from gui.main_window import MainWindow
        window = MainWindow(login.current_user, login.current_session)
        window.show()
        exit_code = app.exec_()
        try:
            sync.stop_auto_sync()
        except Exception:
            pass
        sys.exit(exit_code)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
