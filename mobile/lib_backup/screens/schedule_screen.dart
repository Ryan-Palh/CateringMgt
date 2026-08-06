// screens/schedule_screen.dart — 排班查看
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key});

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  final _dateFormat = DateFormat('yyyy-MM-dd');
  bool _loading = true;
  List<Map<String, dynamic>> _records = [];
  DateTime _weekStart = _getWeekStart(DateTime.now());

  static DateTime _getWeekStart(DateTime date) {
    return date.subtract(Duration(days: date.weekday - 1));
  }

  @override
  void initState() {
    super.initState();
    _loadSchedule();
  }

  Future<void> _loadSchedule() async {
    setState(() => _loading = true);
    try {
      final start = _dateFormat.format(_weekStart);
      final end = _dateFormat.format(_weekStart.add(const Duration(days: 6)));
      _records = await LocalDb.instance.rawQuery(
        """SELECT s.*, e.name as emp_name, e.position
           FROM shifts s LEFT JOIN employees e ON s.employee_id = e.id
           WHERE s.shift_date >= ? AND s.shift_date <= ?
           ORDER BY s.shift_date, s.shift_type""",
        [start, end],
      );
    } catch (e) {
      debugPrint('Schedule load error: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  void _prevWeek() {
    setState(() => _weekStart = _weekStart.subtract(const Duration(days: 7)));
    _loadSchedule();
  }

  void _nextWeek() {
    setState(() => _weekStart = _weekStart.add(const Duration(days: 7)));
    _loadSchedule();
  }

  Color _getShiftColor(String? shiftType) {
    switch (shiftType) {
      case '早班':
        return AppColors.success;
      case '中班':
        return AppColors.primary;
      case '晚班':
        return AppColors.info;
      case '全天':
        return const Color(0xFFE8590C);
      case '休息':
        return AppColors.textSecondary;
      default:
        return AppColors.textSecondary;
    }
  }

  @override
  Widget build(BuildContext context) {
    final weekEnd = _weekStart.add(const Duration(days: 6));
    return Scaffold(
      appBar: AppBar(
        title: const Text('排班表'),
        actions: [
          IconButton(icon: const Icon(Icons.chevron_left), onPressed: _prevWeek),
          IconButton(icon: const Icon(Icons.chevron_right), onPressed: _nextWeek),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                // 周日期显示
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: Text(
                    '${_dateFormat.format(_weekStart)} ~ ${_dateFormat.format(weekEnd)}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                // 班次图例
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                  child: Wrap(
                    spacing: AppSpacing.md,
                    children: [
                      _buildLegend('早班', AppColors.success),
                      _buildLegend('中班', AppColors.primary),
                      _buildLegend('晚班', AppColors.info),
                      _buildLegend('全天', const Color(0xFFE8590C)),
                      _buildLegend('休息', AppColors.textSecondary),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                // 按天分组排班
                Expanded(child: _buildWeekSchedule()),
              ],
            ),
    );
  }

  Widget _buildLegend(String label, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
        ),
        const SizedBox(width: 4),
        Text(label, style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
      ],
    );
  }

  Widget _buildWeekSchedule() {
    // 按日期分组
    final Map<String, List<Map<String, dynamic>>> grouped = {};
    for (final r in _records) {
      final date = r['shift_date'] as String? ?? '';
      grouped.putIfAbsent(date, () => []);
      grouped[date]!.add(r);
    }

    if (grouped.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.calendar_today_outlined, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.5)),
            const SizedBox(height: AppSpacing.md),
            Text('本周暂无排班', style: TextStyle(color: AppColors.textSecondary)),
          ],
        ),
      );
    }

    final sortedDates = grouped.keys.toList()..sort();

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      itemCount: sortedDates.length,
      itemBuilder: (ctx, i) {
        final date = sortedDates[i];
        final dayRecords = grouped[date]!;
        final parsedDate = DateTime.tryParse(date);
        final weekday = parsedDate != null ? DateFormat('EEE', 'zh_CN').format(parsedDate) : '';

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm, bottom: AppSpacing.xs),
              child: Text(
                '$date $weekday',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
            ...dayRecords.map((r) {
              final shiftType = r['shift_type'] as String? ?? '全天';
              final empName = r['emp_name'] as String? ?? '未知';
              final position = r['position'] as String? ?? '';
              final startTime = r['start_time'] as String? ?? '';
              final endTime = r['end_time'] as String? ?? '';
              final color = _getShiftColor(shiftType);

              return Card(
                child: ListTile(
                  leading: Container(
                    width: 4,
                    height: 40,
                    decoration: BoxDecoration(
                      color: color,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  title: Text(empName, style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text([
                    position,
                    if (startTime.isNotEmpty || endTime.isNotEmpty) '$startTime-$endTime',
                  ].join(' · ')),
                  trailing: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      shiftType,
                      style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
              );
            }),
          ],
        );
      },
    );
  }
}
