// api/nutstore_sync.dart — 坚果云 WebDAV 同步
// 凭据从桌面端 config.ini 内置，安装即用，无需手动配置
// 与桌面端 nutstore_sync.py 逻辑完全一致：时间戳对比 + 迁移
import 'dart:io' as io;
import 'dart:convert';
import 'package:webdav_client/webdav_client.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'local_db.dart';
import 'credential_store.dart';

class NutstoreSync {
  // ═══════════════════════════════════════════
  // 默认 WebDAV 服务器地址（不含凭据）
  // 凭据通过 SharedPreferences 安全存储，首次使用需在设置页面配置
  // ═══════════════════════════════════════════
  static const String _defaultServer = 'https://dav.jianguoyun.com/dav/';

  // 与桌面端 config.ini [Sync] remote_dir 完全一致
  static const String _remoteFolder = '/门店管理系统备份/';
  // 与桌面端 nutstore_sync.py REMOTE_DB 完全一致
  static const String _remoteDbName = 'restaurant_backup.db';
  // 与桌面端 REMOTE_META 一致
  static const String _remoteMetaName = 'sync_meta.json';

  Client? _client;
  bool _initialized = false;
  bool _syncBusy = false;

  /// 凭据版本号：当内置密码变更时递增，自动清除旧缓存
  static const int _credVersion = 2;

