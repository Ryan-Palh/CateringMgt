// screens/purchase_screen.dart — 进销存（6Tab与桌面端完全对齐）
// 上月结存 / 进货台账 / 出库管理 / 供货商进货明细 / 供货商管理 / 产品数据
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class PurchaseScreen extends StatefulWidget {
  const PurchaseScreen({super.key});
  @override
  State<PurchaseScreen> createState() => _PurchaseScreenState();
}

class _PurchaseScreenState extends State<PurchaseScreen>
    with TickerProviderStateMixin {
  late TabController _tabController;
  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 6, vsync: this);
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
        isScrollable: true,
        tabs: const [
          Tab(text: '上月结存'),
          Tab(text: '进货台账'),
          Tab(text: '出库管理'),
          Tab(text: '供货商明细'),
          Tab(text: '供货商管理'),
          Tab(text: '产品数据'),
        ],
        labelColor: AppColors.primary,
        unselectedLabelColor: AppColors.textSecondary,
        indicatorColor: AppColors.primary,
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _MonthlyInventoryTab(),
          _PurchaseTab(),
          _StockOutTab(),
          _SupplierQueryTab(),
          _SupplierTab(),
          _ProductTab(),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════
// 上月结存（录入/编辑/删除）
// ═══════════════════════════════════════════
class _MonthlyInventoryTab extends StatefulWidget {
  @override
  State<_MonthlyInventoryTab> createState() => _MonthlyInventoryTabState();
}
class _MonthlyInventoryTabState extends State<_MonthlyInventoryTab> {
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;
  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _records = await LocalDb.instance.rawQuery('SELECT * FROM monthly_inventory ORDER BY id DESC');
    } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }
  Future<void> _addOrEdit([Map<String, dynamic>? existing]) async {
    final db = LocalDb.instance;
    final ingredients = await db.query('ingredients', orderBy: 'name');
    if (ingredients.isEmpty) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请先添加食材'), backgroundColor: AppColors.warning));
      return;
    }
    int? ingId = existing?['ingredient_id'] ?? ingredients.first['id'];
    final qtyCtrl = TextEditingController(text: existing?['quantity']?.toString() ?? '');
    final priceCtrl = TextEditingController(text: existing?['unit_price']?.toString() ?? '');
    final monthCtrl = TextEditingController(text: existing?['month']?.toString() ?? DateFormat('yyyy-MM').format(DateTime.now().subtract(const Duration(days: 30))));
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) => AlertDialog(
        title: Text(existing == null ? '录入上月结存' : '编辑上月结存'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          DropdownButtonFormField<int>(value: ingId, decoration: const InputDecoration(labelText: '食材'),
            items: ingredients.map((ing) => DropdownMenuItem(value: ing['id'] as int, child: Text('${ing['name']} (${ing['unit']})'))).toList(),
            onChanged: (v) { setSt(() { ingId = v; final ing = ingredients.firstWhere((e) => e['id'] == v); priceCtrl.text = ((ing['price'] as num?)?.toDouble() ?? 0).toString(); }); }),
          const SizedBox(height: 8),
          TextField(controller: qtyCtrl, decoration: const InputDecoration(labelText: '结存数量'), keyboardType: TextInputType.number),
          const SizedBox(height: 8),
          TextField(controller: priceCtrl, decoration: const InputDecoration(labelText: '单价'), keyboardType: TextInputType.number),
          const SizedBox(height: 8),
          TextField(controller: monthCtrl, decoration: const InputDecoration(labelText: '所属月份 (YYYY-MM)')),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存')),
        ],
      )),
    );
    if (result == true && ingId != null) {
      final ing = ingredients.firstWhere((e) => e['id'] == ingId);
      final data = {
        'ingredient_id': ingId,
        'ingredient_name': ing['name'],
        'quantity': double.tryParse(qtyCtrl.text) ?? 0,
        'unit_price': double.tryParse(priceCtrl.text) ?? 0,
        'month': monthCtrl.text,
      };
      if (existing == null) {
        await db.insert('monthly_inventory', data);
      } else {
        await db.update('monthly_inventory', data, where: 'id=?', whereArgs: [existing['id']]);
      }
      _load();
    }
  }
  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('确认删除'), content: const Text('确定要删除这条上月结存记录吗？'),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger)))],
    ));
    if (confirm == true) { await LocalDb.instance.delete('monthly_inventory', where: 'id=?', whereArgs: [id]); _load(); }
  }
  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(onPressed: () => _addOrEdit(), backgroundColor: AppColors.info, child: const Icon(Icons.add)),
      body: _records.isEmpty ? _buildEmpty('暂无上月结存数据') : ListView.builder(
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: _records.length,
        itemBuilder: (ctx, i) {
          final r = _records[i];
          final qty = (r['quantity'] as num?)?.toDouble() ?? 0;
          final price = (r['unit_price'] as num?)?.toDouble() ?? 0;
          return Card(child: ListTile(
            leading: CircleAvatar(backgroundColor: AppColors.info.withValues(alpha: 0.1), child: const Icon(Icons.inventory, color: AppColors.info, size: 20)),
            title: Text(r['ingredient_name'] as String? ?? '未知'),
            subtitle: Text('数量: ${qty.toStringAsFixed(2)} · 单价: ¥${price.toStringAsFixed(2)} · ${r['month'] ?? ''}'),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              Text('¥${(qty * price).toStringAsFixed(2)}'),
              IconButton(icon: const Icon(Icons.edit, size: 20, color: AppColors.primary), onPressed: () => _addOrEdit(r)),
              IconButton(icon: const Icon(Icons.delete_outline, size: 20, color: AppColors.danger), onPressed: () => _delete(r['id'] as int)),
            ]),
          ));
        },
      ),
    );
  }
}

