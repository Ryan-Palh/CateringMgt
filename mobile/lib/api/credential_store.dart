// credential_store.dart — 凭据加密存储
//
// 坚果云凭据使用 AES-256-CBC 加密后内置在源码中，运行时通过密钥派生解密。
// 密钥由「应用包名 + 固定盐 + PBKDF2」派生，与设备无关，仅防止反编译直接读取明文。
//
// 加密方式：AES-256-CBC，PKCS7 填充，IV 前 16 字节嵌入密文。
// 生成密文（桌面端执行）：
//   python3 generate_encrypted_credentials.py
// 然后将输出的 base64 密文替换下面的常量即可。

import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart' as crypto;
import 'package:pointycastle/export.dart';

/// 密钥派生参数（不可修改，否则需重新生成密文）
const String _appId = 'com.catering.restaurant_mgt';
const String _kdfSalt = 'CateringMgt_Nutstore_KDF_v2';
const int _pbkdf2Iterations = 100000;
const int _keyLength = 32; // AES-256

/// ═══════════════════════════════════════════
/// 加密后的凭据密文（Base64）
/// 由 generate_encrypted_credentials.py 生成
/// ═══════════════════════════════════════════

// 加密后的 Nutstore 用户名
const String _encryptedUsername =
    'N6CEgdLWbthEcrcYv/wYWVGgdiM0K92KWjQd0DZf0C25XIAOHuxCZmaD8gNGfFZ8';

// 加密后的 Nutstore 密码
const String _encryptedPassword =
    '0Fk+0jWKHwsxNzCJBSN8p3BxRYjrd9oGlcFIHulzAyI5zI3GsS1E5HUJy8yRPp4Y';

/// ═══════════════════════════════════════════
/// 密钥派生
/// ═══════════════════════════════════════════

Uint8List _deriveKey() {
  final pbkdf2 = PBKDF2KeyDerivator(HMac(SHA256Digest(), 64));
  pbkdf2.init(Pbkdf2Parameters(
    utf8.encode(_kdfSalt) as Uint8List,
    _pbkdf2Iterations,
    _keyLength,
  ));
  return pbkdf2.process(utf8.encode(_appId) as Uint8List);
}

/// ═══════════════════════════════════════════
/// AES-256-CBC 解密
/// ═══════════════════════════════════════════

String _decrypt(String base64Ciphertext) {
  // 密文结构: IV(16 bytes) + Ciphertext
  final raw = base64.decode(base64Ciphertext);
  final iv = raw.sublist(0, 16);
  final ciphertext = raw.sublist(16);

  final key = _deriveKey();
  final params = ParametersWithIV(KeyParameter(key), iv);

  final cipher = PaddedBlockCipherImpl(
    PKCS7Padding(),
    CBCBlockCipher(AESEngine()),
  );
  cipher.init(false, params);

  final decrypted = Uint8List(ciphertext.length);
  var offset = 0;
  while (offset < ciphertext.length) {
    offset += cipher.processBlock(ciphertext, offset, decrypted, offset);
  }

  // 去除 PKCS7 填充
  final padLen = decrypted.last;
  return utf8.decode(decrypted.sublist(0, decrypted.length - padLen));
}

/// ═══════════════════════════════════════════
/// 公开接口
/// ═══════════════════════════════════════════

class CredentialStore {
  static final CredentialStore _instance = CredentialStore._();
  factory CredentialStore() => _instance;
  CredentialStore._();

  String? _cachedUsername;
  String? _cachedPassword;

  /// 获取解密后的用户名
  String get username {
    _cachedUsername ??= _decrypt(_encryptedUsername);
    return _cachedUsername!;
  }

  /// 获取解密后的密码
  String get password {
    _cachedPassword ??= _decrypt(_encryptedPassword);
    return _cachedPassword!;
  }

  /// 是否已配置有效凭据
  bool get isConfigured {
    try {
      return username.isNotEmpty && password.isNotEmpty;
    } catch (_) {
      return false;
    }
  }
}