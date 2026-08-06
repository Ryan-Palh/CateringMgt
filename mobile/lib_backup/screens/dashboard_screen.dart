// screens/dashboard_screen.dart — 工作台
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

      // 今日营业额
      final revenueRows = await db.rawQuery(
        "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as cnt FROM daily_revenue WHERE record_date=?",
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
        "SELECT COALESCE(SUM(amount), 0) as total FROM daily_revenue WHERE record_date LIKE ?",
        ['$monthStr%'],
      );
      final monthRevenue = (monthRows.first['total'] as num?)?.toDouble() ?? 0;

      // 低库存预警
      final lowStockRows = await db.rawQuery(
        "SELECT COUNT(*) as cnt FROM ingredients WHERE stock < min_stock AND min_stock > 0",
      );
      final lowStock = lowStockRows.first['cnt'] as int? ?? 0;

      setState(() {
        _stats = {
          'todayRevenue': todayRevenue,
          'todayOrders': todayOrders,
          'avgPerOrder': todayOrders > 0 ? todayRevenue / todayOrders : 0.0,
          'empCount': empCount,
          'monthRevenue': monthRevenue,
          'lowStock': lowStock,
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
    final appState = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(
        title: Text('欢迎, ${appState.displayName}'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadStats,
          ),
          IconButton(
            icon: Icon(appState.isSyncing ? Icons.sync : Icons.cloud_sync_outlined),
            onPressed: () => appState.sync(),
          ),
        ],
      ),
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
                  if (_stats['lowStock'] > 0) _buildLowStockAlert(),
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
            const Text(
              '今日营业额',
              style: TextStyle(color: Colors.white70, fontSize: 14),
            ),
            const SizedBox(height: 8),
            Text(
              '¥${revenue.toStringAsFixed(2)}',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 32,
                fontWeight: FontWeight.bold,
              ),
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
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Widget _buildStatsGrid() {
    final empCount = _stats['empCount'] as int? ?? 0;
    final monthRevenue = _stats['monthRevenue'] as double? ?? 0;

    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      mainAxisSpacing: AppSpacing.md,
      crossAxisSpacing: AppSpacing.md,
      childAspectRatio: 1.8,
      children: [
        _buildStatCard(
          '在岗员工',
          '$empCount',
          '人',
          Icons.people,
          AppColors.success,
        ),
        _buildStatCard(
          '本月营业额',
          '¥${monthRevenue.toStringAsFixed(0)}',
          '',
          Icons.trending_up,
          AppColors.info,
        ),
      ],
    );
  }

  Widget _buildStatCard(
    String title,
    String value,
    String unit,
    IconData icon,
    Color color,
  ) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
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
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  value,
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: color,
                  ),
                ),
                if (unit.isNotEmpty) ...[
                  const SizedBox(width: 4),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      unit,
                      style: TextStyle(
                        fontSize: 14,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLowStockAlert() {
    final count = _stats['lowStock'] as int? ?? 0;
    return Card(
      color: const Color(0xFFFFF4E6),
      child: ListTile(
        leading: const Icon(Icons.warning, color: AppColors.warning),
        title: Text(
          '$count 种食材库存不足',
          style: const TextStyle(color: AppColors.warning, fontWeight: FontWeight.w600),
        ),
        subtitle: const Text('请及时采购补充'),
        trailing: const Icon(Icons.chevron_right, color: AppColors.textSecondary),
      ),
    );
  }
}