// ═══════════════════════════════════════════
// 进货台账（完整录入：产品/品牌/规格/数量/单价/生产日期/用途）
// ═══════════════════════════════════════════
class _PurchaseTab extends StatefulWidget {
  @override
  State<_PurchaseTab> createState() => _PurchaseTabState();
}
class _PurchaseTabState extends State<_PurchaseTab> {
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;
  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _records = await LocalDb.instance.rawQuery(
        "SELECT p.*, s.name as supplier_name FROM purchases p LEFT JOIN suppliers s ON p.supplier_id = s.id WHERE p.purchase_no LIKE 'CG%' ORDER BY p.purchase_date DESC, p.id DESC");
    } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }
  Future<void> _addPurchase() async {
    final db = LocalDb.instance;
    final suppliers = await db.query('suppliers', orderBy: 'name');
    final ingredients = await db.query('ingredients', orderBy: 'name');
    if (suppliers.isEmpty) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请先添加供货商'), backgroundColor: AppColors.warning)); return; }
    if (ingredients.isEmpty) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请先添加食材'), backgroundColor: AppColors.warning)); return; }
    final dateCtrl = TextEditingController(text: DateFormat('yyyy-MM-dd').format(DateTime.now()));
    final operatorCtrl = TextEditingController();
    final remarkCtrl = TextEditingController();
    int? supplierId = suppliers.first['id'];
    List<Map<String, dynamic>> items = [];
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) {
        double total = items.fold<double>(0, (s, item) => s + ((item['quantity'] as num? ?? 0) * (item['unit_price'] as num? ?? 0)));
        return AlertDialog(
          title: const Text('新增进货'),
          content: SizedBox(width: double.maxFinite, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: dateCtrl, decoration: const InputDecoration(labelText: '进货日期'), readOnly: true, onTap: () async {
              final picked = await showDatePicker(context: ctx, initialDate: DateTime.now(), firstDate: DateTime(2020), lastDate: DateTime.now().add(const Duration(days: 365)));
              if (picked != null) dateCtrl.text = DateFormat('yyyy-MM-dd').format(picked);
            }),
            const SizedBox(height: 8),
            DropdownButtonFormField<int>(value: supplierId, decoration: const InputDecoration(labelText: '供货商'),
              items: suppliers.map((s) => DropdownMenuItem(value: s['id'] as int, child: Text(s['name'] as String? ?? ''))).toList(),
              onChanged: (v) => setSt(() => supplierId = v)),
            const SizedBox(height: 8),
            TextField(controller: operatorCtrl, decoration: const InputDecoration(labelText: '经办人')),
            const SizedBox(height: 8),
            TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '备注')),
            const Divider(),
            const Text('进货明细', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...items.asMap().entries.map((entry) {
              final idx = entry.key; final item = entry.value;
              return Card(child: Padding(padding: const EdgeInsets.all(8), child: Column(children: [
                DropdownButtonFormField<int>(value: item['ingredient_id'], decoration: const InputDecoration(labelText: '产品', isDense: true),
                  items: ingredients.map((ing) => DropdownMenuItem(value: ing['id'] as int, child: Text('${ing['name']} (${ing['unit']})'))).toList(),
                  onChanged: (v) { setSt(() { item['ingredient_id'] = v; final ing = ingredients.firstWhere((e) => e['id'] == v); item['ingredient_name'] = ing['name']; item['unit'] = ing['unit']; item['brand'] = ing['brand'] ?? ''; item['spec'] = ing['spec'] ?? ''; item['unit_price'] = (ing['price'] as num?)?.toDouble() ?? 0; }); }),
                Row(children: [
                  Expanded(child: TextFormField(initialValue: item['brand']?.toString() ?? '', decoration: const InputDecoration(labelText: '品牌', isDense: true), onChanged: (v) => item['brand'] = v)),
                  const SizedBox(width: 8),
                  Expanded(child: TextFormField(initialValue: item['spec']?.toString() ?? '', decoration: const InputDecoration(labelText: '规格', isDense: true), onChanged: (v) => item['spec'] = v)),
                ]),
                Row(children: [
                  Expanded(child: TextFormField(initialValue: item['quantity']?.toString() ?? '', decoration: const InputDecoration(labelText: '数量', isDense: true), keyboardType: TextInputType.number, onChanged: (v) => item['quantity'] = double.tryParse(v) ?? 0)),
                  const SizedBox(width: 8),
                  Expanded(child: TextFormField(initialValue: item['unit_price']?.toString() ?? '', decoration: const InputDecoration(labelText: '单价', isDense: true), keyboardType: TextInputType.number, onChanged: (v) => item['unit_price'] = double.tryParse(v) ?? 0)),
                ]),
                Row(children: [
                  Expanded(child: TextFormField(initialValue: item['production_date']?.toString() ?? '', decoration: const InputDecoration(labelText: '生产日期', isDense: true), readOnly: true, onTap: () async {
                    final picked = await showDatePicker(context: ctx, initialDate: DateTime.now(), firstDate: DateTime(2020), lastDate: DateTime.now());
                    if (picked != null) setSt(() => item['production_date'] = DateFormat('yyyy-MM-dd').format(picked));
                  })),
                  const SizedBox(width: 8),
                  Expanded(child: DropdownButtonFormField<String>(value: item['usage']?.toString(), decoration: const InputDecoration(labelText: '用途', isDense: true),
                    items: ['厨房使用', '冷库储存', '吧台使用', '外卖专用', '损耗', '其他'].map((u) => DropdownMenuItem(value: u, child: Text(u))).toList(),
                    onChanged: (v) => setSt(() => item['usage'] = v))),
                ]),
                Align(alignment: Alignment.centerRight, child: TextButton(onPressed: () => setSt(() => items.removeAt(idx)), child: const Text('删除', style: TextStyle(color: AppColors.danger)))),
              ])));
            }),
            TextButton.icon(onPressed: () => setSt(() => items.add({'ingredient_id': null, 'quantity': 0, 'unit_price': 0, 'production_date': '', 'usage': null})), icon: const Icon(Icons.add), label: const Text('添加明细')),
            if (items.isNotEmpty) ...[const Divider(), Text('合计: ¥${total.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16))],
          ]))),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
            ElevatedButton(onPressed: items.isEmpty ? null : () => Navigator.pop(ctx, true), child: const Text('保存')),
          ],
        );
      }),
    );
    if (result == true) {
      final no = 'CG-${DateFormat('yyyyMMdd-HHmmss').format(DateTime.now())}';
      double totalAmount = items.fold<double>(0, (s, item) => s + ((item['quantity'] as num? ?? 0) * (item['unit_price'] as num? ?? 0)));
      final purchaseId = await db.insert('purchases', {'purchase_no': no, 'purchase_date': dateCtrl.text, 'supplier_id': supplierId, 'total_amount': totalAmount, 'operator': operatorCtrl.text.trim(), 'remark': remarkCtrl.text.trim()});
      for (final item in items) {
        if (item['ingredient_id'] != null) {
          await db.insert('purchase_items', {'purchase_id': purchaseId, 'ingredient_id': item['ingredient_id'], 'quantity': item['quantity'] ?? 0, 'unit_price': item['unit_price'] ?? 0, 'total_price': (item['quantity'] ?? 0) * (item['unit_price'] ?? 0), 'production_date': item['production_date'] ?? '', 'usage': item['usage'] ?? ''});
        }
      }
      _load();
    }
  }
  @override
  Future<void> _addReturn() async {
    final db = LocalDb.instance;
    final suppliers = await db.query('suppliers', orderBy: 'name');
    final ingredients = await db.query('ingredients', orderBy: 'name');
    if (suppliers.isEmpty) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请先添加供货商'), backgroundColor: AppColors.warning)); return; }
    if (ingredients.isEmpty) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请先添加食材'), backgroundColor: AppColors.warning)); return; }
    final dateCtrl = TextEditingController(text: DateFormat('yyyy-MM-dd').format(DateTime.now()));
    final operatorCtrl = TextEditingController();
    final remarkCtrl = TextEditingController();
    int? supplierId = suppliers.first['id'];
    List<Map<String, dynamic>> items = [];
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) {
        double total = items.fold<double>(0, (s, item) => s + ((item['quantity'] as num? ?? 0) * (item['unit_price'] as num? ?? 0)));
        return AlertDialog(
          title: const Text('进货退货'),
          content: SizedBox(width: double.maxFinite, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: dateCtrl, decoration: const InputDecoration(labelText: '退货日期'), readOnly: true, onTap: () async {
              final picked = await showDatePicker(context: ctx, initialDate: DateTime.now(), firstDate: DateTime(2020), lastDate: DateTime.now().add(const Duration(days: 365)));
              if (picked != null) dateCtrl.text = DateFormat('yyyy-MM-dd').format(picked);
            }),
            const SizedBox(height: 8),
            DropdownButtonFormField<int>(value: supplierId, decoration: const InputDecoration(labelText: '供货商'),
              items: suppliers.map((s) => DropdownMenuItem(value: s['id'] as int, child: Text(s['name'] as String? ?? ''))).toList(),
              onChanged: (v) => setSt(() => supplierId = v)),
            const SizedBox(height: 8),
            TextField(controller: operatorCtrl, decoration: const InputDecoration(labelText: '经办人')),
            const SizedBox(height: 8),
            TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '退货原因')),
            const Divider(),
            const Text('退货明细', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...items.asMap().entries.map((entry) {
              final idx = entry.key; final item = entry.value;
              return Card(child: Padding(padding: const EdgeInsets.all(8), child: Column(children: [
                DropdownButtonFormField<int>(value: item['ingredient_id'], decoration: const InputDecoration(labelText: '产品', isDense: true),
                  items: ingredients.map((ing) => DropdownMenuItem(value: ing['id'] as int, child: Text('${ing['name']} (${ing['unit']})'))).toList(),
                  onChanged: (v) { setSt(() { item['ingredient_id'] = v; final ing = ingredients.firstWhere((e) => e['id'] == v); item['ingredient_name'] = ing['name']; item['unit'] = ing['unit']; item['brand'] = ing['brand'] ?? ''; item['spec'] = ing['spec'] ?? ''; item['unit_price'] = (ing['price'] as num?)?.toDouble() ?? 0; }); }),
                Row(children: [
                  Expanded(child: TextFormField(initialValue: item['brand']?.toString() ?? '', decoration: const InputDecoration(labelText: '品牌', isDense: true), onChanged: (v) => item['brand'] = v)),
                  const SizedBox(width: 8),
                  Expanded(child: TextFormField(initialValue: item['spec']?.toString() ?? '', decoration: const InputDecoration(labelText: '规格', isDense: true), onChanged: (v) => item['spec'] = v)),
                ]),
                Row(children: [
                  Expanded(child: TextFormField(initialValue: item['quantity']?.toString() ?? '', decoration: const InputDecoration(labelText: '退货数量', isDense: true), keyboardType: TextInputType.number, onChanged: (v) => item['quantity'] = double.tryParse(v) ?? 0)),
                  const SizedBox(width: 8),
                  Expanded(child: TextFormField(initialValue: item['unit_price']?.toString() ?? '', decoration: const InputDecoration(labelText: '单价', isDense: true), keyboardType: TextInputType.number, onChanged: (v) => item['unit_price'] = double.tryParse(v) ?? 0)),
                ]),
                Row(children: [
                  Expanded(child: TextFormField(initialValue: item['production_date']?.toString() ?? '', decoration: const InputDecoration(labelText: '生产日期', isDense: true), readOnly: true, onTap: () async {
                    final picked = await showDatePicker(context: ctx, initialDate: DateTime.now(), firstDate: DateTime(2020), lastDate: DateTime.now());
                    if (picked != null) setSt(() => item['production_date'] = DateFormat('yyyy-MM-dd').format(picked));
                  })),
                  const SizedBox(width: 8),
                  Expanded(child: DropdownButtonFormField<String>(value: item['usage']?.toString(), decoration: const InputDecoration(labelText: '用途', isDense: true),
                    items: ['厨房使用', '冷库储存', '吧台使用', '外卖专用', '损耗', '其他'].map((u) => DropdownMenuItem(value: u, child: Text(u))).toList(),
                    onChanged: (v) => setSt(() => item['usage'] = v))),
                ]),
                Align(alignment: Alignment.centerRight, child: TextButton(onPressed: () => setSt(() => items.removeAt(idx)), child: const Text('删除', style: TextStyle(color: AppColors.danger)))),
              ])));
            }),
            TextButton.icon(onPressed: () => setSt(() => items.add({'ingredient_id': null, 'quantity': 0, 'unit_price': 0, 'production_date': '', 'usage': null})), icon: const Icon(Icons.add), label: const Text('添加明细')),
            if (items.isNotEmpty) ...[const Divider(), Text('退货合计: ¥${total.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppColors.danger))],
          ]))),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
            ElevatedButton(onPressed: items.isEmpty ? null : () => Navigator.pop(ctx, true), style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger, foregroundColor: Colors.white), child: const Text('确认退货')),
          ],
        );
      }),
    );
    if (result == true) {
      final no = 'TH-${DateFormat('yyyyMMdd-HHmmss').format(DateTime.now())}';
      double totalAmount = items.fold<double>(0, (s, item) => s + ((item['quantity'] as num? ?? 0) * (item['unit_price'] as num? ?? 0)));
      final purchaseId = await db.insert('purchases', {'purchase_no': no, 'purchase_date': dateCtrl.text, 'supplier_id': supplierId, 'total_amount': -totalAmount, 'operator': operatorCtrl.text.trim(), 'remark': '[退货]${remarkCtrl.text.trim()}'});
      for (final item in items) {
        if (item['ingredient_id'] != null) {
          await db.insert('purchase_items', {'purchase_id': purchaseId, 'ingredient_id': item['ingredient_id'], 'quantity': item['quantity'] ?? 0, 'unit_price': item['unit_price'] ?? 0, 'total_price': -((item['quantity'] ?? 0) * (item['unit_price'] ?? 0)), 'production_date': item['production_date'] ?? '', 'usage': item['usage'] ?? ''});
        }
      }
      _load();
    }
  }
  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      body: Column(children: [
        Padding(padding: const EdgeInsets.all(8), child: Row(children: [
          Expanded(child: ElevatedButton.icon(onPressed: _addPurchase, icon: const Icon(Icons.add, size: 18), label: const Text('新增进货'), style: ElevatedButton.styleFrom(backgroundColor: AppColors.primary, foregroundColor: Colors.white))),
          const SizedBox(width: 8),
          Expanded(child: ElevatedButton.icon(onPressed: _addReturn, icon: const Icon(Icons.remove, size: 18), label: const Text('退货'), style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger, foregroundColor: Colors.white))),
        ])),
        Expanded(child: _records.isEmpty ? _buildEmpty('暂无进货记录') : _buildRecordList(_records, AppColors.primary, Icons.shopping_cart)),
      ]),
    );
  }
}

