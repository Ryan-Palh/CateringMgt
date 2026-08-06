// screens/reimbursement_screen.dart — 报销管理
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class ReimbursementScreen extends StatefulWidget {
  const ReimbursementScreen({super.key});

  @override
  State<ReimbursementScreen> createState() => _ReimbursementScreenState();
}

class _ReimbursementScreenState extends State<ReimbursementScreen> {
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;

  static const _categories = [
    '差旅费', '办公费', '招待费', '交通费', '通讯费',
    '培训费', '维修费', '采购费', '员工福利', '其他'
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _records = await LocalDb.instance.query('reimbursements', orderBy: 'id DESC');
    } catch (e) {
      debugPrint('Load error: $e');
    }
    setState(() => _loading = false);
  }

  Future<void> _addRecord() async {
    final applicantCtrl = TextEditingController();
    final amountCtrl = TextEditingController();
    final remarkCtrl = TextEditingController();
    String category = _categories.first;
    final today = DateFormat('yyyy-MM-dd').format(DateTime.now());

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => AlertDialog(
          title: const Text('申请报销'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: applicantCtrl, decoration: const InputDecoration(labelText: '申请人 *')),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: category,
                  decoration: const InputDecoration(labelText: '分类'),
                  items: _categories.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
                  onChanged: (v) => setSt(() => category = v!),
                ),
                const SizedBox(height: 12),
                TextField(controller: amountCtrl, decoration: const InputDecoration(labelText: '金额'), keyboardType: TextInputType.number),
                const SizedBox(height: 12),
                TextField(controller: remarkCtrl, decoration: const InputDecoration(labelText: '备注')),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
            ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('提交')),
          ],
        ),
      ),
    );

    if (result == true) {
      final amount = double.tryParse(amountCtrl.text) ?? 0;
      final no = 'BX-${DateTime.now().millisecondsSinceEpoch}';
      await LocalDb.instance.insert('reimbursements', {
        'reimb_no': no,
        'title': '${applicantCtrl.text.trim()} - $category',
        'category': category,
        'amount': amount,
        'submit_date': today,
        'status': '待审批',
        'remark': remarkCtrl.text.trim(),
        'description': remarkCtrl.text.trim(),
      });
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      floatingActionButton: FloatingActionButton(
        onPressed: _addRecord,
        child: const Icon(Icons.add),
      ),
      body: _records.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.receipt_long, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
                  const SizedBox(height: 16),
                  const Text('暂无报销记录', style: TextStyle(color: AppColors.textSecondary)),
                ],
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(AppSpacing.md),
              itemCount: _records.length,
              itemBuilder: (ctx, i) {
                final r = _records[i];
                final amount = (r['amount'] as num?)?.toDouble() ?? 0;
                final status = r['status'] as String? ?? '待审批';
                final statusColor = {'待审批': AppColors.warning, '已批准': AppColors.success, '已拒绝': AppColors.danger}[status] ?? AppColors.textSecondary;
                return Card(
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: statusColor!.withValues(alpha: 0.1),
                      child: Icon(Icons.receipt, color: statusColor, size: 20),
                    ),
                    title: Text(r['title'] as String? ?? '${r['category'] ?? ''}'),
                    subtitle: Text('${r['submit_date'] ?? ''} · ${r['reimb_no'] ?? ''}'),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('¥${amount.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(color: statusColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
                          child: Text(status, style: TextStyle(color: statusColor, fontSize: 11)),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
