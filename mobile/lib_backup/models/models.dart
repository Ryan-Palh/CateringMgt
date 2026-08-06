// models/models.dart — 数据模型
import 'package:intl/intl.dart';

final _dateFormat = DateFormat('yyyy-MM-dd');

/// 门店
class Store {
  final int? id;
  final String name;
  final String? address;
  final String? phone;
  final String? businessHours;
  final String status;

  Store({
    this.id,
    required this.name,
    this.address,
    this.phone,
    this.businessHours,
    this.status = '营业中',
  });

  factory Store.fromMap(Map<String, dynamic> m) => Store(
        id: m['id'] as int?,
        name: m['name'] as String? ?? '',
        address: m['address'] as String?,
        phone: m['phone'] as String?,
        businessHours: m['business_hours'] as String?,
        status: m['status'] as String? ?? '营业中',
      );

  Map<String, dynamic> toMap() => {
        if (id != null) 'id': id,
        'name': name,
        'address': address,
        'phone': phone,
        'business_hours': businessHours,
        'status': status,
      };
}

/// 员工
class Employee {
  final int? id;
  final String name;
  final String? phone;
  final String? position;
  final double baseSalary;
  final String? hireDate;
  final String status;
  final String? role;
  final int? storeId;
  final String? remark;

  Employee({
    this.id,
    required this.name,
    this.phone,
    this.position,
    this.baseSalary = 0,
    this.hireDate,
    this.status = '在职',
    this.role = '员工',
    this.storeId,
    this.remark,
  });

  factory Employee.fromMap(Map<String, dynamic> m) => Employee(
        id: m['id'] as int?,
        name: m['name'] as String? ?? '',
        phone: m['phone'] as String?,
        position: m['position'] as String?,
        baseSalary: (m['base_salary'] as num?)?.toDouble() ?? 0,
        hireDate: m['hire_date'] as String?,
        status: m['status'] as String? ?? '在职',
        role: m['role'] as String?,
        storeId: m['store_id'] as int?,
        remark: m['remark'] as String?,
      );

  Map<String, dynamic> toMap() => {
        if (id != null) 'id': id,
        'name': name,
        'phone': phone,
        'position': position,
        'base_salary': baseSalary,
        'hire_date': hireDate,
        'status': status,
        'role': role,
        'store_id': storeId,
        'remark': remark,
      };
}

/// 营业额记录
class RevenueRecord {
  final int? id;
  final String recordDate;
  final String channel;
  final String packageName;
  final String packageType;
  final int orderCount;
  final double amount;
  final double cashAmount;
  final double cardAmount;
  final double onlineAmount;
  final int diningCount;
  final int takeoutCount;
  final String? remark;
  final String? operator;
  final int? storeId;

  RevenueRecord({
    this.id,
    required this.recordDate,
    this.channel = '',
    this.packageName = '',
    this.packageType = '',
    this.orderCount = 0,
    this.amount = 0,
    this.cashAmount = 0,
    this.cardAmount = 0,
    this.onlineAmount = 0,
    this.diningCount = 0,
    this.takeoutCount = 0,
    this.remark,
    this.operator,
    this.storeId,
  });

  factory RevenueRecord.fromMap(Map<String, dynamic> m) => RevenueRecord(
        id: m['id'] as int?,
        recordDate: m['record_date'] as String? ?? _dateFormat.format(DateTime.now()),
        channel: m['channel'] as String? ?? '',
        packageName: m['package_name'] as String? ?? '',
        packageType: m['package_type'] as String? ?? '',
        orderCount: m['order_count'] as int? ?? 0,
        amount: (m['amount'] as num?)?.toDouble() ?? 0,
        cashAmount: (m['cash_amount'] as num?)?.toDouble() ?? 0,
        cardAmount: (m['card_amount'] as num?)?.toDouble() ?? 0,
        onlineAmount: (m['online_amount'] as num?)?.toDouble() ?? 0,
        diningCount: m['dining_count'] as int? ?? 0,
        takeoutCount: m['takeout_count'] as int? ?? 0,
        remark: m['remark'] as String?,
        operator: m['operator'] as String?,
        storeId: m['store_id'] as int?,
      );

  Map<String, dynamic> toMap() => {
        if (id != null) 'id': id,
        'record_date': recordDate,
        'channel': channel,
        'package_name': packageName,
        'package_type': packageType,
        'order_count': orderCount,
        'amount': amount,
        'cash_amount': cashAmount,
        'card_amount': cardAmount,
        'online_amount': onlineAmount,
        'dining_count': diningCount,
        'takeout_count': takeoutCount,
        'remark': remark,
        'operator': operator,
        'store_id': storeId,
      };
}

/// 考勤记录
class AttendanceRecord {
  final int? id;
  final int? employeeId;
  final String shiftDate;
  final String? checkInTime;
  final String? checkOutTime;
  final String status;
  final String? remark;
  final int? storeId;

