// screens/cost_calc_screen.dart — 成本核算（菜品成本=食材用量×单价之和）
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class CostCalcScreen extends StatefulWidget {
  const CostCalcScreen({super.key});
  @override
  State<CostCalcScreen> createState() => _CostCalcScreenState();
}

class _CostCalcScreenState extends State<CostCalcScreen> {
  List<Map<String, dynamic>> _dishes = [];
  bool _loading = true;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _dishes = await LocalDb.instance.rawQuery('SELECT * FROM dishes ORDER BY name');
    } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }

  Future<double> _calcCost(int dishId) async {
    final items = await LocalDb.instance.rawQuery(
      'SELECT di.quantity, i.price FROM dish_ingredients di LEFT JOIN ingredients i ON di.ingredient_id = i.id WHERE di.dish_id = ?', [dishId]);
    double cost = 0;
    for (final item in items) {
      final qty = (item['quantity'] as num?)?.toDouble() ?? 0;
      final price = (item['price'] as num?)?.toDouble() ?? 0;
      cost += qty * price;
    }
    return cost;
  }

  Future<void> _addOrEditDish([Map<String, dynamic>? existing]) async {
    final nameCtrl = TextEditingController(text: existing?['name']?.toString() ?? '');
    final priceCtrl = TextEditingController(text: existing?['selling_price']?.toString() ?? '');
    final costCtrl = TextEditingController(text: existing?['cost_price']?.toString() ?? '');
    String category = existing?['category']?.toString() ?? '主菜';
    final categories = ['主菜', '凉菜', '汤品', '主食', '甜品', '饮品', '小吃', '其他'];

    final result = await showDialog<bool>(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) => AlertDialog(
      title: Text(existing == null ? '新增菜品' : '编辑菜品'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: '菜品名称 *')),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(value: category, decoration: const InputDecoration(labelText: '分类'),
          items: categories.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(), onChanged: (v) => setSt(() => category = v!)),
        const SizedBox(height: 8),
        TextField(controller: priceCtrl, decoration: const InputDecoration(labelText: '售价'), keyboardType: TextInputType.number),
        const SizedBox(height: 8),
        TextField(controller: costCtrl, decoration: const InputDecoration(labelText: '成本价'), keyboardType: TextInputType.number),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存'))],
    )));

    if (result == true) {
      final data = {'name': nameCtrl.text.trim(), 'category': category, 'selling_price': double.tryParse(priceCtrl.text) ?? 0, 'cost_price': double.tryParse(costCtrl.text) ?? 0, 'status': '在售'};
      if (existing == null) { await LocalDb.instance.insert('dishes', data); }
      else { await LocalDb.instance.update('dishes', data, where: 'id=?', whereArgs: [existing['id']]); }
      _load();
    }
  }

  Future<void> _manageIngredients(int dishId, String dishName) async {
    final ingredients = await LocalDb.instance.query('ingredients', orderBy: 'name');
    final current = await LocalDb.instance.rawQuery('SELECT di.*, i.name as ing_name FROM dish_ingredients di LEFT JOIN ingredients i ON di.ingredient_id = i.id WHERE di.dish_id = ?', [dishId]);

    await showModalBottomSheet(context: context, isScrollControlled: true, builder: (ctx) {
      return StatefulBuilder(builder: (ctx, setSt) {
        return Container(padding: const EdgeInsets.all(AppSpacing.md), height: MediaQuery.of(ctx).size.height * 0.7,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('$dishName - 食材配比', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const Divider(),
            Expanded(child: ListView(children: current.map((item) {
              final qty = (item['quantity'] as num?)?.toDouble() ?? 0;
              return ListTile(title: Text(item['ing_name'] ?? ''), subtitle: Text('用量: ${qty.toStringAsFixed(2)}'),
                trailing: IconButton(icon: const Icon(Icons.delete_outline, color: AppColors.danger), onPressed: () async {
                  await LocalDb.instance.delete('dish_ingredients', where: 'id=?', whereArgs: [item['id']]);
                  setSt(() {}); // 刷新需重新加载
                }));
            }).toList())),
            const Divider(),
            Row(children: [
              Expanded(child: ElevatedButton.icon(onPressed: () async {
                int? selId;
                final qtyCtrl = TextEditingController(text: '1');
                final addResult = await showDialog<bool>(context: ctx, builder: (dctx) => StatefulBuilder(builder: (dctx, dsetSt) => AlertDialog(
                  title: const Text('添加食材'),
                  content: Column(mainAxisSize: MainAxisSize.min, children: [
                    DropdownButtonFormField<int>(value: selId, decoration: const InputDecoration(labelText: '食材'),
                      items: ingredients.map((ing) => DropdownMenuItem(value: ing['id'] as int, child: Text(ing['name'] as String? ?? ''))).toList(),
                      onChanged: (v) => dsetSt(() => selId = v)),
                    const SizedBox(height: 8),
                    TextField(controller: qtyCtrl, decoration: const InputDecoration(labelText: '用量'), keyboardType: TextInputType.number),
                  ]),
                  actions: [TextButton(onPressed: () => Navigator.pop(dctx, false), child: const Text('取消')),
                    ElevatedButton(onPressed: () => Navigator.pop(dctx, true), child: const Text('添加'))],
                )));
                if (addResult == true && selId != null) {
                  await LocalDb.instance.insert('dish_ingredients', {'dish_id': dishId, 'ingredient_id': selId, 'quantity': double.tryParse(qtyCtrl.text) ?? 0});
                  setSt(() {});
                }
              }, icon: const Icon(Icons.add), label: const Text('添加食材'))),
            ]),
          ]));
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(onPressed: () => _addOrEditDish(), child: const Icon(Icons.add)),
      body: _dishes.isEmpty ? _buildEmpty() : ListView.builder(
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: _dishes.length,
        itemBuilder: (ctx, i) {
          final d = _dishes[i];
          final sellPrice = (d['selling_price'] as num?)?.toDouble() ?? 0;
          final costPrice = (d['cost_price'] as num?)?.toDouble() ?? 0;
          final profit = sellPrice - costPrice;
          final margin = sellPrice > 0 ? (profit / sellPrice * 100) : 0.0;
          return Card(child: ListTile(
            leading: CircleAvatar(backgroundColor: AppColors.primary.withValues(alpha: 0.1), child: const Icon(Icons.restaurant_menu, color: AppColors.primary, size: 20)),
            title: Text(d['name'] as String? ?? ''),
            subtitle: Text('售价: ¥${sellPrice.toStringAsFixed(2)} · 成本: ¥${costPrice.toStringAsFixed(2)} · 毛利: ${margin.toStringAsFixed(1)}%'),
            trailing: PopupMenuButton(itemBuilder: (ctx) => [
              const PopupMenuItem(value: 'recipe', child: Text('食材配比')),
              const PopupMenuItem(value: 'edit', child: Text('编辑')),
              const PopupMenuItem(value: 'delete', child: Text('删除')),
            ], onSelected: (v) async {
              if (v == 'recipe') _manageIngredients(d['id'] as int, d['name'] as String? ?? '');
              if (v == 'edit') _addOrEditDish(d);
              if (v == 'delete') {
                await LocalDb.instance.delete('dishes', where: 'id=?', whereArgs: [d['id']]);
                _load();
              }
            }),
          ));
        },
      ),
    );
  }

  Widget _buildEmpty() => Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
    Icon(Icons.calculate_outlined, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
    const SizedBox(height: 16), const Text('暂无菜品', style: TextStyle(color: AppColors.textSecondary)),
  ]));
}
