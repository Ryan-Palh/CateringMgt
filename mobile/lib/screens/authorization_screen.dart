// screens/authorization_screen.dart — 授权管理（与桌面端3Tab对齐：用户管理/门店授权/员工授权）
import 'dart:convert';
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class AuthorizationScreen extends StatefulWidget {
  const AuthorizationScreen({super.key});

  @override
  State<AuthorizationScreen> createState() => _AuthorizationScreenState();
}

class _AuthorizationScreenState extends State<AuthorizationScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: TabBar(
        controller: _tabController,
        labelColor: Colors.white,
        unselectedLabelColor: AppColors.textSecondary,
        indicatorSize: TabBarIndicatorSize.tab,
        indicator: BoxDecoration(
          gradient: const LinearGradient(colors: [AppColors.primary, AppColors.info]),
          borderRadius: BorderRadius.circular(AppRadius.sm),
        ),
        tabs: const [
          Tab(text: '员工授权'),
          Tab(text: '门店授权'),
          Tab(text: '用户管理'),
        ],
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          _EmployeeAuthTab(),
          _StoreAuthTab(),
          _UserMgmtTab(),
        ],
      ),
    );
  }
}

// ── Tab1: 员工授权 ──
class _EmployeeAuthTab extends StatefulWidget {
  const _EmployeeAuthTab();

  @override
  State<_EmployeeAuthTab> createState() => _EmployeeAuthTabState();
}

class _EmployeeAuthTabState extends State<_EmployeeAuthTab> {
  List<Map<String, dynamic>> _employees = [];
  bool _loading = true;
  String _keyword = '';

  static const _tabPermissions = [
    ('dashboard', '工作台'), ('revenue', '营业额'), ('purchase', '进销存管理'),
    ('table_mgt', '桌台管理'), ('finance', '收支管理'), ('employee', '员工管理'),
    ('shifts', '排班管理'), ('attendance', '考勤管理'), ('salary', '工资管理'),
    ('reimbursement', '报销管理'), ('approval', '审批中心'), ('cost_calc', '成本核算'),
    ('reports', '报表中心'), ('store_manager', '门店管理'), ('authorization', '授权管理'),
  ];

  static const _roleMap = {
    'super_admin': '超级管理员', 'admin': '管理员', 'store_manager': '店长',
    'supervisor': '主管', 'employee': '员工',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      if (_keyword.isNotEmpty) {
        _employees = await LocalDb.instance.rawQuery(
          '''SELECT e.id, e.name, e.position, e.role, e.permissions, e.store_id,
                    s.name as store_name
             FROM employees e LEFT JOIN stores s ON e.store_id = s.id
             WHERE e.name LIKE ? ORDER BY e.name''',
          ['%$_keyword%'],
        );
      } else {
        _employees = await LocalDb.instance.rawQuery(
          '''SELECT e.id, e.name, e.position, e.role, e.permissions, e.store_id,
                    s.name as store_name
             FROM employees e LEFT JOIN stores s ON e.store_id = s.id
             ORDER BY e.name''',
        );
      }
    } catch (e) {
      debugPrint('EmployeeAuth load error: $e');
    }
    setState(() => _loading = false);
  }

  String _formatPermissions(String? permsStr) {
    if (permsStr == null || permsStr.isEmpty) return '无';
    try {
      List<dynamic> perms;
      if (permsStr.startsWith('[')) {
        perms = jsonDecode(permsStr);
      } else {
        perms = permsStr.split(',');
      }
      final names = <String>[];
      for (final p in perms) {
        final ps = p.toString().trim();
        for (final (key, name) in _tabPermissions) {
          if (key == ps) {
            names.add(name);
            break;
          }
        }
      }
      return names.isEmpty ? '无' : names.join('、');
    } catch (_) {
      return '无';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: TextField(
                    decoration: InputDecoration(
                      hintText: '搜索员工姓名...',
                      prefixIcon: const Icon(Icons.search),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.sm)),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    ),
                    onChanged: (v) {
                      _keyword = v;
                      _load();
                    },
                  ),
                ),
                Expanded(
                  child: _employees.isEmpty
                      ? Center(child: Text('暂无员工数据', style: TextStyle(color: AppColors.textSecondary)))
                      : ListView.builder(
                          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                          itemCount: _employees.length,
                          itemBuilder: (ctx, i) {
                            final emp = _employees[i];
                            final roleDisplay = _roleMap[emp['role'] as String?] ?? '员工';
                            return Card(
                              child: ListTile(
                                leading: CircleAvatar(
                                  backgroundColor: AppColors.primary.withValues(alpha: 0.1),
                                  child: Text(
                                    (emp['name'] as String? ?? '?')[0],
                                    style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold),
                                  ),
                                ),
                                title: Text(emp['name'] as String? ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
                                subtitle: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('${emp['position'] ?? '未设置'} · $roleDisplay · ${emp['store_name'] ?? '未分配'}'),
                                    const SizedBox(height: 2),
                                    Text(
                                      '权限: ${_formatPermissions(emp['permissions'] as String?)}',
                                      style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ],
                                ),
                                trailing: IconButton(
                                  icon: const Icon(Icons.edit_note, color: AppColors.primary),
                                  onPressed: () => _showAuthDialog(emp),
                                ),
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: _load,
        child: const Icon(Icons.refresh),
      ),
    );
  }

  void _showAuthDialog(Map<String, dynamic> emp) async {
    final stores = await LocalDb.instance.rawQuery('SELECT id, name FROM stores ORDER BY id');
    final empId = emp['id'] as int;
    String role = emp['role'] as String? ?? 'employee';
    int? storeId = emp['store_id'] as int?;
    Set<String> perms = {};
    final permsStr = emp['permissions'] as String?;
    if (permsStr != null && permsStr.isNotEmpty) {
      try {
        List<dynamic> list;
        if (permsStr.startsWith('[')) {
          list = jsonDecode(permsStr);
        } else {
          list = permsStr.split(',');
        }
        perms = list.map((e) => e.toString().trim()).toSet();
      } catch (_) {}
    }

    if (!mounted) return;

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) {
        return _EmployeeAuthDialog(
          empName: emp['name'] as String? ?? '',
          empPosition: emp['position'] as String? ?? '',
          initialRole: role,
          initialStoreId: storeId,
          initialPerms: perms,
          stores: stores,
        );
      },
    );

    if (result != null) {
      try {
        await LocalDb.instance.rawExecute(
          'UPDATE employees SET role=?, store_id=?, permissions=? WHERE id=?',
          [result['role'], result['store_id'], result['permissions'], empId],
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('员工授权已保存'), backgroundColor: AppColors.success),
          );
        }
        _load();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('保存失败: $e'), backgroundColor: AppColors.danger),
          );
        }
      }
    }
  }
}