// ═══════════════════════════════════════════
// 出库管理（录入/编辑/撤销）
// ═══════════════════════════════════════════
class _StockOutTab extends StatefulWidget {
  @override
  State<_StockOutTab> createState() => _StockOutTabState();
}
class _StockOutTabState extends State<_StockOutTab> {
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;
  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _records = await LocalDb.instance.rawQuery(
        "SELECT p.*, s.name as supplier_name FROM purchases p LEFT JOIN suppliers s ON p.supplier_id = s.id WHERE p.purchase_no LIKE 'CK%' ORDER BY p.purchase_date DESC, p.id DESC");
    } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }
  Future<void> _addStockOut() async {
    final db = LocalDb.instance;
    final ingredients = await db.rawQuery('SELECT * FROM ingredients WHERE stock > 0 ORDER BY name');
    if (ingredients.isEmpty) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('暂无库存可出库'), backgroundColor: AppColors.warning)); return; }
    final dateCtrl = TextEditingController(text: DateFormat('yyyy-MM-dd').format(DateTime.now()));
    final operatorCtrl = TextEditingController();
    final remarkCtrl = TextEditingController();
    int? ingId = ingredients.first['id'];
    final qtyCtrl = TextEditingController();
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) => AlertDialog(
        title: const Text('新增出库'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: dateCtrl, decoration: const InputDecoration(labelText: '出库日期'), readOnly: true, onTap: () async {
            final picked = await showDatePicker(context: ctx, initialDate: DateTime.now(), firstDate: DateTime(2020), lastDate: DateTime.now().add(const Duration(days: 365)));
            if (picked != null) dateCtrl.text = DateFormat('yyyy-MM-dd').format(picked);
          }),
          const SizedBox(height: 8),
          DropdownButtonFormField<int>(value: ingId, decoration: const InputDecoration(labelText: '食材'),
            items: ingredients.map((ing) { final stock = (ing['stock'] as num?)?.toDouble() ?? 0; return DropdownMenuItem(value: ing['id'] as int, child: Text('${ing['name']} (库存: ${stock.toStringAsFixed(1)} ${ing['unit']})')); }).toList(),
            onChanged: (v) => setSt(() => ingId = v)),
          const SizedBox(height: 8),
          TextField(controller: qtyCtrl, decoration: const InputDecoration(labelText: '出库数量'), keyboardType: TextInputType.number),
          const SizedBox(height: 8),
          TextField(controller: operatorCtrl, decoration: const InputDecoration(labelText: '经办人')),
          const SizedBox(height: 8),
          TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '备注')),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存'))],
      )),
    );
    if (result == true && ingId != null) {
      final qty = double.tryParse(qtyCtrl.text) ?? 0;
      if (qty <= 0) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请输入有效数量'), backgroundColor: AppColors.danger)); return; }
      final no = 'CK-${DateFormat('yyyyMMdd-HHmmss').format(DateTime.now())}';
      final ing = ingredients.firstWhere((e) => e['id'] == ingId);
      final price = (ing['price'] as num?)?.toDouble() ?? 0;
      final purchaseId = await db.insert('purchases', {'purchase_no': no, 'purchase_date': dateCtrl.text, 'total_amount': qty * price, 'operator': operatorCtrl.text.trim(), 'remark': remarkCtrl.text.trim()});
      await db.insert('purchase_items', {'purchase_id': purchaseId, 'ingredient_id': ingId, 'quantity': qty, 'unit_price': price, 'total_price': qty * price});
      _load();
    }
  }
  Future<void> _editStockOut(Map<String, dynamic> record) async {
    final db = LocalDb.instance;
    final items = await db.rawQuery('SELECT * FROM purchase_items WHERE purchase_id=?', [record['id']]);
    if (items.isEmpty) return;
    final item = items.first;
    final dateCtrl = TextEditingController(text: record['purchase_date']?.toString() ?? '');
    final operatorCtrl = TextEditingController(text: record['operator']?.toString() ?? '');
    final qtyCtrl = TextEditingController(text: item['quantity']?.toString() ?? '');
    final remarkCtrl = TextEditingController(text: record['remark']?.toString() ?? '');
    final result = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('编辑出库'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: dateCtrl, decoration: const InputDecoration(labelText: '出库日期'), readOnly: true, onTap: () async {
          final picked = await showDatePicker(context: ctx, initialDate: DateTime.now(), firstDate: DateTime(2020), lastDate: DateTime.now().add(const Duration(days: 365)));
          if (picked != null) dateCtrl.text = DateFormat('yyyy-MM-dd').format(picked);
        }),
        const SizedBox(height: 8),
        TextField(controller: operatorCtrl, decoration: const InputDecoration(labelText: '经办人')),
        const SizedBox(height: 8),
        TextField(controller: qtyCtrl, decoration: const InputDecoration(labelText: '出库数量'), keyboardType: TextInputType.number),
        const SizedBox(height: 8),
        TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '备注')),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存'))],
    ));
    if (result == true) {
      final qty = double.tryParse(qtyCtrl.text) ?? 0;
      final price = (item['unit_price'] as num?)?.toDouble() ?? 0;
      await db.update('purchases', {'purchase_date': dateCtrl.text, 'operator': operatorCtrl.text.trim(), 'remark': remarkCtrl.text.trim(), 'total_amount': qty * price}, where: 'id=?', whereArgs: [record['id']]);
      await db.update('purchase_items', {'quantity': qty, 'total_price': qty * price}, where: 'id=?', whereArgs: [item['id']]);
      _load();
    }
  }
  Future<void> _undoStockOut(int purchaseId) async {
    final confirm = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('撤销出库'), content: const Text('确定要撤销这条出库记录吗？撤销后库存将自动恢复。'),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('撤销', style: TextStyle(color: AppColors.danger)))],
    ));
    if (confirm == true) {
      await LocalDb.instance.delete('purchase_items', where: 'purchase_id=?', whereArgs: [purchaseId]);
      await LocalDb.instance.delete('purchases', where: 'id=?', whereArgs: [purchaseId]);
      _load();
    }
  }
  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(onPressed: _addStockOut, backgroundColor: AppColors.warning, child: const Icon(Icons.add)),
      body: _records.isEmpty ? _buildEmpty('暂无出库记录') : ListView.builder(
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: _records.length,
        itemBuilder: (ctx, i) {
          final r = _records[i];
          final amount = (r['total_amount'] as num?)?.toDouble() ?? 0;
          return Card(child: ExpansionTile(
            leading: CircleAvatar(backgroundColor: AppColors.warning.withValues(alpha: 0.1), child: const Icon(Icons.outbox, color: AppColors.warning, size: 20)),
            title: Text(r['purchase_no'] as String? ?? ''),
            subtitle: Text('${r['purchase_date'] ?? ''} · ${r['operator'] ?? ''}'),
            trailing: PopupMenuButton(itemBuilder: (ctx) => [
              const PopupMenuItem(value: 'edit', child: Text('编辑')),
              const PopupMenuItem(value: 'undo', child: Text('撤销出库')),
            ], onSelected: (v) {
              if (v == 'edit') _editStockOut(r);
              if (v == 'undo') _undoStockOut(r['id'] as int);
            }),
            children: [
              FutureBuilder<List<Map<String, dynamic>>>(
                future: LocalDb.instance.rawQuery('SELECT pi.*, i.name as ingredient_name, i.unit FROM purchase_items pi LEFT JOIN ingredients i ON pi.ingredient_id = i.id WHERE pi.purchase_id = ?', [r['id']]),
                builder: (ctx, snap) {
                  if (!snap.hasData) return const Padding(padding: EdgeInsets.all(16), child: CircularProgressIndicator());
                  return Column(children: snap.data!.map((item) {
                    final qty = (item['quantity'] as num?)?.toDouble() ?? 0;
                    return ListTile(dense: true, title: Text(item['ingredient_name'] ?? '未知'), subtitle: Text('数量: ${qty.toStringAsFixed(2)} ${item['unit'] ?? ''}'));
                  }).toList());
                },
              ),
            ],
          ));
        },
      ),
    );
  }
}

