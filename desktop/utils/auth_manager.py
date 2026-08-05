# -*- coding: utf-8 -*-
"""
认证管理器 —— 基于 WebDAV (坚果云) 云端存储的用户账号体系
参照 Android 版 Catering Management 的 AuthManager.kt 实现

改进点：
- 凭据从 config.ini 读取，不再硬编码
- 使用 logging 替代 print
- 记住密码使用 Fernet 对称加密存储
- 本地数据库密码使用 SHA-256 加盐哈希
"""
import os
import json
import hashlib
import secrets
import time
import base64
from datetime import datetime
from webdav4.client import Client

from utils.logger import logger
from utils.config import (
    get_nutstore_credentials,
    get_auth_config,
    get_data_dir,
)

# ============ 配置 ============
SERVER, WEBDAV_ACCOUNT, WEBDAV_PASSWORD = get_nutstore_credentials()
REMOTE_FOLDER, USER_FILE, TIMEOUT = get_auth_config()

# 本地 Session 存储路径
SESSION_DIR = get_data_dir()
SESSION_PATH = os.path.join(SESSION_DIR, "session.json")
HISTORY_PATH = os.path.join(SESSION_DIR, "login_history.json")
REMEMBER_PATH = os.path.join(SESSION_DIR, "remembered_passwords.json")

# 记住密码加密密钥（基于机器 MAC + 固定盐派生，不同机器密钥不同）
def _derive_machine_key():
    try:
        import uuid
        mac = uuid.getnode()
        salt = b"CateringMgt_XOR_Salt_2024"
        return hashlib.pbkdf2_hmac('sha256', str(mac).encode(), salt, 100000, dklen=32)
    except Exception:
        return b"RestaurantMgt_2024_SecretKey_XOR"
_ENCRYPT_KEY = _derive_machine_key()

# ============ 数据模型 ============
# 角色体系：5 个预设角色 + 支持自建角色
# 预设角色（英文标识符存储，中文显示）
ROLE_SUPER_ADMIN = "SUPER_ADMIN"       # 超级管理员
ROLE_ADMIN = "ADMIN"                   # 管理员
ROLE_STORE_MANAGER = "STORE_MANAGER"   # 店长
ROLE_SUPERVISOR = "SUPERVISOR"         # 主管
ROLE_EMPLOYEE = "EMPLOYEE"             # 员工

# 预设角色列表（有序，用于 UI 展示）
PRESET_ROLES = [
    (ROLE_SUPER_ADMIN,   "超级管理员"),
    (ROLE_ADMIN,         "管理员"),
    (ROLE_STORE_MANAGER, "店长"),
    (ROLE_SUPERVISOR,    "主管"),
    (ROLE_EMPLOYEE,      "员工"),
]

# 角色中文映射（含旧角色兼容）
ROLE_DISPLAY = {
    ROLE_SUPER_ADMIN:   "超级管理员",
    ROLE_ADMIN:         "管理员",
    ROLE_STORE_MANAGER: "店长",
    ROLE_SUPERVISOR:    "主管",
    ROLE_EMPLOYEE:      "员工",
    "MANAGER":          "店长",
    "CLERK":            "员工",
}

# 角色权限等级（数字越大权限越高）
ROLE_LEVEL = {
    ROLE_SUPER_ADMIN:   100,
    ROLE_ADMIN:         80,
    ROLE_STORE_MANAGER: 60,
    ROLE_SUPERVISOR:    40,
    ROLE_EMPLOYEE:      20,
    "MANAGER":          60,
    "CLERK":            20,
}

# 仅超级管理员拥有全部权限，不需要分配门店
# 管理员也需要分配门店和功能权限
ADMIN_ROLES = {ROLE_SUPER_ADMIN}

# 默认角色
ROLE_DEFAULT = ROLE_EMPLOYEE