class _EmployeeAuthDialog extends StatefulWidget {
  final String empName;
  final String empPosition;
  final String initialRole;
  final int? initialStoreId;
  final Set<String> initialPerms;
  final List<Map<String, dynamic>> stores;

  const _EmployeeAuthDialog({
    required this.empName,
    required this.empPosition,
    required this.initialRole,
    required this.initialStoreId,
    required this.initialPerms,
    required this.stores,
  });

  @override
  State<_EmployeeAuthDialog> createState() => _EmployeeAuthDialogState();
}

class _EmployeeAuthDialogState extends State<_EmployeeAuthDialog> {
  late String _role;
  late int? _storeId;
  late Set<String> _perms;

  static const _tabPermissions = [
    ('dashboard', '工作台'), ('revenue', '营业额'), ('purchase', '进销存管理'),
    ('table_mgt', '桌台管理'), ('finance', '收支管理'), ('employee', '员工管理'),
    ('shifts', '排班管理'), ('attendance', '考勤管理'), ('salary', '工资管理'),
    ('reimbursement', '报销管理'), ('approval', '审批中心'), ('cost_calc', '成本核算'),
    ('reports', '报表中心'), ('store_manager', '门店管理'), ('authorization', '授权管理'),
  ];

  static const _roleMap = [
    ('super_admin', '超级管理员'), ('admin', '管理员'), ('store_manager', '店长'),
    ('supervisor', '主管'), ('employee', '员工'),
  ];