// ═══════════════════════════════════════════
// 供货商进货明细
// ═══════════════════════════════════════════
class _SupplierQueryTab extends StatefulWidget {
  @override
  State<_SupplierQueryTab> createState() => _SupplierQueryTabState();
}
class _SupplierQueryTabState extends State<_SupplierQueryTab> {
  List<Map<String, dynamic>> _suppliers = [];
  int? _selectedSupplierId;
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;
  @override
  void initState() { super.initState(); _loadSuppliers(); }
  Future<void> _loadSuppliers() async {
    try {
      _suppliers = await LocalDb.instance.query('suppliers', orderBy: 'name');
      if (_suppliers.isNotEmpty) { _selectedSupplierId = _suppliers.first['id']; await _loadRecords(); }
    } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }
  Future<void> _loadRecords() async {
    if (_selectedSupplierId == null) return;
    _records = await LocalDb.instance.rawQuery(
      "SELECT p.*, s.name as supplier_name FROM purchases p LEFT JOIN suppliers s ON p.supplier_id = s.id WHERE p.supplier_id=? AND p.purchase_no LIKE 'CG%' ORDER BY p.purchase_date DESC", [_selectedSupplierId]);
    setState(() {});
  }
  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(children: [
      Padding(padding: const EdgeInsets.all(AppSpacing.md), child: DropdownButtonFormField<int>(
        value: _selectedSupplierId, decoration: const InputDecoration(labelText: '选择供货商'),
        items: _suppliers.map((s) => DropdownMenuItem(value: s['id'] as int, child: Text(s['name'] as String? ?? ''))).toList(),
        onChanged: (v) { setState(() => _selectedSupplierId = v); _loadRecords(); },
      )),
      Expanded(child: _records.isEmpty ? _buildEmpty('暂无进货明细') : _buildRecordList(_records, AppColors.info, Icons.receipt_long)),
    ]);
  }
}

