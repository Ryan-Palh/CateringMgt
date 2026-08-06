"""
通用工具函数
"""
import re
from datetime import datetime


def validate_phone(phone):
    """简单手机号验证"""
    return bool(re.match(r'^1[3-9]\d{9}$', phone))


def validate_amount(amount):
    """验证金额"""
    try:
        val = float(amount)
        return val >= 0
    except (ValueError, TypeError):
        return False


def format_date(date_str, fmt="%Y-%m-%d"):
    """格式化日期"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return dt.strftime(fmt)
    except ValueError:
        return str(date_str)[:10]


def format_money(amount):
    """格式化金额显示"""
    if amount is None:
        return "0.00"
    return f"{float(amount):.2f}"


def get_today():
    """获取今天日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def get_current_month():
    """获取当前年月"""
    now = datetime.now()
    return now.year, now.month


def get_month_days(year, month):
    """获取某月天数"""
    if month == 12:
        return (datetime(year + 1, 1, 1) - datetime(year, month, 1)).days
    return (datetime(year, month + 1, 1) - datetime(year, month, 1)).days


def generate_order_no(prefix="PO"):
    """生成单号（含随机后缀避免并发碰撞）"""
    import random, string
    now = datetime.now()
    suffix = ''.join(random.choices(string.digits, k=3))
    return f"{prefix}{now.strftime('%Y%m%d%H%M%S')}{suffix}"
