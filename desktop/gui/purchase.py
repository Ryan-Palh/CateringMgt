# -*- coding: utf-8 -*-
"""
进销存管理模块 v5.0 —— 餐饮食材进销存台账
Tabs: 上月结存 / 进货台账 / 出库管理 / 供货商进货明细 / 供货商管理 / 产品数据
功能：食材原料管理、供应商管理、采购进货（含生产日期/保质期/用途）、出库领用、月度盘点
"""
import os, calendar, logging
from datetime import date, datetime, timedelta
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QDoubleSpinBox, QTabWidget,
                             QGroupBox, QSpinBox, QFrame, QGridLayout, QSizePolicy,
                             QInputDialog, QDialogButtonBox, QFileDialog, QDateEdit)
from gui.calendar_widget import ModernDateEdit, ModernMonthEdit
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QDoubleValidator
from database.db_manager import get_connection
from gui.theme import (DLG_STYLE, COLOR, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
                       make_table_button, primary_btn, success_btn, danger_btn,
                       TABLE_BTN_EDIT, TABLE_BTN_DELETE, TABLE_BTN_VIEW)
from utils.helpers import generate_order_no
from utils.app_context import get_app_context as _ctx
from utils.data_io import export_to_excel
from utils.validators import check_duplicate_supplier, check_duplicate_ingredient, get_low_stock_items
from utils.nutstore_sync import get_sync as _get_sync
from utils.logger import logger

_logger = logging.getLogger(__name__)

# ============================================================
# 云同步
# ============================================================
def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")

