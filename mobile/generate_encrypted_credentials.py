#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成加密凭据密文，用于 credential_store.dart

用法：
  python generate_encrypted_credentials.py

输出：
  - 加密后的用户名和密码（Base64）
  - 直接替换 credential_store.dart 中的 _encryptedUsername / _encryptedPassword 常量

加密方式：
  AES-256-CBC + PKCS7 padding
  密钥 = PBKDF2-HMAC-SHA256(appId, salt, iterations=100000, dklen=32)
  密文结构: IV(16 bytes) || ciphertext
"""

import hashlib
import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ═══════════════════════════════════════════
# 与 credential_store.dart 完全一致的参数
# ═══════════════════════════════════════════
APP_ID = 'com.catering.restaurant_mgt'
KDF_SALT = b'CateringMgt_Nutstore_KDF_v2'
PBKDF2_ITERATIONS = 100000
KEY_LENGTH = 32  # AES-256

# ═══════════════════════════════════════════
# 待加密的凭据（从 config.ini 读取或手动输入）
# ═══════════════════════════════════════════

def _decrypt_config_password(stored: str) -> str:
    """解密 config.ini 中的密码 (fer: / b64: / 明文)"""
    if not stored:
        return ""
    if not stored.startswith(("fer:", "b64:")):
        return stored  # 明文
    if stored.startswith("fer:"):
        try:
            from cryptography.fernet import Fernet
            raw_key = hashlib.sha256(b"RestaurantMgt_2024_SecretKey_XOR").digest()
            fernet_key = base64.urlsafe_b64encode(raw_key)
            return Fernet(fernet_key).decrypt(stored[4:].encode('ascii')).decode('utf-8')
        except Exception:
            return ""
    if stored.startswith("b64:"):
        try:
            return base64.b64decode(stored[4:]).decode('utf-8')
        except Exception:
            return stored
    return stored


def get_credentials_from_config():
    """尝试从桌面端 config.ini 读取凭据（自动解密）"""
    import configparser
    config_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                     'desktop', 'config.ini'),
        os.path.join(os.path.dirname(__file__), '..', 'desktop', 'config.ini'),
    ]
    for cp_path in config_paths:
        if os.path.exists(cp_path):
            cp = configparser.ConfigParser()
            cp.read(cp_path, encoding='utf-8')
            user = cp.get('Nutstore', 'username', fallback='')
            pwd_raw = cp.get('Nutstore', 'password', fallback='')
            pwd = _decrypt_config_password(pwd_raw)
            if user and pwd:
                return user, pwd
    return None, None


def derive_key():
    """派生 AES-256 密钥"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=KDF_SALT,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(APP_ID.encode('utf-8'))


def encrypt(plaintext: str) -> str:
    """AES-256-CBC 加密，返回 Base64(IV + ciphertext)"""
    key = derive_key()
    iv = os.urandom(16)

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode('utf-8')) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return base64.b64encode(iv + ciphertext).decode('ascii')


def main():
    username, password = get_credentials_from_config()

    if not username or not password:
        print("未找到 config.ini 中的凭据，请手动输入：")
        username = input("用户名: ").strip()
        password = input("密码: ").strip()

    if not username or not password:
        print("错误：用户名和密码不能为空")
        return

    print("\n正在加密凭据...\n")
    encrypted_user = encrypt(username)
    encrypted_pwd = encrypt(password)

    print("=" * 60)
    print("  将以下常量替换到 credential_store.dart 中：")
    print("=" * 60)
    print()
    print(f'const String _encryptedUsername =')
    print(f"    '{encrypted_user}';")
    print()
    print(f'const String _encryptedPassword =')
    print(f"    '{encrypted_pwd}';")
    print()
    print("=" * 60)

    # 自动更新 credential_store.dart
    dart_path = os.path.join(os.path.dirname(__file__), 'lib', 'api', 'credential_store.dart')
    if os.path.exists(dart_path):
        with open(dart_path, 'r', encoding='utf-8') as f:
            content = f.read()

        content = content.replace(
            "'REPLACE_WITH_ENCRYPTED_USERNAME_BASE64'",
            f"'{encrypted_user}'"
        )
        content = content.replace(
            "'REPLACE_WITH_ENCRYPTED_PASSWORD_BASE64'",
            f"'{encrypted_pwd}'"
        )

        with open(dart_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"\n✓ 已自动更新 {dart_path}")
    else:
        print(f"\n⚠ 未找到 {dart_path}，请手动替换")


if __name__ == '__main__':
    main()