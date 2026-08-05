// api/local_db.dart — SQLite 本地数据库
// v5.0 统一表结构：与桌面端 db_manager.py 完全一致
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

class LocalDb {
  static final LocalDb instance = LocalDb._init();
  static Database? _database;

  LocalDb._init();

  Future<String> get dbPath async {
    final dir = await getApplicationDocumentsDirectory();
    return p.join(dir.path, 'catering.db');
  }

  Future<Database> get database async {
    if (_database != null && _database!.isOpen) return _database!;
    _database = await _initDb();
    return _database!;
  }

  Future<Database> _initDb() async {
    final path = await dbPath;
    return await openDatabase(
      path,
      version: 5,
      onConfigure: (db) async {
        await db.execute('PRAGMA foreign_keys = ON');
      },
      onCreate: (db, v) async {
        await _createAllTables(db);
      },
      onUpgrade: (db, oldV, newV) async {
        await _migrate(db, oldV, newV);
      },
    );
  }

  /// 创建所有表（与桌面端 db_manager.py init_database 完全一致）
  Future<void> _createAllTables(Database db) async {
    // ========== 门店管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS stores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        address TEXT,
        phone TEXT,
        manager TEXT,
        business_hours TEXT DEFAULT '09:00-22:00',
        status TEXT DEFAULT '正常',
        remark TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    // ========== 部门 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        remark TEXT
      )
    ''');

    // ========== 员工 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        department_id INTEGER REFERENCES departments(id),
        position TEXT,
        base_salary REAL DEFAULT 0,
        hire_date TEXT,
        status TEXT DEFAULT '在职',
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT '员工',
        store_id INTEGER REFERENCES stores(id),
        permissions TEXT DEFAULT '',
        remark TEXT
      )
    ''');

    // ========== 供应商 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact TEXT,
        phone TEXT,
        address TEXT,
        payment_method TEXT DEFAULT '',
        remark TEXT,
        store_id INTEGER
      )
    ''');

    // ========== 食材原料 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT '斤',
        category TEXT,
        stock REAL DEFAULT 0,
        min_stock REAL DEFAULT 0,
        price REAL DEFAULT 0,
        supplier_id INTEGER REFERENCES suppliers(id),
        remark TEXT,
        store_id INTEGER,
        brand TEXT,
        spec TEXT,
        expiry_months INTEGER DEFAULT 0,
        expiry_days INTEGER DEFAULT 0
      )
    ''');

    // ========== 采购进货 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_no TEXT UNIQUE,
        supplier_id INTEGER REFERENCES suppliers(id),
        total_amount REAL DEFAULT 0,
        operator TEXT,
        purchase_date TEXT,
        remark TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_id INTEGER REFERENCES purchases(id) ON DELETE CASCADE,
        ingredient_id INTEGER REFERENCES ingredients(id),
        quantity REAL,
        unit_price REAL,
        total_price REAL,
        production_date TEXT,
        usage TEXT
      )
    ''');

    // ========== 菜品管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS dishes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        selling_price REAL DEFAULT 0,
        cost_price REAL DEFAULT 0,
        status TEXT DEFAULT '在售',
        remark TEXT,
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS dish_ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dish_id INTEGER REFERENCES dishes(id) ON DELETE CASCADE,
        ingredient_id INTEGER REFERENCES ingredients(id),
        quantity REAL
      )
    ''');

    // ========== 菜单管理（点菜用） ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        selling_price REAL DEFAULT 0,
        cost_price REAL DEFAULT 0,
        image_path TEXT,
        status TEXT DEFAULT '在售',
        is_recommend INTEGER DEFAULT 0,
        sort_order INTEGER DEFAULT 0,
        store_id INTEGER REFERENCES stores(id),
        remark TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    // ========== 桌台管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS dining_tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        area TEXT,
        capacity INTEGER DEFAULT 4,
        status TEXT DEFAULT '空闲',
        store_id INTEGER REFERENCES stores(id),
        remark TEXT
      )
    ''');

    // ========== 营业额 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS daily_revenue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_date TEXT NOT NULL,
        channel TEXT DEFAULT '',
        package_name TEXT DEFAULT '',
        package_type TEXT DEFAULT '',
        order_count INTEGER DEFAULT 0,
        amount REAL DEFAULT 0,
        cash_amount REAL DEFAULT 0,
        card_amount REAL DEFAULT 0,
        online_amount REAL DEFAULT 0,
        dining_count INTEGER DEFAULT 0,
        takeout_count INTEGER DEFAULT 0,
        operator TEXT,
        store_id INTEGER REFERENCES stores(id),
        remark TEXT
      )
    ''');

    // ========== 营收渠道配置 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS revenue_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_name TEXT NOT NULL,
        store_id INTEGER,
        sort_order INTEGER DEFAULT 0
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS revenue_package_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_name TEXT NOT NULL,
        type_name TEXT NOT NULL,
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS revenue_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_name TEXT NOT NULL,
        package_name TEXT NOT NULL,
        type_name TEXT DEFAULT '',
        price REAL DEFAULT 0,
        store_id INTEGER
      )
    ''');

    // ========== 营收明细 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS revenue_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        revenue_id INTEGER REFERENCES daily_revenue(id) ON DELETE CASCADE,
        menu_item_id INTEGER REFERENCES menu_items(id),
        menu_name TEXT,
        quantity INTEGER DEFAULT 1,
        unit_price REAL,
        total_price REAL
      )
    ''');

    // ========== 报销管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS reimbursements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reimb_no TEXT UNIQUE,
        employee_id INTEGER REFERENCES employees(id),
        title TEXT,
        category TEXT,
        amount REAL,
        description TEXT,
        status TEXT DEFAULT '待审批',
        submit_date TEXT,
        approve_date TEXT,
        approver_id INTEGER,
        store_id INTEGER REFERENCES stores(id),
        remark TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    // ========== 审批记录 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        biz_type TEXT NOT NULL,
        biz_id INTEGER NOT NULL,
        title TEXT DEFAULT '',
        amount REAL DEFAULT 0,
        applicant_id INTEGER REFERENCES employees(id),
        approver_id INTEGER REFERENCES employees(id),
        status TEXT DEFAULT '待审批',
        comment TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT,
        store_id INTEGER
      )
    ''');

    // ========== 考勤管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER REFERENCES employees(id),
        record_date TEXT NOT NULL,
        check_in TEXT,
        check_out TEXT,
        status TEXT DEFAULT '正常',
        check_in_location TEXT DEFAULT '',
        check_out_location TEXT DEFAULT '',
        check_in_lat TEXT DEFAULT '',
        check_in_lon TEXT DEFAULT '',
        check_out_lat TEXT DEFAULT '',
        check_out_lon TEXT DEFAULT '',
        remark TEXT,
        store_id INTEGER REFERENCES stores(id),
        UNIQUE(employee_id, record_date)
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS leave_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER REFERENCES employees(id),
        start_date TEXT,
        end_date TEXT,
        leave_type TEXT,
        reason TEXT,
        status TEXT DEFAULT '待审批',
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    // ========== 排班管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER REFERENCES employees(id),
        shift_date TEXT NOT NULL,
        shift_type TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        store_id INTEGER REFERENCES stores(id),
        remark TEXT,
        UNIQUE(employee_id, shift_date)
      )
    ''');

    // ========== 工资管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS salary_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER UNIQUE REFERENCES employees(id),
        base_salary REAL DEFAULT 0,
        overtime_rate REAL DEFAULT 1.5,
        bonus REAL DEFAULT 0,
        deduction_per_day REAL DEFAULT 0,
        remark TEXT
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS salary_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER REFERENCES employees(id),
        year INTEGER,
        month INTEGER,
        base_salary REAL,
        overtime_pay REAL DEFAULT 0,
        bonus REAL DEFAULT 0,
        deduction REAL DEFAULT 0,
        actual_salary REAL,
        status TEXT DEFAULT '未发放',
        paid_date TEXT,
        remark TEXT,
        store_id INTEGER,
        UNIQUE(employee_id, year, month)
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS salary_global_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        late_deduction_per_minute REAL DEFAULT 1.0,
        probation_rate REAL DEFAULT 0.7,
        overtime_multiplier_weekday REAL DEFAULT 1.5,
        overtime_multiplier_weekend REAL DEFAULT 2.0,
        overtime_multiplier_holiday REAL DEFAULT 3.0,
        full_attendance_amount REAL DEFAULT 200,
        utility_deduction_amount REAL DEFAULT 30,
        seniority_per_year REAL DEFAULT 100,
        seniority_half_year REAL DEFAULT 50,
        social_pension_rate REAL DEFAULT 0.08,
        social_medical_rate REAL DEFAULT 0.02,
        social_unemployment_rate REAL DEFAULT 0.005,
        tax_threshold REAL DEFAULT 5000.0,
        standard_work_days REAL DEFAULT 30,
        enable_social_insurance INTEGER DEFAULT 0,
        enable_income_tax INTEGER DEFAULT 0
      )
    ''');
    await db.execute('INSERT OR IGNORE INTO salary_global_config (id) VALUES (1)');

    // ========== 收支管理 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS finance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_date TEXT NOT NULL,
        record_type TEXT NOT NULL,
        category TEXT,
        amount REAL NOT NULL,
        account TEXT,
        operator TEXT,
        description TEXT,
        store_id INTEGER,
        remark TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    // ========== 月度库存盘点 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS monthly_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        ingredient_id INTEGER REFERENCES ingredients(id),
        begin_stock REAL DEFAULT 0,
        purchase_amount REAL DEFAULT 0,
        end_stock REAL DEFAULT 0,
        consumption REAL DEFAULT 0,
        store_id INTEGER,
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(year, month, ingredient_id, store_id)
      )
    ''');

    // ========== 报表配置 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS report_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        report_type TEXT,
        filters TEXT,
        created_by TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    // ========== 应用元数据 ==========
    await db.execute('''
      CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT
      )
    ''');

    await db.execute('PRAGMA user_version = 5');
  }

  /// 迁移：从 v4 到 v5 — 统一列名并补充缺失表
  Future<void> _migrate(Database db, int oldV, int newV) async {
    // ignore: avoid_print
    print('LocalDb: migrating from v$oldV to v$newV');

    // 必须按顺序迁移：先处理旧版本
    if (oldV < 4) {
      await _migrateV3toV4(db);
    }
    if (oldV < 5) {
      await _migrateV4toV5(db);
    }
  }

  /// v3 → v4 迁移（保留旧版兼容）
  Future<void> _migrateV3toV4(Database db) async {
    // suppliers 添加 payment_method
    var supCols = await db.rawQuery('PRAGMA table_info(suppliers)');
    var supColNames = supCols.map((r) => r['name'] as String).toSet();
    if (!supColNames.contains('payment_method')) {
      await db.execute("ALTER TABLE suppliers ADD COLUMN payment_method TEXT DEFAULT ''");
    }

    // ingredients 添加 expiry 相关列
    var ingCols = await db.rawQuery('PRAGMA table_info(ingredients)');
    var ingColNames = ingCols.map((r) => r['name'] as String).toSet();
    for (var col in [
      {'name': 'brand', 'def': "TEXT DEFAULT ''"},
      {'name': 'spec', 'def': "TEXT DEFAULT ''"},
      {'name': 'expiry_months', 'def': 'INTEGER DEFAULT 0'},
      {'name': 'expiry_days', 'def': 'INTEGER DEFAULT 0'},
      {'name': 'expiry_value', 'def': 'INTEGER DEFAULT 0'},
      {'name': 'expiry_unit', 'def': "TEXT DEFAULT '天'"},
      {'name': 'supplier_id', 'def': 'INTEGER'},
    ]) {
      if (!ingColNames.contains(col['name'])) {
        await db.execute("ALTER TABLE ingredients ADD COLUMN ${col['name']} ${col['def']}");
      }
    }

    // purchases 添加 remark, created_at
    var purCols = await db.rawQuery('PRAGMA table_info(purchases)');
    var purColNames = purCols.map((r) => r['name'] as String).toSet();
    if (!purColNames.contains('remark')) {
      await db.execute("ALTER TABLE purchases ADD COLUMN remark TEXT");
    }
    if (!purColNames.contains('created_at')) {
      await db.execute("ALTER TABLE purchases ADD COLUMN created_at TEXT DEFAULT (datetime('now','localtime'))");
    }

    // 确保 purchase_items 表存在
    await db.execute('''
      CREATE TABLE IF NOT EXISTS purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_id INTEGER REFERENCES purchases(id) ON DELETE CASCADE,
        ingredient_id INTEGER,
        quantity REAL DEFAULT 0,
        unit_price REAL DEFAULT 0,
        total_price REAL DEFAULT 0,
        production_date TEXT,
        usage TEXT
      )
    ''');

    // 确保 monthly_inventory 表存在
    await db.execute('''
      CREATE TABLE IF NOT EXISTS monthly_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient_id INTEGER,
        ingredient_name TEXT,
        quantity REAL DEFAULT 0,
        unit_price REAL DEFAULT 0,
        month TEXT,
        store_id INTEGER,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    // employees 补充字段
    var empCols = await db.rawQuery('PRAGMA table_info(employees)');
    var empColNames = empCols.map((r) => r['name'] as String).toSet();
    for (var col in [
      {'name': 'pay_type', 'def': "TEXT DEFAULT 'monthly'"},
      {'name': 'hourly_rate', 'def': 'REAL DEFAULT 0'},
      {'name': 'commission_rate', 'def': 'REAL DEFAULT 0'},
      {'name': 'is_housing', 'def': "TEXT DEFAULT '否'"},
      {'name': 'position_allowance', 'def': 'REAL DEFAULT 0'},
      {'name': 'assessment_allowance', 'def': 'REAL DEFAULT 0'},
      {'name': 'social_insurance_base', 'def': 'REAL DEFAULT 0'},
      {'name': 'housing_fund_rate', 'def': 'REAL DEFAULT 0.07'},
      {'name': 'is_system_user', 'def': 'INTEGER DEFAULT 0'},
    ]) {
      if (!empColNames.contains(col['name'])) {
        await db.execute("ALTER TABLE employees ADD COLUMN ${col['name']} ${col['def']}");
      }
    }

    await db.execute('PRAGMA user_version = 4');
  }

  /// v4 → v5 迁移：统一列名、补充缺失表、修正状态默认值
  Future<void> _migrateV4toV5(Database db) async {
    // 1. 补充缺失的表
    await db.execute('''
      CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        remark TEXT
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        selling_price REAL DEFAULT 0,
        cost_price REAL DEFAULT 0,
        image_path TEXT,
        status TEXT DEFAULT '在售',
        is_recommend INTEGER DEFAULT 0,
        sort_order INTEGER DEFAULT 0,
        store_id INTEGER REFERENCES stores(id),
        remark TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        biz_type TEXT NOT NULL,
        biz_id INTEGER NOT NULL,
        title TEXT DEFAULT '',
        amount REAL DEFAULT 0,
        applicant_id INTEGER REFERENCES employees(id),
        approver_id INTEGER REFERENCES employees(id),
        status TEXT DEFAULT '待审批',
        comment TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT,
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS leave_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER REFERENCES employees(id),
        start_date TEXT,
        end_date TEXT,
        leave_type TEXT,
        reason TEXT,
        status TEXT DEFAULT '待审批',
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS report_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        report_type TEXT,
        filters TEXT,
        created_by TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS dining_tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        area TEXT,
        capacity INTEGER DEFAULT 4,
        status TEXT DEFAULT '空闲',
        store_id INTEGER REFERENCES stores(id),
        remark TEXT
      )
    ''');

    // 2. stores: 添加缺失字段，统一状态默认值
    var storeCols = await db.rawQuery('PRAGMA table_info(stores)');
    var storeColNames = storeCols.map((r) => r['name'] as String).toSet();
    for (var col in [
      {'name': 'manager', 'def': 'TEXT'},
      {'name': 'remark', 'def': 'TEXT'},
      {'name': 'created_at', 'def': "TEXT DEFAULT (datetime('now','localtime'))"},
    ]) {
      if (!storeColNames.contains(col['name'])) {
        await db.execute("ALTER TABLE stores ADD COLUMN ${col['name']} ${col['def']}");
      }
    }
    // 统一状态值：营业中 -> 正常
    await db.execute("UPDATE stores SET status='正常' WHERE status='营业中'");
    await db.execute("UPDATE stores SET status='停业' WHERE status='休息中'");

    // 3. employees: 添加 department_id, password
    var empCols = await db.rawQuery('PRAGMA table_info(employees)');
    var empColNames = empCols.map((r) => r['name'] as String).toSet();
    if (!empColNames.contains('department_id')) {
      await db.execute("ALTER TABLE employees ADD COLUMN department_id INTEGER REFERENCES departments(id)");
    }
    if (!empColNames.contains('password')) {
      await db.execute("ALTER TABLE employees ADD COLUMN password TEXT");
    }

    // 4. revenue_channels: 列名 name → channel_name，添加 store_id
    var rcCols = await db.rawQuery('PRAGMA table_info(revenue_channels)');
    var rcColNames = rcCols.map((r) => r['name'] as String).toSet();
    if (rcColNames.contains('name') && !rcColNames.contains('channel_name')) {
      await db.execute("ALTER TABLE revenue_channels RENAME COLUMN name TO channel_name");
    }
    if (!rcColNames.contains('store_id')) {
      await db.execute("ALTER TABLE revenue_channels ADD COLUMN store_id INTEGER");
    }

    // 5. revenue_packages: 重建表结构（与桌面端一致）
    var rpCols = await db.rawQuery('PRAGMA table_info(revenue_packages)');
    var rpColNames = rpCols.map((r) => r['name'] as String).toSet();
    if (rpColNames.contains('name') && !rpColNames.contains('channel_name')) {
      // 旧表结构不同，备份后重建
      await db.execute('ALTER TABLE revenue_packages RENAME TO revenue_packages_old');
      await db.execute('''
        CREATE TABLE IF NOT EXISTS revenue_packages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          channel_name TEXT NOT NULL,
          package_name TEXT NOT NULL,
          type_name TEXT DEFAULT '',
          price REAL DEFAULT 0,
          store_id INTEGER
        )
      ''');
      // 迁移旧数据
      try {
        await db.execute('''
          INSERT INTO revenue_packages (channel_name, package_name, type_name, price)
          SELECT channel, name, '', 0 FROM revenue_packages_old
        ''');
      } catch (_) {}
      await db.execute('DROP TABLE IF EXISTS revenue_packages_old');
    }

    // 6. revenue_package_types: 重建表结构
    var rptCols = await db.rawQuery('PRAGMA table_info(revenue_package_types)');
    var rptColNames = rptCols.map((r) => r['name'] as String).toSet();
    if (rptColNames.contains('package_id') && !rptColNames.contains('channel_name')) {
      await db.execute('ALTER TABLE revenue_package_types RENAME TO revenue_package_types_old');
      await db.execute('''
        CREATE TABLE IF NOT EXISTS revenue_package_types (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          channel_name TEXT NOT NULL,
          type_name TEXT NOT NULL,
          store_id INTEGER
        )
      ''');
      await db.execute('DROP TABLE IF EXISTS revenue_package_types_old');
    }

    // 7. reimbursements: 重建表结构（列名完全不同）
    var reimCols = await db.rawQuery('PRAGMA table_info(reimbursements)');
    var reimColNames = reimCols.map((r) => r['name'] as String).toSet();
    if (reimColNames.contains('reimbursement_no') && !reimColNames.contains('reimb_no')) {
      await db.execute('ALTER TABLE reimbursements RENAME TO reimbursements_old');
      await db.execute('''
        CREATE TABLE IF NOT EXISTS reimbursements (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          reimb_no TEXT UNIQUE,
          employee_id INTEGER REFERENCES employees(id),
          title TEXT,
          category TEXT,
          amount REAL,
          description TEXT,
          status TEXT DEFAULT '待审批',
          submit_date TEXT,
          approve_date TEXT,
          approver_id INTEGER,
          store_id INTEGER REFERENCES stores(id),
          remark TEXT,
          created_at TEXT DEFAULT (datetime('now','localtime'))
        )
      ''');
      // 迁移旧数据
      try {
        await db.execute('''
          INSERT INTO reimbursements (reimb_no, employee_id, title, category, amount, description, status, submit_date, approve_date, remark)
          SELECT reimbursement_no, NULL, category, category, amount, remark, status, application_date, approval_date, remark
          FROM reimbursements_old
        ''');
      } catch (_) {}
      await db.execute('DROP TABLE IF EXISTS reimbursements_old');
    }

    // 8. attendance: 重建表结构（列名不同）
    var attCols = await db.rawQuery('PRAGMA table_info(attendance)');
    var attColNames = attCols.map((r) => r['name'] as String).toSet();
    if (attColNames.contains('shift_date') && !attColNames.contains('record_date')) {
      await db.execute('ALTER TABLE attendance RENAME TO attendance_old');
      await db.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          employee_id INTEGER REFERENCES employees(id),
          record_date TEXT NOT NULL,
          check_in TEXT,
          check_out TEXT,
          status TEXT DEFAULT '正常',
          check_in_location TEXT DEFAULT '',
          check_out_location TEXT DEFAULT '',
          check_in_lat TEXT DEFAULT '',
          check_in_lon TEXT DEFAULT '',
          check_out_lat TEXT DEFAULT '',
          check_out_lon TEXT DEFAULT '',
          remark TEXT,
          store_id INTEGER REFERENCES stores(id),
          UNIQUE(employee_id, record_date)
        )
      ''');
      try {
        await db.execute('''
          INSERT INTO attendance (employee_id, record_date, check_in, check_out, status, remark, store_id)
          SELECT employee_id, shift_date, check_in_time, check_out_time, status, remark, store_id
          FROM attendance_old
        ''');
      } catch (_) {}
      await db.execute('DROP TABLE IF EXISTS attendance_old');
    }

    // 9. monthly_inventory: 重建表结构
    var miCols = await db.rawQuery('PRAGMA table_info(monthly_inventory)');
    var miColNames = miCols.map((r) => r['name'] as String).toSet();
    if (miColNames.contains('ingredient_name') && !miColNames.contains('year')) {
      await db.execute('ALTER TABLE monthly_inventory RENAME TO monthly_inventory_old');
      await db.execute('''
        CREATE TABLE IF NOT EXISTS monthly_inventory (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          year INTEGER NOT NULL,
          month INTEGER NOT NULL,
          ingredient_id INTEGER REFERENCES ingredients(id),
          begin_stock REAL DEFAULT 0,
          purchase_amount REAL DEFAULT 0,
          end_stock REAL DEFAULT 0,
          consumption REAL DEFAULT 0,
          store_id INTEGER,
          updated_at TEXT DEFAULT (datetime('now','localtime')),
          UNIQUE(year, month, ingredient_id, store_id)
        )
      ''');
      try {
        // 尝试从旧 month 字段解析年/月
        await db.execute('''
          INSERT INTO monthly_inventory (year, month, ingredient_id, end_stock, store_id)
          SELECT 
            CAST(substr(month, 1, 4) AS INTEGER),
            CAST(substr(month, 6, 2) AS INTEGER),
            ingredient_id,
            quantity,
            store_id
          FROM monthly_inventory_old
          WHERE month IS NOT NULL AND length(month) >= 7
        ''');
      } catch (_) {}
      await db.execute('DROP TABLE IF EXISTS monthly_inventory_old');
    }

    // 10. dishes: 添加 remark 字段
    var dishCols = await db.rawQuery('PRAGMA table_info(dishes)');
    var dishColNames = dishCols.map((r) => r['name'] as String).toSet();
    if (!dishColNames.contains('remark')) {
      await db.execute("ALTER TABLE dishes ADD COLUMN remark TEXT");
    }

    // 11. salary_config: 补充缺失字段（桌面端核心字段）
    var scCols = await db.rawQuery('PRAGMA table_info(salary_config)');
    var scColNames = scCols.map((r) => r['name'] as String).toSet();
    if (!scColNames.contains('overtime_rate')) {
      await db.execute("ALTER TABLE salary_config ADD COLUMN overtime_rate REAL DEFAULT 1.5");
    }
    if (!scColNames.contains('bonus')) {
      await db.execute("ALTER TABLE salary_config ADD COLUMN bonus REAL DEFAULT 0");
    }
    if (!scColNames.contains('deduction_per_day')) {
      await db.execute("ALTER TABLE salary_config ADD COLUMN deduction_per_day REAL DEFAULT 0");
    }

    // 12. salary_global_config: 补充缺失字段
    var sgCols = await db.rawQuery('PRAGMA table_info(salary_global_config)');
    var sgColNames = sgCols.map((r) => r['name'] as String).toSet();
    for (var col in [
      {'name': 'overtime_multiplier_weekday', 'def': 'REAL DEFAULT 1.5'},
      {'name': 'overtime_multiplier_weekend', 'def': 'REAL DEFAULT 2.0'},
      {'name': 'overtime_multiplier_holiday', 'def': 'REAL DEFAULT 3.0'},
      {'name': 'social_pension_rate', 'def': 'REAL DEFAULT 0.08'},
      {'name': 'social_medical_rate', 'def': 'REAL DEFAULT 0.02'},
      {'name': 'social_unemployment_rate', 'def': 'REAL DEFAULT 0.005'},
    ]) {
      if (!sgColNames.contains(col['name'])) {
        await db.execute("ALTER TABLE salary_global_config ADD COLUMN ${col['name']} ${col['def']}");
      }
    }
    // 确保标准工作日为30
    await db.execute("UPDATE salary_global_config SET standard_work_days=30 WHERE id=1");

    // 13. finance_records: 补充 remark, created_at
    var frCols = await db.rawQuery('PRAGMA table_info(finance_records)');
    var frColNames = frCols.map((r) => r['name'] as String).toSet();
    if (!frColNames.contains('remark')) {
      await db.execute("ALTER TABLE finance_records ADD COLUMN remark TEXT");
    }
    if (!frColNames.contains('created_at')) {
      await db.execute("ALTER TABLE finance_records ADD COLUMN created_at TEXT DEFAULT (datetime('now','localtime'))");
    }

    // 14. 统一桌台状态值
    await db.execute("UPDATE dining_tables SET status='占用' WHERE status='使用中'");
    await db.execute("UPDATE dining_tables SET status='预定' WHERE status='预留'");
    await db.execute("UPDATE dining_tables SET status='清洁中' WHERE status='维修中'");

    await db.execute('PRAGMA user_version = 5');
  }

  /// 同步后重新打开数据库并执行迁移
  Future<void> reopen() async {
    if (_database != null && _database!.isOpen) {
      await _database!.close();
    }
    _database = null;
    _database = await _initDb();
  }

  /// 通用查询
  Future<List<Map<String, dynamic>>> query(
    String table, {
    List<String>? columns,
    String? where,
    List<dynamic>? whereArgs,
    String? orderBy,
    int? limit,
  }) async {
    final db = await database;
    return db.query(
      table,
      columns: columns,
      where: where,
      whereArgs: whereArgs,
      orderBy: orderBy,
      limit: limit,
    );
  }

  /// 通用插入
  Future<int> insert(String table, Map<String, dynamic> values) async {
    final db = await database;
    return db.insert(table, values);
  }

  /// 通用更新
  Future<int> update(
    String table,
    Map<String, dynamic> values, {
    String? where,
    List<dynamic>? whereArgs,
  }) async {
    final db = await database;
    return db.update(table, values, where: where, whereArgs: whereArgs);
  }

  /// 通用删除
  Future<int> delete(
    String table, {
    String? where,
    List<dynamic>? whereArgs,
  }) async {
    final db = await database;
    return db.delete(table, where: where, whereArgs: whereArgs);
  }

  /// 原始SQL查询
  Future<List<Map<String, dynamic>>> rawQuery(String sql, [List<dynamic>? args]) async {
    final db = await database;
    return db.rawQuery(sql, args ?? []);
  }

  /// 原始SQL执行
  Future<void> rawExecute(String sql, [List<dynamic>? args]) async {
    final db = await database;
    await db.execute(sql, args ?? []);
  }
}