# ============================================================
# 数据库迁移：确保新增列存在
# ============================================================
def _ensure_columns():
    """迁移：确保新增列存在（表不存在时跳过，等 init_database 创建）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ingredients'")
    if not cursor.fetchone():
        conn.close()
        return
    cursor.execute("PRAGMA table_info(ingredients)")
    ing_cols = [c[1] for c in cursor.fetchall()]
    if 'expiry_months' not in ing_cols:
        cursor.execute("ALTER TABLE ingredients ADD COLUMN expiry_months INTEGER DEFAULT 0")
    if 'expiry_days' not in ing_cols:
        cursor.execute("ALTER TABLE ingredients ADD COLUMN expiry_days INTEGER DEFAULT 0")
    cursor.execute("PRAGMA table_info(purchase_items)")
    pi_cols = [c[1] for c in cursor.fetchall()]
    if 'production_date' not in pi_cols:
        cursor.execute("ALTER TABLE purchase_items ADD COLUMN production_date TEXT")
    if 'usage' not in pi_cols:
        cursor.execute("ALTER TABLE purchase_items ADD COLUMN usage TEXT")
    conn.commit()
    conn.close()

# ============================================================
# 保质期计算
# ============================================================
def _calc_expiry_info(production_date_str, expiry_months, expiry_days):
    """计算过期日期和剩余天数，返回 (expiry_date_str, remaining_days, status, is_expired)"""
    if not production_date_str:
        return ('', '', '', False)
    try:
        if '-' in production_date_str:
            pd = datetime.strptime(production_date_str, '%Y-%m-%d').date()
        else:
            pd = datetime.strptime(production_date_str, '%Y%m%d').date()
        from dateutil.relativedelta import relativedelta
        expiry = pd + relativedelta(months=expiry_months or 0, days=expiry_days or 0)
        remaining = (expiry - date.today()).days
        if remaining < 0:
            return (expiry.strftime('%Y-%m-%d'), str(remaining), '已过期', True)
        elif remaining <= 30:
            return (expiry.strftime('%Y-%m-%d'), str(remaining), '临近过期', False)
        else:
            return (expiry.strftime('%Y-%m-%d'), str(remaining), '正常', False)
    except Exception:
        return ('', '', '', False)

# ============================================================
# 对话框按钮样式
# ============================================================
def _dlg_save_style():
    return f"background: {COLOR['primary']}; color: #fff; border: none; border-radius: 4px; padding: 10px 36px; font-size: 13px; font-weight: bold;"

def _dlg_cancel_style():
    return f"background: {COLOR['text_primary']}; border: 1px solid {COLOR['border']}; border-radius: 4px; padding: 10px 36px; font-size: 13px;"


# ============================================================
# 进货退货对话框
# ============================================================
class ReturnPurchaseDialog(QDialog):
    """进货退货对话框：与新增进货界面一致，单号TH前缀，金额取负"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("进货退货")
        self.resize(860, 680)
        self.setMinimumSize(760, 600)
        self.setStyleSheet(DLG_STYLE)
        self.items = []
        self._syncing = False
        self._prod_date = ''
        self._build_ui()
        self._load_suppliers()
        self._load_ingredients()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("进货退货登记")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)
        self.cmb_supplier = QComboBox()
        self.cmb_supplier.setStyleSheet(COMBO_STYLE)
        self.cmb_supplier.setFixedHeight(38)
        form.addRow("供应商：", self.cmb_supplier)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("退货原因（必填）")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(38)
        form.addRow("退货原因：", self.txt_remark)
        layout.addLayout(form)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_add_item = QPushButton("+ 添加退货明细")
        btn_add_item.setStyleSheet(success_btn)
        btn_add_item.setFixedHeight(34)
        btn_add_item.clicked.connect(self._add_item)
        btn_bar.addWidget(btn_add_item)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["原料", "数量", "单位", "单价", "金额", "生产日期", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.lbl_total = QLabel("合计：¥ 0.00")
        self.lbl_total.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR['danger']};")
        self.lbl_total.setAlignment(Qt.AlignRight)
        layout.addWidget(self.lbl_total)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(_dlg_cancel_style())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存退货单")
        btn_save.setStyleSheet(_dlg_save_style())
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_suppliers(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM suppliers ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        self.cmb_supplier.clear()
        self._supplier_map = {}
        for r in rows:
            d = dict(r)
            self.cmb_supplier.addItem(d['name'])
            self._supplier_map[d['name']] = d['id']

    def _load_ingredients(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, unit, price FROM ingredients ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        self._ingredient_map = {}
        for r in rows:
            d = dict(r)
            self._ingredient_map[d['name']] = d

    def _add_item(self):
        if not self._ingredient_map:
            QMessageBox.warning(self, "提示", "请先在产品数据中添加原料")
            return
        names = list(self._ingredient_map.keys())
        name, ok = QInputDialog.getItem(self, "选择原料", "原料：", names, 0, False)
        if not ok or not name:
            return
        qty, ok = QInputDialog.getDouble(self, "数量", "数量：", 1, 0, 99999, 2)
        if not ok:
            return
        info = self._ingredient_map[name]
        price = info['price']
        amount = qty * price
        self.items.append({'ingredient_id': info['id'], 'name': name, 'quantity': qty,
                           'unit': info['unit'], 'unit_price': price, 'total_price': amount,
                           'production_date': '', 'usage': ''})
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.items))
        total = 0
        for i, item in enumerate(self.items):
            self.table.setItem(i, 0, QTableWidgetItem(item['name']))
            qty_item = QTableWidgetItem(str(item['quantity']))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, qty_item)
            self.table.setItem(i, 2, QTableWidgetItem(item['unit']))
            price_item = QTableWidgetItem(f"{item['unit_price']:.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, price_item)
            amount = -(item['total_price'])
            amt_item = QTableWidgetItem(f"{amount:.2f}")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 4, amt_item)
            total += amount
            self.table.setItem(i, 5, QTableWidgetItem(item.get('production_date', '')))
            btn_del = QPushButton("删除")
            btn_del.setStyleSheet(TABLE_BTN_DELETE)
            btn_del.clicked.connect(lambda checked, idx=i: self._del_item(idx))
            self.table.setCellWidget(i, 6, btn_del)
        self.lbl_total.setText(f"合计：¥ {total:.2f}")

    def _del_item(self, idx):
        self.items.pop(idx)
        self._refresh_table()

    def _save(self):
        if not self.items:
            QMessageBox.warning(self, "提示", "请添加退货明细")
            return
        supplier_name = self.cmb_supplier.currentText()
        if not supplier_name:
            QMessageBox.warning(self, "提示", "请选择供应商")
            return
        remark = self.txt_remark.text().strip()
        if not remark:
            QMessageBox.warning(self, "提示", "请填写退货原因")
            return
        supplier_id = self._supplier_map.get(supplier_name)
        total = sum(-item['total_price'] for item in self.items)
        purchase_no = generate_order_no("TH")
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""INSERT INTO purchases (purchase_no, supplier_id, total_amount, operator, purchase_date, remark)
                              VALUES (?,?,?,?,?,?)""",
                           (purchase_no, supplier_id, total, _ctx().current_user or '系统',
                            date.today().strftime('%Y-%m-%d'), remark))
            purchase_id = cursor.lastrowid
            for item in self.items:
                cursor.execute("""INSERT INTO purchase_items (purchase_id, ingredient_id, quantity, unit_price, total_price, production_date, usage)
                                  VALUES (?,?,?,?,?,?,?)""",
                               (purchase_id, item['ingredient_id'], -item['quantity'],
                                item['unit_price'], -item['total_price'],
                                item.get('production_date', ''), item.get('usage', '')))
                cursor.execute("UPDATE ingredients SET stock = stock - ? WHERE id = ?",
                               (item['quantity'], item['ingredient_id']))
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")


# ============================================================
# 新增进货对话框
# ============================================================
class PurchaseDialog(QDialog):
    """新增进货单——支持多项明细，每项含生产日期和用途"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增进货")
        self.resize(900, 720)
        self.setMinimumSize(800, 640)
        self.setStyleSheet(DLG_STYLE)
        self.items = []
        self._build_ui()
        self._load_suppliers()
        self._load_ingredients()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("新增进货单")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)
        self.cmb_supplier = QComboBox()
        self.cmb_supplier.setStyleSheet(COMBO_STYLE)
        self.cmb_supplier.setFixedHeight(38)
        form.addRow("供应商：", self.cmb_supplier)

        self.txt_operator = QLineEdit()
        self.txt_operator.setText(_ctx().current_user or '')
        self.txt_operator.setStyleSheet(INPUT_STYLE)
        self.txt_operator.setFixedHeight(38)
        form.addRow("经手人：", self.txt_operator)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注（可选）")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(38)
        form.addRow("备  注：", self.txt_remark)
        layout.addLayout(form)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_add_item = QPushButton("+ 添加明细")
        btn_add_item.setStyleSheet(success_btn)
        btn_add_item.setFixedHeight(34)
        btn_add_item.clicked.connect(self._add_item)
        btn_bar.addWidget(btn_add_item)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["原料", "数量", "单位", "单价", "金额", "生产日期", "用途", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.lbl_total = QLabel("合计：¥ 0.00")
        self.lbl_total.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR['primary']};")
        self.lbl_total.setAlignment(Qt.AlignRight)
        layout.addWidget(self.lbl_total)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(_dlg_cancel_style())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存进货单")
        btn_save.setStyleSheet(_dlg_save_style())
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_suppliers(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM suppliers ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        self.cmb_supplier.clear()
        self._supplier_map = {}
        for r in rows:
            d = dict(r)
            self.cmb_supplier.addItem(d['name'])
            self._supplier_map[d['name']] = d['id']

    def _load_ingredients(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, unit, price FROM ingredients ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        self._ingredient_map = {}
        for r in rows:
            d = dict(r)
            self._ingredient_map[d['name']] = d

    def _add_item(self):
        if not self._ingredient_map:
            QMessageBox.warning(self, "提示", "请先在产品数据中添加原料")
            return
        names = list(self._ingredient_map.keys())
        name, ok = QInputDialog.getItem(self, "选择原料", "原料：", names, 0, False)
        if not ok or not name:
            return
        qty, ok = QInputDialog.getDouble(self, "数量", "数量：", 1, 0, 99999, 2)
        if not ok:
            return
        info = self._ingredient_map[name]
        price = info['price']
        amount = qty * price
        pd_str, ok2 = QInputDialog.getText(self, "生产日期", "生产日期（YYYY-MM-DD，可选）：", text='')
        usage, ok3 = QInputDialog.getText(self, "用途", "用途（可选）：", text='')
        self.items.append({'ingredient_id': info['id'], 'name': name, 'quantity': qty,
                           'unit': info['unit'], 'unit_price': price, 'total_price': amount,
                           'production_date': pd_str if ok2 else '', 'usage': usage if ok3 else ''})
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.items))
        total = 0
        for i, item in enumerate(self.items):
            self.table.setItem(i, 0, QTableWidgetItem(item['name']))
            qty_item = QTableWidgetItem(str(item['quantity']))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, qty_item)
            self.table.setItem(i, 2, QTableWidgetItem(item['unit']))
            price_item = QTableWidgetItem(f"{item['unit_price']:.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, price_item)
            amt_item = QTableWidgetItem(f"{item['total_price']:.2f}")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 4, amt_item)
            total += item['total_price']
            self.table.setItem(i, 5, QTableWidgetItem(item.get('production_date', '')))
            self.table.setItem(i, 6, QTableWidgetItem(item.get('usage', '')))
            btn_del = QPushButton("删除")
            btn_del.setStyleSheet(TABLE_BTN_DELETE)
            btn_del.clicked.connect(lambda checked, idx=i: self._del_item(idx))
            self.table.setCellWidget(i, 7, btn_del)
        self.lbl_total.setText(f"合计：¥ {total:.2f}")

    def _del_item(self, idx):
        self.items.pop(idx)
        self._refresh_table()

    def _save(self):
        if not self.items:
            QMessageBox.warning(self, "提示", "请添加进货明细")
            return
        supplier_name = self.cmb_supplier.currentText()
        if not supplier_name:
            QMessageBox.warning(self, "提示", "请选择供应商")
            return
        supplier_id = self._supplier_map.get(supplier_name)
        total = sum(item['total_price'] for item in self.items)
        purchase_no = generate_order_no("CG")
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""INSERT INTO purchases (purchase_no, supplier_id, total_amount, operator, purchase_date, remark)
                              VALUES (?,?,?,?,?,?)""",
                           (purchase_no, supplier_id, total,
                            self.txt_operator.text().strip() or _ctx().current_user or '系统',
                            date.today().strftime('%Y-%m-%d'), self.txt_remark.text().strip()))
            purchase_id = cursor.lastrowid
            for item in self.items:
                cursor.execute("""INSERT INTO purchase_items (purchase_id, ingredient_id, quantity, unit_price, total_price, production_date, usage)
                                  VALUES (?,?,?,?,?,?,?)""",
                               (purchase_id, item['ingredient_id'], item['quantity'],
                                item['unit_price'], item['total_price'],
                                item.get('production_date', ''), item.get('usage', '')))
                cursor.execute("UPDATE ingredients SET stock = stock + ? WHERE id = ?",
                               (item['quantity'], item['ingredient_id']))
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")


# ============================================================
# 出库管理对话框
# ============================================================
class StockOutDialog(QDialog):
    """产品出库登记"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("出库登记")
        self.resize(700, 560)
        self.setMinimumSize(640, 500)
        self.setStyleSheet(DLG_STYLE)
        self.items = []
        self._build_ui()
        self._load_ingredients()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("出库登记")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)
        self.txt_operator = QLineEdit()
        self.txt_operator.setText(_ctx().current_user or '')
        self.txt_operator.setStyleSheet(INPUT_STYLE)
        self.txt_operator.setFixedHeight(38)
        form.addRow("领用人：", self.txt_operator)

        self.txt_usage = QLineEdit()
        self.txt_usage.setPlaceholderText("用途（如：厨房备料、员工餐等）")
        self.txt_usage.setStyleSheet(INPUT_STYLE)
        self.txt_usage.setFixedHeight(38)
        form.addRow("用  途：", self.txt_usage)
        layout.addLayout(form)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_add_item = QPushButton("+ 添加出库明细")
        btn_add_item.setStyleSheet(success_btn)
        btn_add_item.setFixedHeight(34)
        btn_add_item.clicked.connect(self._add_item)
        btn_bar.addWidget(btn_add_item)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["原料", "数量", "单位", "当前库存", "用途", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(_dlg_cancel_style())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("确认出库")
        btn_save.setStyleSheet(_dlg_save_style())
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_ingredients(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, unit, stock FROM ingredients WHERE stock > 0 ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        self._ingredient_map = {}
        for r in rows:
            d = dict(r)
            self._ingredient_map[d['name']] = d

    def _add_item(self):
        if not self._ingredient_map:
            QMessageBox.warning(self, "提示", "没有可出库的原料（库存为0）")
            return
        names = list(self._ingredient_map.keys())
        name, ok = QInputDialog.getItem(self, "选择原料", "原料：", names, 0, False)
        if not ok or not name:
            return
        info = self._ingredient_map[name]
        max_qty = info['stock']
        qty, ok = QInputDialog.getDouble(self, "数量", f"数量（最大库存：{max_qty}）：", 1, 0.01, max_qty, 2)
        if not ok:
            return
        self.items.append({'ingredient_id': info['id'], 'name': name, 'quantity': qty,
                           'unit': info['unit'], 'stock': info['stock']})
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.items))
        for i, item in enumerate(self.items):
            self.table.setItem(i, 0, QTableWidgetItem(item['name']))
            qty_item = QTableWidgetItem(str(item['quantity']))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, qty_item)
            self.table.setItem(i, 2, QTableWidgetItem(item['unit']))
            stock_item = QTableWidgetItem(str(item['stock']))
            stock_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, stock_item)
            self.table.setItem(i, 4, QTableWidgetItem(''))
            btn_del = QPushButton("删除")
            btn_del.setStyleSheet(TABLE_BTN_DELETE)
            btn_del.clicked.connect(lambda checked, idx=i: self._del_item(idx))
            self.table.setCellWidget(i, 5, btn_del)

    def _del_item(self, idx):
        self.items.pop(idx)
        self._refresh_table()

    def _save(self):
        if not self.items:
            QMessageBox.warning(self, "提示", "请添加出库明细")
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            for item in self.items:
                cursor.execute("UPDATE ingredients SET stock = stock - ? WHERE id = ? AND stock >= ?",
                               (item['quantity'], item['ingredient_id'], item['quantity']))
                if cursor.rowcount == 0:
                    conn.rollback()
                    conn.close()
                    QMessageBox.warning(self, "提示", f"原料\"{item['name']}\"库存不足")
                    return
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"出库失败：{e}")