// ═══════════════════════════════════════════
// 供货商管理（新增/编辑/删除）
// ═══════════════════════════════════════════
class _SupplierTab extends StatefulWidget {
  @override
  State<_SupplierTab> createState() => _SupplierTabState();
}
class _SupplierTabState extends State<_SupplierTab> {
  List<Map<String, dynamic>> _suppliers = [];
  bool _loading = true;
  static const _paymentMethods = ['现结', '月结', '周结', '货到付款', '预付款', '季结', '半年结'];
  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() => _loading = true);
    try { _suppliers = await LocalDb.instance.query('suppliers', orderBy: 'id DESC'); } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }
  Future<void> _addOrEdit([Map<String, dynamic>? existing]) async {
    final nameCtrl = TextEditingController(text: existing?['name']?.toString() ?? '');
    final contactCtrl = TextEditingController(text: existing?['contact']?.toString() ?? '');
    final phoneCtrl = TextEditingController(text: existing?['phone']?.toString() ?? '');
    final addressCtrl = TextEditingController(text: existing?['address']?.toString() ?? '');
    final remarkCtrl = TextEditingController(text: existing?['remark']?.toString() ?? '');
    String pm = existing?['payment_method']?.toString() ?? '现结';
    final result = await showDialog<bool>(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) => AlertDialog(
      title: Text(existing == null ? '新增供货商' : '编辑供货商'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: '供货商名称 *')),
        const SizedBox(height: 8), TextField(controller: contactCtrl, decoration: const InputDecoration(labelText: '联系人')),
        const SizedBox(height: 8), TextField(controller: phoneCtrl, decoration: const InputDecoration(labelText: '电话'), keyboardType: TextInputType.phone),
        const SizedBox(height: 8), TextField(controller: addressCtrl, decoration: const InputDecoration(labelText: '地址')),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(value: pm, decoration: const InputDecoration(labelText: '结款方式'),
          items: _paymentMethods.map((m) => DropdownMenuItem(value: m, child: Text(m))).toList(), onChanged: (v) => setSt(() => pm = v!)),
        const SizedBox(height: 8), TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '备注')),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存'))],
    )));
    if (result == true) {
      final data = {'name': nameCtrl.text.trim(), 'contact': contactCtrl.text.trim(), 'phone': phoneCtrl.text.trim(), 'address': addressCtrl.text.trim(), 'payment_method': pm, 'remark': remarkCtrl.text.trim()};
      if (existing == null) { await LocalDb.instance.insert('suppliers', data); }
      else { await LocalDb.instance.update('suppliers', data, where: 'id=?', whereArgs: [existing['id']]); }
      _load();
    }
  }
  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('确认删除'), content: const Text('确定要删除这个供货商吗？'),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger)))],
    ));
    if (confirm == true) { await LocalDb.instance.delete('suppliers', where: 'id=?', whereArgs: [id]); _load(); }
  }
  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(onPressed: () => _addOrEdit(), child: const Icon(Icons.add)),
      body: _suppliers.isEmpty ? _buildEmpty('暂无供货商') : ListView.builder(
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: _suppliers.length,
        itemBuilder: (ctx, i) {
          final s = _suppliers[i];
          final pm = s['payment_method'] as String? ?? '现结';
          final pmColor = {'现结': AppColors.success, '月结': AppColors.info, '货到付款': AppColors.warning, '预付款': AppColors.danger}[pm] ?? AppColors.textSecondary;
          return Card(child: ListTile(
            leading: CircleAvatar(backgroundColor: AppColors.primary.withValues(alpha: 0.1), child: const Icon(Icons.store, color: AppColors.primary, size: 20)),
            title: Text(s['name'] as String? ?? ''),
            subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${s['contact'] ?? ''} · ${s['phone'] ?? ''}'),
              const SizedBox(height: 4),
              Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2), decoration: BoxDecoration(color: pmColor!.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)), child: Text(pm, style: TextStyle(color: pmColor, fontSize: 11))),
            ]),
            trailing: PopupMenuButton(itemBuilder: (ctx) => [const PopupMenuItem(value: 'edit', child: Text('编辑')), const PopupMenuItem(value: 'delete', child: Text('删除'))],
              onSelected: (v) { if (v == 'edit') _addOrEdit(s); if (v == 'delete') _delete(s['id'] as int); }),
          ));
        },
      ),
    );
  }
}

