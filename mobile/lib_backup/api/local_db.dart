// api/local_db.dart — SQLite 本地数据库
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
      version: 1,
      onConfigure: (db) async {
        await db.execute('PRAGMA foreign_keys = ON');
      },
      onCreate: (db, v) async {
        await _createTables(db);
      },
    );
  }

  Future<void> _createTables(Database db) async {
    // 与桌面端 db_manager.py 保持一致的表结构
    await db.execute('''
      CREATE TABLE IF NOT EXISTS stores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        address TEXT,
        phone TEXT,
        business_hours TEXT,
        status TEXT DEFAULT '营业中'
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        position TEXT,
        base_salary REAL DEFAULT 0,
        hire_date TEXT,
        status TEXT DEFAULT '在职',
        username TEXT,
        role TEXT DEFAULT '员工',
        store_id INTEGER,
        permissions TEXT DEFAULT '',
        remark TEXT
      )
    ''');

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
        remark TEXT,
        operator TEXT,
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER,
        shift_date TEXT,
        check_in_time TEXT,
        check_out_time TEXT,
        status TEXT,
        remark TEXT,
        store_id INTEGER,
        UNIQUE(employee_id, shift_date)
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER,
        shift_date TEXT,
        shift_type TEXT,
        start_time TEXT,
        end_time TEXT,
        store_id INTEGER,
        UNIQUE(employee_id, shift_date)
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_no TEXT UNIQUE,
        supplier_id INTEGER,
        total_amount REAL DEFAULT 0,
        operator TEXT,
        purchase_date TEXT,
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS finance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_date TEXT NOT NULL,
        record_type TEXT,
        category TEXT,
        amount REAL DEFAULT 0,
        account TEXT,
        operator TEXT,
        description TEXT,
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS salary_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER,
        year INTEGER,
        month INTEGER,
        base_salary REAL,
        gross_salary REAL DEFAULT 0,
        total_deduction REAL DEFAULT 0,
        actual_salary REAL,
        status TEXT DEFAULT '未发放',
        paid_date TEXT,
        store_id INTEGER,
        UNIQUE(employee_id, year, month)
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS dishes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        selling_price REAL DEFAULT 0,
        cost_price REAL DEFAULT 0,
        status TEXT DEFAULT '在售',
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        unit TEXT DEFAULT '斤',
        category TEXT,
        stock REAL DEFAULT 0,
        min_stock REAL DEFAULT 0,
        price REAL DEFAULT 0,
        store_id INTEGER
      )
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact TEXT,
        phone TEXT,
        address TEXT,
        store_id INTEGER
      )
    ''');
  }

  /// 重新打开数据库（同步后调用）
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
