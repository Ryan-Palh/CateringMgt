// screens/attendance_screen.dart — 考勤打卡与查看（v5.0 列名已统一）
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';
import '../utils/theme.dart';
import '../api/local_db.dart';

class AttendanceScreen extends StatefulWidget {
  const AttendanceScreen({super.key});

  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  final _dateFormat = DateFormat('yyyy-MM-dd');
  final _timeFormat = DateFormat('HH:mm:ss');
  bool _loading = true;
  String? _checkInTime;
  String? _checkOutTime;
  String _todayStatus = '未打卡';
  List<Map<String, dynamic>> _monthRecords = [];
  int? _employeeId;

  @override
  void initState() {
    super.initState();
    _loadEmployeeId();
    _loadAttendance();
  }

  Future<void> _loadEmployeeId() async {
    final prefs = await SharedPreferences.getInstance();
    final username = prefs.getString('username');
    if (username != null && username.isNotEmpty) {
      final rows = await LocalDb.instance.rawQuery(
        "SELECT id FROM employees WHERE username=?",
        [username],
      );
      if (rows.isNotEmpty) {
        _employeeId = rows.first['id'] as int?;
      }
    }
  }

  Future<void> _loadAttendance() async {
    setState(() => _loading = true);
    try {
      final today = _dateFormat.format(DateTime.now());
      final monthStr = DateFormat('yyyy-MM').format(DateTime.now());

      // 查今日打卡记录
      final todayRows = await LocalDb.instance.rawQuery(
        "SELECT * FROM attendance WHERE record_date=? AND employee_id=? ORDER BY id DESC LIMIT 1",
        [today, _employeeId],
      );

      if (todayRows.isNotEmpty) {
        final r = todayRows.first;
        setState(() {
          _checkInTime = r['check_in'] as String?;
          _checkOutTime = r['check_out'] as String?;
          _todayStatus = r['status'] as String? ?? '正常';
        });
      } else {
        setState(() {
          _checkInTime = null;
          _checkOutTime = null;
          _todayStatus = '未打卡';
        });
      }

      // 本月记录
      _monthRecords = await LocalDb.instance.rawQuery(
        "SELECT a.*, e.name as emp_name FROM attendance a LEFT JOIN employees e ON a.employee_id = e.id WHERE a.record_date LIKE ? ORDER BY a.record_date DESC",
        ['$monthStr%'],
      );
    } catch (e) {
      debugPrint('Attendance load error: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _checkIn() async {
    if (_employeeId == null) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('无法识别员工身份，请先完善员工信息')),
        );
      }
      return;
    }

    final now = DateTime.now();
    final today = _dateFormat.format(now);
    final timeStr = _timeFormat.format(now);

    // 判断是否迟到（9:00后算迟到）
    final isLate = now.hour > 9 || (now.hour == 9 && now.minute > 0);
    final status = isLate ? '迟到' : '正常';

    // 签到位置（TODO: 集成定位服务获取真实经纬度）
    const location = '';
    const lat = '';
    const lon = '';

    await LocalDb.instance.rawExecute(
      "INSERT OR REPLACE INTO attendance (employee_id, record_date, check_in, status, check_in_location, check_in_lat, check_in_lon) VALUES (?, ?, ?, ?, ?, ?, ?)",
      [_employeeId, today, timeStr, status, location, lat, lon],
    );

    setState(() {
      _checkInTime = timeStr;
      _todayStatus = status;
    });

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('签到成功 $timeStr${isLate ? '（迟到）' : ''}'),
          backgroundColor: isLate ? AppColors.warning : AppColors.success,
        ),
      );
    }
  }

  Future<void> _checkOut() async {
    if (_employeeId == null) return;

    final now = DateTime.now();
    final today = _dateFormat.format(now);
    final timeStr = _timeFormat.format(now);

    const location = '';
    const lat = '';
    const lon = '';

    await LocalDb.instance.rawExecute(
      "UPDATE attendance SET check_out=?, check_out_location=?, check_out_lat=?, check_out_lon=? WHERE record_date=? AND employee_id=? AND check_out IS NULL",
      [timeStr, location, lat, lon, today, _employeeId],
    );

    setState(() => _checkOutTime = timeStr);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('签退成功 $timeStr'),
          backgroundColor: AppColors.success,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('考勤打卡')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadAttendance,
              child: ListView(
                padding: const EdgeInsets.all(AppSpacing.md),
                children: [
                  _buildCheckCard(),
                  const SizedBox(height: AppSpacing.md),
                  _buildMonthRecords(),
                ],
              ),
            ),
    );
  }

  Widget _buildCheckCard() {
    final now = DateTime.now();
    final dateStr = DateFormat('yyyy-MM-dd EEE').format(now);

    return Card(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              _todayStatus == '迟到' ? AppColors.warning : AppColors.primary,
              _todayStatus == '迟到' ? const Color(0xFFFFC078) : const Color(0xFFFF922B),
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Column(
          children: [
            Text(dateStr, style: const TextStyle(color: Colors.white70, fontSize: 14)),
            const SizedBox(height: AppSpacing.sm),
            Text(
              _timeFormat.format(now),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 40,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '今日状态: $_todayStatus',
                style: const TextStyle(color: Colors.white, fontSize: 13),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            Row(
              children: [
                Expanded(
                  child: _buildCheckButton(
                    '签到',
                    _checkInTime != null,
                    _checkInTime,
                    _checkIn,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _buildCheckButton(
                    '签退',
                    _checkOutTime != null,
                    _checkOutTime,
                    _checkOut,
                    enabled: _checkInTime != null,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCheckButton(
    String label,
    bool done,
    String? time,
    VoidCallback onTap, {
    bool enabled = true,
  }) {
    return GestureDetector(
      onTap: done || !enabled ? null : onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
        decoration: BoxDecoration(
          color: done ? Colors.white.withValues(alpha: 0.2) : Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.sm),
        ),
        child: Column(
          children: [
            Icon(
              done ? Icons.check_circle : (label == '签到' ? Icons.login : Icons.logout),
              color: done ? Colors.white : AppColors.primary,
              size: 28,
            ),
            const SizedBox(height: 4),
            Text(
              done ? (time ?? '') : label,
              style: TextStyle(
                color: done ? Colors.white : AppColors.primary,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMonthRecords() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: AppSpacing.sm, bottom: AppSpacing.sm),
          child: Text('本月记录', style: Theme.of(context).textTheme.titleMedium),
        ),
        if (_monthRecords.isEmpty)
          Center(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.xl),
              child: Text('暂无考勤记录', style: TextStyle(color: AppColors.textSecondary)),
            ),
          )
        else
          ..._monthRecords.map((r) {
            final status = r['status'] as String? ?? '正常';
            final statusColor = status == '迟到' ? AppColors.warning : status == '旷工' ? AppColors.danger : AppColors.success;
            return Card(
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: statusColor.withValues(alpha: 0.1),
                  child: Icon(Icons.access_time, color: statusColor, size: 20),
                ),
                title: Text(r['record_date'] as String? ?? ''),
                subtitle: Text([
                  if (r['check_in'] != null) '签到: ${r['check_in']}',
                  if (r['check_out'] != null) '签退: ${r['check_out']}',
                ].join('  ')),
                trailing: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(status, style: TextStyle(color: statusColor, fontSize: 12)),
                ),
              ),
            );
          }),
      ],
    );
  }
}