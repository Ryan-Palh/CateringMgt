// screens/supplier_screen.dart — 供货商管理（含结款方式）
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class SupplierScreen extends StatefulWidget {
  const SupplierScreen({super.key});

  @override
  State<SupplierScreen> createState() => _SupplierScreenState();
}

class _SupplierScreenState extends State<SupplierScreen> {
  List<Map<String, dynamic>> _suppliers = [];
  bool _loading = true;

  static const _paymentMethods = ['现结', '月结', '周结', '货到付款', '预付款', '季结', '半年结'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _suppliers = await LocalDb.instance.query('suppliers', orderBy: 'id DESC');
    } catch (e) {
      debugPrint('Load error: $e');
    }
    setState(() => _loading = false);
  }

  Future<void> _addOrEdit([Map<String, dynamic>? existing]) async {
    final nameCtrl = TextEditingController(text: existing?['name']?.toString() ?? '');
    final contactCtrl = TextEditingController(text: existing?['contact']?.toString() ?? '');
    final phoneCtrl = TextEditingController(text: existing?['phone']?.toString() ?? '');
    final addressCtrl = TextEditingController(text: existing?['address']?.toString() ?? '');
    final remarkCtrl = TextEditingController(text: existing?['remark']?.toString() ?? '');
    String paymentMethod = existing?['payment_method']?.toString() ?? '现结';

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => AlertDialog(
          title: Text(existing == null ? '新增供货商' : '编辑供货商'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: '供货商名称 *')),
                const SizedBox(height: 12),
                TextField(controller: contactCtrl, decoration: const InputDecoration(labelText: '联系人')),
                const SizedBox(height: 12),
                TextField(controller: phoneCtrl, decoration: const InputDecoration(labelText: '电话'), keyboardType: TextInputType.phone),
                const SizedBox(height: 12),
                TextField(controller: addressCtrl, decoration: const InputDecoration(labelText: '地址')),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: paymentMethod,
                  decoration: const InputDecoration(labelText: '结款方式'),
                  items: _paymentMethods.map((m) => DropdownMenuItem(value: m, child: Text(m))).toList(),
                  onChanged: (v) => setSt(() => paymentMethod = v!),
                ),
                const SizedBox(height: 12),
                TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '备注')),
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
        'contact': contactCtrl.text.trim(),
        'phone': phoneCtrl.text.trim(),
        'address': addressCtrl.text.trim(),
        'payment_method': paymentMethod,
        'remark': remarkCtrl.text.trim(),
      };
      if (existing == null) {
        await LocalDb.instance.insert('suppliers', data);
      } else {
        await LocalDb.instance.update('suppliers', data, where: 'id=?', whereArgs: [existing['id']]);
      }
      _load();
    }
  }

  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认删除'),
        content: const Text('确定要删除这个供货商吗？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger))),
        ],
      ),
    );
    if (confirm == true) {
      await LocalDb.instance.delete('suppliers', where: 'id=?', whereArgs: [id]);
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
      body: _suppliers.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.local_shipping, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
                  const SizedBox(height: 16),
                  const Text('暂无供货商', style: TextStyle(color: AppColors.textSecondary)),
                ],
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(AppSpacing.md),
              itemCount: _suppliers.length,
              itemBuilder: (ctx, i) {
                final s = _suppliers[i];
                final pm = s['payment_method'] as String? ?? '现结';
                final pmColor = {
                  '现结': AppColors.success,
                  '月结': AppColors.info,
                  '货到付款': AppColors.warning,
                  '预付款': AppColors.danger,
                }[pm] ?? AppColors.textSecondary;
                return Card(
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: AppColors.primary.withValues(alpha: 0.1),
                      child: const Icon(Icons.store, color: AppColors.primary, size: 20),
                    ),
                    title: Text(s['name'] as String? ?? ''),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${s['contact'] ?? ''} · ${s['phone'] ?? ''}'),
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: pmColor!.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(pm, style: TextStyle(color: pmColor, fontSize: 11)),
                        ),
                      ],
                    ),
                    trailing: PopupMenuButton(
                      itemBuilder: (ctx) => [
                        const PopupMenuItem(value: 'edit', child: Text('编辑')),
                        const PopupMenuItem(value: 'delete', child: Text('删除')),
                      ],
                      onSelected: (v) {
                        if (v == 'edit') _addOrEdit(s);
                        if (v == 'delete') _delete(s['id'] as int);
                      },
                    ),
                  ),
                );
              },
            ),
    );
  }
}