  /// 清除旧版缓存凭据（修复历史版本残留的错误密码）
  Future<void> _migrateCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    final savedVersion = prefs.getInt('cred_version') ?? 0;
    if (savedVersion < _credVersion) {
      await prefs.remove('webdav_server');
      await prefs.remove('webdav_username');
      await prefs.remove('webdav_password');
      await prefs.setInt('cred_version', _credVersion);
    }
  }

  Future<Client> _init() async {
    if (_initialized && _client != null) return _client!;

    await _migrateCredentials();

    final prefs = await SharedPreferences.getInstance();
    final store = CredentialStore();
    final server = prefs.getString('webdav_server') ?? _defaultServer;
    final username = prefs.getString('webdav_username') ?? store.username;
    final password = prefs.getString('webdav_password') ?? store.password;

    _client = newClient(
      server,
      user: username,
      password: password,
      debug: false,
    );
    _initialized = true;
    return _client!;
  }

  /// 本地元数据路径
  Future<String> get _localMetaPath async {
    final dir = await getApplicationDocumentsDirectory();
    return p.join(dir.path, 'sync_meta.json');
  }

  /// 读取本地时间戳
  Future<String?> _readLocalMeta() async {
    try {
      final path = await _localMetaPath;
      final file = io.File(path);
      if (await file.exists()) {
        final content = await file.readAsString();
        final json = jsonDecode(content) as Map<String, dynamic>;
        return json['last_upload'] as String?;
      }
    } catch (_) {}
    return null;
  }

  /// 写入本地时间戳
  Future<void> _writeLocalMeta(String timestamp) async {
    final path = await _localMetaPath;
    final file = io.File(path);
    await file.writeAsString(jsonEncode({'last_upload': timestamp}));
  }

  /// 读取云端时间戳
  Future<String?> _readRemoteMeta() async {
    try {
      final client = await _init();
      final remotePath = '$_remoteFolder$_remoteMetaName';
      final tmpPath = await _localMetaPath;
      final tmpFile = io.File('$tmpPath.remote.tmp');
      await client.read2File(remotePath, tmpFile.path);
      if (await tmpFile.exists()) {
        final content = await tmpFile.readAsString();
        await tmpFile.delete();
        if (content.isEmpty) return null;
        final json = jsonDecode(content) as Map<String, dynamic>;
        return json['last_upload'] as String?;
      }
    } catch (_) {}
    return null;
  }

  /// 写入云端时间戳
  Future<void> _writeRemoteMeta(String timestamp) async {
    try {
      final client = await _init();
      final remotePath = '$_remoteFolder$_remoteMetaName';
      final content = jsonEncode({'last_upload': timestamp});
      final tmpPath = await _localMetaPath;
      final tmpFile = io.File('$tmpPath.remote_write.tmp');
      await tmpFile.writeAsString(content);
      await client.writeFromFile(tmpFile.path, remotePath);
      await tmpFile.delete();
    } catch (_) {}
  }

  /// 从云端拉取数据库（覆盖本地）
  Future<bool> pullDatabase() async {
    final client = await _init();
    try {
      await client.mkdirAll(_remoteFolder);

      final remotePath = '$_remoteFolder$_remoteDbName';
      final localPath = await LocalDb.instance.dbPath;

      // 下载到临时文件
      final tmpPath = '$localPath.tmp';
      await client.read2File(remotePath, tmpPath);

      // 验证文件大小 > 0
      final tmpFile = io.File(tmpPath);
      final size = await tmpFile.length();
      if (size < 100) {
        await tmpFile.delete();
        return false;
      }

      // 替换本地数据库
      final localFile = io.File(localPath);
      if (await localFile.exists()) {
        await localFile.delete();
      }
      await io.File(tmpPath).rename(localPath);

      // 重新打开数据库并执行迁移（确保表结构为最新）
      await LocalDb.instance.reopen();

      // 同步元数据到本地
      final remoteMeta = await _readRemoteMeta();
      if (remoteMeta != null) {
        await _writeLocalMeta(remoteMeta);
      }
      return true;
    } catch (e) {
      return false;
    }
  }

  /// 推送本地数据库到云端
  Future<bool> pushDatabase() async {
    final client = await _init();
    try {
      await client.mkdirAll(_remoteFolder);

      final remotePath = '$_remoteFolder$_remoteDbName';
      final localPath = await LocalDb.instance.dbPath;

      await client.writeFromFile(localPath, remotePath);

      // 更新时间戳
      final now = DateTime.now().toIso8601String();
      await _writeLocalMeta(now);
      await _writeRemoteMeta(now);
      return true;
    } catch (e) {
      return false;
    }
  }

  /// 登录后双向同步（与桌面端 sync_on_login 逻辑一致）
  /// 返回同步结果描述
  Future<String> syncOnLogin() async {
    final client = await _init();
    _syncBusy = true;
    try {
      await client.mkdirAll(_remoteFolder);

      final remotePath = '$_remoteFolder$_remoteDbName';
      final localPath = await LocalDb.instance.dbPath;

      // 检查云端数据库是否存在（尝试读取元数据判断）
      bool remoteExists = false;
      try {
        final remoteMetaCheck = await _readRemoteMeta();
        // 如果有元数据，说明云端有数据
        if (remoteMetaCheck != null) {
          remoteExists = true;
        } else {
          // 没有元数据，尝试下载DB文件检查
          final tmpCheck = '$localPath.exist_check';
          await client.read2File(remotePath, tmpCheck);
          final checkFile = io.File(tmpCheck);
          if (await checkFile.exists() && await checkFile.length() > 100) {
            remoteExists = true;
          }
          if (await checkFile.exists()) await checkFile.delete();
        }
      } catch (_) {
        remoteExists = false;
      }

      // 读取时间戳
      final localTs = await _readLocalMeta();
      final remoteTs = await _readRemoteMeta();

      // 1. 云端无数据 → 上传本地（首次使用）
      if (!remoteExists) {
        final ok = await pushDatabase();
        return ok ? '首次同步：已上传本地数据到云端' : '上传失败';
      }

      // 2. 本地无元数据（新装） → 下载云端
      if (localTs == null) {
        final ok = await pullDatabase();
        return ok ? '新设备同步：已从云端下载数据' : '下载失败';
      }

      // 3. 对比时间戳
      if (remoteTs != null && localTs != null) {
        final remote = DateTime.tryParse(remoteTs);
        final local = DateTime.tryParse(localTs);

        if (remote != null && local != null) {
          if (remote.isAfter(local)) {
            // 云端较新 → 下载
            final ok = await pullDatabase();
            return ok ? '已从云端同步最新数据' : '下载失败';
          } else if (local.isAfter(remote)) {
            // 本地较新 → 上传
            final ok = await pushDatabase();
            return ok ? '已上传本地数据到云端' : '上传失败';
          } else {
            // 时间戳相等 → 不操作
            return '数据已是最新';
          }
        }
      }

      // 默认：下载云端
      final ok = await pullDatabase();
      return ok ? '已从云端同步数据' : '同步失败';
    } catch (e) {
      return '同步异常: $e';
    } finally {
      _syncBusy = false;
    }
  }

  /// 测试连接
  Future<bool> testConnection() async {
    try {
      final client = await _init();
      await client.ping();
      return true;
    } catch (e) {
      return false;
    }
  }

  /// 保存 WebDAV 凭据
  static Future<void> saveCredentials({
    required String server,
    required String username,
    required String password,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('webdav_server', server);
    await prefs.setString('webdav_username', username);
    await prefs.setString('webdav_password', password);
  }

  /// 获取当前凭据
  static Future<Map<String, String>> getCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    final store = CredentialStore();
    return {
      'server': prefs.getString('webdav_server') ?? _defaultServer,
      'username': prefs.getString('webdav_username') ?? store.username,
      'password': prefs.getString('webdav_password') ?? store.password,
    };
  }

  /// 是否已配置（凭据非空）
  static Future<bool> isConfigured() async {
    final creds = await getCredentials();
    return creds['username']!.isNotEmpty && creds['password']!.isNotEmpty;
  }
}
