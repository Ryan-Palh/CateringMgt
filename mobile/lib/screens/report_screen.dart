// screens/report_screen.dart — 报表中心（图表形式）
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../utils/app_state.dart';
import '../api/local_db.dart';

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key});

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  bool _loading = true;
  List<Map<String, dynamic>> _revenueByDay = [];
  List<Map<String, dynamic>> _expenseByCategory = [];
  List<Map<String, dynamic>> _revenueByChannel = [];
  double _totalRevenue = 0;
  double _totalExpense = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final now = DateTime.now();
      final monthStr = DateFormat('yyyy-MM').format(now);
      final appState = context.read<AppState>();
      final storeId = appState.storeId;
      final storeFilter = storeId != null ? 'AND store_id=$storeId' : '';

      // 本月每日营业额
      _revenueByDay = await LocalDb.instance.rawQuery(
        "SELECT record_date, SUM(amount) as total FROM daily_revenue WHERE record_date LIKE ? $storeFilter GROUP BY record_date ORDER BY record_date",
        ['$monthStr%'],
      );

      // 本月支出分类
      _expenseByCategory = await LocalDb.instance.rawQuery(
        "SELECT category, SUM(amount) as total FROM finance_records WHERE record_type='支出' AND record_date LIKE ? $storeFilter GROUP BY category ORDER BY total DESC",
        ['$monthStr%'],
      );

      // 营业额渠道分布
      _revenueByChannel = await LocalDb.instance.rawQuery(
        "SELECT channel, SUM(amount) as total FROM daily_revenue WHERE record_date LIKE ? $storeFilter GROUP BY channel ORDER BY total DESC",
        ['$monthStr%'],
      );

      _totalRevenue = _revenueByDay.fold<double>(0, (s, r) => s + ((r['total'] as num?)?.toDouble() ?? 0));
      _totalExpense = _expenseByCategory.fold<double>(0, (s, r) => s + ((r['total'] as num?)?.toDouble() ?? 0));
    } catch (e) {
      debugPrint('Report load error: $e');
    }
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    final profit = _totalRevenue - _totalExpense;
    final maxRevenue = _revenueByDay.isEmpty ? 1.0 : _revenueByDay.map((r) => (r['total'] as num?)?.toDouble() ?? 0).reduce((a, b) => a > b ? a : b);
    final maxExpense = _expenseByCategory.isEmpty ? 1.0 : _expenseByCategory.map((r) => (r['total'] as num?)?.toDouble() ?? 0).reduce((a, b) => a > b ? a : b);
    final maxChannel = _revenueByChannel.isEmpty ? 1.0 : _revenueByChannel.map((r) => (r['total'] as num?)?.toDouble() ?? 0).reduce((a, b) => a > b ? a : b);

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.md),
        children: [
          // 利润概览卡片
          Card(
            child: Container(
              padding: const EdgeInsets.all(AppSpacing.lg),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: profit >= 0 ? [AppColors.success, AppColors.info] : [AppColors.danger, AppColors.warning],
                ),
                borderRadius: BorderRadius.circular(AppRadius.md),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${DateFormat('yyyy年MM月').format(DateTime.now())} 概览', style: const TextStyle(color: Colors.white70, fontSize: 14)),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _buildOverviewItem('营业额', '¥${_totalRevenue.toStringAsFixed(0)}'),
                      _buildOverviewItem('支出', '¥${_totalExpense.toStringAsFixed(0)}'),
                      _buildOverviewItem('净利润', '¥${profit.toStringAsFixed(0)}'),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          // 每日营业额柱状图
          _buildSectionTitle('本月每日营业额'),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: _revenueByDay.isEmpty
                  ? const Text('暂无数据')
                  : Column(
                      children: _revenueByDay.map((r) {
                        final date = r['record_date'] as String? ?? '';
                        final total = (r['total'] as num?)?.toDouble() ?? 0;
                        final day = date.length >= 10 ? date.substring(8, 10) : date;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 4),
                          child: Row(
                            children: [
                              SizedBox(width: 32, child: Text('$day日', style: const TextStyle(fontSize: 12))),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Stack(
                                  children: [
                                    Container(
                                      height: 20,
                                      decoration: BoxDecoration(
                                        color: AppColors.primary.withValues(alpha: 0.1),
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                    ),
                                    FractionallySizedBox(
                                      widthFactor: (total / maxRevenue).clamp(0.01, 1.0),
                                      child: Container(
                                        height: 20,
                                        decoration: BoxDecoration(
                                          gradient: LinearGradient(colors: [AppColors.primary, AppColors.info]),
                                          borderRadius: BorderRadius.circular(4),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 8),
                              SizedBox(width: 60, child: Text('¥${total.toStringAsFixed(0)}', style: const TextStyle(fontSize: 11), textAlign: TextAlign.right)),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          // 支出分类
          _buildSectionTitle('本月支出分类'),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: _expenseByCategory.isEmpty
                  ? const Text('暂无数据')
                  : Column(
                      children: _expenseByCategory.map((r) {
                        final category = r['category'] as String? ?? '';
                        final total = (r['total'] as num?)?.toDouble() ?? 0;
                        final pct = _totalExpense > 0 ? (total / _totalExpense * 100) : 0;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(category, style: const TextStyle(fontSize: 13)),
                                  Text('¥${total.toStringAsFixed(0)} (${pct.toStringAsFixed(1)}%)', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Stack(
                                children: [
                                  Container(height: 8, decoration: BoxDecoration(color: AppColors.danger.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4))),
                                  FractionallySizedBox(
                                    widthFactor: (total / maxExpense).clamp(0.01, 1.0),
                                    child: Container(height: 8, decoration: BoxDecoration(color: AppColors.danger, borderRadius: BorderRadius.circular(4))),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          // 营业额渠道分布
          _buildSectionTitle('营业额渠道分布'),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: _revenueByChannel.isEmpty
                  ? const Text('暂无数据')
                  : Column(
                      children: _revenueByChannel.map((r) {
                        final channel = r['channel'] as String? ?? '';
                        final total = (r['total'] as num?)?.toDouble() ?? 0;
                        final pct = _totalRevenue > 0 ? (total / _totalRevenue * 100) : 0;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(channel, style: const TextStyle(fontSize: 13)),
                                  Text('¥${total.toStringAsFixed(0)} (${pct.toStringAsFixed(1)}%)', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Stack(
                                children: [
                                  Container(height: 8, decoration: BoxDecoration(color: AppColors.success.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4))),
                                  FractionallySizedBox(
                                    widthFactor: (total / maxChannel).clamp(0.01, 1.0),
                                    child: Container(height: 8, decoration: BoxDecoration(color: AppColors.success, borderRadius: BorderRadius.circular(4))),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOverviewItem(String label, String value) {
    return Column(
      children: [
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
      ],
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold));
  }
}