# ============================================================
# 出库记录查看对话框
# ============================================================
class StockOutRecordDialog(QDialog):
    """查看产品出库记录，支持删除单条出库单"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("出库记录")
        self.resize(960, 600)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("出库记录")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["序号", "单号", "原料", "数量", "单价", "金额", "日期", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet(primary_btn)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)
        self.setLayout(layout)

    def _load_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT p.purchase_no, pi.ingredient_id, pi.quantity, pi.unit_price, pi.total_price,
                                 p.purchase_date, p.id, ing.name
                          FROM purchase_items pi
                          JOIN purchases p ON pi.purchase_id = p.id
                          JOIN ingredients ing ON pi.ingredient_id = ing.id
                          WHERE pi.quantity < 0
                          ORDER BY p.id DESC""")
        rows = cursor.fetchall()
        conn.close()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(d['purchase_no']))
            self.table.setItem(i, 2, QTableWidgetItem(d['name']))
            self.table.setItem(i, 3, QTableWidgetItem(str(abs(d['quantity']))))
            self.table.setItem(i, 4, QTableWidgetItem(f"{d['unit_price']:.2f}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{abs(d['total_price']):.2f}"))
            self.table.setItem(i, 6, QTableWidgetItem(d['purchase_date'] or ''))
            btn_del = QPushButton("删除")
            btn_del.setStyleSheet(TABLE_BTN_DELETE)
            btn_del.clicked.connect(lambda checked, pid=d['id']: self._delete(pid))
            self.table.setCellWidget(i, 7, btn_del)

    def _delete(self, purchase_id):
        reply = QMessageBox.question(self, "确认", "确定要删除这条出库记录吗？此操作不可恢复。")
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
            conn.commit()
            _sync_cloud()
            self._load_data()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"删除失败：{e}")


