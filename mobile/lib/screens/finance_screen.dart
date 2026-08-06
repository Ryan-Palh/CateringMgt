// screens/finance_screen.dart — 收支管理（收入/支出 Tab切换）
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class FinanceScreen extends StatefulWidget {
  const FinanceScreen({super.key});

  @override
  State<FinanceScreen> createState() => _FinanceScreenState();
}

class _FinanceScreenState extends State<FinanceScreen>
    with TickerProviderStateMixin {
  late TabController _tabController;
  List<Map<String, dynamic>> _incomeRecords = [];
  List<Map<String, dynamic>> _expenseRecords = [];
  bool _loading = true;

  static const _incomeCategories = ['堂食营业额', '外卖平台结算', '外带打包', '会员充值', '包间服务费', '酒水销售', '其他收入'];
  // v5.0 与桌面端对齐的完整分类列表
  static const _expenseCategories = [
    '食材采购', '酒水采购', '工资', '房租', '物业费',
    '水费', '电费', '燃气费', '外卖平台佣金', '包装耗材',
    '餐具耗材', '设备维修', '营销推广', '保洁服务',
    '垃圾排污费', '办公用品', '交通费', '培训费',
    '员工福利', '保险', '税费', '证照年审',
    '员工餐费', '通讯费', '社保公积金', '其他支出'
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _load();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final db = LocalDb.instance;
      _incomeRecords = await db.query('finance_records', where: "record_type='收入'", orderBy: 'id DESC');
      _expenseRecords = await db.query('finance_records', where: "record_type='支出'", orderBy: 'id DESC');
    } catch (e) {
      debugPrint('Load error: $e');
    }
    setState(() => _loading = false);
  }

  Future<void> _addRecord(String type, List<String> categories) async {
    final amountCtrl = TextEditingController();
    final descCtrl = TextEditingController();
    String category = categories.first;
    String account = '现金';
    final today = DateFormat('yyyy-MM-dd').format(DateTime.now());

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => AlertDialog(
          title: Text('新增$type'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  value: category,
                  decoration: const InputDecoration(labelText: '分类'),
                  items: categories.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
                  onChanged: (v) => setSt(() => category = v!),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: amountCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '金额'),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: account,
                  decoration: const InputDecoration(labelText: '账户'),
                  items: ['现金', '微信', '支付宝', '银行卡', '其他'].map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
                  onChanged: (v) => setSt(() => account = v!),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: descCtrl,
                  decoration: const InputDecoration(labelText: '说明'),
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
      final amount = double.tryParse(amountCtrl.text) ?? 0;
      await LocalDb.instance.insert('finance_records', {
        'record_date': today,
        'record_type': type,
        'category': category,
        'amount': amount,
        'account': account,
        'description': descCtrl.text,
      });
      _load();
    }
  }

  Future<void> _deleteRecord(int id) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认删除'),
        content: const Text('确定要删除这条记录吗？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger))),
        ],
      ),
    );
    if (confirm == true) {
      await LocalDb.instance.delete('finance_records', where: 'id=?', whereArgs: [id]);
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    final incomeTotal = _incomeRecords.fold<double>(0, (s, r) => s + ((r['amount'] as num?)?.toDouble() ?? 0));
    final expenseTotal = _expenseRecords.fold<double>(0, (s, r) => s + ((r['amount'] as num?)?.toDouble() ?? 0));

    return Scaffold(
      appBar: TabBar(
        controller: _tabController,
        tabs: [
          Tab(text: '收入 (¥${incomeTotal.toStringAsFixed(0)})'),
          Tab(text: '支出 (¥${expenseTotal.toStringAsFixed(0)})'),
        ],
        labelColor: AppColors.primary,
        unselectedLabelColor: AppColors.textSecondary,
        indicatorColor: AppColors.primary,
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildList(_incomeRecords, '收入', AppColors.success, _incomeCategories),
          _buildList(_expenseRecords, '支出', AppColors.danger, _expenseCategories),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          if (_tabController.index == 0) {
            _addRecord('收入', _incomeCategories);
          } else {
            _addRecord('支出', _expenseCategories);
          }
        },
        child: const Icon(Icons.add),
      ),
    );
  }

  Widget _buildList(List<Map<String, dynamic>> records, String type, Color color, List<String> categories) {
    if (records.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.receipt, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
            const SizedBox(height: 16),
            Text('暂无$type记录', style: TextStyle(color: AppColors.textSecondary)),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: records.length,
      itemBuilder: (ctx, i) {
        final r = records[i];
        final amount = (r['amount'] as num?)?.toDouble() ?? 0;
        return Card(
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: color.withValues(alpha: 0.1),
              child: Icon(type == '收入' ? Icons.trending_up : Icons.trending_down, color: color, size: 20),
            ),
            title: Text(r['category'] as String? ?? ''),
            subtitle: Text('${r['record_date'] ?? ''} · ${r['account'] ?? ''}${r['description'] != null && (r['description'] as String).isNotEmpty ? ' · ${r['description']}' : ''}'),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('¥${amount.toStringAsFixed(2)}', style: TextStyle(fontWeight: FontWeight.bold, color: color)),
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: AppColors.danger, size: 20),
                  onPressed: () => _deleteRecord(r['id'] as int),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
