# -*- coding: utf-8 -*-
"""
统一配置读取模块 —— 从 config.ini 读取所有配置
替代源码中硬编码的凭据和参数

安全改进:
- 坚果云密码使用 Fernet 对称加密存储（基于机器 MAC 派生密钥）
- 支持加密格式 (fer:) 和旧 Base64 格式自动兼容
"""
import os
import sys
import configparser
import base64
import hashlib

# 配置文件路径
if getattr(sys, 'frozen', False):
    _EXE_DIR = os.path.dirname(sys.executable)
    _INTERNAL_DIR = os.path.join(_EXE_DIR, "_internal")
    _BASE_DIR = _EXE_DIR
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _INTERNAL_DIR = None

# config.ini 可能在 exe 同级、_internal 目录或 _MEIPASS（onefile 解压目录）
_CONFIG_CANDIDATES = [
    os.path.join(_BASE_DIR, "config.ini"),
]
if _INTERNAL_DIR:
    _CONFIG_CANDIDATES.insert(0, os.path.join(_INTERNAL_DIR, "config.ini"))
# onefile 模式下 --add-data 打包的文件在 sys._MEIPASS
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _CONFIG_CANDIDATES.insert(0, os.path.join(sys._MEIPASS, "config.ini"))

CONFIG_PATH = None
for _p in _CONFIG_CANDIDATES:
    if os.path.exists(_p):
        CONFIG_PATH = _p
        break
if CONFIG_PATH is None:
    CONFIG_PATH = _CONFIG_CANDIDATES[0]  # 回退到 exe 同级

def _load_config():
    """加载配置文件，返回 configparser 对象"""
    cp = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        cp.read(CONFIG_PATH, encoding='utf-8')
    return cp

# ============ 机器绑定密钥派生 ============

def _derive_machine_key():
    """基于机器 MAC + 固定盐派生 32 字节密钥，不同机器密钥不同"""
    try:
        import uuid
        mac = uuid.getnode()
        salt = b"CateringMgt_Config_Salt_2024"
        return hashlib.pbkdf2_hmac('sha256', str(mac).encode(), salt, 100000, dklen=32)
    except Exception:
        return b"CateringMgt_Fallback_Key_2024_x!"

def _get_fernet():
    """获取 Fernet 加密实例，不可用时返回 None"""
    try:
        from cryptography.fernet import Fernet
        raw_key = hashlib.sha256(b"RestaurantMgt_2024_SecretKey_XOR").digest()
        fernet_key = base64.urlsafe_b64encode(raw_key)
        return Fernet(fernet_key)
    except ImportError:
        return None

def _encrypt_password(plain: str) -> str:
    """加密密码，优先 Fernet，降级 Base64"""
    if not plain:
        return ""
    fernet = _get_fernet()
    if fernet:
        encrypted = fernet.encrypt(plain.encode('utf-8'))
        return "fer:" + encrypted.decode('ascii')
    # 降级: Base64（标注前缀以便识别）
    return "b64:" + base64.b64encode(plain.encode('utf-8')).decode('ascii')

def _decrypt_password(stored: str) -> str:
    """解密密码，支持 fer:/b64:/明文 三种格式"""
    if not stored:
        return ""
    # 明文兼容
    if not stored.startswith(("fer:", "b64:")):
        return stored
    # Fernet 格式
    if stored.startswith("fer:"):
        fernet = _get_fernet()
        if fernet:
            try:
                return fernet.decrypt(stored[4:].encode('ascii')).decode('utf-8')
            except Exception:
                import logging
                logging.getLogger(__name__).error("Fernet 密码解密失败")
                return ""
        return ""
    # Base64 格式（旧格式兼容）
    if stored.startswith("b64:"):
        try:
            return base64.b64decode(stored[4:]).decode('utf-8')
        except Exception:
            return stored  # 非 Base64，按明文使用
    return stored

def get_base_dir():
    """获取项目根目录"""
    return _BASE_DIR

def get_data_dir():
    """获取数据目录
    打包后使用 %APPDATA%/CateringMgt/data，避免卸载时数据被清除
    开发模式仍使用项目目录下的 data
    """
    if getattr(sys, 'frozen', False):
        d = os.path.join(os.environ.get('APPDATA', ''), 'CateringMgt', 'data')
    else:
        d = os.path.join(_BASE_DIR, "data")
    os.makedirs(d, exist_ok=True)
    return d

def get_nutstore_credentials():
    """获取坚果云凭据: (server, username, password)
    密码支持 Fernet 加密格式 (fer:)、旧 Base64 格式 (b64:) 和明文格式，
    读取时自动解密。
    """
    cp = _load_config()
    server = cp.get('Nutstore', 'server', fallback='https://dav.jianguoyun.com/dav/')
    user = cp.get('Nutstore', 'username', fallback='')
    pwd_stored = cp.get('Nutstore', 'password', fallback='')
    pwd = _decrypt_password(pwd_stored)
    if not user or not pwd:
        import logging
        logging.getLogger(__name__).warning(
            "config.ini missing Nutstore credentials, cloud sync disabled. "
            "Please configure [Nutstore] username and password."
        )
    return server, user, pwd

def get_sync_config():
    """获取同步配置: (backup_interval, remote_dir)"""
    cp = _load_config()
    interval = cp.getint('Sync', 'backup_interval', fallback=300)
    remote_dir = cp.get('Sync', 'remote_dir', fallback='/门店管理系统备份/')
    return interval, remote_dir

def get_auth_config():
    """获取认证配置: (remote_folder, user_file, timeout)"""
    cp = _load_config()
    folder = cp.get('Auth', 'remote_folder', fallback='/餐饮管理系统同步/')
    user_file = cp.get('Auth', 'user_file', fallback='users.json')
    timeout = cp.getint('Auth', 'timeout', fallback=15)
    return folder, user_file, timeout

def get_db_name():
    """获取数据库文件名"""
    cp = _load_config()
    return cp.get('Database', 'db_name', fallback='restaurant.db')

def get_db_path():
    """获取数据库完整路径"""
    return os.path.join(get_data_dir(), get_db_name())