# ============================================================
# 供应商管理对话框
# ============================================================
class SupplierDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("编辑供应商" if data else "新增供应商")
        self.resize(520, 480)
        self.setMinimumSize(460, 420)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()
        if data:
            self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("编辑供应商" if self.data else "新增供应商")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("供应商名称（必填）")
        self.txt_name.setStyleSheet(INPUT_STYLE)
        self.txt_name.setFixedHeight(38)
        form.addRow("名称 *：", self.txt_name)

        self.txt_contact = QLineEdit()
        self.txt_contact.setPlaceholderText("联系人")
        self.txt_contact.setStyleSheet(INPUT_STYLE)
        self.txt_contact.setFixedHeight(38)
        form.addRow("联系人：", self.txt_contact)

        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("联系电话")
        self.txt_phone.setStyleSheet(INPUT_STYLE)
        self.txt_phone.setFixedHeight(38)
        form.addRow("电  话：", self.txt_phone)

        self.txt_address = QLineEdit()
        self.txt_address.setPlaceholderText("地址")
        self.txt_address.setStyleSheet(INPUT_STYLE)
        self.txt_address.setFixedHeight(38)
        form.addRow("地  址：", self.txt_address)

        self.txt_payment = QLineEdit()
        self.txt_payment.setPlaceholderText("结算方式（如：月结、现结）")
        self.txt_payment.setStyleSheet(INPUT_STYLE)
        self.txt_payment.setFixedHeight(38)
        form.addRow("结算方式：", self.txt_payment)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(38)
        form.addRow("备  注：", self.txt_remark)

        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(_dlg_cancel_style())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(_dlg_save_style())
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_data(self):
        self.txt_name.setText(self.data['name'])
        self.txt_contact.setText(self.data.get('contact', '') or '')
        self.txt_phone.setText(self.data.get('phone', '') or '')
        self.txt_address.setText(self.data.get('address', '') or '')
        self.txt_payment.setText(self.data.get('payment_method', '') or '')
        self.txt_remark.setText(self.data.get('remark', '') or '')

    def _save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入供应商名称")
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            if self.data:
                cursor.execute("""UPDATE suppliers SET name=?,contact=?,phone=?,address=?,payment_method=?,remark=?
                                  WHERE id=?""",
                               (name, self.txt_contact.text(), self.txt_phone.text(),
                                self.txt_address.text(), self.txt_payment.text(),
                                self.txt_remark.text(), self.data['id']))
            else:
                cursor.execute("""INSERT INTO suppliers (name,contact,phone,address,payment_method,remark)
                                  VALUES (?,?,?,?,?,?)""",
                               (name, self.txt_contact.text(), self.txt_phone.text(),
                                self.txt_address.text(), self.txt_payment.text(),
                                self.txt_remark.text()))
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")


