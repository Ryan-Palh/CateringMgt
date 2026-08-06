# -*- coding: utf-8 -*-
"""
坚果云双向同步模块
通过 WebDAV 协议实现数据库双向同步

核心机制：
- 本地修改后防抖上传（trigger_sync）
- 登录后对比本地/云端时间戳，新的覆盖旧的（sync_on_login）
- 云端存储 meta.json 记录最后上传时间戳
- 整库同步：本地删除 → commit → 上传 → 云端同步删除
"""
import os
import json
import threading
import time
from datetime import datetime
from webdav4.client import Client

from utils.logger import logger
from utils.config import get_nutstore_credentials, get_sync_config, get_db_path

# 防抖同步：短时间内多次修改只上传一次
_DEBOUNCE_DELAY = 2.0  # 秒

# 从配置读取
NUTSTORE_URL, NUTSTORE_USER, NUTSTORE_PWD = get_nutstore_credentials()
BACKUP_INTERVAL, REMOTE_DIR = get_sync_config()
DB_PATH = get_db_path()

# 云端文件名
REMOTE_DB = f"{REMOTE_DIR}restaurant_backup.db"
REMOTE_META = f"{REMOTE_DIR}sync_meta.json"

# 本地元数据文件（记录最后上传时间）
LOCAL_META = os.path.join(os.path.dirname(DB_PATH), "sync_meta.json")