// ═══════════════════════════════════════════
// 产品数据（食材管理：新增/编辑/删除）
// ═══════════════════════════════════════════
class _ProductTab extends StatefulWidget {
  @override
  State<_ProductTab> createState() => _ProductTabState();
}
class _ProductTabState extends State<_ProductTab> {
  List<Map<String, dynamic>> _products = [];
  bool _loading = true;
  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    setState(() => _loading = true);
    try { _products = await LocalDb.instance.query('ingredients', orderBy: 'name'); } catch (e) { debugPrint('Load error: $e'); }
    setState(() => _loading = false);
  }
  Future<void> _addOrEdit([Map<String, dynamic>? existing]) async {
    final nameCtrl = TextEditingController(text: existing?['name']?.toString() ?? '');
    final unitCtrl = TextEditingController(text: existing?['unit']?.toString() ?? '斤');
    final brandCtrl = TextEditingController(text: existing?['brand']?.toString() ?? '');
    final specCtrl = TextEditingController(text: existing?['spec']?.toString() ?? '');
    final priceCtrl = TextEditingController(text: existing?['price']?.toString() ?? '');
    final minStockCtrl = TextEditingController(text: existing?['min_stock']?.toString() ?? '');
    final expiryCtrl = TextEditingController(text: existing?['expiry_value']?.toString() ?? '');
    String category = existing?['category']?.toString() ?? '肉类';
    String expiryUnit = existing?['expiry_unit']?.toString() ?? '天';
    final categories = ['肉类', '蔬菜', '海鲜', '调料', '粮油', '酒水', '干货', '水果', '其他'];
    final result = await showDialog<bool>(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setSt) => AlertDialog(
      title: Text(existing == null ? '新增食材' : '编辑食材'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: '名称 *')),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(value: category, decoration: const InputDecoration(labelText: '分类'),
          items: categories.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(), onChanged: (v) => setSt(() => category = v!)),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: TextField(controller: brandCtrl, decoration: const InputDecoration(labelText: '品牌'))),
          const SizedBox(width: 8),
          Expanded(child: TextField(controller: specCtrl, decoration: const InputDecoration(labelText: '规格'))),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: TextField(controller: unitCtrl, decoration: const InputDecoration(labelText: '单位'))),
          const SizedBox(width: 8),
          Expanded(child: TextField(controller: priceCtrl, decoration: const InputDecoration(labelText: '单价'), keyboardType: TextInputType.number)),
        ]),
        const SizedBox(height: 8),
        TextField(controller: minStockCtrl, decoration: const InputDecoration(labelText: '最低库存预警'), keyboardType: TextInputType.number),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: TextField(controller: expiryCtrl, decoration: const InputDecoration(labelText: '保质期'), keyboardType: TextInputType.number)),
          const SizedBox(width: 8),
          Expanded(child: DropdownButtonFormField<String>(value: expiryUnit, decoration: const InputDecoration(labelText: '单位'),
            items: ['天', '月'].map((u) => DropdownMenuItem(value: u, child: Text(u))).toList(), onChanged: (v) => setSt(() => expiryUnit = v!))),
        ]),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存'))],
    )));
    if (result == true) {
      final data = {
        'name': nameCtrl.text.trim(), 'category': category, 'brand': brandCtrl.text.trim(), 'spec': specCtrl.text.trim(),
        'unit': unitCtrl.text.trim(), 'price': double.tryParse(priceCtrl.text) ?? 0, 'min_stock': double.tryParse(minStockCtrl.text) ?? 0,
        'expiry_value': int.tryParse(expiryCtrl.text) ?? 0, 'expiry_unit': expiryUnit,
      };
      if (existing == null) { data['stock'] = 0; await LocalDb.instance.insert('ingredients', data); }
      else { await LocalDb.instance.update('ingredients', data, where: 'id=?', whereArgs: [existing['id']]); }
      _load();
    }
  }
  Future<void> _delete(int id) async {
    final confirm = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('确认删除'), content: const Text('确定要删除这个食材吗？'),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger)))],
    ));
    if (confirm == true) { await LocalDb.instance.delete('ingredients', where: 'id=?', whereArgs: [id]); _load(); }
  }
  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(onPressed: () => _addOrEdit(), backgroundColor: AppColors.info, child: const Icon(Icons.add)),
      body: _products.isEmpty ? _buildEmpty('暂无食材数据') : ListView.builder(
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: _products.length,
        itemBuilder: (ctx, i) {
          final p = _products[i];
          final stock = (p['stock'] as num?)?.toDouble() ?? 0;
          final price = (p['price'] as num?)?.toDouble() ?? 0;
          final minStock = (p['min_stock'] as num?)?.toDouble() ?? 0;
          final isLow = minStock > 0 && stock < minStock;
          return Card(child: ListTile(
            leading: CircleAvatar(backgroundColor: (isLow ? AppColors.danger : AppColors.success).withValues(alpha: 0.1), child: Icon(isLow ? Icons.warning : Icons.restaurant, color: isLow ? AppColors.danger : AppColors.success, size: 20)),
            title: Text('${p['name']} (${p['unit']})'),
            subtitle: Text('${p['brand'] ?? ''} ${p['spec'] ?? ''} · 库存: ${stock.toStringAsFixed(1)} · ¥${price.toStringAsFixed(2)}'),
            trailing: PopupMenuButton(itemBuilder: (ctx) => [const PopupMenuItem(value: 'edit', child: Text('编辑')), const PopupMenuItem(value: 'delete', child: Text('删除'))],
              onSelected: (v) { if (v == 'edit') _addOrEdit(p); if (v == 'delete') _delete(p['id'] as int); }),
          ));
        },
      ),
    );
  }
}

