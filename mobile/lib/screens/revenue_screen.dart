// screens/revenue_screen.dart — 营业额管理（录入/列表/按日期分组）
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class RevenueScreen extends StatefulWidget {
  const RevenueScreen({super.key});

  @override
  State<RevenueScreen> createState() => _RevenueScreenState();
}

class _RevenueScreenState extends State<RevenueScreen> {
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;
  DateTime _selectedDate = DateTime.now();

  @override
  void initState() {
    super.initState();
    _loadRecords();
  }

  Future<void> _loadRecords() async {
    setState(() => _loading = true);
    try {
      final dateStr = DateFormat('yyyy-MM-dd').format(_selectedDate);
      final db = LocalDb.instance;
      _records = await db.rawQuery(
        "SELECT * FROM daily_revenue WHERE record_date=? ORDER BY id DESC",
        [dateStr],
      );
    } catch (e) {
      debugPrint('Load error: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _addRecord() async {
    final amountCtrl = TextEditingController();
    final orderCtrl = TextEditingController(text: '0');
    final remarkCtrl = TextEditingController();
    String channel = '堂食';
    String packageType = '';

    // 从数据库读取渠道配置，而非硬编码
    final channelRows = await LocalDb.instance.rawQuery(
      'SELECT channel_name FROM revenue_channels ORDER BY sort_order ASC',
    );
    final channels = channelRows.isNotEmpty
        ? channelRows.map((r) => r['channel_name'] as String).toList()
        : ['堂食', '外卖', '外带', '包间', '酒水', '其他'];
    if (channels.isNotEmpty) channel = channels.first;
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => AlertDialog(
          title: const Text('录入营业额'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  value: channel,
                  decoration: const InputDecoration(labelText: '渠道'),
                  items: channels.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
                  onChanged: (v) => setSt(() => channel = v!),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: amountCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '金额'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: orderCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '订单数'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: remarkCtrl,
                  decoration: const InputDecoration(labelText: '备注'),
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
      final orders = int.tryParse(orderCtrl.text) ?? 0;
      final dateStr = DateFormat('yyyy-MM-dd').format(_selectedDate);
      final db = LocalDb.instance;
      await db.insert('daily_revenue', {
        'record_date': dateStr,
        'channel': channel,
        'amount': amount,
        'order_count': orders,
        'remark': remarkCtrl.text,
      });
      _loadRecords();
    }
  }

  Future<void> _deleteRecord(int id) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认删除'),
        content: const Text('确定要删除这条营业额记录吗？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除', style: TextStyle(color: AppColors.danger))),
        ],
      ),
    );
    if (confirm == true) {
      await LocalDb.instance.delete('daily_revenue', where: 'id=?', whereArgs: [id]);
      _loadRecords();
    }
  }

  @override
  Widget build(BuildContext context) {
    final dateStr = DateFormat('yyyy-MM-dd').format(_selectedDate);
    final totalAmount = _records.fold<double>(0, (sum, r) => sum + ((r['amount'] as num?)?.toDouble() ?? 0));
    final totalOrders = _records.fold<int>(0, (sum, r) => sum + ((r['order_count'] as int?) ?? 0));

    return Scaffold(
      floatingActionButton: FloatingActionButton(
        onPressed: _addRecord,
        child: const Icon(Icons.add),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                // 日期选择栏
                Container(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  color: AppColors.primary.withValues(alpha: 0.05),
                  child: Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.chevron_left),
                        onPressed: () {
                          setState(() => _selectedDate = _selectedDate.subtract(const Duration(days: 1)));
                          _loadRecords();
                        },
                      ),
                      Expanded(
                        child: GestureDetector(
                          onTap: () async {
                            final picked = await showDatePicker(
                              context: context,
                              initialDate: _selectedDate,
                              firstDate: DateTime(2020),
                              lastDate: DateTime.now(),
                            );
                            if (picked != null) {
                              setState(() => _selectedDate = picked);
                              _loadRecords();
                            }
                          },
                          child: Text(
                            dateStr,
                            textAlign: TextAlign.center,
                            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.chevron_right),
                        onPressed: _selectedDate.isBefore(DateTime.now())
                            ? () {
                                setState(() => _selectedDate = _selectedDate.add(const Duration(days: 1)));
                                _loadRecords();
                              }
                            : null,
                      ),
                    ],
                  ),
                ),
                // 汇总卡片
                if (_records.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                    padding: const EdgeInsets.all(AppSpacing.md),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [AppColors.primary.withValues(alpha: 0.1), AppColors.info.withValues(alpha: 0.05)],
                      ),
                      borderRadius: BorderRadius.circular(AppRadius.md),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                      children: [
                        _buildSummaryItem('总营业额', '¥${totalAmount.toStringAsFixed(2)}'),
                        _buildSummaryItem('订单数', '$totalOrders'),
                        _buildSummaryItem('客单价', '¥${totalOrders > 0 ? (totalAmount / totalOrders).toStringAsFixed(1) : '0.0'}'),
                      ],
                    ),
                  ),
                // 记录列表
                Expanded(
                  child: _records.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.receipt_long, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
                              const SizedBox(height: 16),
                              Text('$dateStr 暂无营业额记录', style: TextStyle(color: AppColors.textSecondary)),
                            ],
                          ),
                        )
                      : Column(
                          children: [
                            // 表头
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                              color: AppColors.primary.withValues(alpha: 0.08),
                              child: const Row(
                                children: [
                                  SizedBox(width: 28, child: Text('#', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textSecondary))),
                                  Expanded(flex: 3, child: Text('渠道', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textSecondary))),
                                  Expanded(flex: 2, child: Text('数量', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textSecondary))),
                                  Expanded(flex: 3, child: Text('金额', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.textSecondary), textAlign: TextAlign.right)),
                                  SizedBox(width: 40),
                                ],
                              ),
                            ),
                            // 数据行
                            Expanded(
                              child: ListView.builder(
                                padding: EdgeInsets.zero,
                                itemCount: _records.length,
                                itemBuilder: (ctx, i) {
                                  final r = _records[i];
                                  final amount = (r['amount'] as num?)?.toDouble() ?? 0;
                                  final isLast = i == _records.length - 1;
                                  return Container(
                                    decoration: BoxDecoration(
                                      color: i.isEven ? Colors.white : AppColors.primary.withValues(alpha: 0.02),
                                      border: isLast ? null : Border(bottom: BorderSide(color: AppColors.textSecondary.withValues(alpha: 0.1))),
                                    ),
                                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm + 2),
                                    child: Row(
                                      children: [
                                        SizedBox(width: 28, child: Text('${i + 1}', style: TextStyle(fontSize: 13, color: AppColors.textSecondary))),
                                        Expanded(flex: 3, child: Text(r['channel'] as String? ?? '', style: const TextStyle(fontSize: 14))),
                                        Expanded(flex: 2, child: Text('${r['order_count'] ?? 0}', style: const TextStyle(fontSize: 14))),
                                        Expanded(
                                          flex: 3,
                                          child: Text('¥${amount.toStringAsFixed(2)}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppColors.success), textAlign: TextAlign.right),
                                        ),
                                        SizedBox(
                                          width: 40,
                                          child: IconButton(
                                            icon: const Icon(Icons.delete_outline, color: AppColors.danger, size: 20),
                                            onPressed: () => _deleteRecord(r['id'] as int),
                                            padding: EdgeInsets.zero,
                                            constraints: const BoxConstraints(),
                                          ),
                                        ),
                                      ],
                                    ),
                                  );
                                },
                              ),
                            ),
                          ],
                        ),
                ),
              ],
            ),
    );
  }

  Widget _buildSummaryItem(String label, String value) {
    return Column(
      children: [
        Text(label, style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.primary)),
      ],
    );
  }
}
