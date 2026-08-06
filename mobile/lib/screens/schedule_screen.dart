// screens/schedule_screen.dart — 排班管理（查看+批量录入，与桌面端对齐）
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../utils/app_state.dart';
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

  static const _shiftTypes = [
    '早班(08:00-16:00)',
    '中班(12:00-20:00)',
    '晚班(16:00-00:00)',
    '全天(08:00-20:00)',
    '休息',
  ];

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
      final appState = context.read<AppState>();
      final storeId = appState.storeId;
      final storeFilter = storeId != null ? 'AND s.store_id=$storeId' : '';
      _records = await LocalDb.instance.rawQuery(
        """SELECT s.*, e.name as emp_name, e.position
           FROM shifts s LEFT JOIN employees e ON s.employee_id = e.id
           WHERE s.shift_date >= ? AND s.shift_date <= ? $storeFilter
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
      case '早班(08:00-16:00)':
        return AppColors.success;
      case '中班(12:00-20:00)':
        return AppColors.primary;
      case '晚班(16:00-00:00)':
        return AppColors.info;
      case '全天(08:00-20:00)':
        return const Color(0xFFE8590C);
      case '休息':
        return AppColors.textSecondary;
      default:
        return AppColors.textSecondary;
    }
  }

  String _shortShiftName(String? shiftType) {
    if (shiftType == null) return '';
    if (shiftType.contains('早班')) return '早班';
    if (shiftType.contains('中班')) return '中班';
    if (shiftType.contains('晚班')) return '晚班';
    if (shiftType.contains('全天')) return '全天';
    if (shiftType.contains('休息')) return '休息';
    return shiftType;
  }

  void _showAddShiftDialog() async {
    final employees = await LocalDb.instance.rawQuery(
      "SELECT id, name FROM employees WHERE status='在职' AND (is_system_user=0 OR is_system_user IS NULL) ORDER BY name",
    );

    if (employees.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('暂无可排班员工'), backgroundColor: AppColors.warning),
        );
      }
      return;
    }

    if (!mounted) return;

    int? empId = employees.first['id'] as int;
    DateTime startDate = DateTime.now();
    DateTime endDate = DateTime.now().add(const Duration(days: 6));
    String shiftType = _shiftTypes.first;

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('批量排班'),
          content: SizedBox(
            width: double.maxFinite,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<int>(
                  value: empId,
                  decoration: const InputDecoration(labelText: '员工', border: OutlineInputBorder()),
                  items: employees.map((e) => DropdownMenuItem(
                    value: e['id'] as int,
                    child: Text(e['name'] as String),
                  )).toList(),
                  onChanged: (v) => setDialogState(() => empId = v),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextButton.icon(
                        icon: const Icon(Icons.calendar_today, size: 18),
                        label: Text(DateFormat('MM-dd').format(startDate)),
                        onPressed: () async {
                          final d = await showDatePicker(
                            context: ctx,
                            initialDate: startDate,
                            firstDate: DateTime(2024),
                            lastDate: DateTime(2027),
                          );
                          if (d != null) setDialogState(() => startDate = d);
                        },
                      ),
                    ),
                    const Text('~'),
                    Expanded(
                      child: TextButton.icon(
                        icon: const Icon(Icons.calendar_today, size: 18),
                        label: Text(DateFormat('MM-dd').format(endDate)),
                        onPressed: () async {
                          final d = await showDatePicker(
                            context: ctx,
                            initialDate: endDate,
                            firstDate: DateTime(2024),
                            lastDate: DateTime(2027),
                          );
                          if (d != null) setDialogState(() => endDate = d);
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: shiftType,
                  decoration: const InputDecoration(labelText: '班次', border: OutlineInputBorder()),
                  items: _shiftTypes.map((s) => DropdownMenuItem(value: s, child: Text(_shortShiftName(s)))).toList(),
                  onChanged: (v) => setDialogState(() => shiftType = v ?? _shiftTypes.first),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            ElevatedButton(
              onPressed: () => Navigator.pop(ctx, {
                'emp_id': empId,
                'start': startDate,
                'end': endDate,
                'shift_type': shiftType,
              }),
              child: const Text('批量设置'),
            ),
          ],
        ),
      ),
    );

    if (result != null) {
      await _saveBatchShift(
        result['emp_id'] as int,
        result['start'] as DateTime,
        result['end'] as DateTime,
        result['shift_type'] as String,
      );
    }
  }

  Future<void> _saveBatchShift(int empId, DateTime start, DateTime end, String shiftType) async {
    // 解析班次时间
    String startTime = '';
    String endTime = '';
    final match = RegExp(r'(\d{2}:\d{2})\s*[-~–]\s*(\d{2}:\d{2})').firstMatch(shiftType);
    if (match != null) {
      startTime = match.group(1)!;
      endTime = match.group(2)!;
    }

    int count = 0;
    DateTime current = start;
    while (!current.isAfter(end)) {
      final dateStr = _dateFormat.format(current);
      await LocalDb.instance.rawExecute(
        '''INSERT OR REPLACE INTO shifts (employee_id, shift_date, shift_type, start_time, end_time)
           VALUES (?, ?, ?, ?, ?)''',
        [empId, dateStr, shiftType, startTime, endTime],
      );
      count++;
      current = current.add(const Duration(days: 1));
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('已设置 $count 天排班'), backgroundColor: AppColors.success),
      );
    }
    _loadSchedule();
  }

  Future<void> _deleteShift(int shiftId) async {
    await LocalDb.instance.rawExecute('DELETE FROM shifts WHERE id=?', [shiftId]);
    _loadSchedule();
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
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: Text(
                    '${_dateFormat.format(_weekStart)} ~ ${_dateFormat.format(weekEnd)}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
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
                Expanded(child: _buildWeekSchedule()),
              ],
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: _showAddShiftDialog,
        child: const Icon(Icons.add),
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
            const SizedBox(height: 8),
            Text('点击右下角 + 添加排班', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
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
              final shiftId = r['id'] as int?;

              return Dismissible(
                key: ValueKey(shiftId),
                direction: DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 20),
                  color: AppColors.danger,
                  child: const Icon(Icons.delete, color: Colors.white),
                ),
                confirmDismiss: (_) async {
                  return await showDialog<bool>(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: const Text('确认删除'),
                      content: Text('删除 $empName 的排班记录？'),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
                        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除')),
                      ],
                    ),
                  );
                },
                onDismissed: (_) => _deleteShift(shiftId!),
                child: Card(
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
                        _shortShiftName(shiftType),
                        style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w600),
                      ),
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
