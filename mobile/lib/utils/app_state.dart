// utils/app_state.dart — 全局状态管理
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../api/nutstore_sync.dart';
import '../api/local_db.dart';

class AppState extends ChangeNotifier {
  String _username = '';
  String _displayName = '';
  String _role = 'EMPLOYEE';
  int? _storeId;
  String _storeName = '全部门店';
  bool _isLoggedIn = false;
  DateTime? _lastSyncTime;

  String get username => _username;
  String get displayName => _displayName;
  String get role => _role;
  int? get storeId => _storeId;
  String get storeName => _storeName;
  bool get isLoggedIn => _isLoggedIn;
  bool get isSyncing => _syncing;
  DateTime? get lastSyncTime => _lastSyncTime;

  bool _syncing = false;

  /// 恢复会话
  void restoreSession(String username, String displayName, String role) {
    _username = username;
    _displayName = displayName;
    _role = role;
    _isLoggedIn = true;
    notifyListeners();
  }

  /// 登录成功
  Future<void> login(String username, String displayName, String role) async {
    _username = username;
    _displayName = displayName;
    _role = role;
    _isLoggedIn = true;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('username', username);
    await prefs.setString('displayName', displayName);
    await prefs.setString('role', role);

    notifyListeners();
  }

  /// 登出
  Future<void> logout() async {
    _username = '';
    _displayName = '';
    _role = 'EMPLOYEE';
    _storeId = null;
    _storeName = '全部门店';
    _isLoggedIn = false;

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('username');
    await prefs.remove('displayName');
    await prefs.remove('role');

    notifyListeners();
  }

  /// 设置当前门店
  void setStore(int? storeId, String storeName) {
    _storeId = storeId;
    _storeName = storeName;
    notifyListeners();
  }

  /// 从数据库加载门店列表
  Future<List<Map<String, dynamic>>> loadStores() async {
    try {
      return await LocalDb.instance.query('stores', orderBy: 'id ASC');
    } catch (e) {
      debugPrint('Load stores error: $e');
      return [];
    }
  }

  /// 触发云同步（双向：对比时间戳，新的覆盖旧的）
  Future<String> sync() async {
    if (_syncing) return '同步进行中';
    _syncing = true;
    notifyListeners();

    try {
      final sync = NutstoreSync();
      final result = await sync.syncOnLogin();
      _lastSyncTime = DateTime.now();
      return result;
    } catch (e) {
      debugPrint('Sync error: $e');
      return '同步异常: $e';
    } finally {
      _syncing = false;
      notifyListeners();
    }
  }
}
