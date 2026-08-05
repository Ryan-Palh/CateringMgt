"""
数据联动模块 - 自动创建关联记录
营业额 → 收支收入 | 采购 → 收支支出 | 工资 → 收支支出
"""
from database.db_manager import get_connection
from utils.logger import logger
from utils.app_context import get_app_context
from utils.helpers import get_today

from utils.nutstore_sync import get_sync as _get_sync
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")


def auto_finance_from_revenue(revenue_id, amount, record_date, operator=""):
    """营业额录入后自动创建收入记录"""
    conn = get_connection()
    cursor = conn.cursor()
    ctx = get_app_context()
    _sid = ctx.store_id
    try:
        cursor.execute("""
            INSERT INTO finance_records (record_date, record_type, category, amount, account, operator, description, store_id)
            VALUES (?, '收入', '堂食营业额', ?, '营业款', ?, ?, ?)
        """, (record_date, amount, operator, f"日营业额(关联ID:{revenue_id})", _sid))
        conn.commit()
        _sync_cloud()
    except Exception as e:
        logger.error(f"auto_finance_from_revenue failed: {e}", exc_info=True)
    finally:
        conn.close()


def auto_finance_from_purchase(purchase_id, total_amount, purchase_date, operator=""):
    """采购入库后自动创建支出记录"""
    if total_amount <= 0:
        return
    conn = get_connection()
    cursor = conn.cursor()
    ctx = get_app_context()
    _sid = ctx.store_id
    try:
        cursor.execute("""
            INSERT INTO finance_records (record_date, record_type, category, amount, account, operator, description, store_id)
            VALUES (?, '支出', '食材采购', ?, '对公账户', ?, ?, ?)
        """, (purchase_date, total_amount, operator, f"食材采购(关联ID:{purchase_id})", _sid))
        conn.commit()
        _sync_cloud()
    except Exception as e:
        logger.error(f"auto_finance_from_purchase failed: {e}", exc_info=True)
    finally:
        conn.close()


def auto_finance_from_salary(salary_id, total_amount, month_str, operator=""):
    """工资发放后自动创建支出记录"""
    if total_amount <= 0:
        return
    conn = get_connection()
    cursor = conn.cursor()
    ctx = get_app_context()
    _sid = ctx.store_id
    today = get_today()
    try:
        cursor.execute("""
            INSERT INTO finance_records (record_date, record_type, category, amount, account, operator, description, store_id)
            VALUES (?, '支出', '工资', ?, '对公账户', ?, ?, ?)
        """, (today, total_amount, operator, f"工资-{month_str}(关联ID:{salary_id})", _sid))
        conn.commit()
        _sync_cloud()
    except Exception as e:
        logger.error(f"auto_finance_from_salary failed: {e}", exc_info=True)
    finally:
        conn.close()


def auto_finance_from_reimbursement(reimb_id, amount, employee_name, operator=""):
    """报销审批通过后自动创建支出记录"""
    if amount <= 0:
        return
    conn = get_connection()
    cursor = conn.cursor()
    ctx = get_app_context()
    _sid = ctx.store_id
    today = get_today()
    try:
        cursor.execute("""
            INSERT INTO finance_records (record_date, record_type, category, amount, account, operator, description, store_id)
            VALUES (?, '支出', '其他支出', ?, '对公账户', ?, ?, ?)
        """, (today, amount, operator, f"报销-{employee_name}(关联ID:{reimb_id})", _sid))
        conn.commit()
        _sync_cloud()
    except Exception as e:
        logger.error(f"auto_finance_from_reimbursement failed: {e}", exc_info=True)
    finally:
        conn.close()


def get_attendance_summary(employee_id, year, month):
    """获取考勤汇总：迟到次数、缺勤天数、请假天数"""
    conn = get_connection()
    cursor = conn.cursor()
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year+1}-01-01"
    else:
        end = f"{year}-{month+1:02d}-01"

    cursor.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE employee_id=? AND record_date>=? AND record_date<?
        AND (status='迟到' OR status='早退')
    """, (employee_id, start, end))
    late_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE employee_id=? AND record_date>=? AND record_date<?
        AND status='旷工'
    """, (employee_id, start, end))
    absent_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM leave_records
        WHERE employee_id=? AND status='已批准'
        AND start_date<? AND end_date>=?
    """, (employee_id, end, start))
    leave_count = cursor.fetchone()[0]

    conn.close()
    return late_count, absent_count, leave_count