// screens/salary_screen.dart — 工资管理（薪资设置+计算+发放，与桌面端对齐）
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../utils/theme.dart';
import '../utils/app_state.dart';
import '../api/local_db.dart';

class SalaryScreen extends StatefulWidget {
  const SalaryScreen({super.key});

  @override
  State<SalaryScreen> createState() => _SalaryScreenState();
}

class _SalaryScreenState extends State<SalaryScreen> {
  List<Map<String, dynamic>> _records = [];
  List<Map<String, dynamic>> _employees = [];
  bool _loading = true;
  int _year = DateTime.now().year;
  int _month = DateTime.now().month;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final appState = context.read<AppState>();
      final storeId = appState.storeId;
      final storeFilter = storeId != null ? 'AND sr.store_id=$storeId' : '';

      _records = await LocalDb.instance.rawQuery('''
        SELECT sr.*, e.name as emp_name, e.position
        FROM salary_records sr
        LEFT JOIN employees e ON sr.employee_id = e.id
        WHERE sr.year=? AND sr.month=? $storeFilter
        ORDER BY e.name
      ''', [_year, _month]);

      final empStoreFilter = storeId != null ? 'AND store_id=$storeId' : '';
      _employees = await LocalDb.instance.rawQuery(
        "SELECT id, name, position, base_salary, hire_date FROM employees WHERE status='在职' $empStoreFilter ORDER BY name",
      );
    } catch (e) {
      debugPrint('Load error: $e');
    }
    setState(() => _loading = false);
  }

  // 获取考勤数据
  Future<Map<String, dynamic>> _getAttendance(int empId, int year, int month) async {
    final monthStr = '$year-${month.toString().padLeft(2, '0')}';
    final attRecords = await LocalDb.instance.rawQuery(
      """SELECT * FROM attendance
         WHERE employee_id=? AND check_in LIKE ?
         AND (check_out IS NOT NULL AND check_out != '')""",
      [empId, '$monthStr%'],
    );

    int attendDays = attRecords.length;
    int lateCount = 0;
    int lateMinutes = 0;
    double absentDays = 0;
    double leaveDays = 0;

    for (final r in attRecords) {
      final checkIn = r['check_in'] as String? ?? '';
      // 简单判断迟到：9点后打卡算迟到
      if (checkIn.length >= 16) {
        final timePart = checkIn.substring(11, 16);
        if (timePart.compareTo('09:00') > 0) {
          lateCount++;
          // 估算迟到分钟
          final parts = timePart.split(':');
          final h = int.tryParse(parts[0]) ?? 9;
          final m = int.tryParse(parts[1]) ?? 0;
          lateMinutes += (h - 9) * 60 + m;
        }
      }
    }

    return {
      'attend_days': attendDays,
      'late_count': lateCount,
      'late_minutes': lateMinutes,
      'absent_days': absentDays,
      'leave_days': leaveDays,
    };
  }

  // 获取薪资配置
  Future<Map<String, dynamic>> _getSalaryConfig(int empId) async {
    final rows = await LocalDb.instance.rawQuery(
      'SELECT * FROM salary_config WHERE employee_id=?',
      [empId],
    );
    if (rows.isNotEmpty) return rows.first;
    return {};
  }

  // 获取全局配置
  Future<Map<String, dynamic>> _getGlobalConfig() async {
    final rows = await LocalDb.instance.rawQuery('SELECT * FROM salary_global_config WHERE id=1');
    if (rows.isNotEmpty) return rows.first;
    return {};
  }

  // 计算单个员工工资
  Future<Map<String, dynamic>> _calcEmployee(Map<String, dynamic> emp) async {
    final empId = emp['id'] as int;
    final attendance = await _getAttendance(empId, _year, _month);
    final salaryCfg = await _getSalaryConfig(empId);
    final globalCfg = await _getGlobalConfig();

    final stdDays = (globalCfg['standard_work_days'] as num?)?.toInt() ?? 30;
    final probationRate = (globalCfg['probation_rate'] as num?)?.toDouble() ?? 0.7;
    final fullAttAmount = (globalCfg['full_attendance_amount'] as num?)?.toDouble() ?? 200;
    final lateDeductionPerMin = (globalCfg['late_deduction_per_minute'] as num?)?.toDouble() ?? 1.0;
    final utilityAmount = (globalCfg['utility_deduction_amount'] as num?)?.toDouble() ?? 30;
    final seniorityPerYear = (globalCfg['seniority_per_year'] as num?)?.toDouble() ?? 100;
    final seniorityHalfYear = (globalCfg['seniority_half_year'] as num?)?.toDouble() ?? 50;

    final position = emp['position'] as String? ?? '';
    final hireDate = emp['hire_date'] as String? ?? '';
    final isMgmt = _isManagement(position);

    // 基本工资
    final baseSalary = (salaryCfg['base_salary'] as num?)?.toDouble() ??
        (emp['base_salary'] as num?)?.toDouble() ?? 0;

    // 计薪天数
    final attendDays = attendance['attend_days'] as int;
    final lateCount = attendance['late_count'] as int;
    final lateMinutes = attendance['late_minutes'] as int;
    final absentDays = (attendance['absent_days'] as num).toDouble();
    final leaveDays = (attendance['leave_days'] as num).toDouble();
    final payDays = (attendDays - absentDays).clamp(0, stdDays).toDouble();

    // 试用期折算
    double probationDays = 0;
    if (hireDate.isNotEmpty) {
      try {
        final hd = DateTime.parse(hireDate.substring(0, 10));
        final ref = DateTime(_year, _month, 15);
        final months = (ref.year - hd.year) * 12 + (ref.month - hd.month);
        if (months < 2) probationDays = payDays;
      } catch (_) {}
    }

    final effectiveDays = probationDays > 0 ? payDays * probationRate : payDays;
    final basePay = (baseSalary / stdDays * effectiveDays).roundToDouble();

    // 全勤奖
    double fullAttendance = 0;
    if (!isMgmt && lateCount == 0 && absentDays == 0 && leaveDays == 0) {
      fullAttendance = fullAttAmount;
    }

    final positionAllowance = (salaryCfg['position_allowance'] as num?)?.toDouble() ?? 0;
    final assessmentAllowance = (salaryCfg['assessment_allowance'] as num?)?.toDouble() ?? 0;
    final housingAllowance = (salaryCfg['housing_allowance'] as num?)?.toDouble() ?? 0;
    final prevSupplement = (salaryCfg['prev_supplement'] as num?)?.toDouble() ?? 0;
    final uniformRefund = (salaryCfg['uniform_refund'] as num?)?.toDouble() ?? 0;

    // 工龄工资
    double seniorityPay = 0;
    if (!isMgmt && hireDate.isNotEmpty) {
      try {
        final hd = DateTime.parse(hireDate.substring(0, 10));
        final ref = DateTime(_year, _month, 15);
        final months = (ref.year - hd.year) * 12 + (ref.month - hd.month);
        if (months >= 6) {
          final years = months ~/ 12;
          final halfYears = (months % 12) >= 6 ? 1 : 0;
          seniorityPay = years * seniorityPerYear + halfYears * seniorityHalfYear;
        }
      } catch (_) {}
    }

    final grossSalary = (basePay + fullAttendance + positionAllowance + assessmentAllowance +
        housingAllowance + seniorityPay + prevSupplement - uniformRefund).roundToDouble();

    // 扣款
    final lateDeduction = (lateMinutes * lateDeductionPerMin).roundToDouble();
    final absentDeduction = (baseSalary / stdDays * absentDays).roundToDouble();
    final fineCompensation = (salaryCfg['fine_compensation'] as num?)?.toDouble() ?? 0;
    final utilityDeduction = payDays > 0 ? (utilityAmount / stdDays * payDays).roundToDouble() : 0.0;
    final salaryAdvance = (salaryCfg['salary_advance'] as num?)?.toDouble() ?? 0;

    final totalDeduction = (lateDeduction + absentDeduction + fineCompensation +
        utilityDeduction + salaryAdvance).roundToDouble();
    final actualSalary = (grossSalary - totalDeduction).roundToDouble();

    return {
      'employee_id': empId,
      'year': _year,
      'month': _month,
      'base_salary': baseSalary,
      'pay_days': payDays,
      'probation_days': probationDays,
      'full_attendance': fullAttendance,
      'position_allowance': positionAllowance,
      'assessment_allowance': assessmentAllowance,
      'housing_allowance': housingAllowance,
      'seniority_pay': seniorityPay,
      'prev_supplement': prevSupplement,
      'uniform_refund': uniformRefund,
      'gross_salary': grossSalary,
      'late_count': lateCount,
      'late_minutes': lateMinutes,
      'late_deduction': lateDeduction,
      'absent_days': absentDays,
      'absent_deduction': absentDeduction,
      'fine_compensation': fineCompensation,
      'utility_deduction': utilityDeduction,
      'salary_advance': salaryAdvance,
      'total_deduction': totalDeduction,
      'actual_salary': actualSalary,
      'status': '未发放',
      'attend_days': attendDays,
      'leave_days': leaveDays,
      'is_housing': salaryCfg['is_housing'] ?? '否',
    };
  }

  bool _isManagement(String position) {
    const mgmtKeywords = ['经理', '店长', '主管', '总监', '管理'];
    return mgmtKeywords.any((k) => position.contains(k));
  }

  // 批量计算所有员工工资
  Future<void> _calcAll() async {
    if (_employees.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('暂无在职员工'), backgroundColor: AppColors.warning),
      );
      return;
    }

    setState(() => _loading = true);
    try {
      for (final emp in _employees) {
        final data = await _calcEmployee(emp);
        // 检查是否已有记录
        final existing = await LocalDb.instance.rawQuery(
          'SELECT id FROM salary_records WHERE employee_id=? AND year=? AND month=?',
          [data['employee_id'], _year, _month],
        );

        if (existing.isNotEmpty) {
          // 更新已有记录
          final recordId = existing.first['id'];
          await LocalDb.instance.rawExecute(
            '''UPDATE salary_records SET
               base_salary=?, gross_salary=?, total_deduction=?, actual_salary=?,
               pay_days=?, full_attendance=?, position_allowance=?, assessment_allowance=?,
               housing_allowance=?, seniority_pay=?, late_count=?, late_minutes=?,
               late_deduction=?, absent_days=?, absent_deduction=?, fine_compensation=?,
               utility_deduction=?, salary_advance=?, status=CASE WHEN status='已发放' THEN '已发放' ELSE '未发放' END
               WHERE id=?''',
            [
              data['base_salary'], data['gross_salary'], data['total_deduction'], data['actual_salary'],
              data['pay_days'], data['full_attendance'], data['position_allowance'], data['assessment_allowance'],
              data['housing_allowance'], data['seniority_pay'], data['late_count'], data['late_minutes'],
              data['late_deduction'], data['absent_days'], data['absent_deduction'], data['fine_compensation'],
              data['utility_deduction'], data['salary_advance'], recordId,
            ],
          );
        } else {
          // 新增记录
          await LocalDb.instance.rawExecute(
            '''INSERT INTO salary_records
               (employee_id, year, month, base_salary, gross_salary, total_deduction,
                actual_salary, pay_days, full_attendance, position_allowance, assessment_allowance,
                housing_allowance, seniority_pay, late_count, late_minutes, late_deduction,
                absent_days, absent_deduction, fine_compensation, utility_deduction, salary_advance, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            [
              data['employee_id'], data['year'], data['month'], data['base_salary'],
              data['gross_salary'], data['total_deduction'], data['actual_salary'],
              data['pay_days'], data['full_attendance'], data['position_allowance'],
              data['assessment_allowance'], data['housing_allowance'], data['seniority_pay'],
              data['late_count'], data['late_minutes'], data['late_deduction'],
              data['absent_days'], data['absent_deduction'], data['fine_compensation'],
              data['utility_deduction'], data['salary_advance'], data['status'],
            ],
          );
        }
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已计算 ${_employees.length} 名员工工资'), backgroundColor: AppColors.success),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('计算失败: $e'), backgroundColor: AppColors.danger),
        );
      }
    }
    _load();
  }

  // 发放单个员工工资
  Future<void> _payOne(int recordId) async {
    final now = DateTime.now();
    final dateStr = '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    await LocalDb.instance.rawExecute(
      "UPDATE salary_records SET status='已发放', paid_date=? WHERE id=?",
      [dateStr, recordId],
    );
    _load();
  }

  // 批量发放
  Future<void> _payBatch() async {
    final unpaid = _records.where((r) => (r['status'] as String?) != '已发放').toList();
    if (unpaid.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('没有待发放工资'), backgroundColor: AppColors.warning),
      );
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('批量发放'),
        content: Text('确认发放 ${unpaid.length} 名员工的工资？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('确认发放')),
        ],
      ),
    );

    if (confirmed != true) return;

    final now = DateTime.now();
    final dateStr = '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    for (final r in unpaid) {
      await LocalDb.instance.rawExecute(
        "UPDATE salary_records SET status='已发放', paid_date=? WHERE id=?",
        [dateStr, r['id']],
      );
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('已发放 ${unpaid.length} 名员工工资'), backgroundColor: AppColors.success),
      );
    }
    _load();
  }

  // 显示薪资设置对话框
  void _showSalaryConfig(int empId, String empName) async {
    final cfg = await _getSalaryConfig(empId);
    final empInfo = _employees.where((e) => e['id'] == empId).firstOrNull;

    if (!mounted) return;

    final controllers = <String, TextEditingController>{};
    for (final field in ['base_salary', 'position_allowance', 'assessment_allowance', 'housing_allowance',
          'uniform_refund', 'prev_supplement', 'salary_advance', 'fine_compensation']) {
      controllers[field] = TextEditingController(
        text: field == 'base_salary'
            ? ((cfg['base_salary'] as num?)?.toDouble() ?? (empInfo?['base_salary'] as num?)?.toDouble() ?? 0).toString()
            : ((cfg[field] as num?)?.toDouble() ?? 0).toString(),
      );
    }
    String isHousing = cfg['is_housing'] as String? ?? '否';
    final remarkCtrl = TextEditingController(text: cfg['remark'] as String? ?? '');

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: Text('薪资设置 - $empName'),
          content: SizedBox(
            width: double.maxFinite,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (empInfo != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        '岗位: ${empInfo['position'] ?? '未设置'}  |  入职: ${empInfo['hire_date'] ?? '未设置'}',
                        style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                      ),
                    ),
                  ..._buildSalaryFields(controllers),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    value: isHousing,
                    decoration: const InputDecoration(labelText: '提供住宿', border: OutlineInputBorder()),
                    items: const [DropdownMenuItem(value: '否', child: Text('否')), DropdownMenuItem(value: '是', child: Text('是'))],
                    onChanged: (v) => setDialogState(() => isHousing = v ?? '否'),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: remarkCtrl,
                    decoration: const InputDecoration(labelText: '备注', border: OutlineInputBorder()),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            ElevatedButton(
              onPressed: () {
                final data = <String, dynamic>{};
                for (final entry in controllers.entries) {
                  data[entry.key] = double.tryParse(entry.value.text) ?? 0;
                }
                data['is_housing'] = isHousing;
                data['remark'] = remarkCtrl.text.trim();
                Navigator.pop(ctx, data);
              },
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );

    if (result != null) {
      try {
        // 保存到 salary_config
        final cols = ['employee_id', ...result.keys.toList()];
        final vals = [empId, ...result.values.toList()];
        final placeholders = List.filled(cols.length, '?').join(', ');
        final updates = result.keys.map((k) => '$k=excluded.$k').join(', ');
        await LocalDb.instance.rawExecute(
          'INSERT INTO salary_config (${'${cols.join(', ')}'}) VALUES ($placeholders) ON CONFLICT(employee_id) DO UPDATE SET $updates',
          vals,
        );
        // 同步更新 employees.base_salary
        await LocalDb.instance.rawExecute(
          'UPDATE employees SET base_salary=? WHERE id=?',
          [result['base_salary'], empId],
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('薪资设置已保存'), backgroundColor: AppColors.success),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('保存失败: $e'), backgroundColor: AppColors.danger),
          );
        }
      }
    }
  }

  List<Widget> _buildSalaryFields(Map<String, TextEditingController> controllers) {
    final fields = [
      ('base_salary', '基本工资(元)'),
      ('position_allowance', '岗位补贴(元)'),
      ('assessment_allowance', '考核补贴(元)'),
      ('housing_allowance', '住房补贴(元)'),
      ('uniform_refund', '工服退款(元)'),
      ('prev_supplement', '上月补发(元)'),
      ('salary_advance', '预支工资(元)'),
      ('fine_compensation', '罚赔款(元)'),
    ];
    return fields.map((f) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: TextField(
          controller: controllers[f.$1],
          decoration: InputDecoration(labelText: f.$2, border: const OutlineInputBorder()),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
        ),
      );
    }).toList();
  }

  // 显示工资详情
  void _showDetail(int recordId) async {
    final rows = await LocalDb.instance.rawQuery(
      '''SELECT sr.*, e.name as emp_name, e.position
         FROM salary_records sr LEFT JOIN employees e ON sr.employee_id = e.id
         WHERE sr.id=?''',
      [recordId],
    );
    if (rows.isEmpty || !mounted) return;
    final r = rows.first;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('${r['emp_name'] ?? ''} - $_year-$_month 工资明细'),
        content: SizedBox(
          width: double.maxFinite,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _detailRow('基本工资', '¥${(r['base_salary'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('计薪天数', '${(r['pay_days'] as num?)?.toDouble() ?? 0}'),
                _detailRow('全勤奖', '¥${(r['full_attendance'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('岗位补贴', '¥${(r['position_allowance'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('考核补贴', '¥${(r['assessment_allowance'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('住房补贴', '¥${(r['housing_allowance'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('工龄工资', '¥${(r['seniority_pay'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('上月补发', '¥${(r['prev_supplement'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('工服退款', '¥${(r['uniform_refund'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                const Divider(),
                _detailRow('应发合计', '¥${(r['gross_salary'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}', isBold: true),
                const Divider(),
                _detailRow('迟到次数', '${r['late_count'] ?? 0}次 (${r['late_minutes'] ?? 0}分钟)'),
                _detailRow('迟到扣款', '¥${(r['late_deduction'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('旷工天数', '${(r['absent_days'] as num?)?.toDouble() ?? 0}'),
                _detailRow('旷工扣款', '¥${(r['absent_deduction'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('罚赔款', '¥${(r['fine_compensation'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('水电扣款', '¥${(r['utility_deduction'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                _detailRow('预支工资', '¥${(r['salary_advance'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}'),
                const Divider(),
                _detailRow('扣款合计', '¥${(r['total_deduction'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}', isBold: true),
                const Divider(),
                _detailRow('实发工资', '¥${(r['actual_salary'] as num?)?.toDouble().toStringAsFixed(2) ?? '0.00'}', isBold: true, color: AppColors.primary),
                const SizedBox(height: 8),
                Text('状态: ${r['status'] ?? '未发放'}', style: TextStyle(color: r['status'] == '已发放' ? AppColors.success : AppColors.warning)),
              ],
            ),
          ),
        ),
        actions: [
          if ((r['status'] as String?) != '已发放')
            ElevatedButton(
              onPressed: () {
                Navigator.pop(ctx);
                _payOne(recordId);
              },
              child: const Text('发放'),
            ),
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('关闭')),
        ],
      ),
    );
  }

  Widget _detailRow(String label, String value, {bool isBold = false, Color? color}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          Text(value, style: TextStyle(fontSize: 13, fontWeight: isBold ? FontWeight.bold : FontWeight.normal, color: color)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final totalGross = _records.fold<double>(0, (s, r) => s + ((r['gross_salary'] as num?)?.toDouble() ?? 0));
    final totalActual = _records.fold<double>(0, (s, r) => s + ((r['actual_salary'] as num?)?.toDouble() ?? 0));
    final unpaidCount = _records.where((r) => (r['status'] as String?) != '已发放').length;

    return Scaffold(
      appBar: AppBar(
        title: Text('$_year-$_month 工资'),
        actions: [
          PopupMenuButton(
            itemBuilder: (ctx) => [
              const PopupMenuItem(value: 'calc', child: Text('计算工资')),
              const PopupMenuItem(value: 'pay_batch', child: Text('批量发放')),
              const PopupMenuItem(value: 'set_salary', child: Text('薪资设置')),
            ],
            onSelected: (v) {
              if (v == 'calc') {
                _calcAll();
              } else if (v == 'pay_batch') {
                _payBatch();
              } else if (v == 'set_salary') {
                _showEmployeePicker();
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.chevron_left),
            onPressed: () {
              setState(() {
                if (_month == 1) { _year--; _month = 12; } else { _month--; }
              });
              _load();
            },
          ),
          IconButton(
            icon: const Icon(Icons.chevron_right),
            onPressed: () {
              setState(() {
                if (_month == 12) { _year++; _month = 1; } else { _month++; }
              });
              _load();
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _records.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.payments_outlined, size: 64, color: AppColors.textSecondary.withValues(alpha: 0.3)),
                      const SizedBox(height: 16),
                      Text('$_year-$_month 暂无工资记录', style: const TextStyle(color: AppColors.textSecondary)),
                      const SizedBox(height: 8),
                      Text('点击右上角菜单 → 计算工资', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                    ],
                  ),
                )
              : Column(
                  children: [
                    Container(
                      margin: const EdgeInsets.all(AppSpacing.md),
                      padding: const EdgeInsets.all(AppSpacing.md),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(colors: [AppColors.primary.withValues(alpha: 0.1), AppColors.info.withValues(alpha: 0.05)]),
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceAround,
                        children: [
                          _buildSummary('应发总额', '¥${totalGross.toStringAsFixed(0)}'),
                          _buildSummary('实发总额', '¥${totalActual.toStringAsFixed(0)}'),
                          _buildSummary('待发放', '$unpaidCount人'),
                        ],
                      ),
                    ),
                    Expanded(
                      child: ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                        itemCount: _records.length,
                        itemBuilder: (ctx, i) {
                          final r = _records[i];
                          final actual = (r['actual_salary'] as num?)?.toDouble() ?? 0;
                          final status = r['status'] as String? ?? '未发放';
                          final isPaid = status == '已发放';
                          final recordId = r['id'] as int;
                          final empId = r['employee_id'] as int?;
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: (isPaid ? AppColors.success : AppColors.warning).withValues(alpha: 0.1),
                                child: Icon(isPaid ? Icons.check : Icons.pending, color: isPaid ? AppColors.success : AppColors.warning, size: 20),
                              ),
                              title: Text(r['emp_name'] as String? ?? ''),
                              subtitle: Text('${r['position'] ?? ''} · $status'),
                              trailing: Text('¥${actual.toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                              onTap: () => _showDetail(recordId),
                              onLongPress: () {
                                showModalBottomSheet(
                                  context: context,
                                  builder: (ctx) => Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      ListTile(
                                        leading: const Icon(Icons.calculate),
                                        title: const Text('查看明细'),
                                        onTap: () { Navigator.pop(ctx); _showDetail(recordId); },
                                      ),
                                      if (!isPaid)
                                        ListTile(
                                          leading: const Icon(Icons.payment),
                                          title: const Text('发放工资'),
                                          onTap: () { Navigator.pop(ctx); _payOne(recordId); },
                                        ),
                                      if (empId != null)
                                        ListTile(
                                          leading: const Icon(Icons.settings),
                                          title: const Text('薪资设置'),
                                          onTap: () { Navigator.pop(ctx); _showSalaryConfig(empId, r['emp_name'] as String? ?? ''); },
                                        ),
                                    ],
                                  ),
                                );
                              },
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
    );
  }

  void _showEmployeePicker() {
    if (_employees.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('暂无在职员工'), backgroundColor: AppColors.warning),
      );
      return;
    }
    showModalBottomSheet(
      context: context,
      builder: (ctx) => ListView.builder(
        itemCount: _employees.length,
        itemBuilder: (ctx, i) {
          final emp = _employees[i];
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: AppColors.primary.withValues(alpha: 0.1),
              child: Text((emp['name'] as String)[0], style: const TextStyle(color: AppColors.primary)),
            ),
            title: Text(emp['name'] as String),
            subtitle: Text('${emp['position'] ?? '未设置'}'),
            onTap: () {
              Navigator.pop(ctx);
              _showSalaryConfig(emp['id'] as int, emp['name'] as String);
            },
          );
        },
      ),
    );
  }

  Widget _buildSummary(String label, String value) {
    return Column(
      children: [
        Text(label, style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.primary)),
      ],
    );
  }
}
