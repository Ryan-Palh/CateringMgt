// screens/employee_screen.dart — 员工管理
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class EmployeeScreen extends StatefulWidget {
  const EmployeeScreen({super.key});

  @override
  State<EmployeeScreen> createState() => _EmployeeScreenState();
}

class _EmployeeScreenState extends State<EmployeeScreen> {
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
      _employees = await LocalDb.instance.query('employees', orderBy: 'id DESC');
    } catch (e) {
      debugPrint('Load error: $e');
    }
    setState(() => _loading = false);
  }

  Future<void> _addOrEdit([Map<String, dynamic>? existing]) async {
    final nameCtrl = TextEditingController(text: existing?['name']?.toString() ?? '');
    final phoneCtrl = TextEditingController(text: existing?['phone']?.toString() ?? '');
    final salaryCtrl = TextEditingController(text: existing?['base_salary']?.toString() ?? '');
    String position = existing?['position']?.toString() ?? '厨师';
    String status = existing?['status']?.toString() ?? '在职';

    final positions = ['店长', '前厅经理', '厨师长', '炒锅', '切配', '打荷', '面点师', '传菜员', '服务员', '迎宾', '收银员', '吧台', '采购', '保洁', '会计', '其他'];
    final statuses = ['在职', '离职', '休假'];

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => AlertDialog(
          title: Text(existing == null ? '新增员工' : '编辑员工'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: '姓名 *')),
                const SizedBox(height: 12),
                TextField(controller: phoneCtrl, decoration: const InputDecoration(labelText: '电话'), keyboardType: TextInputType.phone),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: position,
                  decoration: const InputDecoration(labelText: '职位'),
                  items: positions.map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
                  onChanged: (v) => setSt(() => position = v!),
                ),
                const SizedBox(height: 12),
                TextField(controller: salaryCtrl, decoration: const InputDecoration(labelText: '基本工资'), keyboardType: TextInputType.number),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: status,
                  decoration: const InputDecoration(labelText: '状态'),
                  items: statuses.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
                  onChanged: (v) => setSt(() => status = v!),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
            ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存')),
          ],
        ),
      ),
    );

    if (result == true) {
      final data = {
        'name': nameCtrl.text.trim(),
        'phone': phoneCtrl.text.trim(),
        'position': position,
        'base_salary': double.tryParse(salaryCtrl.text) ?? 0,
        'status': status,
        'hire_date': existing?['hire_date'] ?? DateTime.now().toString().substring(0, 10),
      };
      if (existing == null) {
        await LocalDb.instance.insert('employees', data);
      } else {
        await LocalDb.instance.update('employees', data, where: 'id=?', whereArgs: [existing['id']]);
      }
      _load();
    }
  }

  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认删除'),
        content: const Text('确定要删除这个员工吗？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger))),
        ],
      ),
    );
    if (confirm == true) {
      await LocalDb.instance.delete('employees', where: 'id=?', whereArgs: [id]);
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(
        onPressed: () => _addOrEdit(),
        child: const Icon(Icons.add),
      ),
      body: _employees.isEmpty
          ? _buildEmpty()
          : ListView.builder(
              padding: const EdgeInsets.all(AppSpacing.md),
              itemCount: _employees.length,
              itemBuilder: (ctx, i) {
                final e = _employees[i];
                final status = e['status'] as String? ?? '在职';
                final statusColor = {'在职': AppColors.success, '离职': AppColors.danger, '休假': AppColors.warning}[status] ?? AppColors.textSecondary;
                return Card(
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: statusColor!.withValues(alpha: 0.1),
                      child: Text((e['name'] as String?)?.substring(0, 1) ?? '?', style: TextStyle(color: statusColor, fontWeight: FontWeight.bold)),
                    ),
                    title: Text(e['name'] as String? ?? ''),
                    subtitle: Text('${e['position'] ?? ''} · ${e['phone'] ?? ''}'),
                    trailing: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(color: statusColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
                      child: Text(status, style: TextStyle(color: statusColor, fontSize: 12)),
                    ),
                    onTap: () => _addOrEdit(e),
                    onLongPress: () => _delete(e['id'] as int),
                  ),
                );
              },
            ),
    );
  }

  Widget _buildEmpty() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.people_outline, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
          const SizedBox(height: 16),
          const Text('暂无员工', style: TextStyle(color: AppColors.textSecondary)),
        ],
      ),
    );
  }
}