# ============================================================
# 产品数据（原料）管理对话框
# ============================================================
class IngredientDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("编辑原料" if data else "新增原料")
        self.resize(560, 640)
        self.setMinimumSize(500, 580)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()
        if data:
            self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("编辑原料" if self.data else "新增原料")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("原料名称（必填）")
        self.txt_name.setStyleSheet(INPUT_STYLE)
        self.txt_name.setFixedHeight(36)
        form.addRow("名称 *：", self.txt_name)

        self.txt_category = QLineEdit()
        self.txt_category.setPlaceholderText("如：蔬菜、肉类、调料、粮油")
        self.txt_category.setStyleSheet(INPUT_STYLE)
        self.txt_category.setFixedHeight(36)
        form.addRow("分  类：", self.txt_category)

        self.txt_unit = QLineEdit()
        self.txt_unit.setText("斤")
        self.txt_unit.setStyleSheet(INPUT_STYLE)
        self.txt_unit.setFixedHeight(36)
        form.addRow("单  位：", self.txt_unit)

        self.sp_price = QDoubleSpinBox()
        self.sp_price.setRange(0, 99999)
        self.sp_price.setDecimals(2)
        self.sp_price.setPrefix("¥ ")
        self.sp_price.setFixedHeight(36)
        form.addRow("参考单价：", self.sp_price)

        self.sp_min_stock = QDoubleSpinBox()
        self.sp_min_stock.setRange(0, 99999)
        self.sp_min_stock.setDecimals(1)
        self.sp_min_stock.setFixedHeight(36)
        form.addRow("最低库存：", self.sp_min_stock)

        self.sp_expiry_months = QSpinBox()
        self.sp_expiry_months.setRange(0, 120)
        self.sp_expiry_months.setSuffix(" 月")
        self.sp_expiry_months.setFixedHeight(36)
        form.addRow("保质期(月)：", self.sp_expiry_months)

        self.sp_expiry_days = QSpinBox()
        self.sp_expiry_days.setRange(0, 365)
        self.sp_expiry_days.setSuffix(" 天")
        self.sp_expiry_days.setFixedHeight(36)
        form.addRow("保质期(天)：", self.sp_expiry_days)

        self.txt_brand = QLineEdit()
        self.txt_brand.setPlaceholderText("品牌")
        self.txt_brand.setStyleSheet(INPUT_STYLE)
        self.txt_brand.setFixedHeight(36)
        form.addRow("品  牌：", self.txt_brand)

        self.txt_spec = QLineEdit()
        self.txt_spec.setPlaceholderText("规格")
        self.txt_spec.setStyleSheet(INPUT_STYLE)
        self.txt_spec.setFixedHeight(36)
        form.addRow("规  格：", self.txt_spec)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注")
        self.txt_remark.setStyleSheet(INPUT_STYLE)
        self.txt_remark.setFixedHeight(36)
        form.addRow("备  注：", self.txt_remark)

        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(_dlg_cancel_style())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(_dlg_save_style())
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_data(self):
        self.txt_name.setText(self.data['name'])
        self.txt_category.setText(self.data.get('category', '') or '')
        self.txt_unit.setText(self.data.get('unit', '斤') or '斤')
        self.sp_price.setValue(self.data.get('price', 0) or 0)
        self.sp_min_stock.setValue(self.data.get('min_stock', 0) or 0)
        self.sp_expiry_months.setValue(self.data.get('expiry_months', 0) or 0)
        self.sp_expiry_days.setValue(self.data.get('expiry_days', 0) or 0)
        self.txt_brand.setText(self.data.get('brand', '') or '')
        self.txt_spec.setText(self.data.get('spec', '') or '')
        self.txt_remark.setText(self.data.get('remark', '') or '')

    def _save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入原料名称")
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            if self.data:
                cursor.execute("""UPDATE ingredients SET name=?,category=?,unit=?,price=?,min_stock=?,
                                  expiry_months=?,expiry_days=?,brand=?,spec=?,remark=? WHERE id=?""",
                               (name, self.txt_category.text(), self.txt_unit.text(),
                                self.sp_price.value(), self.sp_min_stock.value(),
                                self.sp_expiry_months.value(), self.sp_expiry_days.value(),
                                self.txt_brand.text(), self.txt_spec.text(),
                                self.txt_remark.text(), self.data['id']))
            else:
                cursor.execute("""INSERT INTO ingredients (name,category,unit,price,min_stock,
                                  expiry_months,expiry_days,brand,spec,remark)
                                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
                               (name, self.txt_category.text(), self.txt_unit.text(),
                                self.sp_price.value(), self.sp_min_stock.value(),
                                self.sp_expiry_months.value(), self.sp_expiry_days.value(),
                                self.txt_brand.text(), self.txt_spec.text(),
                                self.txt_remark.text()))
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")


# ============================================================
# 进销存管理主界面
# ============================================================
class PurchaseWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        _ensure_columns()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"QTabWidget::pane {{ border: none; }}")

        self.tab_inventory = QWidget()
        self._build_inventory_tab()
        self.tabs.addTab(self.tab_inventory, "上月结存")

        self.tab_purchase = QWidget()
        self._build_purchase_tab()
        self.tabs.addTab(self.tab_purchase, "进货台账")

        self.tab_stock_out = QWidget()
        self._build_stock_out_tab()
        self.tabs.addTab(self.tab_stock_out, "出库管理")

        self.tab_supplier_detail = QWidget()
        self._build_supplier_detail_tab()
        self.tabs.addTab(self.tab_supplier_detail, "供货商进货明细")

        self.tab_supplier = QWidget()
        self._build_supplier_tab()
        self.tabs.addTab(self.tab_supplier, "供货商管理")

        self.tab_ingredient = QWidget()
        self._build_ingredient_tab()
        self.tabs.addTab(self.tab_ingredient, "产品数据")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self._loaded_tabs = {0: True}
        self._load_inventory()
        self._load_purchase()

    def _on_tab_changed(self, index):
        if index in self._loaded_tabs:
            return
        loaders = {0: self._load_inventory, 1: self._load_purchase, 2: self._load_stock_out,
                   3: self._load_supplier_detail, 4: self._load_supplier, 5: self._load_ingredient}
        if index in loaders:
            loaders[index]()
            self._loaded_tabs[index] = True

    # ========== 上月结存 ==========
    def _build_inventory_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.inv_month = ModernMonthEdit()
        self.inv_month.setFixedWidth(180)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("结存月份："))
        toolbar.addWidget(self.inv_month)
        toolbar.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_inventory)
        toolbar.addWidget(btn_refresh)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.inv_table, "库存结存"))
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.inv_table = QTableWidget()
        self.inv_table.setColumnCount(8)
        self.inv_table.setHorizontalHeaderLabels(["序号", "原料", "分类", "单位", "期初库存", "本月入库", "本月出库", "期末库存"])
        self.inv_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.inv_table.setStyleSheet(TABLE_STYLE)
        self.inv_table.verticalHeader().setVisible(False)
        self.inv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.inv_table)
        self.tab_inventory.setLayout(layout)

    def _load_inventory(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, category, unit, stock FROM ingredients ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        self.inv_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.inv_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.inv_table.setItem(i, 1, QTableWidgetItem(d['name']))
            self.inv_table.setItem(i, 2, QTableWidgetItem(d.get('category', '') or ''))
            self.inv_table.setItem(i, 3, QTableWidgetItem(d.get('unit', '') or ''))
            self.inv_table.setItem(i, 4, QTableWidgetItem(f"{d['stock']:.1f}"))
            self.inv_table.setItem(i, 5, QTableWidgetItem(''))
            self.inv_table.setItem(i, 6, QTableWidgetItem(''))
            self.inv_table.setItem(i, 7, QTableWidgetItem(f"{d['stock']:.1f}"))

    # ========== 进货台账 ==========
    def _build_purchase_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        btn_purchase = QPushButton("+ 新增进货")
        btn_purchase.setStyleSheet(primary_btn)
        btn_purchase.clicked.connect(self._add_purchase)
        toolbar.addWidget(btn_purchase)
        btn_return = QPushButton("+ 进货退货")
        btn_return.setStyleSheet(danger_btn)
        btn_return.clicked.connect(self._add_return)
        toolbar.addWidget(btn_return)
        toolbar.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_purchase)
        toolbar.addWidget(btn_refresh)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.pur_table, "进货台账"))
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.pur_table = QTableWidget()
        self.pur_table.setColumnCount(10)
        self.pur_table.setHorizontalHeaderLabels(["序号", "单号", "供应商", "金额", "日期", "经手人", "类型", "备注", "操作"])
        self.pur_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pur_table.setStyleSheet(TABLE_STYLE)
        self.pur_table.verticalHeader().setVisible(False)
        self.pur_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.pur_table)
        self.tab_purchase.setLayout(layout)

    def _load_purchase(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT p.id, p.purchase_no, s.name as supplier_name, p.total_amount,
                                 p.purchase_date, p.operator, p.remark,
                                 CASE WHEN p.purchase_no LIKE 'TH%' THEN '退货' ELSE '进货' END as type
                          FROM purchases p
                          LEFT JOIN suppliers s ON p.supplier_id = s.id
                          ORDER BY p.id DESC""")
        rows = cursor.fetchall()
        conn.close()
        self.pur_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.pur_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.pur_table.setItem(i, 1, QTableWidgetItem(d['purchase_no']))
            self.pur_table.setItem(i, 2, QTableWidgetItem(d['supplier_name'] or ''))
            amt = d['total_amount'] or 0
            amt_item = QTableWidgetItem(f"{amt:.2f}")
            amt_item.setForeground(QColor(COLOR['danger'] if amt < 0 else COLOR['primary']))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.pur_table.setItem(i, 3, amt_item)
            self.pur_table.setItem(i, 4, QTableWidgetItem(d['purchase_date'] or ''))
            self.pur_table.setItem(i, 5, QTableWidgetItem(d['operator'] or ''))
            self.pur_table.setItem(i, 6, QTableWidgetItem(d['type']))
            self.pur_table.setItem(i, 7, QTableWidgetItem(d['remark'] or ''))
            btn_view = QPushButton("查看")
            btn_view.setStyleSheet(TABLE_BTN_VIEW)
            btn_view.clicked.connect(lambda checked, pid=d['id']: self._view_purchase(pid))
            self.pur_table.setCellWidget(i, 8, btn_view)

    def _add_purchase(self):
        dlg = PurchaseDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._load_purchase()
            self._load_inventory()

    def _add_return(self):
        dlg = ReturnPurchaseDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._load_purchase()

    def _view_purchase(self, purchase_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT pi.*, ing.name as ingredient_name, ing.unit
                          FROM purchase_items pi
                          JOIN ingredients ing ON pi.ingredient_id = ing.id
                          WHERE pi.purchase_id = ?""", (purchase_id,))
        items = cursor.fetchall()
        conn.close()
        msg = "\n".join(f"  • {dict(it)['ingredient_name']} × {abs(dict(it)['quantity'])} {dict(it)['unit']} = ¥{abs(dict(it)['total_price']):.2f}"
                        for it in items)
        QMessageBox.information(self, "进货明细", f"明细：\n{msg}" if msg else "无明细")

    # ========== 出库管理 ==========
    def _build_stock_out_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        btn_out = QPushButton("+ 出库登记")
        btn_out.setStyleSheet(primary_btn)
        btn_out.clicked.connect(self._add_stock_out)
        toolbar.addWidget(btn_out)
        btn_records = QPushButton("出库记录")
        btn_records.setStyleSheet(success_btn)
        btn_records.clicked.connect(self._show_stock_out_records)
        toolbar.addWidget(btn_records)
        toolbar.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_stock_out)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self.so_table = QTableWidget()
        self.so_table.setColumnCount(8)
        self.so_table.setHorizontalHeaderLabels(["序号", "原料", "库存", "单位", "分类", "最低库存", "保质期", "状态"])
        self.so_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.so_table.setStyleSheet(TABLE_STYLE)
        self.so_table.verticalHeader().setVisible(False)
        self.so_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.so_table)
        self.tab_stock_out.setLayout(layout)

    def _load_stock_out(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT id, name, stock, unit, category, min_stock, expiry_months, expiry_days
                          FROM ingredients ORDER BY name""")
        rows = cursor.fetchall()
        conn.close()
        self.so_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.so_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.so_table.setItem(i, 1, QTableWidgetItem(d['name']))
            stock_item = QTableWidgetItem(f"{d['stock']:.1f}")
            if d['stock'] <= d['min_stock']:
                stock_item.setForeground(QColor(COLOR['danger']))
            stock_item.setTextAlignment(Qt.AlignCenter)
            self.so_table.setItem(i, 2, stock_item)
            self.so_table.setItem(i, 3, QTableWidgetItem(d['unit']))
            self.so_table.setItem(i, 4, QTableWidgetItem(d.get('category', '') or ''))
            self.so_table.setItem(i, 5, QTableWidgetItem(f"{d['min_stock']:.1f}"))
            expiry = f"{d['expiry_months'] or 0}月{d['expiry_days'] or 0}天"
            self.so_table.setItem(i, 6, QTableWidgetItem(expiry))
            status = "库存不足" if d['stock'] <= d['min_stock'] else "正常"
            self.so_table.setItem(i, 7, QTableWidgetItem(status))

    def _add_stock_out(self):
        dlg = StockOutDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._load_stock_out()
            self._load_inventory()

    def _show_stock_out_records(self):
        dlg = StockOutRecordDialog(self)
        dlg.exec_()

    # ========== 供货商进货明细 ==========
    def _build_supplier_detail_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("供应商："))
        self.sd_supplier = QComboBox()
        self.sd_supplier.setStyleSheet(COMBO_STYLE)
        self.sd_supplier.setFixedWidth(200)
        toolbar.addWidget(self.sd_supplier)
        toolbar.addStretch()
        btn_refresh = QPushButton("查询")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_supplier_detail)
        toolbar.addWidget(btn_refresh)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.sd_table, "供货商进货明细"))
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.sd_table = QTableWidget()
        self.sd_table.setColumnCount(9)
        self.sd_table.setHorizontalHeaderLabels(["序号", "单号", "原料", "数量", "单价", "金额", "日期", "类型", "备注"])
        self.sd_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sd_table.setStyleSheet(TABLE_STYLE)
        self.sd_table.verticalHeader().setVisible(False)
        self.sd_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.sd_table)
        self.tab_supplier_detail.setLayout(layout)

    def _load_supplier_detail(self):
        supplier_name = self.sd_supplier.currentText()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM suppliers ORDER BY name")
        suppliers = cursor.fetchall()
        self.sd_supplier.blockSignals(True)
        current = self.sd_supplier.currentText()
        self.sd_supplier.clear()
        self._sd_map = {}
        for s in suppliers:
            d = dict(s)
            self.sd_supplier.addItem(d['name'])
            self._sd_map[d['name']] = d['id']
        if current:
            idx = self.sd_supplier.findText(current)
            if idx >= 0:
                self.sd_supplier.setCurrentIndex(idx)
        self.sd_supplier.blockSignals(False)

        sid = self._sd_map.get(supplier_name)
        if not sid:
            conn.close()
            return
        cursor.execute("""SELECT p.id, p.purchase_no, p.total_amount, p.purchase_date, p.remark,
                                 CASE WHEN p.purchase_no LIKE 'TH%' THEN '退货' ELSE '进货' END as type,
                                 pi.quantity, pi.unit_price, pi.total_price, ing.name as ingredient_name
                          FROM purchases p
                          JOIN purchase_items pi ON p.id = pi.purchase_id
                          JOIN ingredients ing ON pi.ingredient_id = ing.id
                          WHERE p.supplier_id = ?
                          ORDER BY p.id DESC""", (sid,))
        rows = cursor.fetchall()
        conn.close()
        self.sd_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.sd_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.sd_table.setItem(i, 1, QTableWidgetItem(d['purchase_no']))
            self.sd_table.setItem(i, 2, QTableWidgetItem(d['ingredient_name']))
            self.sd_table.setItem(i, 3, QTableWidgetItem(str(abs(d['quantity']))))
            self.sd_table.setItem(i, 4, QTableWidgetItem(f"{d['unit_price']:.2f}"))
            self.sd_table.setItem(i, 5, QTableWidgetItem(f"{abs(d['total_price']):.2f}"))
            self.sd_table.setItem(i, 6, QTableWidgetItem(d['purchase_date'] or ''))
            self.sd_table.setItem(i, 7, QTableWidgetItem(d['type']))
            self.sd_table.setItem(i, 8, QTableWidgetItem(d['remark'] or ''))

    # ========== 供货商管理 ==========
    def _build_supplier_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ 新增供应商")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_supplier)
        toolbar.addWidget(btn_add)
        toolbar.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_supplier)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self.sp_table = QTableWidget()
        self.sp_table.setColumnCount(8)
        self.sp_table.setHorizontalHeaderLabels(["序号", "名称", "联系人", "电话", "地址", "结算方式", "备注", "操作"])
        self.sp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sp_table.setStyleSheet(TABLE_STYLE)
        self.sp_table.verticalHeader().setVisible(False)
        self.sp_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.sp_table)
        self.tab_supplier.setLayout(layout)

    def _load_supplier(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM suppliers ORDER BY id")
        rows = cursor.fetchall()
        conn.close()
        self.sp_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.sp_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.sp_table.setItem(i, 1, QTableWidgetItem(d['name']))
            self.sp_table.setItem(i, 2, QTableWidgetItem(d.get('contact', '') or ''))
            self.sp_table.setItem(i, 3, QTableWidgetItem(d.get('phone', '') or ''))
            self.sp_table.setItem(i, 4, QTableWidgetItem(d.get('address', '') or ''))
            self.sp_table.setItem(i, 5, QTableWidgetItem(d.get('payment_method', '') or ''))
            self.sp_table.setItem(i, 6, QTableWidgetItem(d.get('remark', '') or ''))
            btn_edit = QPushButton("编辑")
            btn_edit.setStyleSheet(TABLE_BTN_EDIT)
            btn_edit.clicked.connect(lambda checked, rd=d: self._edit_supplier(rd))
            self.sp_table.setCellWidget(i, 7, btn_edit)

    def _add_supplier(self):
        dlg = SupplierDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._load_supplier()
            self._load_supplier_detail()

    def _edit_supplier(self, data):
        dlg = SupplierDialog(self, data)
        if dlg.exec_() == QDialog.Accepted:
            self._load_supplier()
            self._load_supplier_detail()

    # ========== 产品数据 ==========
    def _build_ingredient_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ 新增原料")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_ingredient)
        toolbar.addWidget(btn_add)
        toolbar.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_ingredient)
        toolbar.addWidget(btn_refresh)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.ing_table, "产品数据"))
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.ing_table = QTableWidget()
        self.ing_table.setColumnCount(9)
        self.ing_table.setHorizontalHeaderLabels(["序号", "名称", "分类", "单位", "参考单价", "库存", "最低库存", "保质期", "操作"])
        self.ing_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ing_table.setStyleSheet(TABLE_STYLE)
        self.ing_table.verticalHeader().setVisible(False)
        self.ing_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.ing_table)
        self.tab_ingredient.setLayout(layout)

    def _load_ingredient(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ingredients ORDER BY id")
        rows = cursor.fetchall()
        conn.close()
        self.ing_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.ing_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.ing_table.setItem(i, 1, QTableWidgetItem(d['name']))
            self.ing_table.setItem(i, 2, QTableWidgetItem(d.get('category', '') or ''))
            self.ing_table.setItem(i, 3, QTableWidgetItem(d.get('unit', '') or ''))
            self.ing_table.setItem(i, 4, QTableWidgetItem(f"{d.get('price', 0) or 0:.2f}"))
            stock = d.get('stock', 0) or 0
            stock_item = QTableWidgetItem(f"{stock:.1f}")
            if stock <= (d.get('min_stock', 0) or 0):
                stock_item.setForeground(QColor(COLOR['danger']))
            stock_item.setTextAlignment(Qt.AlignCenter)
            self.ing_table.setItem(i, 5, stock_item)
            self.ing_table.setItem(i, 6, QTableWidgetItem(f"{d.get('min_stock', 0) or 0:.1f}"))
            expiry = f"{d.get('expiry_months', 0) or 0}月{d.get('expiry_days', 0) or 0}天"
            self.ing_table.setItem(i, 7, QTableWidgetItem(expiry))
            btn_edit = QPushButton("编辑")
            btn_edit.setStyleSheet(TABLE_BTN_EDIT)
            btn_edit.clicked.connect(lambda checked, rd=d: self._edit_ingredient(rd))
            self.ing_table.setCellWidget(i, 8, btn_edit)

    def _add_ingredient(self):
        dlg = IngredientDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._load_ingredient()
            self._load_inventory()

    def _edit_ingredient(self, data):
        dlg = IngredientDialog(self, data)
        if dlg.exec_() == QDialog.Accepted:
            self._load_ingredient()
            self._load_inventory()

    def _export_table(self, table, name):
        path, _ = QFileDialog.getSaveFileName(self, "导出", f"{name}_{date.today().strftime('%Y%m%d')}.xlsx",
                                               "Excel (*.xlsx)")
        if path:
            export_to_excel(table, path)
            QMessageBox.information(self, "提示", f"已导出到：{path}")