// ═══════════════════════════════════════════
// 公共组件
// ═══════════════════════════════════════════
Widget _buildRecordList(List<Map<String, dynamic>> records, Color color, IconData icon) {
  return ListView.builder(
    padding: const EdgeInsets.all(AppSpacing.md),
    itemCount: records.length,
    itemBuilder: (ctx, i) {
      final r = records[i];
      final amount = (r['total_amount'] as num?)?.toDouble() ?? 0;
      return Card(child: ExpansionTile(
        leading: CircleAvatar(backgroundColor: color.withValues(alpha: 0.1), child: Icon(icon, color: color, size: 20)),
        title: Text(r['purchase_no'] as String? ?? ''),
        subtitle: Text('${r['purchase_date'] ?? ''} · ${r['supplier_name'] ?? r['operator'] ?? ''}'),
        trailing: Text('¥${amount.toStringAsFixed(2)}', style: TextStyle(fontWeight: FontWeight.bold, color: color)),
        children: [
          FutureBuilder<List<Map<String, dynamic>>>(
            future: LocalDb.instance.rawQuery('SELECT pi.*, i.name as ingredient_name, i.unit, i.brand, i.spec FROM purchase_items pi LEFT JOIN ingredients i ON pi.ingredient_id = i.id WHERE pi.purchase_id = ?', [r['id']]),
            builder: (ctx, snap) {
              if (!snap.hasData) return const Padding(padding: EdgeInsets.all(16), child: CircularProgressIndicator());
              final items = snap.data!;
              if (items.isEmpty) return const ListTile(dense: true, title: Text('无明细'));
              return Column(children: items.map((item) {
                final qty = (item['quantity'] as num?)?.toDouble() ?? 0;
                final price = (item['unit_price'] as num?)?.toDouble() ?? 0;
                final total = (item['total_price'] as num?)?.toDouble() ?? 0;
                return ListTile(dense: true,
                  title: Text('${item['ingredient_name'] ?? '未知'} ${item['brand'] != null && (item['brand'] as String).isNotEmpty ? '· ${item['brand']}' : ''} ${item['spec'] != null && (item['spec'] as String).isNotEmpty ? '· ${item['spec']}' : ''}'),
                  subtitle: Text('${qty.toStringAsFixed(2)} ${item['unit'] ?? ''} × ¥${price.toStringAsFixed(2)}${item['production_date'] != null && (item['production_date'] as String).isNotEmpty ? ' · 生产: ${item['production_date']}' : ''}${item['usage'] != null && (item['usage'] as String).isNotEmpty ? ' · ${item['usage']}' : ''}'),
                  trailing: Text('¥${total.toStringAsFixed(2)}', style: const TextStyle(color: AppColors.success)),
                );
              }).toList());
            },
          ),
        ],
      ));
    },
  );
}

Widget _buildEmpty(String text) {
  return Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
    Icon(Icons.inbox, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
    const SizedBox(height: 16),
    Text(text, style: TextStyle(color: AppColors.textSecondary)),
  ]));
}
