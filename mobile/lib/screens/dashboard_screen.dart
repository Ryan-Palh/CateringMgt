// screens/dashboard_screen.dart — 工作台（与桌面端对齐：统计卡片+库存预警+过期预警+渐变色）
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../utils/app_state.dart';
import '../api/local_db.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic> _stats = {};
  List<Map<String, dynamic>> _lowStock = [];
  List<Map<String, dynamic>> _expiryWarning = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadStats();
  }

  Future<void> _loadStats() async {
    setState(() => _loading = true);
    try {
      final today = DateFormat('yyyy-MM-dd').format(DateTime.now());
      final db = LocalDb.instance;
      final appState = context.read<AppState>();
      final storeId = appState.storeId;
      final storeFilter = storeId != null ? 'AND store_id=$storeId' : '';

      // 今日营业额
      final revenueRows = await db.rawQuery(
        "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as cnt FROM daily_revenue WHERE record_date=? $storeFilter",
        [today],
      );
      final todayRevenue = (revenueRows.first['total'] as num?)?.toDouble() ?? 0;
      final todayOrders = revenueRows.first['cnt'] as int? ?? 0;

      // 在岗员工
      final empRows = await db.query('employees', where: "status='在职'");
      final empCount = empRows.length;

      // 本月营业额
      final monthStr = DateFormat('yyyy-MM').format(DateTime.now());
      final monthRows = await db.rawQuery(
        "SELECT COALESCE(SUM(amount), 0) as total FROM daily_revenue WHERE record_date LIKE ? $storeFilter",
        ['$monthStr%'],
      );
      final monthRevenue = (monthRows.first['total'] as num?)?.toDouble() ?? 0;

      // 本月支出
      final expenseRows = await db.rawQuery(
        "SELECT COALESCE(SUM(amount), 0) as total FROM finance_records WHERE record_type='支出' AND record_date LIKE ? $storeFilter",
        ['$monthStr%'],
      );
      final monthExpense = (expenseRows.first['total'] as num?)?.toDouble() ?? 0;

      // 低库存预警（库存 < min_stock 且 min_stock > 0），按门店过滤
      _lowStock = await db.rawQuery(
        "SELECT name, unit, stock, min_stock FROM ingredients WHERE stock < min_stock AND min_stock > 0 ${storeId != null ? 'AND store_id=$storeId' : ''} ORDER BY stock ASC",
      );

      // 过期预警（expiry_value > 0，计算剩余天数），按门店过滤
      _expiryWarning = await db.rawQuery(
        "SELECT name, unit, spec, expiry_value, expiry_unit FROM ingredients WHERE expiry_value > 0 ${storeId != null ? 'AND store_id=$storeId' : ''}",
      );

      // 本月净利润
      final monthProfit = monthRevenue - monthExpense;

      setState(() {
        _stats = {
          'todayRevenue': todayRevenue,
          'todayOrders': todayOrders,
          'avgPerOrder': todayOrders > 0 ? todayRevenue / todayOrders : 0.0,
          'empCount': empCount,
          'monthRevenue': monthRevenue,
          'monthExpense': monthExpense,
          'monthProfit': monthProfit,
          'lowStockCount': _lowStock.length,
          'expiryCount': _expiryWarning.length,
        };
      });
    } catch (e) {
      debugPrint('Dashboard load error: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadStats,
              child: ListView(
                padding: const EdgeInsets.all(AppSpacing.md),
                children: [
                  _buildRevenueCard(),
                  const SizedBox(height: AppSpacing.md),
                  _buildStatsGrid(),
                  const SizedBox(height: AppSpacing.md),
                  _buildWarningCards(),
                  const SizedBox(height: AppSpacing.md),
                  if (_lowStock.isNotEmpty) ...[
                    _buildLowStockList(),
                    const SizedBox(height: AppSpacing.md),
                  ],
                  if (_expiryWarning.isNotEmpty) ...[
                    _buildExpiryList(),
                  ],
                ],
              ),
            ),
    );
  }

  Widget _buildRevenueCard() {
    final revenue = _stats['todayRevenue'] as double? ?? 0;
    final orders = _stats['todayOrders'] as int? ?? 0;
    final avg = _stats['avgPerOrder'] as double? ?? 0;

    return Card(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [AppColors.primary, Color(0xFFFF922B)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('今日营业额', style: TextStyle(color: Colors.white70, fontSize: 14)),
            const SizedBox(height: 8),
            Text(
              '¥${revenue.toStringAsFixed(2)}',
              style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                _buildMiniStat('订单数', '$orders'),
                const SizedBox(width: AppSpacing.lg),
                _buildMiniStat('客单价', '¥${avg.toStringAsFixed(1)}'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMiniStat(String label, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
        Text(value, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
      ],
    );
  }

  Widget _buildStatsGrid() {
    final empCount = _stats['empCount'] as int? ?? 0;
    final monthRevenue = _stats['monthRevenue'] as double? ?? 0;
    final monthExpense = _stats['monthExpense'] as double? ?? 0;
    final monthProfit = _stats['monthProfit'] as double? ?? 0;

    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      mainAxisSpacing: AppSpacing.md,
      crossAxisSpacing: AppSpacing.md,
      childAspectRatio: 1.6,
      children: [
        _buildStatCard('本月营业额', '¥${monthRevenue.toStringAsFixed(0)}', Icons.trending_up, AppColors.info),
        _buildStatCard('本月支出', '¥${monthExpense.toStringAsFixed(0)}', Icons.trending_down, AppColors.danger),
        _buildStatCard('本月净利', '¥${monthProfit.toStringAsFixed(0)}', Icons.savings, AppColors.success),
        _buildStatCard('在岗员工', '$empCount 人', Icons.people, AppColors.warning),
      ],
    );
  }

  Widget _buildStatCard(String title, String value, IconData icon, Color color) {
    return Card(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [color.withValues(alpha: 0.1), color.withValues(alpha: 0.05)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 20),
                const SizedBox(width: AppSpacing.sm),
                Text(title, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
            const Spacer(),
            Text(
              value,
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: color),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWarningCards() {
    final lowStockCount = _stats['lowStockCount'] as int? ?? 0;
    final expiryCount = _stats['expiryCount'] as int? ?? 0;

    return Row(
      children: [
        Expanded(
          child: _buildWarningCard(
            '库存预警',
            '$lowStockCount 种食材库存不足',
            lowStockCount > 0 ? AppColors.warning : AppColors.success,
            Icons.inventory_2,
            lowStockCount > 0,
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: _buildWarningCard(
            '过期预警',
            '$expiryCount 种食材需关注',
            expiryCount > 0 ? AppColors.danger : AppColors.success,
            Icons.schedule,
            expiryCount > 0,
          ),
        ),
      ],
    );
  }

  Widget _buildWarningCard(String title, String subtitle, Color color, IconData icon, bool hasWarning) {
    return Card(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [color.withValues(alpha: 0.15), color.withValues(alpha: 0.05)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 8),
            Text(title, style: TextStyle(color: color, fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(subtitle, style: TextStyle(color: color.withValues(alpha: 0.8), fontSize: 12)),
          ],
        ),
      ),
    );
  }

  Widget _buildLowStockList() {
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(
              children: [
                const Icon(Icons.warning, color: AppColors.warning, size: 20),
                const SizedBox(width: AppSpacing.sm),
                Text('库存预警详情', style: Theme.of(context).textTheme.titleSmall),
              ],
            ),
          ),
          const Divider(height: 1),
          ..._lowStock.map((item) {
            final stock = (item['stock'] as num?)?.toDouble() ?? 0;
            final minStock = (item['min_stock'] as num?)?.toDouble() ?? 0;
            final isCritical = stock < 5;
            return ListTile(
              leading: CircleAvatar(
                backgroundColor: isCritical ? AppColors.danger.withValues(alpha: 0.1) : AppColors.warning.withValues(alpha: 0.1),
                child: Icon(isCritical ? Icons.error : Icons.warning, color: isCritical ? AppColors.danger : AppColors.warning, size: 20),
              ),
              title: Text('${item['name']} (${item['unit']})'),
              subtitle: Text('库存: ${stock.toStringAsFixed(1)} / 最低: ${minStock.toStringAsFixed(1)}'),
              trailing: Text(
                isCritical ? '紧急' : '不足',
                style: TextStyle(color: isCritical ? AppColors.danger : AppColors.warning, fontWeight: FontWeight.bold),
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildExpiryList() {
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(
              children: [
                const Icon(Icons.schedule, color: AppColors.danger, size: 20),
                const SizedBox(width: AppSpacing.sm),
                Text('过期预警详情', style: Theme.of(context).textTheme.titleSmall),
              ],
            ),
          ),
          const Divider(height: 1),
          ..._expiryWarning.map((item) {
            final expiryValue = item['expiry_value'] as int? ?? 0;
            final unit = item['expiry_unit'] as String? ?? '天';
            return ListTile(
              leading: CircleAvatar(
                backgroundColor: AppColors.danger.withValues(alpha: 0.1),
                child: const Icon(Icons.timer, color: AppColors.danger, size: 20),
              ),
              title: Text('${item['name']}'),
              subtitle: Text('规格: ${item['spec'] ?? '-'} (${item['unit']})'),
              trailing: Text('保质期: $expiryValue$unit'),
            );
          }),
        ],
      ),
    );
  }
}