  AttendanceRecord({
    this.id,
    this.employeeId,
    required this.shiftDate,
    this.checkInTime,
    this.checkOutTime,
    this.status = '正常',
    this.remark,
    this.storeId,
  });

  factory AttendanceRecord.fromMap(Map<String, dynamic> m) => AttendanceRecord(
        id: m['id'] as int?,
        employeeId: m['employee_id'] as int?,
        shiftDate: m['shift_date'] as String? ?? '',
        checkInTime: m['check_in_time'] as String?,
        checkOutTime: m['check_out_time'] as String?,
        status: m['status'] as String? ?? '正常',
        remark: m['remark'] as String?,
        storeId: m['store_id'] as int?,
      );

  Map<String, dynamic> toMap() => {
        if (id != null) 'id': id,
        'employee_id': employeeId,
        'shift_date': shiftDate,
        'check_in_time': checkInTime,
        'check_out_time': checkOutTime,
        'status': status,
        'remark': remark,
        'store_id': storeId,
      };
}

/// 排班记录
class ShiftRecord {
  final int? id;
  final int? employeeId;
  final String shiftDate;
  final String shiftType;
  final String? startTime;
  final String? endTime;
  final int? storeId;

  ShiftRecord({
    this.id,
    this.employeeId,
    required this.shiftDate,
    this.shiftType = '全天',
    this.startTime,
    this.endTime,
    this.storeId,
  });

  factory ShiftRecord.fromMap(Map<String, dynamic> m) => ShiftRecord(
        id: m['id'] as int?,
        employeeId: m['employee_id'] as int?,
        shiftDate: m['shift_date'] as String? ?? '',
        shiftType: m['shift_type'] as String? ?? '全天',
        startTime: m['start_time'] as String?,
        endTime: m['end_time'] as String?,
        storeId: m['store_id'] as int?,
      );

  Map<String, dynamic> toMap() => {
        if (id != null) 'id': id,
        'employee_id': employeeId,
        'shift_date': shiftDate,
        'shift_type': shiftType,
        'start_time': startTime,
        'end_time': endTime,
        'store_id': storeId,
      };
}

/// 财务记录
class FinanceRecord {
  final int? id;
  final String recordDate;
  final String recordType;
  final String category;
  final double amount;
  final String? account;
  final String? operator;
  final String? description;
  final int? storeId;

  FinanceRecord({
    this.id,
    required this.recordDate,
    this.recordType = '支出',
    this.category = '',
    this.amount = 0,
    this.account,
    this.operator,
    this.description,
    this.storeId,
  });

  factory FinanceRecord.fromMap(Map<String, dynamic> m) => FinanceRecord(
        id: m['id'] as int?,
        recordDate: m['record_date'] as String? ?? '',
        recordType: m['record_type'] as String? ?? '支出',
        category: m['category'] as String? ?? '',
        amount: (m['amount'] as num?)?.toDouble() ?? 0,
        account: m['account'] as String?,
        operator: m['operator'] as String?,
        description: m['description'] as String?,
        storeId: m['store_id'] as int?,
      );

  Map<String, dynamic> toMap() => {
        if (id != null) 'id': id,
        'record_date': recordDate,
        'record_type': recordType,
        'category': category,
        'amount': amount,
        'account': account,
        'operator': operator,
        'description': description,
        'store_id': storeId,
      };
}

/// 工资记录
class SalaryRecord {
  final int? id;
  final int? employeeId;
  final int year;
  final int month;
  final double baseSalary;
  final double grossSalary;
  final double totalDeduction;
  final double actualSalary;
  final String status;
  final String? paidDate;
  final int? storeId;

  SalaryRecord({
    this.id,
    this.employeeId,
    required this.year,
    required this.month,
    this.baseSalary = 0,
    this.grossSalary = 0,
    this.totalDeduction = 0,
    this.actualSalary = 0,
    this.status = '未发放',
    this.paidDate,
    this.storeId,
  });

  factory SalaryRecord.fromMap(Map<String, dynamic> m) => SalaryRecord(
        id: m['id'] as int?,
        employeeId: m['employee_id'] as int?,
        year: m['year'] as int? ?? DateTime.now().year,
        month: m['month'] as int? ?? DateTime.now().month,
        baseSalary: (m['base_salary'] as num?)?.toDouble() ?? 0,
        grossSalary: (m['gross_salary'] as num?)?.toDouble() ?? 0,
        totalDeduction: (m['total_deduction'] as num?)?.toDouble() ?? 0,
        actualSalary: (m['actual_salary'] as num?)?.toDouble() ?? 0,
        status: m['status'] as String? ?? '未发放',
        paidDate: m['paid_date'] as String?,
        storeId: m['store_id'] as int?,
      );

  Map<String, dynamic> toMap() => {
        if (id != null) 'id': id,
        'employee_id': employeeId,
        'year': year,
        'month': month,
        'base_salary': baseSalary,
        'gross_salary': grossSalary,
        'total_deduction': totalDeduction,
        'actual_salary': actualSalary,
        'status': status,
        'paid_date': paidDate,
        'store_id': storeId,
      };
}
