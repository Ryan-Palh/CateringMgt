# -*- coding: utf-8 -*-
"""
数据库管理模块 v5.0 —— 餐饮专业版
新增：菜品菜单管理、桌台管理、订单流水、营收渠道配置
"""
import sqlite3
import os
import re as _re
import secrets
from datetime import datetime

try:
    import bcrypt as _bcrypt
    _HAS_BCRYPT = True
except ImportError:
    try:
        from passlib.context import CryptContext
        _pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        _HAS_BCRYPT = True
    except ImportError:
        _HAS_BCRYPT = False

from utils.logger import logger
from utils.config import get_db_path

DB_PATH = get_db_path()


def _hash_password(password):
    if _HAS_BCRYPT:
        pwd_bytes = password.encode('utf-8')
        if len(pwd_bytes) > 72:
            pwd_bytes = pwd_bytes[:72]
        salt = _bcrypt.gensalt()
        return _bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')
    import hashlib
    salt = secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"sha256:{salt}:{digest}"


def _verify_password(password, stored_hash):
    try:
        if stored_hash.startswith("$2"):
            if _HAS_BCRYPT:
                pwd_bytes = password.encode('utf-8')
                if len(pwd_bytes) > 72:
                    pwd_bytes = pwd_bytes[:72]
                return _bcrypt.checkpw(pwd_bytes, stored_hash.encode('utf-8'))
            return False
        if stored_hash.startswith("sha256:"):
            import hashlib
            parts = stored_hash.split(":", 2)
            if len(parts) == 3:
                salt, expected = parts[1], parts[2]
                actual = hashlib.sha256(
                    f"{salt}:{password}".encode("utf-8")).hexdigest()
                return actual == expected
            return False
        if ":" in stored_hash:
            import hashlib
            salt, expected = stored_hash.split(":", 1)
            actual = hashlib.sha256(
                f"{salt}:{password}".encode("utf-8")).hexdigest()
            return actual == expected
        import hashlib
        return hashlib.sha256(password.encode(
            "utf-8")).hexdigest() == stored_hash
    except Exception:
        return False


class AutoSyncConnection(sqlite3.Connection):
    """SQLite 连接子类：commit 后自动触发坚果云防抖同步"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._skip_sync = False

    @property
    def skip_sync(self):
        return self._skip_sync

    @skip_sync.setter
    def skip_sync(self, value):
        self._skip_sync = value

    def commit(self):
        super().commit()
        if self._skip_sync:
            return
        try:
            from utils.nutstore_sync import get_sync
            get_sync().trigger_sync()
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"同步失败: {e}")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, factory=AutoSyncConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    """初始化数据库，创建所有表"""
    conn = get_connection()
    cursor = conn.cursor()

    # ========== 门店管理 ==========
    cursor.execute("""
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
    """)

    # ========== 部门 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            remark TEXT
        )
    """)

    # ========== 员工 ==========
    cursor.execute("""
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
    """)

    # ========== 供应商 ==========
    cursor.execute("""
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
    """)

    # ========== 食材原料 ==========
    cursor.execute("""
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
    """)

    # ========== 采购进货 ==========
    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    # ========== 菜品管理 ==========
    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dish_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id INTEGER REFERENCES dishes(id) ON DELETE CASCADE,
            ingredient_id INTEGER REFERENCES ingredients(id),
            quantity REAL
        )
    """)

    # ========== 菜单管理（点菜用） ==========
    cursor.execute("""
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
    """)

    # ========== 桌台管理 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dining_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            area TEXT,
            capacity INTEGER DEFAULT 4,
            status TEXT DEFAULT '空闲',
            store_id INTEGER REFERENCES stores(id),
            remark TEXT
        )
    """)

    # ========== 营业额 ==========
    cursor.execute("""
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
    """)

    # ========== 营收渠道配置 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name TEXT NOT NULL,
            store_id INTEGER,
            sort_order INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue_package_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name TEXT NOT NULL,
            type_name TEXT NOT NULL,
            store_id INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name TEXT NOT NULL,
            package_name TEXT NOT NULL,
            type_name TEXT DEFAULT '',
            price REAL DEFAULT 0,
            store_id INTEGER
        )
    """)

    # ========== 营收明细 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revenue_id INTEGER REFERENCES daily_revenue(id) ON DELETE CASCADE,
            menu_item_id INTEGER REFERENCES menu_items(id),
            menu_name TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL,
            total_price REAL
        )
    """)

    # ========== 报销管理 ==========
    cursor.execute("""
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
    """)

    # ========== 审批记录 ==========
    cursor.execute("""
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
    """)

    # ========== 考勤管理 ==========
    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    # ========== 排班管理 ==========
    cursor.execute("""
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
    """)

    # ========== 工资管理 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salary_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER UNIQUE REFERENCES employees(id),
            base_salary REAL DEFAULT 0,
            position_allowance REAL DEFAULT 0,
            assessment_allowance REAL DEFAULT 0,
            housing_allowance REAL DEFAULT 0,
            uniform_refund REAL DEFAULT 0,
            prev_supplement REAL DEFAULT 0,
            salary_advance REAL DEFAULT 0,
            fine_compensation REAL DEFAULT 0,
            is_housing TEXT DEFAULT '否',
            overtime_rate REAL DEFAULT 1.5,
            bonus REAL DEFAULT 0,
            deduction_per_day REAL DEFAULT 0,
            remark TEXT
        )
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)
    cursor.execute(
        "INSERT OR IGNORE INTO salary_global_config (id) VALUES (1)")

    # ========== 收支管理 ==========
    cursor.execute("""
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
    """)

    # ========== 月度库存盘点 ==========
    cursor.execute("""
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
    """)

    # ========== 报表配置 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            report_type TEXT,
            filters TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # ========== 应用元数据（标记初始化/种子状态）==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    migrate_database()
    logger.info(f"数据库初始化完成: {DB_PATH}")
    return True


