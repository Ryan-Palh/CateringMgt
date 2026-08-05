// api/auth_manager.dart — 用户认证（与桌面端 auth_manager.py 逻辑一致）
// 直接使用 http 包 + Basic Auth 从坚果云下载 users.json 验证
// 绕过 webdav_client 包的认证兼容性问题
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:crypto/crypto.dart' as crypto;
import 'package:bcrypt/bcrypt.dart';
import 'credential_store.dart';

// 与桌面端 config.ini [Auth] 完全一致
const String _authRemotePath =
    'https://dav.jianguoyun.com/dav/餐饮管理系统同步/users.json';

// 凭据通过 SharedPreferences 存储，首次使用需在设置页面配置
// 桌面端 config.ini 中的凭据应通过安全渠道传输给移动端，不可硬编码

/// 凭据版本号：当内置密码变更时递增，自动清除 SharedPreferences 中的旧缓存
const int _credentialVersion = 3;

class AuthUser {
  final String username;
  final String passwordHash;
  final String displayName;
  final String role;
  final bool enabled;

  AuthUser({
    required this.username,
    required this.passwordHash,
    required this.displayName,
    required this.role,
    required this.enabled,
  });

  factory AuthUser.fromMap(Map<String, dynamic> d) {
    return AuthUser(
      username: d['username'] ?? '',
      passwordHash: d['passwordHash'] ?? '',
      displayName: d['displayName'] ?? '',
      role: d['role'] ?? 'EMPLOYEE',
      enabled: d['enabled'] ?? true,
    );
  }
}

class AuthSession {
  final String username;
  final String role;
  final String displayName;

  AuthSession({
    required this.username,
    required this.role,
    required this.displayName,
  });
}

class AuthManager {
  static final AuthManager _instance = AuthManager._internal();
  factory AuthManager() => _instance;
  AuthManager._internal();

  List<AuthUser>? _usersCache;
  DateTime? _cacheTime;
  String? _lastError;

  /// 检查并清除旧版缓存凭据
  Future<void> _migrateCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    final savedVersion = prefs.getInt('cred_version') ?? 0;
    if (savedVersion < _credentialVersion) {
      // 清除旧凭据和会话，使用内置默认值
      await prefs.remove('webdav_server');
      await prefs.remove('webdav_username');
      await prefs.remove('webdav_password');
      await prefs.remove('username');
      await prefs.remove('displayName');
      await prefs.remove('role');
      await prefs.setInt('cred_version', _credentialVersion);
    }
  }

  /// 获取 Basic Auth header
  /// 优先使用 SharedPreferences 中的自定义凭据，否则使用内置加密凭据
  Future<String> _getAuthHeader() async {
    await _migrateCredentials();
    final prefs = await SharedPreferences.getInstance();
    final store = CredentialStore();
    final username = prefs.getString('webdav_username') ?? store.username;
    final password = prefs.getString('webdav_password') ?? store.password;
    final credentials = base64Encode(utf8.encode('$username:$password'));
    return 'Basic $credentials';
  }

  /// 从坚果云下载用户列表
  Future<List<AuthUser>?> fetchUsers({bool useCache = true}) async {
    if (useCache && _usersCache != null && _cacheTime != null) {
      if (DateTime.now().difference(_cacheTime!).inSeconds < 10) {
        return _usersCache;
      }
    }

    _lastError = null;
    try {
      final authHeader = await _getAuthHeader();

      final response = await http.get(
        Uri.parse(_authRemotePath),
        headers: {
          'Authorization': authHeader,
          'Accept': 'application/json',
        },
      ).timeout(const Duration(seconds: 15));

      if (response.statusCode != 200) {
        _lastError = 'HTTP ${response.statusCode}';
        return null;
      }

      final body = utf8.decode(response.bodyBytes);
      if (body.isEmpty) {
        _lastError = 'users.json 内容为空';
        return null;
      }

      final data = jsonDecode(body) as Map<String, dynamic>;
      final usersList = data['users'] as List? ?? [];
      _usersCache =
          usersList.map((u) => AuthUser.fromMap(u as Map<String, dynamic>)).toList();
      _cacheTime = DateTime.now();
      return _usersCache;
    } catch (e) {
      _lastError = e.toString();
      return null;
    }
  }

  /// 获取最后的错误信息（用于调试）
  String? get lastError => _lastError;

  /// 登录验证：从坚果云 users.json 验证用户名+密码
  Future<AuthSession?> login(String username, String password) async {
    final users = await fetchUsers();
    if (users == null) return null;

    for (final u in users) {
      if (u.username == username) {
        if (!u.enabled) return null;
        if (!verifyPassword(password, u.passwordHash)) return null;
        return AuthSession(
          username: u.username,
          role: u.role,
          displayName: u.displayName.isNotEmpty ? u.displayName : u.username,
        );
      }
    }
    return null;
  }

  /// 验证密码（与桌面端 verify_password 逻辑完全一致）
  /// 支持 bcrypt($2b$/$2a$/$2y$)、SHA-256加盐(sha256:salt:hash)、旧格式(salt:hash)、无盐SHA-256
  bool verifyPassword(String password, String storedHash) {
    if (storedHash.isEmpty) return false;
    try {
      // bcrypt 格式
      if (storedHash.startsWith(r'$2')) {
        try {
          return BCrypt.checkpw(password, storedHash);
        } catch (_) {
          return false;
        }
      }
      // SHA-256 加盐格式 (sha256:salt:hash)
      if (storedHash.startsWith('sha256:')) {
        final parts = storedHash.split(':');
        if (parts.length == 3) {
          final salt = parts[1];
          final expected = parts[2];
          final hash =
              crypto.sha256.convert(utf8.encode('$salt:$password')).toString();
          return hash == expected;
        }
        return false;
      }
      // 旧格式 (salt:hash)
      if (storedHash.contains(':')) {
        final idx = storedHash.indexOf(':');
        final salt = storedHash.substring(0, idx);
        final hashed = storedHash.substring(idx + 1);
        final hash =
            crypto.sha256.convert(utf8.encode('$salt:$password')).toString();
        return hash == hashed;
      }
      // 无盐 SHA-256
      return crypto.sha256.convert(utf8.encode(password)).toString() ==
          storedHash;
    } catch (_) {
      return false;
    }
  }
}
