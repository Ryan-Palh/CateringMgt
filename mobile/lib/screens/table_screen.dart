// screens/table_screen.dart — 桌台管理
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class TableScreen extends StatefulWidget {
  const TableScreen({super.key});
  @override
  State<TableScreen> createState() => _TableScreenState();
}

class _TableScreenState extends State<TableScreen> {
  List<Map<String, dynamic>> _tables = [];
  bool _loading = true;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _tables = await LocalDb.instance.query('dining_tables', orderBy: 'id');
    } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }

  Future<void> _addOrEdit([Map<String, dynamic>? existing]) async {
    final nameCtrl = TextEditingController(text: existing?['name']?.toString() ?? '');
    final areaCtrl = TextEditingController(text: existing?['area']?.toString() ?? '大厅');
    final capCtrl = TextEditingController(text: existing?['capacity']?.toString() ?? '4');
    final remarkCtrl = TextEditingController(text: existing?['remark']?.toString() ?? '');
    String status = existing?['status']?.toString() ?? '空闲';
    final areas = ['大厅', '包间', '卡座', '露台', '其他'];
    final statuses = ['空闲', '占用', '预定', '清洁中'];

    final result = await showDialog<bool>(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) => AlertDialog(
      title: Text(existing == null ? '新增桌台' : '编辑桌台'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: '桌台名称 *')),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(value: areaCtrl.text, decoration: const InputDecoration(labelText: '区域'),
          items: areas.map((a) => DropdownMenuItem(value: a, child: Text(a))).toList(),
          onChanged: (v) => setSt(() => areaCtrl.text = v!)),
        const SizedBox(height: 8),
        TextField(controller: capCtrl, decoration: const InputDecoration(labelText: '容纳人数'), keyboardType: TextInputType.number),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(value: status, decoration: const InputDecoration(labelText: '状态'),
          items: statuses.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
          onChanged: (v) => setSt(() => status = v!)),
        const SizedBox(height: 8),
        TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '备注')),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存'))],
    )));

    if (result == true) {
      final data = {
        'name': nameCtrl.text.trim(), 'area': areaCtrl.text.trim(),
        'capacity': int.tryParse(capCtrl.text) ?? 4, 'status': status, 'remark': remarkCtrl.text.trim(),
      };
      if (existing == null) { await LocalDb.instance.insert('dining_tables', data); }
      else { await LocalDb.instance.update('dining_tables', data, where: 'id=?', whereArgs: [existing['id']]); }
      _load();
    }
  }

  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('确认删除'), content: const Text('确定要删除这个桌台吗？'),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger)))],
    ));
    if (confirm == true) { await LocalDb.instance.delete('dining_tables', where: 'id=?', whereArgs: [id]); _load(); }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final grouped = <String, List<Map<String, dynamic>>>{};
    for (final t in _tables) {
      final area = t['area'] as String? ?? '大厅';
      grouped.putIfAbsent(area, () => []);
      grouped[area]!.add(t);
    }
    return Scaffold(
      floatingActionButton: FloatingActionButton(onPressed: () => _addOrEdit(), child: const Icon(Icons.add)),
      body: _tables.isEmpty ? _buildEmpty() : ListView(
        padding: const EdgeInsets.all(AppSpacing.md),
        children: grouped.keys.map((area) {
          return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(padding: const EdgeInsets.only(left: 4, bottom: 8), child: Text(area, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold))),
            Wrap(spacing: 8, runSpacing: 8, children: grouped[area]!.map((t) {
              final status = t['status'] as String? ?? '空闲';
              final color = {'空闲': AppColors.success, '占用': AppColors.danger, '预定': AppColors.warning, '清洁中': AppColors.textSecondary}[status] ?? AppColors.textSecondary;
              return GestureDetector(
                onTap: () => _addOrEdit(t),
                onLongPress: () => _delete(t['id'] as int),
                child: Container(width: 100, height: 80,
                  decoration: BoxDecoration(color: color!.withValues(alpha: 0.1), border: Border.all(color: color.withValues(alpha: 0.3)), borderRadius: BorderRadius.circular(8)),
                  child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Text(t['name'] as String? ?? '', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: color)),
                    const SizedBox(height: 4),
                    Text('${t['capacity'] ?? 4}人', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                    const SizedBox(height: 2),
                    Text(status, style: TextStyle(fontSize: 11, color: color)),
                  ]),
                ),
              );
            }).toList()),
            const SizedBox(height: AppSpacing.md),
          ]);
        }).toList(),
      ),
    );
  }

  Widget _buildEmpty() => Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
    Icon(Icons.table_restaurant, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
    const SizedBox(height: 16), const Text('暂无桌台', style: TextStyle(color: AppColors.textSecondary)),
  ]));
}