_SQL_IDENTIFIER_RE = _re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _safe_sql_identifier(name):
    """验证 SQL 标识符仅包含安全字符，防止注入"""
    if not _SQL_IDENTIFIER_RE.match(name):
        raise ValueError(f"非法 SQL 标识符: {name}")
    return name


def migrate_database():
    """迁移已有数据库：补充新字段"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA user_version")
    current_version = cursor.fetchone()[0]
    TARGET_VERSION = 5

    if current_version >= TARGET_VERSION:
        conn.close()

    logger.info(f"开始数据库迁移: v{current_version} -> v{TARGET_VERSION}")

    import shutil
    backup_path = DB_PATH + f".bak.v{current_version}"
    try:
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_path)
    except Exception as e:
        logger.warning(f"迁移前备份失败: {e}")

    # employees 表新增字段
    cursor.execute("PRAGMA table_info(employees)")
    cols = {row[1] for row in cursor.fetchall()}
    emp_new_cols = {
        "store_id": "INTEGER REFERENCES stores(id)",
        "permissions": 'TEXT DEFAULT ""',
        "pay_type": "TEXT DEFAULT 'monthly'",
        "hourly_rate": "REAL DEFAULT 0",
        "commission_rate": "REAL DEFAULT 0",
        "is_housing": "TEXT DEFAULT '否'",
        "position_allowance": "REAL DEFAULT 0",
        "assessment_allowance": "REAL DEFAULT 0",
        "social_insurance_base": "REAL DEFAULT 0",
        "housing_fund_rate": "REAL DEFAULT 0.07",
        "is_system_user": "INTEGER DEFAULT 0",
    }
    for col_name, col_def in emp_new_cols.items():
        if col_name not in cols:
            cursor.execute(
                f"ALTER TABLE employees ADD COLUMN {
                    _safe_sql_identifier(col_name)} {
                    _safe_sql_identifier(col_def)}")

    cursor.execute(
        "UPDATE employees SET is_system_user = 1 WHERE username IS NOT NULL AND username != ''")

    # salary_records 表新增字段
    cursor.execute("PRAGMA table_info(salary_records)")
    sr_cols = {row[1] for row in cursor.fetchall()}
    new_sr_cols = {
        "pay_type": "TEXT DEFAULT 'monthly'", "work_age": "REAL DEFAULT 0",
        "is_housing": "TEXT DEFAULT '否'", "attend_days": "INTEGER DEFAULT 30",
        "work_days": "REAL DEFAULT 0", "probation_days": "REAL DEFAULT 0",
        "public_rest": "REAL DEFAULT 0", "unpaid_rest": "REAL DEFAULT 0",
        "comp_rest": "TEXT DEFAULT ''", "leave_days": "REAL DEFAULT 0",
        "late_minutes": "INTEGER DEFAULT 0", "late_count": "INTEGER DEFAULT 0",
        "absent_days": "REAL DEFAULT 0", "urgent_quit": "TEXT DEFAULT ''",
        "pay_days": "REAL DEFAULT 0", "full_attendance": "REAL DEFAULT 0",
        "uniform_refund": "REAL DEFAULT 0", "prev_supplement": "REAL DEFAULT 0",
        "position_allowance": "REAL DEFAULT 0", "assessment_allowance": "REAL DEFAULT 0",
        "housing_allowance": "REAL DEFAULT 0", "seniority_pay": "REAL DEFAULT 0",
        "gross_salary": "REAL DEFAULT 0", "late_deduction": "REAL DEFAULT 0",
        "absent_deduction": "REAL DEFAULT 0", "fine_compensation": "REAL DEFAULT 0",
        "urgent_deduction": "REAL DEFAULT 0", "utility_deduction": "REAL DEFAULT 0",
        "salary_advance": "REAL DEFAULT 0", "total_deduction": "REAL DEFAULT 0",
        "social_insurance": "REAL DEFAULT 0", "housing_fund": "REAL DEFAULT 0",
        "income_tax": "REAL DEFAULT 0",
    }
    for col_name, col_def in new_sr_cols.items():
        if col_name not in sr_cols:
            cursor.execute(
                f"ALTER TABLE salary_records ADD COLUMN {
                    _safe_sql_identifier(col_name)} {
                    _safe_sql_identifier(col_def)}")

    # 为业务表添加 store_id
    store_tables = ["purchases", "daily_revenue", "finance_records", "attendance",
                    "salary_records", "reimbursements", "ingredients", "dishes", "suppliers"]
    for tbl in store_tables:
        cursor.execute(f"PRAGMA table_info({tbl})")
        tbl_cols = {row[1] for row in cursor.fetchall()}
        if "store_id" not in tbl_cols:
            cursor.execute(
                f"ALTER TABLE {
                    _safe_sql_identifier(tbl)} ADD COLUMN store_id INTEGER REFERENCES stores(id)")

    # daily_revenue 补充字段
    cursor.execute("PRAGMA table_info(daily_revenue)")
    dr_cols = {row[1] for row in cursor.fetchall()}
    for col_name, col_def in [("channel", "TEXT DEFAULT ''"), ("package_name", "TEXT DEFAULT ''"),
                              ("package_type", "TEXT DEFAULT ''"), ("order_count", "INTEGER DEFAULT 0")]:
        if col_name not in dr_cols:
            cursor.execute(
                f"ALTER TABLE daily_revenue ADD COLUMN {
                    _safe_sql_identifier(col_name)} {
                    _safe_sql_identifier(col_def)}")

    # ingredients 表补充字段
    cursor.execute("PRAGMA table_info(ingredients)")
    ing_cols = {row[1] for row in cursor.fetchall()}
    for col_name, col_def in [("spec", "TEXT DEFAULT ''"), ("expiry_value", "INTEGER DEFAULT 0"),
                              ("expiry_unit", "TEXT DEFAULT '天'"), ("brand",
                                                                    "TEXT DEFAULT ''"),
                              ("expiry_months", "INTEGER DEFAULT 0"), ("expiry_days", "INTEGER DEFAULT 0")]:
        if col_name not in ing_cols:
            cursor.execute(
                f"ALTER TABLE ingredients ADD COLUMN {
                    _safe_sql_identifier(col_name)} {
                    _safe_sql_identifier(col_def)}")

    # approvals 表扩展
    cursor.execute("PRAGMA table_info(approvals)")
    app_cols = {row[1] for row in cursor.fetchall()}
    if "title" not in app_cols:
        cursor.execute(
            "ALTER TABLE approvals ADD COLUMN title TEXT DEFAULT ''")
    if "amount" not in app_cols:
        cursor.execute(
            "ALTER TABLE approvals ADD COLUMN amount REAL DEFAULT 0")

    # attendance 表添加打卡位置字段
    cursor.execute("PRAGMA table_info(attendance)")
    att_cols = {row[1] for row in cursor.fetchall()}
    for col_name, col_def in [("check_in_location", "TEXT DEFAULT ''"), ("check_out_location", "TEXT DEFAULT ''"),
                              ("check_in_lat", "TEXT DEFAULT ''"), ("check_in_lon",
                                                                    "TEXT DEFAULT ''"),
                              ("check_out_lat", "TEXT DEFAULT ''"), ("check_out_lon", "TEXT DEFAULT ''")]:
        if col_name not in att_cols:
            cursor.execute(
                f"ALTER TABLE attendance ADD COLUMN {
                    _safe_sql_identifier(col_name)} {
                    _safe_sql_identifier(col_def)}")

    # salary_global_config 补充新列
    cursor.execute("PRAGMA table_info(salary_global_config)")
    sg_cols = {row[1] for row in cursor.fetchall()}
    for col_name, col_def in [("probation_rate", "REAL DEFAULT 0.7"), ("full_attendance_amount", "REAL DEFAULT 200"),
                              ("utility_deduction_amount", "REAL DEFAULT 30"), (
                                  "seniority_per_year", "REAL DEFAULT 100"),
                              ("seniority_half_year", "REAL DEFAULT 50"), (
                                  "enable_social_insurance", "INTEGER DEFAULT 0"),
                              ("enable_income_tax", "INTEGER DEFAULT 0")]:
        if col_name not in sg_cols:
            cursor.execute(
                f"ALTER TABLE salary_global_config ADD COLUMN {
                    _safe_sql_identifier(col_name)} {
                    _safe_sql_identifier(col_def)}")
    cursor.execute(
        "UPDATE salary_global_config SET standard_work_days=30 WHERE id=1")

    # stores 表添加 business_hours
    cursor.execute("PRAGMA table_info(stores)")
    store_cols = {row[1] for row in cursor.fetchall()}
    if "business_hours" not in store_cols:
        cursor.execute(
            "ALTER TABLE stores ADD COLUMN business_hours TEXT DEFAULT '09:00-22:00'")

    # suppliers 表添加 payment_method
    cursor.execute("PRAGMA table_info(suppliers)")
    sup_cols = {row[1] for row in cursor.fetchall()}
    if "payment_method" not in sup_cols:
        cursor.execute(
            "ALTER TABLE suppliers ADD COLUMN payment_method TEXT DEFAULT ''")

    # salary_config 表补充字段
    cursor.execute("PRAGMA table_info(salary_config)")
    sc_cols = {row[1] for row in cursor.fetchall()}
    sc_new_cols = [
        ("position_allowance", "REAL DEFAULT 0"),
        ("assessment_allowance", "REAL DEFAULT 0"),
        ("housing_allowance", "REAL DEFAULT 0"),
        ("uniform_refund", "REAL DEFAULT 0"),
        ("prev_supplement", "REAL DEFAULT 0"),
        ("salary_advance", "REAL DEFAULT 0"),
        ("fine_compensation", "REAL DEFAULT 0"),
        ("is_housing", "TEXT DEFAULT '否'"),
    ]
    for col_name, col_def in sc_new_cols:
        if col_name not in sc_cols:
            cursor.execute(
                f"ALTER TABLE salary_config ADD COLUMN {
                    _safe_sql_identifier(col_name)} {
                    _safe_sql_identifier(col_def)}")

    conn.commit()
    conn.close()

    try:
        conn3 = get_connection()
        conn3.execute(f"PRAGMA user_version = {TARGET_VERSION}")
        conn3.commit()
        conn3.close()
        logger.info(f"数据库迁移完成，版本已更新至 v{TARGET_VERSION}")
    except Exception as e:
        logger.error(f"更新数据库版本号失败: {e}")

def seed_default_data():
    """插入默认数据"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM employees WHERE username='admin'")
    if cursor.fetchone()[0] == 0:
        hashed_pwd = _hash_password("admin123")
        cursor.execute("""
            INSERT INTO employees (name, username, password, role, position, hire_date, is_system_user)
            VALUES ('管理员', 'admin', ?, '管理员', '系统管理员', ?, 1)
        """, (hashed_pwd, datetime.now().strftime("%Y-%m-%d")))
        cursor.execute(
            "INSERT OR IGNORE INTO departments (name) VALUES ('前厅'), ('后厨'), ('吧台'), ('管理')")
        logger.info("默认管理员账号已创建")
    else:
        cursor.execute(
            "SELECT id, password FROM employees WHERE username='admin'")
        row = cursor.fetchone()
        if row and row["password"] == "admin123":
            hashed = _hash_password("admin123")
            cursor.execute(
                "UPDATE employees SET password=? WHERE id=?", (hashed, row["id"]))

    # 默认营收渠道（仅在首次初始化时插入，用户删除后不再重新插入）
    cursor.execute(
        "SELECT value FROM app_meta WHERE key='revenue_channels_seeded'")
    seeded = cursor.fetchone()
    if not seeded:
        # 检查是否已有渠道数据（从旧版升级时表可能已有数据）
        cursor.execute("SELECT COUNT(*) FROM revenue_channels")
        existing = cursor.fetchone()[0]
        if existing == 0:
            for i, ch in enumerate(
                    ["美团团购", "美团外卖", "饿了么", "抖音团购", "堂食", "大众点评"]):
                cursor.execute("INSERT INTO revenue_channels (channel_name, sort_order) VALUES (?, ?)",
                               (ch, i))
            logger.info("首次初始化：已插入默认营收渠道")
        else:
            logger.info(f"首次初始化：检测到已有 {existing} 条渠道，跳过种子数据")
        cursor.execute(
            "INSERT INTO app_meta (key, value) VALUES ('revenue_channels_seeded', '1')")

    conn.commit()


def verify_local_password(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT password FROM employees WHERE username=?", (username,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row["password"]:
        return False
    return _verify_password(password, row["password"])
