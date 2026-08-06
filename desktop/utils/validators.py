# -*- coding: utf-8 -*-
"""
冲突检测与数据校验工具
在写入数据库前进行业务逻辑层面的冲突检查
"""
from database.db_manager import get_connection

def check_duplicate_employee(name, phone, exclude_id=None):
    """检查员工姓名+手机号是否重复
    
    Returns:
        (bool, str): (是否通过, 错误消息)
    """
    conn = get_connection()
    cursor = conn.cursor()
    if exclude_id:
        if phone:
            cursor.execute(
                "SELECT id FROM employees WHERE name=? AND phone=? AND id!=?",
                (name, phone, exclude_id)
            )
        else:
            cursor.execute(
                "SELECT id FROM employees WHERE name=? AND (phone IS NULL OR phone = '') AND id!=?",
                (name, exclude_id)
            )
    else:
        if phone:
            cursor.execute(
                "SELECT id FROM employees WHERE name=? AND phone=?",
                (name, phone)
            )
        else:
            cursor.execute(
                "SELECT id FROM employees WHERE name=? AND (phone IS NULL OR phone = '')",
                (name,)
            )
    row = cursor.fetchone()
    conn.close()
    if row:
        return False, f"已存在同名员工「{name}」" + (f"，手机号 {phone} 重复" if phone else "")
    return True, ""

def check_duplicate_revenue_date(date_str, exclude_id=None, store_id=None):
    """[已废弃] 检查营业额日期是否重复
    
    daily_revenue 表已移除 UNIQUE 约束，支持同一天多条明细。
    此函数保留仅用于向后兼容，始终返回 (True, "")。
    
    Returns:
        (bool, str)
    """
    import warnings
    warnings.warn("check_duplicate_revenue_date is deprecated", DeprecationWarning, stacklevel=2)
    return True, ""

def check_duplicate_store_name(name, exclude_id=None):
    """检查门店名称是否重复
    
    Returns:
        (bool, str)
    """
    conn = get_connection()
    cursor = conn.cursor()
    if exclude_id:
        cursor.execute("SELECT id FROM stores WHERE name=? AND id!=?", (name, exclude_id))
    else:
        cursor.execute("SELECT id FROM stores WHERE name=?", (name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return False, f"门店名称「{name}」已存在"
    return True, ""

def check_duplicate_supplier(name, exclude_id=None, store_id=None):
    """检查供应商名称是否重复（支持门店隔离）
    
    Returns:
        (bool, str)
    """
    conn = get_connection()
    cursor = conn.cursor()
    if exclude_id:
        if store_id:
            cursor.execute("SELECT id FROM suppliers WHERE name=? AND id!=? AND (store_id=? OR store_id IS NULL)", (name, exclude_id, store_id))
        else:
            cursor.execute("SELECT id FROM suppliers WHERE name=? AND id!=?", (name, exclude_id))
    else:
        if store_id:
            cursor.execute("SELECT id FROM suppliers WHERE name=? AND (store_id=? OR store_id IS NULL)", (name, store_id))
        else:
            cursor.execute("SELECT id FROM suppliers WHERE name=?", (name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return False, f"供应商「{name}」已存在"
    return True, ""

def check_duplicate_ingredient(name, exclude_id=None, store_id=None):
    """检查食材名称是否重复
    
    Returns:
        (bool, str)
    """
    conn = get_connection()
    cursor = conn.cursor()
    if exclude_id:
        cursor.execute("SELECT id FROM ingredients WHERE name=? AND id!=?", (name, exclude_id))
    else:
        cursor.execute("SELECT id FROM ingredients WHERE name=?", (name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return False, f"食材「{name}」已存在"
    return True, ""

def check_stock_available(ingredient_id, quantity):
    """检查库存是否足够出库
    
    Returns:
        (bool, str, current_stock): (是否通过, 错误消息, 当前库存)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, stock FROM ingredients WHERE id=?", (ingredient_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False, "食材不存在", 0
    d = dict(row)
    if d["stock"] < quantity:
        return False, f"{d['name']} 库存不足！当前: {d['stock']:.1f}，需要: {quantity:.1f}", d["stock"]
    return True, "", d["stock"]

def get_low_stock_items(store_id=None):
    """获取库存不足的食材列表
    
    Returns:
        list[dict]: [{name, stock, min_stock, unit, category}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()
    if store_id:
        cursor.execute(
            """SELECT name, stock, min_stock, unit, category FROM ingredients
               WHERE min_stock > 0 AND stock <= min_stock
               AND (store_id=? OR store_id IS NULL)
               ORDER BY (min_stock - stock) DESC""",
            (store_id,)
        )
    else:
        cursor.execute(
            """SELECT name, stock, min_stock, unit, category FROM ingredients
               WHERE min_stock > 0 AND stock <= min_stock
               ORDER BY (min_stock - stock) DESC"""
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