class NutstoreSync:
    """坚果云双向同步管理"""

    def __init__(self):
        self.client = None
        self._connected = False
        self._stop_flag = False
        self._thread = None
        self._last_sync_time = None
        self._debounce_timer = None
        self._debounce_lock = threading.Lock()
        self._sync_lock = threading.RLock()  # 可重入锁，允许 sync_on_login 内部调用 upload_db/download_db
        self._sync_busy = False  # sync_on_login 进行中标记，防止 trigger_sync 竞态上传
        self._init_client()

    def _init_client(self):
        import traceback
        try:
            self.client = Client(
                NUTSTORE_URL,
                auth=(NUTSTORE_USER, NUTSTORE_PWD)
            )
            # 测试连接
            self.client.ls("/")
            self._connected = True
            logger.info("坚果云同步连接成功")
        except Exception as e:
            self._connected = False
            logger.error(f"坚果云连接失败: {e}")
            try:
                log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
                os.makedirs(log_dir, exist_ok=True)
                with open(os.path.join(log_dir, "sync_debug.log"), "w", encoding="utf-8") as f:
                    f.write(f"时间: {datetime.now()}\n")
                    f.write(f"错误: {e}\n")
                    f.write(f"类型: {type(e).__name__}\n")
                    f.write(f"\n回溯:\n")
                    traceback.print_exc(file=f)
            except Exception as log_err:
                logger.error(f"写诊断日志失败: {log_err}")

    @property
    def is_connected(self):
        return self._connected

    def ensure_remote_dir(self):
        """确保远程目录存在"""
        try:
            self.client.mkdir(REMOTE_DIR)
        except Exception:
            pass  # 目录已存在

    # ═══════════════════════════════════════
    # 元数据读写（时间戳对比的核心）
    # ═══════════════════════════════════════

    def _read_local_meta(self):
        """读取本地元数据，返回最后上传时间戳（ISO 字符串），无则返回 None"""
        try:
            if os.path.exists(LOCAL_META):
                with open(LOCAL_META, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("last_upload")
        except Exception as e:
            logger.warning(f"读取本地元数据失败: {e}")
        return None

    def _write_local_meta(self, timestamp_str):
        """写入本地元数据"""
        try:
            with open(LOCAL_META, "w", encoding="utf-8") as f:
                json.dump({"last_upload": timestamp_str}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"写入本地元数据失败: {e}")

    def _read_remote_meta(self):
        """读取云端元数据，返回最后上传时间戳，无则返回 None"""
        if not self._connected:
            return None
        try:
            import io
            buf = io.BytesIO()
            self.client.download_fileobj(REMOTE_META, buf)
            buf.seek(0)
            data = json.loads(buf.read().decode("utf-8"))
            return data.get("last_upload")
        except Exception:
            # 云端无元数据文件
            return None

    def _upload_meta(self, timestamp_str):
        """上传元数据到云端"""
        if not self._connected:
            return
        try:
            import io
            data = json.dumps({"last_upload": timestamp_str}, ensure_ascii=False).encode("utf-8")
            buf = io.BytesIO(data)
            self.client.upload_fileobj(buf, REMOTE_META, overwrite=True)
        except Exception as e:
            logger.warning(f"上传元数据失败: {e}")

    def _get_remote_db_mtime(self):
        """获取云端数据库文件的修改时间，返回 datetime 或 None"""
        if not self._connected:
            return None
        try:
            files = self.client.ls(REMOTE_DIR)
            for f in files:
                if f.get("name") == "restaurant_backup.db":
                    mtime_str = f.get("modified") or f.get("mtime")
                    if mtime_str:
                        # webdav4 返回的可能是 ISO 格式字符串
                        try:
                            return datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
                        except Exception:
                            try:
                                return datetime.strptime(mtime_str, "%a, %d %b %Y %H:%M:%S %Z")
                            except Exception:
                                return None
            return None
        except Exception as e:
            logger.warning(f"获取云端文件信息失败: {e}")
            return None

    # ═══════════════════════════════════════
    # 上传 / 下载
    # ═══════════════════════════════════════

    def upload_db(self):
        """上传数据库文件 + 元数据到坚果云"""
        if not self._connected:
            return False, "未连接到坚果云"

        if not os.path.exists(DB_PATH):
            return False, "数据库文件不存在"

        with self._sync_lock:
            # WAL checkpoint: 确保所有写入已持久化到主数据库文件（在锁内执行，避免与download_db竞争）
            try:
                import sqlite3 as _sqlite3
                _ckpt_conn = _sqlite3.connect(DB_PATH)
                _ckpt_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                _ckpt_conn.close()
            except Exception as e:
                logger.warning(f"WAL checkpoint 失败(非致命): {e}")
            try:
                self.ensure_remote_dir()
                # 上传数据库
                self.client.upload_file(DB_PATH, REMOTE_DB, overwrite=True)
                # 上传元数据（当前时间戳）
                now_str = datetime.now().isoformat()
                self._upload_meta(now_str)
                self._write_local_meta(now_str)
                self._last_sync_time = datetime.now()
                logger.info("数据库上传成功（含元数据）")
                return True, "上传成功"
            except Exception as e:
                logger.error(f"数据库上传失败: {e}")
                return False, f"上传失败: {e}"

    def download_db(self):
        """从坚果云下载数据库（覆盖本地）"""
        if not self._connected:
            return False, "未连接到坚果云"

        with self._sync_lock:
            try:
                # 先下载到临时文件，验证完整性后再覆盖
                tmp_path = DB_PATH + ".tmp"
                self.client.download_file(REMOTE_DB, tmp_path)
                # 验证下载的文件是有效的 SQLite 数据库
                import sqlite3
                try:
                    test_conn = sqlite3.connect(tmp_path)
                    test_conn.execute("SELECT 1")
                    test_conn.close()
                except Exception as e:
                    os.remove(tmp_path)
                    return False, f"下载的数据库文件无效: {e}"
                # 验证通过，替换本地文件
                if os.path.exists(DB_PATH):
                    # 使用 shutil.move 替代 os.replace，支持跨文件系统
                    import shutil
                    shutil.move(tmp_path, DB_PATH)
                else:
                    os.rename(tmp_path, DB_PATH)
                # 同步元数据到本地
                remote_meta = self._read_remote_meta()
                if remote_meta:
                    self._write_local_meta(remote_meta)
                # 下载后重新执行数据库迁移，确保表结构为最新
                try:
                    from database.db_manager import migrate_database
                    migrate_database()
                    logger.info("下载后数据库迁移完成")
                except Exception as me:
                    logger.warning(f"下载后数据库迁移失败: {me}")
                logger.info("数据库从云端下载成功")
                return True, "下载成功"
            except Exception as e:
                logger.error(f"数据库下载失败: {e}")
                return False, f"下载失败: {e}"

    # ═══════════════════════════════════════
    # 双向同步核心逻辑
    # ═══════════════════════════════════════

    def sync_on_login(self):
        """登录后双向同步：对比本地/云端时间戳，新的覆盖旧的

        判断逻辑：
        1. 云端无数据 → 上传本地（首次使用）
        2. 本地无元数据（新装） → 下载云端
        3. 云端时间戳 > 本地时间戳 → 下载云端
        4. 本地时间戳 > 云端时间戳 → 上传本地
        5. 时间戳相等 → 不操作
        """
        if not self._connected:
            logger.warning("坚果云未连接，跳过登录同步")
            return "未连接云端"

        self._sync_busy = True
        try:
            return self._do_sync_on_login()
        finally:
            self._sync_busy = False

    def _do_sync_on_login(self):
        """sync_on_login 的实际实现"""
        with self._sync_lock:
            local_ts = self._read_local_meta()
            remote_ts = self._read_remote_meta()

            logger.info(f"双向同步: 本地时间戳={local_ts}, 云端时间戳={remote_ts}")

            # 情况1：云端无元数据 → 首次使用，上传本地
            if remote_ts is None:
                if os.path.exists(DB_PATH):
                    success, msg = self.upload_db()
                    if success:
                        logger.info("首次同步：本地数据已上传到云端")
                        return "首次上传成功"
                    return f"首次上传失败: {msg}"
                return "本地和云端均无数据"

            # 情况2：本地无元数据（新安装/卸载重装） → 下载云端
            if local_ts is None:
                success, msg = self.download_db()
                if success:
                    logger.info("新设备同步：云端数据已下载到本地")
                    return "已从云端恢复数据"
                return f"云端恢复失败: {msg}"

            # 情况3 & 4 & 5：对比时间戳
            try:
                local_dt = datetime.fromisoformat(local_ts)
                remote_dt = datetime.fromisoformat(remote_ts)
            except Exception as e:
                logger.warning(f"时间戳解析失败: {e}，回退到本地文件修改时间对比")
                # 回退：用本地 db 文件修改时间 vs 云端修改时间
                local_dt = datetime.fromtimestamp(os.path.getmtime(DB_PATH)) if os.path.exists(DB_PATH) else datetime.min
                remote_dt = self._get_remote_db_mtime() or datetime.min

            if remote_dt > local_dt:
                # 云端更新 → 下载
                success, msg = self.download_db()
                if success:
                    logger.info(f"双向同步：云端更新 ({remote_ts}) > 本地 ({local_ts})，已下载")
                    return "云端数据较新，已同步到本地"
                return f"下载失败: {msg}"

            elif local_dt > remote_dt:
                # 本地更新 → 上传
                success, msg = self.upload_db()
                if success:
                    logger.info(f"双向同步：本地更新 ({local_ts}) > 云端 ({remote_ts})，已上传")
                    return "本地数据较新，已同步到云端"
                return f"上传失败: {msg}"

            else:
                # 时间戳相等 → 无需操作
                logger.info("双向同步：本地与云端时间戳一致，无需同步")
                return "数据已是最新"

    # ═══════════════════════════════════════
    # 防抖上传（本地修改后触发）
    # ═══════════════════════════════════════

    def trigger_sync(self):
        """触发防抖同步：本地数据修改后调用，延迟上传

        短时间内多次调用只会触发一次上传，避免频繁写网络。
        如果 sync_on_login 正在进行中，跳过上传（防止竞态覆盖）。
        """
        if not self._connected:
            return
        if self._sync_busy:
            logger.debug("sync_on_login 进行中，跳过 trigger_sync")
            return
        with self._debounce_lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(_DEBOUNCE_DELAY, self._do_sync)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _do_sync(self):
        """执行实际的上传操作（由防抖定时器触发）"""
        try:
            success, msg = self.upload_db()
            if success:
                logger.info(f"实时同步完成: {datetime.now().strftime('%H:%M:%S')}")
            else:
                logger.warning(f"实时同步失败: {msg}")
        except Exception as e:
            logger.error(f"实时同步异常: {e}")

    # ═══════════════════════════════════════
    # 其他工具方法
    # ═══════════════════════════════════════

    def upload_export(self, local_path, remote_filename):
        """上传导出文件到坚果云"""
        if not self._connected or not os.path.exists(local_path):
            return False
        try:
            self.ensure_remote_dir()
            self.client.upload_file(local_path, f"{REMOTE_DIR}{remote_filename}", overwrite=True)
            return True
        except Exception as e:
            logger.error(f"导出文件上传失败: {e}")
            return False

    def list_backups(self):
        """列出远程备份文件"""
        if not self._connected:
            return []
        try:
            files = self.client.ls(REMOTE_DIR)
            return [f.get('name', '') for f in files if f.get('type') != 'directory']
        except Exception as e:
            logger.error(f"列出备份文件失败: {e}")
            return []

    def start_auto_sync(self):
        """启动自动同步线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag = False
        self._thread = threading.Thread(target=self._auto_sync_loop, daemon=True)
        self._thread.start()
        logger.info(f"坚果云自动同步已启动，间隔 {BACKUP_INTERVAL} 秒")

    def stop_auto_sync(self):
        """停止自动同步"""
        self._stop_flag = True

    def _auto_sync_loop(self):
        """自动同步循环（定期上传保持云端最新）"""
        while not self._stop_flag:
            time.sleep(BACKUP_INTERVAL)
            if not self._stop_flag:
                success, msg = self.upload_db()
                if success:
                    logger.info(f"自动备份完成: {datetime.now().strftime('%H:%M:%S')}")
                else:
                    logger.warning(f"自动备份失败: {msg}")

    def get_last_sync_info(self):
        """获取最后同步信息"""
        if self._last_sync_time:
            return f"上次同步: {self._last_sync_time.strftime('%Y-%m-%d %H:%M:%S')}"
        return "尚未同步"


# 全局单例
_sync_instance = None

def get_sync():
    """获取坚果云同步实例（单例）"""
    global _sync_instance
    if _sync_instance is None:
        _sync_instance = NutstoreSync()
    return _sync_instance
