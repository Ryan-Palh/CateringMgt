// screens/approval_screen.dart — 审批管理（v5.0 使用 approvals 表）
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class ApprovalScreen extends StatefulWidget {
  const ApprovalScreen({super.key});

  @override
  State<ApprovalScreen> createState() => _ApprovalScreenState();
}

class _ApprovalScreenState extends State<ApprovalScreen> {
  List<Map<String, dynamic>> _records = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      // 查询待审批的报销记录
      _records = await LocalDb.instance.rawQuery(
        "SELECT r.*, e.name as applicant_name FROM reimbursements r "
        "LEFT JOIN employees e ON r.employee_id = e.id "
        "WHERE r.status='待审批' ORDER BY r.submit_date DESC, r.id DESC",
      );
    } catch (e) {
      debugPrint('Load error: $e');
    }
    setState(() => _loading = false);
  }

  Future<void> _approve(int id, bool approved) async {
    final status = approved ? '已批准' : '已拒绝';
    final now = DateTime.now().toString().substring(0, 19);

    await LocalDb.instance.update(
      'reimbursements',
      {
        'status': status,
        'approve_date': now.substring(0, 10),
      },
      where: 'id=?',
      whereArgs: [id],
    );

    // 同步写入审批记录
    final record = await LocalDb.instance.query('reimbursements', where: 'id=?', whereArgs: [id]);
    if (record.isNotEmpty) {
      final r = record.first;
      await LocalDb.instance.insert('approvals', {
        'biz_type': 'reimbursement',
        'biz_id': id,
        'title': r['title'] ?? r['category'] ?? '',
        'amount': r['amount'] ?? 0,
        'applicant_id': r['employee_id'],
        'status': status,
        'comment': approved ? '审批通过' : '审批拒绝',
        'updated_at': now,
      });
    }

    _load();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      body: _records.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.check_circle_outline, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
                  const SizedBox(height: 16),
                  const Text('暂无待审批记录', style: TextStyle(color: AppColors.textSecondary)),
                ],
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(AppSpacing.md),
              itemCount: _records.length,
              itemBuilder: (ctx, i) {
                final r = _records[i];
                final amount = (r['amount'] as num?)?.toDouble() ?? 0;
                final title = r['title'] as String? ?? r['category'] as String? ?? '';
                final applicant = r['applicant_name'] as String? ?? '未知';
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            CircleAvatar(
                              backgroundColor: AppColors.warning.withValues(alpha: 0.1),
                              child: const Icon(Icons.pending, color: AppColors.warning, size: 20),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('$applicant · $title', style: const TextStyle(fontWeight: FontWeight.bold)),
                                  Text('${r['submit_date'] ?? ''} · ${r['reimb_no'] ?? ''}', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                                ],
                              ),
                            ),
                            Text('¥${amount.toStringAsFixed(2)}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.danger)),
                          ],
                        ),
                        if (r['remark'] != null && (r['remark'] as String).isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(color: AppColors.textSecondary.withValues(alpha: 0.05), borderRadius: BorderRadius.circular(4)),
                            child: Text(r['remark'] as String, style: const TextStyle(fontSize: 13)),
                          ),
                        ],
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: () => _approve(r['id'] as int, false),
                                icon: const Icon(Icons.close, size: 18),
                                label: const Text('拒绝'),
                                style: OutlinedButton.styleFrom(foregroundColor: AppColors.danger),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: ElevatedButton.icon(
                                onPressed: () => _approve(r['id'] as int, true),
                                icon: const Icon(Icons.check, size: 18),
                                label: const Text('批准'),
                                style: ElevatedButton.styleFrom(backgroundColor: AppColors.success),
                              ),
                            ),
                          ],
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