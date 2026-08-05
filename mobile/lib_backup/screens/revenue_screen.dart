// screens/revenue_screen.dart — 营业额录入与查看
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';
import '../models/models.dart';
import '../widgets/summary_card.dart';

class RevenueScreen extends StatefulWidget {
  const RevenueScreen({super.key});

  @override
  State<RevenueScreen> createState() => _RevenueScreenState();
}

class _RevenueScreenState extends State<RevenueScreen> {
  final _dateFormat = DateFormat('yyyy-MM-dd');
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;
  DateTime _selectedDate = DateTime.now();

  // 渠道选项
  final _channels = ['美团团购', '美团外卖', '饿了么', '抖音团购', '堂食', '大众点评'];
  String _selectedChannel = '堂食';

  final _amountCtrl = TextEditingController();
  final _orderCountCtrl = TextEditingController();
  final _remarkCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadRecords();
  }

  Future<void> _loadRecords() async {
    setState(() => _loading = true);
    try {
      final dateStr = _dateFormat.format(_selectedDate);
      final rows = await LocalDb.instance.rawQuery(
        "SELECT r.*, e.name as emp_name FROM daily_revenue r LEFT JOIN employees e ON r.operator = e.username WHERE r.record_date=? ORDER BY r.id DESC",
        [dateStr],
      );
      setState(() => _records = rows);
    } catch (e) {
      debugPrint('Revenue load error: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _addRecord() async {
    final amount = double.tryParse(_amountCtrl.text.trim()) ?? 0;
    if (amount <= 0) {
      _showError('请输入有效金额');
      return;
    }

    final orderCount = int.tryParse(_orderCountCtrl.text.trim()) ?? 0;
    final dateStr = _dateFormat.format(_selectedDate);

    final record = RevenueRecord(
      recordDate: dateStr,
      channel: _selectedChannel,
      amount: amount,
      orderCount: orderCount,
      cashAmount: _selectedChannel == '堂食' ? amount : 0,
      onlineAmount: _selectedChannel != '堂食' ? amount : 0,
      remark: _remarkCtrl.text.trim(),
    );

    await LocalDb.instance.insert('daily_revenue', record.toMap());

    _amountCtrl.clear();
    _orderCountCtrl.clear();
    _remarkCtrl.clear();

    _loadRecords();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('营业额已记录'), backgroundColor: AppColors.success),
      );
    }
  }

  Future<void> _deleteRecord(int id) async {
    await LocalDb.instance.delete('daily_revenue', where: 'id=?', whereArgs: [id]);
    _loadRecords();
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: AppColors.danger),
    );
  }

  @override
  Widget build(BuildContext context) {
    final todayTotal = _records.fold<double>(0, (s, r) => s + ((r['amount'] as num?)?.toDouble() ?? 0));
    final todayOrders = _records.fold<int>(0, (s, r) => s + ((r['order_count'] as int?) ?? 0));

    return Scaffold(
      appBar: AppBar(title: const Text('营业额')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                // 日期选择
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: Row(
                    children: [
                      Expanded(
                        child: InkWell(
                          onTap: () async {
                            final d = await showDatePicker(
                              context: context,
                              initialDate: _selectedDate,
                              firstDate: DateTime(2020),
                              lastDate: DateTime.now(),
                            );
                            if (d != null) {
                              setState(() => _selectedDate = d);
                              _loadRecords();
                            }
                          },
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.md),
                            decoration: BoxDecoration(
                              color: AppColors.bgCard,
                              borderRadius: BorderRadius.circular(AppRadius.sm),
                              border: Border.all(color: AppColors.divider),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.calendar_today, size: 18, color: AppColors.primary),
                                const SizedBox(width: AppSpacing.sm),
                                Text(DateFormat('yyyy-MM-dd EEE').format(_selectedDate)),
                                const Spacer(),
                                const Icon(Icons.arrow_drop_down, color: AppColors.textSecondary),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                // 汇总卡片
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                  child: Row(
                    children: [
                      Expanded(child: SummaryCard(title: '今日营业额', value: '¥${todayTotal.toStringAsFixed(2)}', color: AppColors.primary)),
                      const SizedBox(width: AppSpacing.sm),
                      Expanded(child: SummaryCard(title: '订单数', value: '$todayOrders', color: AppColors.success)),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                // 录入表单
                _buildInputForm(),
                const Divider(height: AppSpacing.lg),
                // 记录列表
                Expanded(child: _buildRecordList()),
              ],
            ),
    );
  }

  Widget _buildInputForm() {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('快速录入', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: AppSpacing.sm),
            // 渠道选择
            DropdownButtonFormField<String>(
              value: _selectedChannel,
              decoration: const InputDecoration(labelText: '渠道', isDense: true),
              items: _channels.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
              onChanged: (v) => setState(() => _selectedChannel = v ?? '堂食'),
            ),
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                Expanded(
                  flex: 2,
                  child: TextField(
                    controller: _amountCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: '金额(元)', isDense: true, prefixText: '¥'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  flex: 1,
                  child: TextField(
                    controller: _orderCountCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: '订单数', isDense: true),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            TextField(
              controller: _remarkCtrl,
              decoration: const InputDecoration(labelText: '备注', isDense: true),
            ),
            const SizedBox(height: AppSpacing.md),
            ElevatedButton.icon(
              onPressed: _addRecord,
              icon: const Icon(Icons.add),
              label: const Text('记录营业额'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRecordList() {
    if (_records.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.receipt_long_outlined, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.5)),
            const SizedBox(height: AppSpacing.md),
            Text('暂无营业额记录', style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: AppColors.textSecondary)),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      itemCount: _records.length,
      itemBuilder: (ctx, i) {
        final r = _records[i];
        final amount = (r['amount'] as num?)?.toDouble() ?? 0;
        final channel = r['channel'] as String? ?? '';
        final orders = r['order_count'] as int? ?? 0;
        final remark = r['remark'] as String? ?? '';

        return Dismissible(
          key: ValueKey(r['id']),
          direction: DismissDirection.endToStart,
          background: Container(
            alignment: Alignment.centerRight,
            color: AppColors.danger,
            padding: const EdgeInsets.only(right: AppSpacing.lg),
            child: const Icon(Icons.delete, color: Colors.white),
          ),
          onDismissed: (_) => _deleteRecord(r['id'] as int),
          child: Card(
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: AppColors.primary.withValues(alpha: 0.1),
                child: Text(channel.isNotEmpty ? channel[0] : '?', style: const TextStyle(color: AppColors.primary)),
              ),
              title: Text(channel, style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Text([
                if (orders > 0) '$orders单',
                if (remark.isNotEmpty) remark,
              ].join(' · ')),
              trailing: Text(
                '¥${amount.toStringAsFixed(2)}',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.primary),
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  void dispose() {
    _amountCtrl.dispose();
    _orderCountCtrl.dispose();
    _remarkCtrl.dispose();
    super.dispose();
  }
}