  @override
  void initState() {
    super.initState();
    _role = widget.initialRole;
    _storeId = widget.initialStoreId;
    _perms = Set.from(widget.initialPerms);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('员工授权 - ${widget.empName}'),
      content: SizedBox(
        width: double.maxFinite,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('岗位: ${widget.empPosition}', style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _role,
                decoration: const InputDecoration(labelText: '系统角色', border: OutlineInputBorder()),
                items: _roleMap.map((r) => DropdownMenuItem(value: r.$1, child: Text(r.$2))).toList(),
                onChanged: (v) => setState(() => _role = v ?? 'employee'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                value: _storeId,
                decoration: const InputDecoration(labelText: '所属门店', border: OutlineInputBorder()),
                items: widget.stores.map((s) => DropdownMenuItem(value: s['id'] as int, child: Text(s['name'] as String))).toList(),
                onChanged: (v) => setState(() => _storeId = v),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('功能权限', style: TextStyle(fontWeight: FontWeight.bold)),
                  Row(
                    children: [
                      TextButton(onPressed: () => setState(() => _perms = _tabPermissions.map((e) => e.$1).toSet()), child: const Text('全选')),
                      TextButton(onPressed: () => setState(() => _perms.clear()), child: const Text('清除')),
                    ],
                  ),
                ],
              ),
              Wrap(
                spacing: 4,
                runSpacing: 0,
                children: _tabPermissions.map((e) {
                  final checked = _perms.contains(e.$1);
                  return SizedBox(
                    width: 100,
                    child: CheckboxListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(e.$2, style: const TextStyle(fontSize: 13)),
                      value: checked,
                      onChanged: (v) => setState(() {
                        if (v == true) {
                          _perms.add(e.$1);
                        } else {
                          _perms.remove(e.$1);
                        }
                      }),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')),
        ElevatedButton(
          onPressed: () => Navigator.pop(context, {
            'role': _role,
            'store_id': _storeId,
            'permissions': jsonEncode(_perms.toList()),
          }),
          child: const Text('保存'),
        ),
      ],
    );
  }
}

// ── Tab2: 门店授权（只读） ──
class _StoreAuthTab extends StatefulWidget {
  const _StoreAuthTab();

  @override
  State<_StoreAuthTab> createState() => _StoreAuthTabState();
}

class _StoreAuthTabState extends State<_StoreAuthTab> {
  List<Map<String, dynamic>> _stores = [];
  List<Map<String, dynamic>> _employees = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _stores = await LocalDb.instance.rawQuery('SELECT id, name FROM stores ORDER BY id');
      _employees = await LocalDb.instance.rawQuery(
        'SELECT id, name, role, store_id, permissions FROM employees WHERE store_id IS NOT NULL ORDER BY name',
      );
    } catch (e) {
      debugPrint('StoreAuth load error: $e');
    }
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_stores.isEmpty) {
      return Center(child: Text('暂无门店数据', style: TextStyle(color: AppColors.textSecondary)));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: _stores.length,
      itemBuilder: (ctx, i) {
        final store = _stores[i];
        final storeId = store['id'];
        final authorized = _employees.where((e) => e['store_id'] == storeId).toList();
        final roleMap = {
          'super_admin': '超级管理员', 'admin': '管理员', 'store_manager': '店长',
          'supervisor': '主管', 'employee': '员工',
        };

        return Card(
          child: ExpansionTile(
            title: Text(store['name'] as String, style: const TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text('授权 ${authorized.length} 人'),
            children: authorized.isEmpty
                ? [const ListTile(dense: true, title: Text('暂无授权员工'))]
                : authorized.map((emp) {
                    final role = roleMap[emp['role'] as String?] ?? '员工';
                    return ListTile(
                      dense: true,
                      leading: CircleAvatar(
                        radius: 16,
                        backgroundColor: AppColors.primary.withValues(alpha: 0.1),
                        child: Text((emp['name'] as String)[0], style: const TextStyle(fontSize: 14, color: AppColors.primary)),
                      ),
                      title: Text(emp['name'] as String),
                      trailing: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(role, style: const TextStyle(fontSize: 12, color: AppColors.primary)),
                      ),
                    );
                  }).toList(),
          ),
        );
      },
    );
  }
}

// ── Tab3: 用户管理（只读列表） ──
class _UserMgmtTab extends StatefulWidget {
  const _UserMgmtTab();

  @override
  State<_UserMgmtTab> createState() => _UserMgmtTabState();
}

class _UserMgmtTabState extends State<_UserMgmtTab> {
  List<Map<String, dynamic>> _systemUsers = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _systemUsers = await LocalDb.instance.rawQuery(
        'SELECT id, name, position, role, username, store_id FROM employees WHERE username IS NOT NULL AND username != "" ORDER BY name',
      );
    } catch (e) {
      debugPrint('UserMgmt load error: $e');
    }
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_systemUsers.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.people_outline, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
            const SizedBox(height: 16),
            Text('暂无系统用户', style: TextStyle(color: AppColors.textSecondary)),
            const SizedBox(height: 8),
            Text('系统用户请在桌面端管理', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
          ],
        ),
      );
    }

    final roleMap = {
      'super_admin': '超级管理员', 'admin': '管理员', 'store_manager': '店长',
      'supervisor': '主管', 'employee': '员工',
    };

    return ListView.builder(
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: _systemUsers.length,
      itemBuilder: (ctx, i) {
        final u = _systemUsers[i];
        final role = roleMap[u['role'] as String?] ?? '员工';
        return Card(
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: AppColors.primary.withValues(alpha: 0.1),
              child: Icon(Icons.person, color: AppColors.primary),
            ),
            title: Text(u['name'] as String? ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text('${u['username'] ?? ''} · $role'),
            trailing: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: AppColors.success.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Text('启用', style: TextStyle(fontSize: 12, color: AppColors.success)),
            ),
          ),
        );
      },
    );
  }
}
