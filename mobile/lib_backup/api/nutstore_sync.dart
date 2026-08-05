// api/nutstore_sync.dart — 坚果云 WebDAV 同步
import 'dart:io';
import 'package:webdav_client/webdav_client.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path/path.dart' as p;
import 'local_db.dart';

class NutstoreSync {
  static const String _remoteFolder = '/catering_mgt';
  static const String _dbFileName = 'catering.db';

  late Client _client;
  bool _initialized = false;

  Future<void> _init() async {
    if (_initialized) return;
    final prefs = await SharedPreferences.getInstance();

    final server = prefs.getString('webdav_server') ?? '';
    final username = prefs.getString('webdav_username') ?? '';
    final password = prefs.getString('webdav_password') ?? '';

    if (server.isEmpty || username.isEmpty || password.isEmpty) {
      throw Exception('WebDAV 凭据未配置');
    }

    _client = Client(
      Uri.parse(server),
      user: username,
      password: password,
      debug: false,
    );
    _initialized = true;
  }

  /// 拉取远程数据库
  Future<void> pullDatabase() async {
    await _init();
    try {
      // 确保远程目录存在
      await _client.mkdir(_remoteFolder);

      final remotePath = '$_remoteFolder/$_dbFileName';
      final localPath = await LocalDb.instance.dbPath;

      // 下载到临时文件
      final tmpPath = '$localPath.tmp';
      await _client.read2File(remotePath, tmpPath);

      // 替换本地数据库
      final localFile = File(localPath);
      if (await localFile.exists()) {
        await localFile.delete();
      }
      await File(tmpPath).rename(localPath);

      // 重新打开数据库
      await LocalDb.instance.reopen();
    } catch (e) {
      rethrow;
    }
  }

  /// 推送本地数据库到远程
  Future<void> pushDatabase() async {
    await _init();
    try {
      await _client.mkdir(_remoteFolder);

      final remotePath = '$_remoteFolder/$_dbFileName';
      final localPath = await LocalDb.instance.dbPath;

      await _client.writeFromFile(localPath, remotePath, overwrite: true);
    } catch (e) {
      rethrow;
    }
  }

  /// 测试连接
  Future<bool> testConnection() async {
    try {
      await _init();
      await _client.ping();
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

  /// 获取已保存的凭据
  static Future<Map<String, String>> getCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    return {
      'server': prefs.getString('webdav_server') ?? '',
      'username': prefs.getString('webdav_username') ?? '',
      'password': prefs.getString('webdav_password') ?? '',
    };
  }
}
