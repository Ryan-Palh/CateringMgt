// screens/store_screen.dart — 门店管理
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class StoreScreen extends StatefulWidget {
  const StoreScreen({super.key});
  @override
  State<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends State<StoreScreen> {
  List<Map<String, dynamic>> _stores = [];
  bool _loading = true;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    setState(() => _loading = true);
    try { _stores = await LocalDb.instance.query('stores', orderBy: 'id'); }
    catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }

  Future<void> _addOrEdit([Map<String, dynamic>? existing]) async {
    final nameCtrl = TextEditingController(text: existing?['name']?.toString() ?? '');
    final addressCtrl = TextEditingController(text: existing?['address']?.toString() ?? '');
    final phoneCtrl = TextEditingController(text: existing?['phone']?.toString() ?? '');
    final hoursCtrl = TextEditingController(text: existing?['business_hours']?.toString() ?? '09:00-22:00');
    String status = existing?['status']?.toString() ?? '正常';

    final result = await showDialog<bool>(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) => AlertDialog(
      title: Text(existing == null ? '新增门店' : '编辑门店'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: '门店名称 *')),
        const SizedBox(height: 8),
        TextField(controller: addressCtrl, decoration: const InputDecoration(labelText: '地址')),
        const SizedBox(height: 8),
        TextField(controller: phoneCtrl, decoration: const InputDecoration(labelText: '电话'), keyboardType: TextInputType.phone),
        const SizedBox(height: 8),
        TextField(controller: hoursCtrl, decoration: const InputDecoration(labelText: '营业时间')),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(value: status, decoration: const InputDecoration(labelText: '状态'),
          items: ['正常', '停业', '装修中'].map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
          onChanged: (v) => setSt(() => status = v!)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存'))],
    )));

    if (result == true) {
      final data = {'name': nameCtrl.text.trim(), 'address': addressCtrl.text.trim(), 'phone': phoneCtrl.text.trim(), 'business_hours': hoursCtrl.text.trim(), 'status': status};
      if (existing == null) { await LocalDb.instance.insert('stores', data); }
      else { await LocalDb.instance.update('stores', data, where: 'id=?', whereArgs: [existing['id']]); }
      _load();
    }
  }

  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('确认删除'), content: const Text('确定要删除这个门店吗？'),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger)))],
    ));
    if (confirm == true) { await LocalDb.instance.delete('stores', where: 'id=?', whereArgs: [id]); _load(); }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(onPressed: () => _addOrEdit(), child: const Icon(Icons.add)),
      body: _stores.isEmpty ? _buildEmpty() : ListView.builder(
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: _stores.length,
        itemBuilder: (ctx, i) {
          final s = _stores[i];
          final status = s['status'] as String? ?? '正常';
          final statusColor = {'正常': AppColors.success, '停业': AppColors.warning, '装修中': AppColors.danger}[status] ?? AppColors.textSecondary;
          return Card(child: ListTile(
            leading: CircleAvatar(backgroundColor: AppColors.primary.withValues(alpha: 0.1), child: const Icon(Icons.store, color: AppColors.primary, size: 20)),
            title: Text(s['name'] as String? ?? ''),
            subtitle: Text('${s['address'] ?? ''} · ${s['phone'] ?? ''}\n营业时间: ${s['business_hours'] ?? ''}'),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4), decoration: BoxDecoration(color: statusColor!.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)), child: Text(status, style: TextStyle(color: statusColor, fontSize: 11))),
              PopupMenuButton(itemBuilder: (ctx) => [const PopupMenuItem(value: 'edit', child: Text('编辑')), const PopupMenuItem(value: 'delete', child: Text('删除'))],
                onSelected: (v) { if (v == 'edit') _addOrEdit(s); if (v == 'delete') _delete(s['id'] as int); }),
            ]),
          ));
        },
      ),
    );
  }

  Widget _buildEmpty() => Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
    Icon(Icons.store_outlined, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
    const SizedBox(height: 16), const Text('暂无门店', style: TextStyle(color: AppColors.textSecondary)),
  ]));
}