class User:
    def __init__(self, username="", password_hash="", display_name="",
                 role=ROLE_DEFAULT, allowed_stores=None, visible_tabs=None,
                 store_tab_permissions=None, created_at=None, enabled=True):
        self.username = username
        self.passwordHash = password_hash
        self.displayName = display_name
        self.role = role
        self.allowedStores = allowed_stores or []
        self.visibleTabs = visible_tabs or []
        self.storeTabPermissions = store_tab_permissions or {}
        self.createdAt = created_at or int(time.time() * 1000)
        self.enabled = enabled

    def to_dict(self):
        return {
            "username": self.username,
            "passwordHash": self.passwordHash,
            "displayName": self.displayName,
            "role": self.role,
            "allowedStores": self.allowedStores,
            "visibleTabs": self.visibleTabs,
            "storeTabPermissions": self.storeTabPermissions,
            "createdAt": self.createdAt,
            "enabled": self.enabled
        }

    @staticmethod
    def from_dict(d):
        return User(
            username=d.get("username", ""),
            password_hash=d.get("passwordHash", ""),
            display_name=d.get("displayName", ""),
            role=d.get("role", ROLE_DEFAULT),
            allowed_stores=d.get("allowedStores", []),
            visible_tabs=d.get("visibleTabs", []),
            store_tab_permissions=d.get("storeTabPermissions", {}),
            created_at=d.get("createdAt"),
            enabled=d.get("enabled", True)
        )


class UserList:
    def __init__(self, users=None, updated_at=None):
        self.users = users or []
        self.updatedAt = updated_at or int(time.time() * 1000)

    def to_dict(self):
        return {
            "users": [u.to_dict() for u in self.users],
            "updatedAt": self.updatedAt
        }

    @staticmethod
    def from_dict(d):
        return UserList(
            users=[User.from_dict(u) for u in d.get("users", [])],
            updated_at=d.get("updatedAt")
        )


class Session:
    def __init__(self, username, role, display_name="",
                 allowed_stores=None, visible_tabs=None,
                 store_tab_permissions=None):
        self.username = username
        self.role = role
        self.displayName = display_name
        self.allowedStores = allowed_stores or []
        self.visibleTabs = visible_tabs or []
        self.storeTabPermissions = store_tab_permissions or {}

    def to_dict(self):
        return {
            "username": self.username,
            "role": self.role,
            "displayName": self.displayName,
            "allowedStores": self.allowedStores,
            "visibleTabs": self.visibleTabs,
            "storeTabPermissions": self.storeTabPermissions
        }

    @staticmethod
    def from_dict(d):
        return Session(
            username=d.get("username", ""),
            role=d.get("role", ROLE_DEFAULT),
            display_name=d.get("displayName", ""),
            allowed_stores=d.get("allowedStores", []),
            visible_tabs=d.get("visibleTabs", []),
            store_tab_permissions=d.get("storeTabPermissions", {})
        )


# ============ 密码加密工具（用于记住密码的本地存储）============
# 使用 Fernet 对称加密替代 XOR，提升安全性

try:
    from cryptography.fernet import Fernet
    import hashlib
    _raw_key = hashlib.sha256(b"RestaurantMgt_2024_SecretKey_XOR").digest()
    _fernet_key = base64.urlsafe_b64encode(_raw_key)
    _fernet = Fernet(_fernet_key)
    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False

def _xor_encrypt(text):
    """加密文本，优先使用 Fernet，降级到 XOR"""
    if not text:
        return ""
    try:
        if _HAS_FERNET:
            encrypted = _fernet.encrypt(text.encode('utf-8'))
            return "fer:" + encrypted.decode('ascii')
        else:
            text_bytes = text.encode('utf-8')
            encrypted = bytearray()
            for i, b in enumerate(text_bytes):
                encrypted.append(b ^ _ENCRYPT_KEY[i % len(_ENCRYPT_KEY)])
            return "enc:" + base64.b64encode(bytes(encrypted)).decode('ascii')
    except Exception as e:
        logger.error(f"密码加密失败: {e}")
        return ""


def _xor_decrypt(encrypted_text):
    """解密文本，支持 Fernet 和 XOR 两种格式"""
    if not encrypted_text:
        return ""
    if not encrypted_text.startswith("enc:") and not encrypted_text.startswith("fer:"):
        return encrypted_text
    try:
        if encrypted_text.startswith("fer:"):
            if _HAS_FERNET:
                return _fernet.decrypt(encrypted_text[4:].encode('ascii')).decode('utf-8')
            else:
                logger.error("Fernet 加密的密码无法解密：缺少 cryptography 库")
                return ""
        else:
            data = base64.b64decode(encrypted_text[4:])
            decrypted = bytearray()
            for i, b in enumerate(data):
                decrypted.append(b ^ _ENCRYPT_KEY[i % len(_ENCRYPT_KEY)])
            return decrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return ""


# ============ 认证管理器 ============

