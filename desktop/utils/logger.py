# -*- coding: utf-8 -*-
"""
统一日志模块 —— 替代全项目的 print() 调用
日志写入 AppData/CateringMgt/logs 同时输出到控制台
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# 日志目录：打包后使用 AppData\Local\CateringMgt（用户可写），开发时使用项目 data/
if getattr(sys, 'frozen', False):
    _APP_NAME = "CateringMgt"
    _LOG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), _APP_NAME, "logs")
else:
    _LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")

os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

def _create_logger():
    """创建并返回配置好的 logger"""
    log = logging.getLogger("restaurant_mgt")
    log.setLevel(logging.DEBUG)

    # 避免重复添加 handler
    if log.handlers:
        return log

    # 读取配置级别
    level = logging.INFO
    try:
        import configparser
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")
        if os.path.exists(config_path):
            cp = configparser.ConfigParser()
            cp.read(config_path, encoding='utf-8')
            level_str = cp.get('Log', 'level', fallback='INFO').upper()
            level = getattr(logging, level_str, logging.INFO)
    except Exception:
        pass  # 日志级别解析失败，使用默认级别
    log.setLevel(level)

    # 文件 handler —— 轮转，单文件最大 2MB，保留 3 个备份
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    fh = RotatingFileHandler(_LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(fmt)
    log.addHandler(fh)

    # 控制台 handler —— 仅在非打包（开发模式）且 stdout 可用时添加
    if not getattr(sys, 'frozen', False) and sys.stdout is not None:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(fmt)
        log.addHandler(ch)

    return log

# 模块级单例，直接 import 使用
logger = _create_logger()
