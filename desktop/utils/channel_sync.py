"""
云端渠道同步模块
将 revenue_channels 数据同步到坚果云 WebDAV，实现渠道数据云端共享
"""
import json
import io
import os
import configparser
import base64
import hashlib
import uuid
from cryptography.fernet import Fernet


def _get_webdav_client():
    """获取 WebDAV 客户端"""
    config_paths = [
        r'D:\RiderProjects\CateringMgt\desktop\config.ini',
        r'D:\Program Files\CateringMgt\config.ini',
    ]
    cp = configparser.ConfigParser()
    for p in config_paths:
        if os.path.exists(p):
            cp.read(p, encoding='utf-8')
            break

    server = cp.get('Nutstore', 'server', fallback='')
    user = cp.get('Nutstore', 'username', fallback='')
    pwd_stored = cp.get('Nutstore', 'password', fallback='')

    mac = uuid.getnode()
    salt = b'CateringMgt_Config_Salt_2024'
    key = hashlib.pbkdf2_hmac('sha256', str(mac).encode(), salt, 100000, dklen=32)
    pwd = Fernet(base64.urlsafe_b64encode(key)).decrypt(pwd_stored[4:].encode('ascii')).decode('utf-8')

    from webdav4.client import Client
    return Client(server, auth=(user, pwd), timeout=15)


def upload_channels(conn):
    """上传本地渠道到云端"""
    try:
        client = _get_webdav_client()
        cursor = conn.cursor()
        cursor.execute("SELECT id, channel_name, sort_order FROM revenue_channels ORDER BY sort_order, id")
        channels = [{"id": r[0], "channel_name": r[1], "sort_order": r[2]} for r in cursor.fetchall()]
        data = json.dumps({'channels': channels}, ensure_ascii=False).encode('utf-8')
        client.upload_fileobj(io.BytesIO(data), '/餐饮综合管理系统/认证/channels.json', overwrite=True)
        return True
    except Exception as e:
        print(f"上传渠道失败: {e}")
        return False


def download_channels(conn):
    """从云端下载渠道并同步到本地数据库"""
    try:
        client = _get_webdav_client()
        buf = io.BytesIO()
        client.download_fileobj('/餐饮综合管理系统/认证/channels.json', buf)
        buf.seek(0)
        data = json.loads(buf.read().decode('utf-8'))
        cloud_channels = data.get('channels', [])

        cursor = conn.cursor()
        # 获取本地渠道
        cursor.execute("SELECT id, channel_name FROM revenue_channels")
        local_channels = {dict(r)['channel_name']: dict(r)['id'] for r in cursor.fetchall()}
        cloud_names = {c['channel_name'] for c in cloud_channels}

        # 新增云端有但本地没有的渠道
        for c in cloud_channels:
            if c['channel_name'] not in local_channels:
                cursor.execute(
                    "INSERT INTO revenue_channels (channel_name, sort_order) VALUES (?,?)",
                    (c['channel_name'], c.get('sort_order', 0))
                )

        # 删除本地有但云端没有的渠道（可选，保守起见暂不删除）

        conn.commit()
        return True
    except Exception as e:
        # 404 说明云端还没有 channels.json，首次使用
        if '404' in str(e):
            print("云端尚无 channels.json，将上传本地数据")
            return upload_channels(conn)
        print(f"下载渠道失败: {e}")
        return False


if __name__ == '__main__':
    import sqlite3
    db = os.path.expandvars(r'%APPDATA%\CateringMgt\data\restaurant.db')
    if not os.path.exists(db):
        db = r'D:\RiderProjects\CateringMgt\desktop\data\restaurant.db'
    conn = sqlite3.connect(db)
    upload_channels(conn)
    print("渠道已上传到云端")
    conn.close()