class AuthManager:
    """认证管理器 —— 基于 WebDAV (坚果云) 云端存储的用户账号体系"""

    def __init__(self):
        self._client = None
        self._users_cache = None       # 用户列表内存缓存
        self._users_cache_time = 0     # 缓存时间戳
        self._init_webdav()

    def _init_webdav(self):
        """初始化 WebDAV 客户端"""
        try:
            self._client = Client(
                SERVER,
                auth=(WEBDAV_ACCOUNT, WEBDAV_PASSWORD),
                timeout=TIMEOUT
            )
        except Exception as e:
            logger.error(f"WebDAV 初始化失败: {e}")
            self._client = None

    @property
    def is_connected(self):
        """检查 WebDAV 连接是否可用"""
        return self._client is not None

    # ---- 密码哈希 ----

    @staticmethod
    def hash_password(password):
        """密码哈希：优先 bcrypt，降级 SHA-256 加盐"""
        try:
            import bcrypt
            pwd_bytes = password.encode('utf-8')
            if len(pwd_bytes) > 72:
                pwd_bytes = pwd_bytes[:72]
            return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode('utf-8')
        except ImportError:
            salt = secrets.token_hex(8)
            digest = hashlib.sha256(f"{salt}:{password}".encode('utf-8')).hexdigest()
            return f"sha256:{salt}:{digest}"

    @staticmethod
    def verify_password(password, stored_hash):
        """验证密码：支持 bcrypt、SHA-256 加盐、旧格式无盐"""
        try:
            # bcrypt 格式
            if stored_hash.startswith('$2'):
                try:
                    import bcrypt
                    pwd_bytes = password.encode('utf-8')
                    if len(pwd_bytes) > 72:
                        pwd_bytes = pwd_bytes[:72]
                    return bcrypt.checkpw(pwd_bytes, stored_hash.encode('utf-8'))
                except ImportError:
                    return False
            # 新 SHA-256 格式 (sha256:salt:hash)
            if stored_hash.startswith('sha256:'):
                parts = stored_hash.split(':', 2)
                if len(parts) == 3:
                    salt, expected = parts[1], parts[2]
                    return hashlib.sha256(f"{salt}:{password}".encode('utf-8')).hexdigest() == expected
                return False
            # 旧格式 (salt:hash)
            if ':' in stored_hash:
                salt, hashed = stored_hash.split(':', 1)
                return hashlib.sha256(f"{salt}:{password}".encode('utf-8')).hexdigest() == hashed
            # 兼容旧版无盐哈希
            return hashlib.sha256(password.encode('utf-8')).hexdigest() == stored_hash
        except Exception:
            return False

    # ---- WebDAV 用户列表操作 ----

    def _fetch_users(self, use_cache=True):
        """从 WebDAV 下载用户列表（10秒内缓存，避免短时间重复网络请求）"""
        import time as _time
        # 10秒内返回缓存
        if use_cache and self._users_cache is not None:
            if _time.time() - self._users_cache_time < 10:
                return self._users_cache
        try:
            if self._client is None:
                self._init_webdav()
            if self._client is None:
                return None
            # 确保远程目录存在
            try:
                self._client.mkdir(REMOTE_FOLDER)
            except Exception:
                pass  # 目录可能已存在
            remote_path = f"{REMOTE_FOLDER}/{USER_FILE}"
            import io

            # 尝试下载 users.json，404 时返回空列表（首次使用）
            buf = io.BytesIO()
            try:
                self._client.download_fileobj(remote_path, buf)
            except Exception as dl_err:
                err_str = str(dl_err).lower()
                # 404 / not found 表示首次使用，返回空用户列表
                if '404' in err_str or 'not found' in err_str:
                    empty = UserList()
                    self._users_cache = empty
                    self._users_cache_time = _time.time()
                    logger.info("users.json 不存在，首次使用，返回空用户列表")
                    return empty
                # 其他错误（网络/SSL等）向上抛出
                raise
            buf.seek(0)
            data = json.loads(buf.read().decode('utf-8'))
            result = UserList.from_dict(data)
            # 更新缓存
            self._users_cache = result
            self._users_cache_time = _time.time()
            return result
        except Exception as e:
            logger.error(f"fetchUsers error: {e}")
            return None

    def _push_users(self, user_list):
        """上传用户列表到 WebDAV"""
        try:
            if self._client is None:
                self._init_webdav()
            if self._client is None:
                return False
            try:
                self._client.mkdir(REMOTE_FOLDER)
            except Exception:
                pass  # 目录可能已存在
            remote_path = f"{REMOTE_FOLDER}/{USER_FILE}"
            data = json.dumps(user_list.to_dict(), ensure_ascii=False).encode('utf-8')
            import io
            self._client.upload_fileobj(io.BytesIO(data), remote_path, overwrite=True)
            return True
        except Exception as e:
            logger.error(f"pushUsers error: {e}")
            return False

    # ---- 登录 / 注册 ----

    def login(self, username, password):
        """云端认证登录。返回 (session, err_msg)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                return None, "无法连接云端服务，请检查网络"
            if len(user_list.users) == 0:
                return None, "暂无注册用户，请先点击「立即注册」创建账号"
            for u in user_list.users:
                if u.username == username:
                    if not u.enabled:
                        return None, "账号已禁用，请联系管理员"
                    if not self.verify_password(password, u.passwordHash):
                        return None, "密码错误"
                    session = Session(
                        username=u.username,
                        role=u.role,
                        display_name=u.displayName,
                        allowed_stores=u.allowedStores,
                        visible_tabs=u.visibleTabs,
                        store_tab_permissions=u.storeTabPermissions
                    )
                    self.save_session(session)
                    self.add_login_history(username)
                    return session, None
            return None, "账号不存在"
        except Exception as e:
            logger.error(f"login error: {e}")
            return None, f"登录异常：{e}"

    def register(self, username, password, display_name=""):
        """注册新用户。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                user_list = UserList()
            for u in user_list.users:
                if u.username == username:
                    return False, "账号已存在"
            # 第一个注册的用户自动成为管理员
            role = ROLE_SUPER_ADMIN if len(user_list.users) == 0 else ROLE_DEFAULT
            new_user = User(
                username=username,
                password_hash=self.hash_password(password),
                display_name=display_name or username,
                role=role
            )
            user_list.users.append(new_user)
            user_list.updatedAt = int(time.time() * 1000)
            if self._push_users(user_list):
                return True, "注册成功"
            return False, "同步到云端失败"
        except Exception as e:
            logger.error(f"register error: {e}")
            return False, f"注册异常：{e}"

    # ---- Session 管理 ----

    def save_session(self, session):
        """保存会话到本地"""
        try:
            os.makedirs(SESSION_DIR, exist_ok=True)
            with open(SESSION_PATH, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"saveSession error: {e}")

    def load_session(self):
        """从本地加载会话"""
        try:
            if not os.path.exists(SESSION_PATH):
                return None
            with open(SESSION_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session.from_dict(data)
        except Exception as e:
            logger.error(f"loadSession error: {e}")
            return None

    def clear_session(self):
        """清除本地会话"""
        try:
            if os.path.exists(SESSION_PATH):
                os.remove(SESSION_PATH)
        except Exception as e:
            logger.error(f"clearSession error: {e}")

    # ---- 登录历史 ----

    def _get_login_history(self):
        """获取登录历史列表"""
        try:
            if not os.path.exists(HISTORY_PATH):
                return []
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def add_login_history(self, username):
        """添加登录历史（最近优先，最多10条）"""
        try:
            history = self._get_login_history()
            if username in history:
                history.remove(username)
            history.insert(0, username)
            history = history[:10]
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"addLoginHistory error: {e}")

    def remove_login_history(self, username):
        """删除某条登录历史"""
        try:
            history = self._get_login_history()
            if username in history:
                history.remove(username)
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"removeLoginHistory error: {e}")

    def get_login_history(self):
        """获取登录历史列表"""
        return self._get_login_history()

    # ---- 记住密码（加密存储） ----

    def save_remembered_password(self, username, password):
        """保存记住的密码（XOR+Base64 加密存储）"""
        try:
            data = {}
            if os.path.exists(REMEMBER_PATH):
                with open(REMEMBER_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[username] = _xor_encrypt(password)
            os.makedirs(os.path.dirname(REMEMBER_PATH), exist_ok=True)
            with open(REMEMBER_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info(f"已保存记住密码: {username}")
        except Exception as e:
            logger.error(f"saveRememberedPassword error: {e}")

    def get_remembered_password(self, username):
        """获取记住的密码（自动解密）"""
        try:
            if not os.path.exists(REMEMBER_PATH):
                return ""
            with open(REMEMBER_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            encrypted = data.get(username, "")
            return _xor_decrypt(encrypted)
        except Exception as e:
            logger.error(f"getRememberedPassword error: {e}")
            return ""

    def clear_remembered_password(self, username):
        """清除记住的密码"""
        try:
            if not os.path.exists(REMEMBER_PATH):
                return
            with open(REMEMBER_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if username in data:
                del data[username]
            with open(REMEMBER_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"clearRememberedPassword error: {e}")

    # ---- 用户管理 CRUD ----

    def get_all_users(self):
        """获取所有用户列表"""
        try:
            user_list = self._fetch_users()
            return user_list.users if user_list else []
        except Exception as e:
            logger.error(f"getAllUsers error: {e}")
            return []

    def add_user(self, user):
        """添加新用户。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                user_list = UserList()
            for u in user_list.users:
                if u.username == user.username:
                    return False, "账号已存在"
            user_list.users.append(user)
            user_list.updatedAt = int(time.time() * 1000)
            if self._push_users(user_list):
                return True, "添加成功"
            return False, "同步到云端失败"
        except Exception as e:
            logger.error(f"addUser error: {e}")
            return False, f"添加异常：{e}"

    def update_user(self, updated_user):
        """更新用户信息。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                return False, "无法获取用户列表"
            idx = -1
            for i, u in enumerate(user_list.users):
                if u.username == updated_user.username:
                    idx = i
                    break
            if idx < 0:
                return False, "用户不存在"
            user_list.users[idx] = updated_user
            user_list.updatedAt = int(time.time() * 1000)
            if self._push_users(user_list):
                return True, "更新成功"
            return False, "同步到云端失败"
        except Exception as e:
            logger.error(f"updateUser error: {e}")
            return False, f"更新异常：{e}"

    def delete_user(self, username):
        """删除用户。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                return False, "无法获取用户列表"
            user_list.users = [u for u in user_list.users if u.username != username]
            user_list.updatedAt = int(time.time() * 1000)
            if self._push_users(user_list):
                return True, "删除成功"
            return False, "同步到云端失败"
        except Exception as e:
            logger.error(f"deleteUser error: {e}")
            return False, f"删除异常：{e}"

    def enable_user(self, username):
        """启用用户。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                return False, "无法获取用户列表"
            for u in user_list.users:
                if u.username == username:
                    u.enabled = True
                    user_list.updatedAt = int(time.time() * 1000)
                    if self._push_users(user_list):
                        return True, "已启用"
                    return False, "同步到云端失败"
            return False, "用户不存在"
        except Exception as e:
            logger.error(f"enableUser error: {e}")
            return False, f"启用异常：{e}"

    def disable_user(self, username):
        """禁用用户。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                return False, "无法获取用户列表"
            for u in user_list.users:
                if u.username == username:
                    u.enabled = False
                    user_list.updatedAt = int(time.time() * 1000)
                    if self._push_users(user_list):
                        return True, "已禁用"
                    return False, "同步到云端失败"
            return False, "用户不存在"
        except Exception as e:
            logger.error(f"disableUser error: {e}")
            return False, f"禁用异常：{e}"

    def reset_password(self, username, new_password):
        """重置用户密码。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                return False, "无法获取用户列表"
            for u in user_list.users:
                if u.username == username:
                    u.passwordHash = self.hash_password(new_password)
                    user_list.updatedAt = int(time.time() * 1000)
                    if self._push_users(user_list):
                        return True, "密码已重置"
                    return False, "同步到云端失败"
            return False, "用户不存在"
        except Exception as e:
            logger.error(f"resetPassword error: {e}")
            return False, f"重置异常：{e}"

    def change_password(self, username, old_password, new_password):
        """修改密码（需验证旧密码）。返回 (success, message)"""
        try:
            user_list = self._fetch_users()
            if user_list is None:
                return False, "无法获取用户列表"
            for u in user_list.users:
                if u.username == username:
                    if not self.verify_password(old_password, u.passwordHash):
                        return False, "原密码错误"
                    u.passwordHash = self.hash_password(new_password)
                    user_list.updatedAt = int(time.time() * 1000)
                    if self._push_users(user_list):
                        return True, "密码已修改"
                    return False, "同步到云端失败"
            return False, "用户不存在"
        except Exception as e:
            logger.error(f"changePassword error: {e}")
            return False, f"修改异常：{e}"


# ============ 全局单例 ============
_auth_instance = None


def get_auth():
    """获取认证管理器单例"""
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = AuthManager()
    return _auth_instance
