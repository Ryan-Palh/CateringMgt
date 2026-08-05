# -*- coding: utf-8 -*-
"""
进销存管理模块 v5.0 —— 餐饮食材进销存台账
Tabs: 上月结存 / 进货台账 / 出库管理 / 供货商进货明细 / 供货商管理 / 产品数据
功能：食材原料管理、供应商管理、采购进货（含生产日期/保质期/用途）、出库领用、月度盘点
"""
import os
import calendar
import logging
from datetime import date, datetime, timedelta

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QDoubleSpinBox,
                             QTabWidget, QGroupBox, QSpinBox, QFrame,
                             QGridLayout, QSizePolicy, QInputDialog,
                             QDialogButtonBox, QFileDialog, QDateEdit)
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
from utils.validators import (check_duplicate_supplier, check_duplicate_ingredient,
                               get_low_stock_items)
from utils.nutstore_sync import get_sync as _get_sync

_logger = logging.getLogger(__name__)


def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        _logger.debug(f"云同步失败: {e}")


def _ensure_columns():
    """迁移：确保新增列存在（表不存在时跳过，等 init_database 创建）"""
    conn = get_connection()
    cursor = conn.cursor()
    # 检查表是否存在，不存在则跳过（init_database 会创建完整表结构）
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ingredients'")
    if not cursor.fetchone():
            conn.close()
            return
    cursor.execute("PRAGMA table_info(ingredients)")
    ing_cols = [c[1] for c in cursor.fetchall()]
    if "expiry_months" not in ing_cols:
        cursor.execute("ALTER TABLE ingredients ADD COLUMN expiry_months INTEGER DEFAULT 0")
    if "expiry_days" not in ing_cols:
        cursor.execute("ALTER TABLE ingredients ADD COLUMN expiry_days INTEGER DEFAULT 0")
    cursor.execute("PRAGMA table_info(purchase_items)")
    pi_cols = [c[1] for c in cursor.fetchall()]
    if "production_date" not in pi_cols:
        cursor.execute("ALTER TABLE purchase_items ADD COLUMN production_date TEXT")
    if "usage" not in pi_cols:
        cursor.execute("ALTER TABLE purchase_items ADD COLUMN usage TEXT")
    conn.commit()
    conn.close()


try:
    _ensure_columns()
except Exception as _e:
    _logger.debug(f"_ensure_columns skipped: {_e}")


def _calc_expiry_info(production_date_str, expiry_months, expiry_days):
    """计算保质期信息，返回 (储存天数, 过期日期, 提醒文字, 是否过期)"""
    if not production_date_str:
        return ("", "", "", False)
    try:
        pd = datetime.strptime(production_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return ("", "", "", False)
    today = date.today()
    stored_days = (today - pd).days

    exp_date = None
    if expiry_months and expiry_months > 0:
        y, m = pd.year, pd.month + expiry_months
        while m > 12:
            y += 1
            m -= 12
        d = min(pd.day, calendar.monthrange(y, m)[1])
        exp_date = date(y, m, d)
    if expiry_days and expiry_days > 0:
        exp_date = (exp_date or pd) + timedelta(days=expiry_days)

    if exp_date:
        exp_str = exp_date.strftime("%Y-%m-%d")
        diff = (exp_date - today).days
        if diff < 0:
            return (stored_days, exp_str, f"已过期{-diff}天", True)
        else:
            return (stored_days, exp_str, f"距保质期{diff}天", False)
    else:
        return (stored_days, "", "未设保质期", False)


def _dlg_save_style():
    return (f"background-color: {COLOR['primary']}; color: #fff; border: none; "
            f"border-radius: 4px; padding: 10px 36px; font-size: 13px; font-weight: bold;")


def _dlg_cancel_style():
    return (f"background-color: #fff; color: {COLOR['text_primary']}; "
            f"border: 1px solid {COLOR['border']}; border-radius: 4px; "
            f"padding: 10px 36px; font-size: 13px;")


# ═══════════════════════════════════════════════════════════
# 进货对话框
# ═══════════════════════════════════════════════════════════
class ReturnPurchaseDialog(QDialog):
    """进货退货对话框：与新增进货界面一致，单号TH前缀，金额取负"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("进货退货")
        self.resize(860, 680)
        self.setMinimumSize(760, 600)
        self.items = []
        self._syncing = False
        self._prod_date = ""
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 基本信息
        basic = QGroupBox("基本信息")
        basic_layout = QGridLayout()
        basic_layout.setSpacing(12)
        _bw, _bh = 80, 40

        lbl_date = QLabel("退货日期：")
        lbl_date.setFixedWidth(_bw); lbl_date.setFixedHeight(_bh)
        lbl_date.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.date_purchase = ModernDateEdit()
        self.date_purchase.setDate(QDate.currentDate())
        self.date_purchase.setFixedHeight(_bh)
        basic_layout.addWidget(lbl_date, 0, 0)
        basic_layout.addWidget(self.date_purchase, 0, 1)

        lbl_supplier = QLabel("供应商 *：")
        lbl_supplier.setFixedWidth(_bw); lbl_supplier.setFixedHeight(_bh)
        lbl_supplier.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cmb_supplier = QComboBox()
        self.cmb_supplier.setStyleSheet(COMBO_STYLE)
        self.cmb_supplier.setFixedHeight(_bh)
        self._load_suppliers()
        basic_layout.addWidget(lbl_supplier, 0, 2)
        basic_layout.addWidget(self.cmb_supplier, 0, 3)

        lbl_op = QLabel("经办人 *：")
        lbl_op.setFixedWidth(_bw); lbl_op.setFixedHeight(_bh)
        lbl_op.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.txt_operator = QLineEdit()
        self.txt_operator.setFixedHeight(_bh)
        self.txt_operator.setPlaceholderText("请输入经办人")
        basic_layout.addWidget(lbl_op, 1, 0)
        basic_layout.addWidget(self.txt_operator, 1, 1)

        lbl_remark = QLabel("退货原因：")
        lbl_remark.setFixedWidth(_bw); lbl_remark.setFixedHeight(_bh)
        lbl_remark.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.txt_remark = QLineEdit()
        self.txt_remark.setFixedHeight(_bh)
        self.txt_remark.setPlaceholderText("如：质量不合格、过期退回等")
        basic_layout.addWidget(lbl_remark, 1, 2)
        basic_layout.addWidget(self.txt_remark, 1, 3)

        basic_layout.setColumnStretch(1, 1)
        basic_layout.setColumnStretch(3, 1)
        basic.setLayout(basic_layout)
        layout.addWidget(basic)

        # 退货明细
        detail_group = QGroupBox("退货明细（每项需填写生产日期和用途）")
        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(12)

        # 第一行：产品 / 品牌 / 规格 / 单位
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.cmb_ingredient = QComboBox()
        self.cmb_ingredient.setFixedHeight(40)
        row1.addWidget(QLabel("产品 *："))
        row1.addWidget(self.cmb_ingredient, 3)

        self.txt_brand = QLineEdit()
        self.txt_brand.setPlaceholderText("品牌")
        self.txt_brand.setFixedHeight(40); self.txt_brand.setMaximumWidth(100)
        self.txt_brand.setStyleSheet("background: #f5f5f5; color: #999;")
        row1.addWidget(QLabel("品牌："))
        row1.addWidget(self.txt_brand)

        self.txt_spec = QLineEdit()
        self.txt_spec.setPlaceholderText("规格")
        self.txt_spec.setFixedHeight(40); self.txt_spec.setMaximumWidth(120)
        self.txt_spec.setStyleSheet("background: #f5f5f5; color: #999;")
        row1.addWidget(QLabel("规格："))
        row1.addWidget(self.txt_spec)

        self.txt_unit = QLineEdit()
        self.txt_unit.setPlaceholderText("单位")
        self.txt_unit.setFixedHeight(40); self.txt_unit.setMaximumWidth(80)
        self.txt_unit.setStyleSheet("background: #f5f5f5; color: #999;")
        row1.addWidget(QLabel("单位："))
        row1.addWidget(self.txt_unit)

        self._load_ingredients()
        self.cmb_ingredient.currentIndexChanged.connect(self._on_ingredient_changed)
        if self.cmb_ingredient.count() > 0:
            self._on_ingredient_changed(0)
        row1.addStretch()
        detail_layout.addLayout(row1)

        # 第二行：数量 / 单价 / 金额
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.spin_qty = QLineEdit("1")
        self.spin_qty.setValidator(QDoubleValidator(0.0001, 999999, 10))
        self.spin_qty.setMaximumWidth(100); self.spin_qty.setFixedHeight(40)
        row2.addWidget(QLabel("数量 *："))
        row2.addWidget(self.spin_qty)

        self.spin_unit_price = QLineEdit()
        self.spin_unit_price.setPlaceholderText("¥ 单价")
        self.spin_unit_price.setValidator(QDoubleValidator(0, 99999, 2))
        self.spin_unit_price.setMaximumWidth(110); self.spin_unit_price.setFixedHeight(40)
        row2.addWidget(QLabel("单价 *："))
        row2.addWidget(self.spin_unit_price)

        self.spin_amount = QLineEdit()
        self.spin_amount.setPlaceholderText("¥ 总金额")
        self.spin_amount.setValidator(QDoubleValidator(0, 9999999, 2))
        self.spin_amount.setMaximumWidth(120); self.spin_amount.setFixedHeight(40)
        row2.addWidget(QLabel("金额 *："))
        row2.addWidget(self.spin_amount)

        self.spin_qty.textChanged.connect(self._on_qty_changed)
        self.spin_unit_price.textChanged.connect(self._on_price_changed)
        self.spin_amount.textChanged.connect(self._on_amount_changed)
        row2.addStretch()
        detail_layout.addLayout(row2)

        # 第三行：生产日期 / 用途 / 添加
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(QLabel("生产日期："))
        self.date_prod = ModernDateEdit(default_today=False, placeholder="请选择生产日期")
        self.date_prod.setFixedWidth(200); self.date_prod.setFixedHeight(40)
        self.date_prod.dateChanged.connect(lambda d: setattr(self, "_prod_date", d.toString("yyyy-MM-dd")))
        row3.addWidget(self.date_prod)

        self.cmb_usage = QComboBox()
        self.cmb_usage.setEditable(True)
        self.cmb_usage.setPlaceholderText("选择或输入用途")
        self.cmb_usage.setStyleSheet(COMBO_STYLE)
        self.cmb_usage.setFixedHeight(40)
        self._load_usage_options()
        self.cmb_usage.currentIndexChanged.connect(self._on_usage_index_changed)
        row3.addWidget(QLabel("用途 *："))
        row3.addWidget(self.cmb_usage, 1)

        btn_add = QPushButton("添加")
        btn_add.setFixedHeight(40); btn_add.setFixedWidth(80)
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_item)
        row3.addWidget(btn_add)
        detail_layout.addLayout(row3)

        # 明细表格
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(8)
        self.detail_table.setHorizontalHeaderLabels(
            ["序号", "产品", "数量", "单价", "小计", "生产日期", "用途", "操作"])
        self.detail_table.setColumnWidth(0, 50)
        hdr = self.detail_table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        hdr.setSectionResizeMode(7, QHeaderView.Fixed)
        hdr.setStretchLastSection(False)
        self.detail_table.setColumnWidth(7, 80)
        self.detail_table.setStyleSheet(TABLE_STYLE)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.verticalHeader().setDefaultSectionSize(52)
        detail_layout.addWidget(self.detail_table)

        self.lbl_total = QLabel("退货合计：¥ 0.00")
        self.lbl_total.setStyleSheet(
            f"color: {COLOR['danger']}; font-size: 13px; font-weight: bold; padding: 8px 0;")
        detail_layout.addWidget(self.lbl_total)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        # 保存按钮
        btn_save = QPushButton("确认退货")
        btn_save.setStyleSheet(danger_btn)
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save)
        self.setLayout(layout)

    def _load_suppliers(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM suppliers ORDER BY name")
        self.cmb_supplier.clear()
        self.cmb_supplier.addItem("", None)
        for r in cursor.fetchall():
            self.cmb_supplier.addItem(r["name"], r["id"])
        conn.close()

    def _load_ingredients(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT id, name, brand, spec, unit FROM ingredients ORDER BY name")
        else:
            cursor.execute(
                "SELECT id, name, brand, spec, unit FROM ingredients "
                "WHERE store_id=? OR store_id IS NULL ORDER BY name", (_sid,))
        self.cmb_ingredient.clear()
        self._ing_data = {}
        for r in cursor.fetchall():
            self.cmb_ingredient.addItem(r["name"], r["id"])
            self._ing_data[r["id"]] = {
                "name": r["name"], "brand": r["brand"] or "",
                "spec": r["spec"] or "", "unit": r["unit"] or ""}
        conn.close()

    def _load_usage_options(self):
        usages = ["客餐", "员工餐"]
        try:
            conn = get_connection()
            cursor = conn.cursor()
            _sid, _all = _ctx().get_store_filter()
            if _all:
                cursor.execute(
                    "SELECT DISTINCT usage FROM purchase_items "
                    "WHERE usage IS NOT NULL AND usage != '' ORDER BY usage")
            else:
                cursor.execute(
                    "SELECT DISTINCT pi.usage FROM purchase_items pi "
                    "JOIN purchases p ON pi.purchase_id = p.id "
                    "WHERE pi.usage IS NOT NULL AND pi.usage != '' "
                    "AND (p.store_id=? OR p.store_id IS NULL) ORDER BY pi.usage", (_sid,))
            saved = [r["usage"] for r in cursor.fetchall() if r["usage"] not in usages]
            usages.extend(saved)
            conn.close()
        except Exception:
            pass
        self.cmb_usage.clear()
        self.cmb_usage.addItems(usages)
        self.cmb_usage.addItem("+ 新增用途")

    def _on_usage_index_changed(self, index):
        if index < 0:
            return
        if self.cmb_usage.itemText(index) == "+ 新增用途":
            self.cmb_usage.blockSignals(True)
            self.cmb_usage.setCurrentIndex(-1)
            self.cmb_usage.blockSignals(False)
            text, ok = QInputDialog.getText(self, "新建用途", "请输入用途名称：")
            if ok and text.strip():
                usage = text.strip()
                exists = any(self.cmb_usage.itemText(i) == usage
                            for i in range(self.cmb_usage.count()))
                if exists:
                    QMessageBox.information(self, "提示", f"用途「{usage}」已存在")
                    self.cmb_usage.setCurrentText(usage)
                else:
                    self.cmb_usage.insertItem(self.cmb_usage.count() - 1, usage)
                    self.cmb_usage.setCurrentText(usage)
            else:
                self.cmb_usage.setCurrentText("")

    def _on_ingredient_changed(self, idx):
        ing_id = self.cmb_ingredient.currentData()
        data = getattr(self, "_ing_data", {}).get(ing_id, {})
        self.txt_brand.setText(data.get("brand", ""))
        self.txt_spec.setText(data.get("spec", ""))
        self.txt_unit.setText(data.get("unit", ""))

    def _on_qty_changed(self, text):
        if self._syncing:
            return
        self._syncing = True
        try:
            qty = float(text or "0")
            if qty <= 0:
                self._syncing = False
                return
            p = self.spin_unit_price.text().strip()
            if p:
                pv = float(p)
                if pv > 0:
                    self.spin_amount.setText(f"{round(qty * pv, 2):.2f}")
        except ValueError:
            pass
        self._syncing = False

    def _on_price_changed(self, text):
        if self._syncing:
            return
        self._syncing = True
        try:
            qty = float(self.spin_qty.text() or "0")
            price = float(text or "0")
            if qty > 0 and price > 0:
                self.spin_amount.setText(f"{round(qty * price, 2):.2f}")
        except ValueError:
            pass
        self._syncing = False

    def _on_amount_changed(self, text):
        if self._syncing:
            return
        self._syncing = True
        try:
            qty = float(self.spin_qty.text() or "0")
            amount = float(text or "0")
            if qty > 0 and amount > 0:
                self.spin_unit_price.setText(f"{round(amount / qty, 2):.2f}")
        except ValueError:
            pass
        self._syncing = False

    def _add_item(self):
        ing_id = self.cmb_ingredient.currentData()
        if not ing_id:
            QMessageBox.warning(self, "提示", "请选择产品")
            return
        ing = self._ing_data.get(ing_id, {})
        try:
            qty = float(self.spin_qty.text().strip())
        except ValueError:
            QMessageBox.warning(self, "提示", "请输入有效的退货数量")
            return
        if qty <= 0:
            QMessageBox.warning(self, "提示", "退货数量必须大于0")
            return
        try:
            price = float(self.spin_unit_price.text().strip() or "0")
        except ValueError:
            price = 0
        try:
            amount = float(self.spin_amount.text().strip() or "0")
        except ValueError:
            amount = qty * price
        if amount <= 0:
            amount = qty * price
        usage = self.cmb_usage.currentText().strip()
        if not usage or usage == "+ 新增用途":
            QMessageBox.warning(self, "提示", "请选择或输入用途")
            return
        prod_date = self._prod_date or ""
        self.items.append({
            "ingredient_id": ing_id,
            "name": ing.get("name", ""),
            "brand": ing.get("brand", ""),
            "spec": ing.get("spec", ""),
            "unit": ing.get("unit", ""),
            "quantity": qty,
            "unit_price": price,
            "total_price": amount,
            "production_date": prod_date,
            "usage": usage,
        })
        self._refresh_detail()
        self.spin_qty.clear()
        self.spin_unit_price.clear()
        self.spin_amount.clear()
        self._prod_date = ""
        self.cmb_usage.setCurrentIndex(-1)

    def _refresh_detail(self):
        self.detail_table.setRowCount(len(self.items))
        grand_total = 0
        for i, item in enumerate(self.items):
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 0, sn)
            self.detail_table.setItem(i, 1, QTableWidgetItem(
                f"{item['name']} ({item['spec']}/{item['unit']})"))
            qty_item = QTableWidgetItem(f"-{item['quantity']:.2f}")
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setForeground(QColor(COLOR["danger"]))
            self.detail_table.setItem(i, 2, qty_item)
            _ci1 = QTableWidgetItem(f"¥{item['unit_price']:.2f}")
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 3, _ci1)
            subtotal_item = QTableWidgetItem(f"¥{item['total_price']:.2f}")
            subtotal_item.setTextAlignment(Qt.AlignCenter)
            subtotal_item.setForeground(QColor(COLOR["danger"]))
            self.detail_table.setItem(i, 4, subtotal_item)
            _ci2 = QTableWidgetItem(item.get("production_date", ""))
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 5, _ci2)
            _ci3 = QTableWidgetItem(item.get("usage", ""))
            _ci3.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 6, _ci3)
            # 删除按钮
            btn_del = QPushButton("✕")
            btn_del.setFixedSize(30, 30)
            btn_del.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; "
                f"color: {COLOR['danger']}; font-size: 16px; }}")
            btn_del.clicked.connect(lambda checked, r=i: self._remove_item(r))
            wrapper = QWidget()
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_del)
            self.detail_table.setCellWidget(i, 7, wrapper)
            grand_total += item["total_price"]
        self.lbl_total.setText(f"退货合计：¥ {grand_total:.2f}")

    def _remove_item(self, row):
        self.items.pop(row)
        self._refresh_detail()

    def _save(self):
        operator = self.txt_operator.text().strip()
        if not operator:
            QMessageBox.warning(self, "提示", "请输入经办人")
            return
        if not self.items:
            QMessageBox.warning(self, "提示", "请添加退货明细")
            return
        return_date = self.date_purchase.date().toString("yyyy-MM-dd")
        _sid, _ = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        today_str = self.date_purchase.date().toString("yyyyMMdd")
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM purchases WHERE purchase_no LIKE ?",
            (f"TH-{today_str}-%",))
        cnt = cursor.fetchone()["cnt"]
        return_no = f"TH-{today_str}-{cnt + 1:03d}"
        supplier_id = self.cmb_supplier.currentData()
        remark = self.txt_remark.text().strip()
        try:
            cursor.execute(
                "INSERT INTO purchases (purchase_no, purchase_date, operator, supplier_id, "
                "remark, store_id) VALUES (?,?,?,?,?,?)",
                (return_no, return_date, operator, supplier_id,
                 f"[退货]{remark}", _sid))
            pid = cursor.lastrowid
            for item in self.items:
                cursor.execute(
                    "INSERT INTO purchase_items (purchase_id, ingredient_id, quantity, "
                    "unit_price, total_price, usage, production_date) VALUES (?,?,?,?,?,?,?)",
                    (pid, item["ingredient_id"], item["quantity"],
                     item["unit_price"], -item["total_price"],
                     item.get("usage", ""), item.get("production_date", "")))
                cursor.execute(
                    "UPDATE ingredients SET stock = stock - ? WHERE id=?",
                    (item["quantity"], item["ingredient_id"]))
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", f"退货单 {return_no} 已保存")
            self.accept()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"保存退货单失败：{e}")
        finally:
            conn.close()

class PurchaseDialog(QDialog):
    """新增进货单——支持多项明细，每项含生产日期和用途"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增进货单")
        self.resize(860, 680)
        self.setMinimumSize(760, 600)
        self.items = []
        self._syncing = False
        self._prod_date = ""
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 基本信息
        basic = QGroupBox("基本信息")
        basic_layout = QGridLayout()
        basic_layout.setSpacing(12)
        _bw, _bh = 80, 40

        lbl_date = QLabel("进货日期：")
        lbl_date.setFixedWidth(_bw); lbl_date.setFixedHeight(_bh)
        lbl_date.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.date_purchase = ModernDateEdit()
        self.date_purchase.setDate(QDate.currentDate())
        self.date_purchase.setFixedHeight(_bh)
        basic_layout.addWidget(lbl_date, 0, 0)
        basic_layout.addWidget(self.date_purchase, 0, 1)

        lbl_supplier = QLabel("供应商 *：")
        lbl_supplier.setFixedWidth(_bw); lbl_supplier.setFixedHeight(_bh)
        lbl_supplier.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cmb_supplier = QComboBox()
        self.cmb_supplier.setStyleSheet(COMBO_STYLE)
        self.cmb_supplier.setFixedHeight(_bh)
        self._load_suppliers()
        basic_layout.addWidget(lbl_supplier, 0, 2)
        basic_layout.addWidget(self.cmb_supplier, 0, 3)

        lbl_remark = QLabel("备注：")
        lbl_remark.setFixedWidth(_bw); lbl_remark.setFixedHeight(_bh)
        lbl_remark.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.txt_remark = QLineEdit()
        self.txt_remark.setFixedHeight(_bh)
        basic_layout.addWidget(lbl_remark, 1, 0)
        basic_layout.addWidget(self.txt_remark, 1, 1, 1, 3)

        basic_layout.setColumnStretch(1, 1)
        basic_layout.setColumnStretch(3, 1)
        basic.setLayout(basic_layout)
        layout.addWidget(basic)

        # 进货明细
        detail_group = QGroupBox("进货明细（每项需填写生产日期和用途）")
        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(12)

        # 第一行：产品 / 品牌 / 规格 / 单位
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.cmb_ingredient = QComboBox()
        self.cmb_ingredient.setFixedHeight(40)
        row1.addWidget(QLabel("产品 *："))
        row1.addWidget(self.cmb_ingredient, 3)

        self.txt_brand = QLineEdit()
        self.txt_brand.setPlaceholderText("品牌")
        self.txt_brand.setFixedHeight(40); self.txt_brand.setMaximumWidth(100)
        self.txt_brand.setStyleSheet("background: #f5f5f5; color: #999;")
        row1.addWidget(QLabel("品牌："))
        row1.addWidget(self.txt_brand)

        self.txt_spec = QLineEdit()
        self.txt_spec.setPlaceholderText("规格")
        self.txt_spec.setFixedHeight(40); self.txt_spec.setMaximumWidth(120)
        self.txt_spec.setStyleSheet("background: #f5f5f5; color: #999;")
        row1.addWidget(QLabel("规格："))
        row1.addWidget(self.txt_spec)

        self.txt_unit = QLineEdit()
        self.txt_unit.setPlaceholderText("单位")
        self.txt_unit.setFixedHeight(40); self.txt_unit.setMaximumWidth(80)
        self.txt_unit.setStyleSheet("background: #f5f5f5; color: #999;")
        row1.addWidget(QLabel("单位："))
        row1.addWidget(self.txt_unit)

        self._load_ingredients()
        self.cmb_ingredient.currentIndexChanged.connect(self._on_ingredient_changed)
        if self.cmb_ingredient.count() > 0:
            self._on_ingredient_changed(0)
        row1.addStretch()
        detail_layout.addLayout(row1)

        # 第二行：数量 / 单价 / 金额
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.spin_qty = QLineEdit("1")
        self.spin_qty.setValidator(QDoubleValidator(0.0001, 999999, 10))
        self.spin_qty.setMaximumWidth(100); self.spin_qty.setFixedHeight(40)
        row2.addWidget(QLabel("数量 *："))
        row2.addWidget(self.spin_qty)

        self.spin_unit_price = QLineEdit()
        self.spin_unit_price.setPlaceholderText("¥ 单价")
        self.spin_unit_price.setValidator(QDoubleValidator(0, 99999, 2))
        self.spin_unit_price.setMaximumWidth(110); self.spin_unit_price.setFixedHeight(40)
        row2.addWidget(QLabel("单价 *："))
        row2.addWidget(self.spin_unit_price)

        self.spin_amount = QLineEdit()
        self.spin_amount.setPlaceholderText("¥ 总金额")
        self.spin_amount.setValidator(QDoubleValidator(0, 9999999, 2))
        self.spin_amount.setMaximumWidth(120); self.spin_amount.setFixedHeight(40)
        row2.addWidget(QLabel("金额 *："))
        row2.addWidget(self.spin_amount)

        self.spin_qty.textChanged.connect(self._on_qty_changed)
        self.spin_unit_price.textChanged.connect(self._on_price_changed)
        self.spin_amount.textChanged.connect(self._on_amount_changed)
        row2.addStretch()
        detail_layout.addLayout(row2)

        # 第三行：生产日期 / 用途 / 添加
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(QLabel("生产日期："))
        self.date_prod = ModernDateEdit(default_today=False, placeholder="请选择生产日期")
        self.date_prod.setFixedWidth(200); self.date_prod.setFixedHeight(40)
        self.date_prod.dateChanged.connect(lambda d: setattr(self, "_prod_date", d.toString("yyyy-MM-dd")))
        row3.addWidget(self.date_prod)

        self.cmb_usage = QComboBox()
        self.cmb_usage.setEditable(True)
        self.cmb_usage.setPlaceholderText("选择或输入用途")
        self.cmb_usage.setStyleSheet(COMBO_STYLE)
        self.cmb_usage.setFixedHeight(40)
        self._load_usage_options()
        self.cmb_usage.currentIndexChanged.connect(self._on_usage_index_changed)
        row3.addWidget(QLabel("用途 *："))
        row3.addWidget(self.cmb_usage, 1)

        btn_add = QPushButton("添加")
        btn_add.setFixedHeight(40); btn_add.setFixedWidth(80)
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_item)
        row3.addWidget(btn_add)
        detail_layout.addLayout(row3)

        # 明细表格
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(8)
        self.detail_table.setHorizontalHeaderLabels(
            ["序号", "产品", "数量", "单价", "小计", "生产日期", "用途", "操作"])
        self.detail_table.setColumnWidth(0, 50)
        hdr = self.detail_table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        hdr.setSectionResizeMode(7, QHeaderView.Fixed)
        hdr.setStretchLastSection(False)
        self.detail_table.setColumnWidth(7, 80)
        self.detail_table.setStyleSheet(TABLE_STYLE)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.verticalHeader().setDefaultSectionSize(52)
        detail_layout.addWidget(self.detail_table)

        self.lbl_total = QLabel("合计：¥ 0.00")
        self.lbl_total.setStyleSheet(
            f"color: {COLOR['primary']}; font-size: 13px; font-weight: bold; padding: 8px 0;")
        detail_layout.addWidget(self.lbl_total)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        # 保存按钮
        btn_save = QPushButton("保存进货单")
        btn_save.setStyleSheet(success_btn)
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save)
        self.setLayout(layout)

    def _load_suppliers(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM suppliers ORDER BY name")
        self.cmb_supplier.clear()
        self.cmb_supplier.addItem("", None)
        for r in cursor.fetchall():
            self.cmb_supplier.addItem(r["name"], r["id"])
        conn.close()

    def _load_ingredients(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT id, name, brand, spec, unit FROM ingredients ORDER BY name")
        else:
            cursor.execute(
                "SELECT id, name, brand, spec, unit FROM ingredients "
                "WHERE store_id=? OR store_id IS NULL ORDER BY name", (_sid,))
        self.cmb_ingredient.clear()
        self._ing_data = {}
        for r in cursor.fetchall():
            self.cmb_ingredient.addItem(r["name"], r["id"])
            self._ing_data[r["id"]] = {
                "name": r["name"], "brand": r["brand"] or "",
                "spec": r["spec"] or "", "unit": r["unit"] or ""}
        conn.close()

    def _load_usage_options(self):
        usages = ["客餐", "员工餐"]
        try:
            conn = get_connection()
            cursor = conn.cursor()
            _sid, _all = _ctx().get_store_filter()
            if _all:
                cursor.execute(
                    "SELECT DISTINCT usage FROM purchase_items "
                    "WHERE usage IS NOT NULL AND usage != '' ORDER BY usage")
            else:
                cursor.execute(
                    "SELECT DISTINCT pi.usage FROM purchase_items pi "
                    "JOIN purchases p ON pi.purchase_id = p.id "
                    "WHERE pi.usage IS NOT NULL AND pi.usage != '' "
                    "AND (p.store_id=? OR p.store_id IS NULL) ORDER BY pi.usage", (_sid,))
            saved = [r["usage"] for r in cursor.fetchall() if r["usage"] not in usages]
            usages.extend(saved)
            conn.close()
        except Exception:
            pass
        self.cmb_usage.clear()
        self.cmb_usage.addItems(usages)
        self.cmb_usage.addItem("+ 新增用途")

    def _on_usage_index_changed(self, index):
        if index < 0:
            return
        if self.cmb_usage.itemText(index) == "+ 新增用途":
            self.cmb_usage.blockSignals(True)
            self.cmb_usage.setCurrentIndex(-1)
            self.cmb_usage.blockSignals(False)
            text, ok = QInputDialog.getText(self, "新建用途", "请输入用途名称：")
            if ok and text.strip():
                usage = text.strip()
                exists = any(self.cmb_usage.itemText(i) == usage
                            for i in range(self.cmb_usage.count()))
                if exists:
                    QMessageBox.information(self, "提示", f"用途「{usage}」已存在")
                    self.cmb_usage.setCurrentText(usage)
                else:
                    self.cmb_usage.insertItem(self.cmb_usage.count() - 1, usage)
                    self.cmb_usage.setCurrentText(usage)
            else:
                self.cmb_usage.setCurrentText("")

    def _on_ingredient_changed(self, idx):
        ing_id = self.cmb_ingredient.currentData()
        data = getattr(self, "_ing_data", {}).get(ing_id, {})
        self.txt_brand.setText(data.get("brand", ""))
        self.txt_spec.setText(data.get("spec", ""))
        self.txt_unit.setText(data.get("unit", ""))

    def _on_qty_changed(self, text):
        if self._syncing:
            return
        self._syncing = True
        try:
            qty = float(text or "0")
            if qty <= 0:
                self._syncing = False
                return
            # 数量变化时只更新金额 = 数量 * 单价，不反算单价
            p = self.spin_unit_price.text().strip()
            if p:
                pv = float(p)
                if pv > 0:
                    self.spin_amount.setText(f"{round(qty * pv, 2):.2f}")
        except ValueError:
            pass
        self._syncing = False

    def _on_price_changed(self, text):
        if self._syncing:
            return
        self._syncing = True
        try:
            qty = float(self.spin_qty.text() or "0")
            price = float(text or "0")
            if qty > 0 and price > 0:
                self.spin_amount.setText(f"{round(qty * price, 2):.2f}")
        except ValueError:
            pass
        self._syncing = False

    def _on_amount_changed(self, text):
        if self._syncing:
            return
        self._syncing = True
        try:
            qty = float(self.spin_qty.text() or "0")
            amount = float(text or "0")
            if qty > 0 and amount > 0:
                self.spin_unit_price.setText(f"{round(amount / qty, 2):.2f}")
        except ValueError:
            pass
        self._syncing = False

    def _add_item(self):
        ing_id = self.cmb_ingredient.currentData()
        ing_name = self.cmb_ingredient.currentText()
        if not ing_id:
            QMessageBox.warning(self, "提示", "请选择产品")
            return
        try:
            qty = float(self.spin_qty.text() or "0")
        except ValueError:
            QMessageBox.warning(self, "提示", "数量格式错误")
            return
        if qty <= 0:
            QMessageBox.warning(self, "提示", "请输入有效的数量")
            return
        amt_str = self.spin_amount.text().strip()
        if amt_str:
            try:
                total = round(float(amt_str), 2)
            except ValueError:
                QMessageBox.warning(self, "提示", "金额格式错误")
                return
            if total <= 0:
                QMessageBox.warning(self, "提示", "请输入有效的金额")
                return
            price = round(total / qty, 2) if qty > 0 else 0
        else:
            try:
                price = float(self.spin_unit_price.text() or "0")
            except ValueError:
                QMessageBox.warning(self, "提示", "单价格式错误")
                return
            if price <= 0:
                QMessageBox.warning(self, "提示", "请输入单价或金额")
                return
            total = round(qty * price, 2)
        usage = self.cmb_usage.currentText().strip()
        if not usage or usage == "+ 新增用途":
            QMessageBox.warning(self, "提示", "请选择或输入用途")
            return
        self.items.append({
            "ingredient_id": ing_id, "name": ing_name, "qty": qty,
            "price": price, "total": total,
            "production_date": self._prod_date, "usage": usage})
        self._refresh_detail_table()
        self.spin_qty.setText("1")
        self.spin_amount.setText("0.00")
        self.spin_unit_price.clear()
        self.date_prod._clear_date() if hasattr(self.date_prod, "_clear_date") else None
        self._prod_date = ""

    def _refresh_detail_table(self):
        self.detail_table.setRowCount(len(self.items))
        total = 0
        for i, item in enumerate(self.items):
            total += item["total"]
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 0, sn)
            _ci4 = QTableWidgetItem(item["name"])
            _ci4.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 1, _ci4)
            _ci5 = QTableWidgetItem(f"{item['qty']:.1f}")
            _ci5.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 2, _ci5)
            _ci6 = QTableWidgetItem(f"¥{item['price']:.2f}")
            _ci6.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 3, _ci6)
            _ci7 = QTableWidgetItem(f"¥{item['total']:.2f}")
            _ci7.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 4, _ci7)
            _ci8 = QTableWidgetItem(item.get("production_date", ""))
            _ci8.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 5, _ci8)
            _ci9 = QTableWidgetItem(item["usage"])
            _ci9.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 6, _ci9)
            btn_del = make_table_button("删除", "delete")
            btn_del.clicked.connect(lambda checked, idx=i: self._remove_item(idx))
            wrapper = QWidget()
            wrapper.setObjectName("btnCell")
            wrapper.setStyleSheet("#btnCell { background: transparent; border: none; }")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_del)
            self.detail_table.setCellWidget(i, 7, wrapper)
        self.lbl_total.setText(f"合计：¥ {total:.2f}")

    def _remove_item(self, idx):
        if 0 <= idx < len(self.items):
            self.items.pop(idx)
            self._refresh_detail_table()

    def _save(self):
        if not self.items:
            QMessageBox.warning(self, "提示", "请添加进货明细")
            return
        _sid, _ = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        try:
            purchase_no = generate_order_no("CG")
            supplier_id = self.cmb_supplier.currentData()
            total = sum(it["total"] for it in self.items)
            cursor.execute(
                "INSERT INTO purchases (purchase_no, supplier_id, total_amount, "
                "purchase_date, remark, store_id) VALUES (?,?,?,?,?,?)",
                (purchase_no, supplier_id, total,
                 self.date_purchase.date().toString("yyyy-MM-dd"),
                 self.txt_remark.text().strip(), _sid))
            pid = cursor.lastrowid
            for item in self.items:
                cursor.execute(
                    "INSERT INTO purchase_items "
                    "(purchase_id, ingredient_id, quantity, unit_price, total_price, "
                    " production_date, usage) VALUES (?,?,?,?,?,?,?)",
                    (pid, item["ingredient_id"], item["qty"], item["price"],
                     item["total"], item.get("production_date", ""), item["usage"]))
                cursor.execute(
                    "UPDATE ingredients SET stock = stock + ? WHERE id=?",
                    (item["qty"], item["ingredient_id"]))
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", f"进货单 {purchase_no} 已保存")
            self.accept()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════
# 出库对话框
# ═══════════════════════════════════════════════════════════
class StockOutDialog(QDialog):
    """产品出库登记"""

    def __init__(self, parent=None, ingredient_id=None):
        super().__init__(parent)
        self.setWindowTitle("产品出库")
        self.resize(900, 680)
        self.setMinimumSize(760, 580)
        self.setStyleSheet(DLG_STYLE)
        self.items = []
        self._preset_ingredient_id = ingredient_id
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("产品出库登记")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLOR['border']}; max-height: 1px;")
        layout.addWidget(line)

        # 出库信息
        info_group = QGroupBox("出库信息")
        info_layout = QGridLayout()
        info_layout.setSpacing(16)
        info_layout.setContentsMargins(20, 18, 20, 18)
        _lw = 80

        self.date_out = ModernDateEdit()
        self.date_out.setDate(QDate.currentDate())
        self.date_out.setFixedHeight(40)
        lbl_date = QLabel("出库日期：")
        lbl_date.setFixedWidth(_lw); lbl_date.setFixedHeight(40)
        lbl_date.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(lbl_date, 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self.date_out, 0, 1)

        self.cmb_reason = QComboBox()
        self.cmb_reason.addItems(["日常领用", "损耗报废", "盘点调整", "调拨出库", "其他"])
        self.cmb_reason.setFixedHeight(40)
        lbl_reason = QLabel("出库类型：")
        lbl_reason.setFixedWidth(_lw); lbl_reason.setFixedHeight(40)
        lbl_reason.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(lbl_reason, 0, 2, alignment=Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self.cmb_reason, 0, 3)

        self.txt_operator = QLineEdit()
        self.txt_operator.setPlaceholderText("经办人")
        self.txt_operator.setFixedHeight(40)
        lbl_op = QLabel("经办人：")
        lbl_op.setFixedWidth(_lw); lbl_op.setFixedHeight(40)
        lbl_op.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(lbl_op, 1, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self.txt_operator, 1, 1)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注（可选）")
        self.txt_remark.setFixedHeight(40)
        lbl_remark = QLabel("备　　注：")
        lbl_remark.setFixedWidth(_lw); lbl_remark.setFixedHeight(40)
        lbl_remark.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(lbl_remark, 1, 2, alignment=Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self.txt_remark, 1, 3)
        info_layout.setColumnStretch(1, 1)
        info_layout.setColumnStretch(3, 1)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 出库明细
        detail_group = QGroupBox("出库明细")
        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(12)
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.cmb_ingredient = QComboBox()
        self.cmb_ingredient.setFixedHeight(40)
        self._load_ingredients()
        if self._preset_ingredient_id is not None:
            for i in range(self.cmb_ingredient.count()):
                if self.cmb_ingredient.itemData(i) == self._preset_ingredient_id:
                    self.cmb_ingredient.setCurrentIndex(i)
                    break
        lbl_product = QLabel("产品：")
        lbl_product.setFixedWidth(50); lbl_product.setFixedHeight(40)
        lbl_product.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        add_row.addWidget(lbl_product)
        add_row.addWidget(self.cmb_ingredient, 2)

        self.spin_qty = QLineEdit("1")
        self.spin_qty.setValidator(QDoubleValidator(0.0001, 999999, 10))
        self.spin_qty.setMaximumWidth(100); self.spin_qty.setFixedHeight(40)
        lbl_qty = QLabel("数量：")
        lbl_qty.setFixedWidth(50); lbl_qty.setFixedHeight(40)
        lbl_qty.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        add_row.addWidget(lbl_qty)
        add_row.addWidget(self.spin_qty)

        btn_add = QPushButton("添加")
        btn_add.setFixedHeight(40); btn_add.setFixedWidth(70)
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_item)
        add_row.addWidget(btn_add)
        detail_layout.addLayout(add_row)

        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(4)
        self.detail_table.setHorizontalHeaderLabels(["序号", "产品", "数量", "操作"])
        self.detail_table.setStyleSheet(TABLE_STYLE)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.verticalHeader().setDefaultSectionSize(52)
        self.detail_table.setColumnWidth(0, 60)
        self.detail_table.setColumnWidth(2, 100)
        self.detail_table.setColumnWidth(3, 80)
        hdr = self.detail_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setStretchLastSection(False)
        self.detail_table.setMinimumHeight(100)
        detail_layout.addWidget(self.detail_table)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(40)
        btn_cancel.setStyleSheet(_dlg_cancel_style())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("确认出库")
        btn_save.setFixedHeight(40)
        btn_save.setStyleSheet(_dlg_save_style())
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_ingredients(self):
        """加载食材列表，显示基于交易记录的可用库存"""
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT id, name, unit FROM ingredients ORDER BY name")
        else:
            cursor.execute(
                "SELECT id, name, unit FROM ingredients "
                "WHERE store_id=? OR store_id IS NULL ORDER BY name", (_sid,))
        ingredients = [dict(r) for r in cursor.fetchall()]

        # 计算每个食材的可用库存 = 累计进货 - 累计出库
        avail_sql = (
            "SELECT pi.ingredient_id, "
            "SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END) - "
            "SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END) as total_in, "
            "SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END) as total_out "
            "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
            "GROUP BY pi.ingredient_id")
        cursor.execute(avail_sql)
        avail_map = {}
        for r in cursor.fetchall():
            d = dict(r)
            avail_map[d["ingredient_id"]] = d["total_in"] - d["total_out"]
        conn.close()

        self.cmb_ingredient.clear()
        for d in ingredients:
            avail = avail_map.get(d["id"], 0)
            if avail < 0:
                avail = 0
            self.cmb_ingredient.addItem(
                f"{d['name']}（可用:{avail:.1f}{d.get('unit', '')}）", d["id"])

    def _add_item(self):
        ing_id = self.cmb_ingredient.currentData()
        ing_name = self.cmb_ingredient.currentText().split("（")[0]
        if not ing_id:
            QMessageBox.warning(self, "提示", "请选择产品")
            return
        try:
            qty = float(self.spin_qty.text() or "0")
        except ValueError:
            QMessageBox.warning(self, "提示", "请输入有效的数量")
            return
        if qty <= 0:
            QMessageBox.warning(self, "提示", "出库数量必须大于0")
            return
        for item in self.items:
            if item["ingredient_id"] == ing_id:
                item["qty"] += qty
                self._refresh_detail_table()
                self.spin_qty.setText("1")
                return
        self.items.append({"ingredient_id": ing_id, "name": ing_name, "qty": qty})
        self._refresh_detail_table()
        self.spin_qty.setText("1")

    def _refresh_detail_table(self):
        self.detail_table.setRowCount(len(self.items))
        for i, item in enumerate(self.items):
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 0, sn)
            _ci10 = QTableWidgetItem(item["name"])
            _ci10.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 1, _ci10)
            _ci11 = QTableWidgetItem(f"{item['qty']:.1f}")
            _ci11.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 2, _ci11)
            btn_del = make_table_button("删除", "delete")
            btn_del.clicked.connect(lambda checked, idx=i: self._remove_item(idx))
            wrapper = QWidget()
            wrapper.setObjectName("btnCell")
            wrapper.setStyleSheet("#btnCell { background: transparent; border: none; }")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_del)
            self.detail_table.setCellWidget(i, 3, wrapper)

    def _remove_item(self, idx):
        if 0 <= idx < len(self.items):
            self.items.pop(idx)
            self._refresh_detail_table()

    def _save(self):
        if not self.items:
            QMessageBox.warning(self, "提示", "请添加出库明细")
            return
        _sid, _all = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        try:
            out_no = generate_order_no("CK")
            for item in self.items:
        # 基于交易记录计算可用库存 = 累计进货 - 累计出库
                if _all:
                    cursor.execute(
                        "SELECT "
                        "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END), 0) - "
                        "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END), 0) as total_in, "
                        "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END), 0) as total_out "
                        "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
                        "WHERE pi.ingredient_id=?",
                        (item["ingredient_id"],))
                else:
                    cursor.execute(
                        "SELECT "
                        "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END), 0) - "
                        "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END), 0) as total_in, "
                        "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END), 0) as total_out "
                        "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
                        "WHERE pi.ingredient_id=? "
                        "AND (p.store_id=? OR p.store_id IS NULL)",
                        (item["ingredient_id"], _sid))
                row = cursor.fetchone()
                if row:
                    d = dict(row)
                    available = d["total_in"] - d["total_out"]
                    if available < 0:
                        available = 0
                    if available < item["qty"]:
                        QMessageBox.warning(
                            self, "库存不足",
                            f"{item['name']} 可用库存不足！当前可用: {available:.2f}")
                        conn.close()
                        return
            cursor.execute(
                "INSERT INTO purchases (purchase_no, supplier_id, total_amount, "
                "purchase_date, remark, store_id, operator) VALUES (?,?,?,?,?,?,?)",
                (out_no, None, 0, self.date_out.date().toString("yyyy-MM-dd"),
                 f"[出库]{self.cmb_reason.currentText()} {self.txt_remark.text()}",
                 _sid, self.txt_operator.text()))
            out_id = cursor.lastrowid
            for item in self.items:
                cursor.execute(
                    "INSERT INTO purchase_items "
                    "(purchase_id, ingredient_id, quantity, unit_price, total_price) "
                    "VALUES (?,?,?,?,?)",
                    (out_id, item["ingredient_id"], item["qty"], 0, 0))
                cursor.execute(
                    "UPDATE ingredients SET stock = stock - ? WHERE id=?",
                    (item["qty"], item["ingredient_id"]))
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", f"出库单 {out_no} 已保存")
            self.accept()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"保存出库单失败：{e}")
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════
# 出库记录查看对话框
# ═══════════════════════════════════════════════════════════
class StockOutRecordDialog(QDialog):
    """查看产品出库记录，支持删除单条出库单"""

    def __init__(self, ingredient_name, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"出库记录 - {ingredient_name}")
        self.resize(580, 420)
        self.setMinimumSize(500, 320)
        self.setStyleSheet(DLG_STYLE)
        self._parent = parent
        self._rows = rows
        self._data_changed = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)

        total_out = sum(dict(r)["quantity"] for r in self._rows)
        title = QLabel(f"出库记录（合计：{total_out:.1f}）")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLOR['border']}; max-height: 1px;")
        layout.addWidget(line)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["序号", "出库日期", "经办人", "数量", "备注", "操作"])
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setStretchLastSection(False)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(5, 130)
        self.table.setMinimumHeight(220)
        layout.addWidget(self.table)
        self._fill_table()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet(_dlg_cancel_style())
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _fill_table(self):
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            d = dict(r)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sn)
            _ci12 = QTableWidgetItem(d.get("purchase_date", ""))
            _ci12.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, _ci12)
            _ci13 = QTableWidgetItem(d.get("operator", ""))
            _ci13.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, _ci13)
            qty_item = QTableWidgetItem(f"{d['quantity']:.1f}")
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, qty_item)
            _ci14 = QTableWidgetItem(d.get("remark", ""))
            _ci14.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, _ci14)
            btn_edit = make_table_button("编辑", "edit")
            btn_edit.clicked.connect(
                lambda checked, pid=d["purchase_id"]: self._edit_record(pid))
            btn_del = make_table_button("撤销", "delete")
            btn_del.clicked.connect(
                lambda checked, pid=d["purchase_id"]: self._delete_record(pid))
            wrapper = QWidget()
            wrapper.setObjectName("btnCell")
            wrapper.setStyleSheet("#btnCell { background: transparent; border: none; }")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.setSpacing(4)
            wl.addWidget(btn_edit)
            wl.addWidget(btn_del)
            self.table.setCellWidget(i, 5, wrapper)

    def _delete_record(self, pid):
        reply = QMessageBox.question(self, "确认撤销",
            "确定撤销该出库记录吗？撤销后库存将自动恢复。")
        if reply != QMessageBox.Yes:
            return
        if self._parent and hasattr(self._parent, "delete_stockout"):
            self._parent.delete_stockout(pid)
            self._data_changed = True
            self.accept()

    def _edit_record(self, pid):
        """编辑出库记录：修改日期、经办人、数量、备注"""
        from PyQt5.QtWidgets import QDialog as _Dlg, QFormLayout as _Form,             QDoubleSpinBox as _DSpin, QLineEdit as _LE, QLabel as _Lbl
        # 找到当前行数据
        row_data = None
        for r in self._rows:
            if dict(r)["purchase_id"] == pid:
                row_data = dict(r)
                break
        if not row_data:
            return
        dlg = _Dlg(self)
        dlg.setWindowTitle("编辑出库记录")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(DLG_STYLE)
        form = _Form(dlg)
        lbl_name = _Lbl(row_data.get("ingredient_name", ""))
        lbl_name.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {COLOR['primary']};")
        form.addRow("产品：", lbl_name)
        # 日期
        from PyQt5.QtWidgets import QDateEdit as _DE
        spn_date = _DE()
        spn_date.setCalendarPopup(True)
        spn_date.setDisplayFormat("yyyy-MM-dd")
        spn_date.setStyleSheet(INPUT_STYLE)
        try:
            from PyQt5.QtCore import QDate as _QD
            parts = row_data.get("purchase_date", "").split("-")
            if len(parts) == 3:
                spn_date.setDate(_QD(int(parts[0]), int(parts[1]), int(parts[2])))
        except (ValueError, TypeError):
            pass
        form.addRow("出库日期：", spn_date)
        # 经办人
        txt_op = _LE(row_data.get("operator", "") or "")
        txt_op.setStyleSheet(INPUT_STYLE)
        form.addRow("经办人：", txt_op)
        # 数量
        spn_qty = _DSpin()
        spn_qty.setRange(0.0001, 999999)
        spn_qty.setDecimals(10)
        spn_qty.setValue(row_data.get("quantity", 0) or 0)
        spn_qty.setStyleSheet(INPUT_STYLE)
        form.addRow("出库数量：", spn_qty)
        # 备注
        txt_remark = _LE(row_data.get("remark", "") or "")
        txt_remark.setStyleSheet(INPUT_STYLE)
        form.addRow("备注：", txt_remark)
        # 保存按钮
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(primary_btn)
        btn_save.clicked.connect(dlg.accept)
        form.addRow(btn_save)
        if dlg.exec_() != _Dlg.Accepted:
            return
        new_date = spn_date.date().toString("yyyy-MM-dd")
        new_op = txt_op.text().strip()
        new_qty = spn_qty.value()
        new_remark = txt_remark.text().strip()
        if new_qty <= 0:
            QMessageBox.warning(self, "提示", "出库数量必须大于0")
            return
        if self._parent and hasattr(self._parent, "edit_stockout"):
            self._parent.edit_stockout(pid, new_date, new_op, new_qty, new_remark)
            self._data_changed = True
            self.accept()

    def data_changed(self):
        return self._data_changed


# ═══════════════════════════════════════════════════════════
# 供应商对话框
# ═══════════════════════════════════════════════════════════
class SupplierDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("编辑供应商" if data else "添加供应商")
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
        title = QLabel("编辑供应商" if self.data else "添加供应商")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {COLOR['text_primary']};")
        layout.addWidget(title)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLOR['border']}; max-height: 1px;")
        layout.addWidget(line)
        form = QFormLayout()
        form.setSpacing(20)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("供应商名称（必填）")
        self.txt_name.setFixedHeight(40)
        form.addRow("名称 *：", self.txt_name)
        self.txt_contact = QLineEdit()
        self.txt_contact.setPlaceholderText("联系人")
        self.txt_contact.setFixedHeight(40)
        form.addRow("联系人：", self.txt_contact)
        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("联系电话")
        self.txt_phone.setFixedHeight(40)
        form.addRow("电话：", self.txt_phone)
        self.txt_address = QLineEdit()
        self.txt_address.setPlaceholderText("地址")
        self.txt_address.setFixedHeight(40)
        form.addRow("地址：", self.txt_address)
        self.cmb_payment = QComboBox()
        self.cmb_payment.setStyleSheet(COMBO_STYLE)
        self.cmb_payment.setFixedHeight(40)
        self.cmb_payment.setEditable(True)
        self.cmb_payment.addItems(["现结", "月结", "周结", "货到付款", "预付款", "季结", "半年结"])
        form.addRow("结款方式：", self.cmb_payment)
        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注（可选）")
        self.txt_remark.setFixedHeight(40)
        form.addRow("备注：", self.txt_remark)
        layout.addLayout(form)
        layout.addStretch()
        btn_layout = QHBoxLayout()
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
        self.txt_name.setText(self.data.get("name", ""))
        self.txt_contact.setText(self.data.get("contact", ""))
        self.txt_phone.setText(self.data.get("phone", ""))
        self.txt_address.setText(self.data.get("address", ""))
        payment = self.data.get("payment_method", "") or ""
        idx = self.cmb_payment.findText(payment)
        if idx >= 0:
            self.cmb_payment.setCurrentIndex(idx)
        else:
            self.cmb_payment.setCurrentText(payment)
        self.txt_remark.setText(self.data.get("remark", ""))

    def _save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入供应商名称")
            return
        exclude_id = self.data["id"] if self.data else None
        ok, msg = check_duplicate_supplier(name, exclude_id)
        if not ok:
            QMessageBox.warning(self, "重复提示", msg)
            return
        _sid, _ = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        if self.data:
            cursor.execute(
                "UPDATE suppliers SET name=?,contact=?,phone=?,address=?,payment_method=?,remark=? WHERE id=?",
                (name, self.txt_contact.text(), self.txt_phone.text(),
                 self.txt_address.text(), self.cmb_payment.currentText().strip(),
                 self.txt_remark.text(), self.data["id"]))
        else:
            cursor.execute(
                "INSERT INTO suppliers (name,contact,phone,address,payment_method,remark,store_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (name, self.txt_contact.text(), self.txt_phone.text(),
                 self.txt_address.text(), self.cmb_payment.currentText().strip(),
                 self.txt_remark.text(), _sid))
        conn.commit()
        _sync_cloud()
        self.accept()


# ═══════════════════════════════════════════════════════════
# 产品（食材）对话框
# ═══════════════════════════════════════════════════════════
class IngredientDialog(QDialog):
    ING_CATEGORIES = ["", "蔬菜", "肉类", "水产", "禽蛋", "调料",
                      "粮油", "冻品", "干货", "酒水饮料", "其他"]
    ING_UNITS = ["斤", "kg", "g", "个", "包", "箱", "瓶", "袋", "条", "只", "升", "份"]

    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("编辑产品" if data else "添加产品")
        self.resize(560, 560)
        self.setMinimumSize(500, 500)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()
        if data:
            self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel("编辑产品" if self.data else "添加产品")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {COLOR['text_primary']};")
        layout.addWidget(title)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLOR['border']}; max-height: 1px;")
        layout.addWidget(line)
        form = QFormLayout()
        form.setSpacing(20)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cmb_category = QComboBox()
        self.cmb_category.setStyleSheet(COMBO_STYLE)
        self.cmb_category.addItems(self.ING_CATEGORIES)
        self.cmb_category.setFixedHeight(40)
        form.addRow("分类：", self.cmb_category)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("品名（必填）")
        self.txt_name.setFixedHeight(40)
        form.addRow("品名 *：", self.txt_name)

        self.txt_brand = QLineEdit()
        self.txt_brand.setPlaceholderText("品牌")
        self.txt_brand.setFixedHeight(40)
        form.addRow("品牌：", self.txt_brand)

        self.txt_spec = QLineEdit()
        self.txt_spec.setPlaceholderText("规格")
        self.txt_spec.setFixedHeight(40)
        form.addRow("规格：", self.txt_spec)

        self.cmb_unit = QComboBox()
        self.cmb_unit.setStyleSheet(COMBO_STYLE)
        self.cmb_unit.addItems(self.ING_UNITS)
        self.cmb_unit.setFixedHeight(40)
        form.addRow("单位：", self.cmb_unit)

        self.spin_expiry_months = QSpinBox()
        self.spin_expiry_months.setRange(0, 999)
        self.spin_expiry_months.setFixedHeight(40)
        self.spin_expiry_months.setSuffix(" 个月")
        form.addRow("保质期（月）：", self.spin_expiry_months)

        self.spin_expiry_days = QSpinBox()
        self.spin_expiry_days.setRange(0, 9999)
        self.spin_expiry_days.setFixedHeight(40)
        self.spin_expiry_days.setSuffix(" 天")
        form.addRow("保质期（天）：", self.spin_expiry_days)

        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注（可选）")
        self.txt_remark.setFixedHeight(40)
        form.addRow("备注：", self.txt_remark)
        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
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
        self.txt_name.setText(self.data["name"])
        self.txt_brand.setText(self.data.get("brand", ""))
        self.txt_spec.setText(self.data.get("spec", ""))
        self.cmb_unit.setCurrentText(self.data.get("unit", "斤"))
        self.spin_expiry_months.setValue(self.data.get("expiry_months", 0) or 0)
        self.spin_expiry_days.setValue(self.data.get("expiry_days", 0) or 0)
        self.cmb_category.setCurrentText(self.data.get("category", ""))
        self.txt_remark.setText(self.data.get("remark", ""))

    def _save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入品名")
            return
        exclude_id = self.data["id"] if self.data else None
        ok, msg = check_duplicate_ingredient(name, exclude_id)
        if not ok:
            QMessageBox.warning(self, "重复提示", msg)
            return
        _sid, _ = _ctx().get_store_filter()
        conn = get_connection()
        cursor = conn.cursor()
        brand = self.txt_brand.text().strip()
        spec = self.txt_spec.text().strip()
        exp_m = self.spin_expiry_months.value()
        exp_d = self.spin_expiry_days.value()
        if self.data:
            cursor.execute(
                "UPDATE ingredients SET name=?,brand=?,spec=?,unit=?,"
                "expiry_months=?,expiry_days=?,category=?,remark=? WHERE id=?",
                (name, brand, spec, self.cmb_unit.currentText(), exp_m, exp_d,
                 self.cmb_category.currentText(), self.txt_remark.text(), self.data["id"]))
        else:
            cursor.execute(
                "INSERT INTO ingredients "
                "(name,brand,spec,unit,expiry_months,expiry_days,category,remark,store_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (name, brand, spec, self.cmb_unit.currentText(), exp_m, exp_d,
                 self.cmb_category.currentText(), self.txt_remark.text(), _sid))
        conn.commit()
        _sync_cloud()
        self.accept()


# ═══════════════════════════════════════════════════════════
# 进销存主界面 Widget —— 6 Tab
# ═══════════════════════════════════════════════════════════
class PurchaseWidget(QWidget):

    def __init__(self):
        super().__init__()
        self._build_ui()
        # load_data() 延迟到首次切换时调用（懒加载）

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        title = QLabel("进销存管理")
        title.setFont(__import__("utils.font_utils", fromlist=["make_font"]).make_font(14, bold=True))
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {COLOR['border']}; top: -1px; }}
            QTabBar::tab {{
                background: {COLOR['bg_page']};
                color: {COLOR['text_secondary']};
                padding: 8px 16px; font-size: 13px;
                border: 1px solid {COLOR['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: #fff; color: {COLOR['primary']}; font-weight: bold;
            }}
            QTabBar::tab:hover {{ background: {COLOR['primary_light']}; }}
        """)

        self.tab_prev_balance = QWidget()
        self._init_prev_balance_tab()
        self.tabs.addTab(self.tab_prev_balance, "上月结存")

        self.tab_ledger = QWidget()
        self._init_ledger_tab()
        self.tabs.addTab(self.tab_ledger, "进货台账")

        self.tab_inout = QWidget()
        self._init_inout_tab()
        self.tabs.addTab(self.tab_inout, "出库管理")

        self.tab_supplier_query = QWidget()
        self._init_supplier_query_tab()
        self.tabs.addTab(self.tab_supplier_query, "供货商进货明细")

        self.tab_supplier = QWidget()
        self._init_supplier_tab()
        self.tabs.addTab(self.tab_supplier, "供货商管理")

        self.tab_product = QWidget()
        self._init_product_tab()
        self.tabs.addTab(self.tab_product, "产品数据")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    # ── Tab: 产品数据 ──
    def _init_product_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        btn_add = QPushButton("+ 添加产品")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self.add_ingredient)
        toolbar.addWidget(btn_add)
        btn_export = QPushButton("导出Excel")
        btn_export.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_export.clicked.connect(lambda: self._export("ingredients"))
        toolbar.addWidget(btn_export)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("搜索："))
        self.txt_product_search = QLineEdit()
        self.txt_product_search.setPlaceholderText("输入品名/品牌/分类...")
        self.txt_product_search.setFixedWidth(200)
        self.txt_product_search.setStyleSheet(INPUT_STYLE)
        self.txt_product_search.textChanged.connect(self.load_ingredients)
        toolbar.addWidget(self.txt_product_search)
        toolbar.addWidget(QLabel("分类："))
        self.cmb_product_filter = QComboBox()
        self.cmb_product_filter.setStyleSheet(COMBO_STYLE)
        self.cmb_product_filter.addItem("全部")
        self.cmb_product_filter.addItems(
            ["蔬菜", "肉类", "水产", "禽蛋", "调料", "粮油", "冻品", "干货", "酒水饮料", "其他"])
        self.cmb_product_filter.currentIndexChanged.connect(self.load_ingredients)
        toolbar.addWidget(self.cmb_product_filter)
        layout.addLayout(toolbar)

        self.product_table = QTableWidget()
        self.product_table.setColumnCount(8)
        self.product_table.setHorizontalHeaderLabels(
            ["序号", "品名", "品牌", "分类", "规格", "单位", "保质期", "操作"])
        self.product_table.setColumnWidth(0, 50)
        hdr = self.product_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setStretchLastSection(False)
        self.product_table.setAlternatingRowColors(True)
        self.product_table.setStyleSheet(TABLE_STYLE)
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.verticalHeader().setDefaultSectionSize(52)
        self.product_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.product_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.product_table)
        self.tab_product.setLayout(layout)

    # ── Tab: 供货商管理 ──
    def _init_supplier_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        btn_add = QPushButton("+ 添加供应商")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self.add_supplier)
        toolbar.addWidget(btn_add)
        btn_export = QPushButton("导出Excel")
        btn_export.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_export.clicked.connect(lambda: self._export("suppliers"))
        toolbar.addWidget(btn_export)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.supplier_table = QTableWidget()
        self.supplier_table.setColumnCount(7)
        self.supplier_table.setHorizontalHeaderLabels(
            ["序号", "名称", "联系人", "电话", "结款方式", "地址", "操作"])
        self.supplier_table.setColumnWidth(0, 50)
        self.supplier_table.setColumnWidth(1, 140)
        self.supplier_table.setColumnWidth(2, 100)
        self.supplier_table.setColumnWidth(3, 120)
        self.supplier_table.setColumnWidth(4, 100)
        self.supplier_table.setColumnWidth(5, 200)
        self.supplier_table.setColumnWidth(6, 120)
        hdr = self.supplier_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(False)
        self.supplier_table.setAlternatingRowColors(True)
        self.supplier_table.setStyleSheet(TABLE_STYLE)
        self.supplier_table.verticalHeader().setVisible(False)
        self.supplier_table.verticalHeader().setDefaultSectionSize(52)
        self.supplier_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.supplier_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.supplier_table)
        self.tab_supplier.setLayout(layout)

    # ── Tab: 进货台账 ──
    def _init_ledger_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        btn_add = QPushButton("+ 新增进货")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self.add_purchase)
        toolbar.addWidget(btn_add)
        btn_return = QPushButton("- 退货")
        btn_return.setStyleSheet(danger_btn)
        btn_return.clicked.connect(self.add_purchase_return)
        toolbar.addWidget(btn_return)
        btn_export = QPushButton("导出Excel")
        btn_export.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_export.clicked.connect(self._export_ledger)
        toolbar.addWidget(btn_export)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("查询月份："))
        self.ledger_date = ModernMonthEdit()
        self.ledger_date.setMinimumDate(QDate(2020, 1, 1))
        self.ledger_date.setMaximumDate(QDate(2100, 12, 31))
        self.ledger_date.setStyleSheet(INPUT_STYLE)
        toolbar.addWidget(self.ledger_date)
        self.ledger_date.dateChanged.connect(self.load_ledger)
        btn_filter = QPushButton("查询")
        btn_filter.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_filter.clicked.connect(self.load_ledger)
        toolbar.addWidget(btn_filter)
        layout.addLayout(toolbar)

        self.ledger_table = QTableWidget()
        self.ledger_table.setColumnCount(18)
        self.ledger_table.setHorizontalHeaderLabels([
            "序号", "进货日期", "品名", "品类", "规格", "单位",
            "用途", "数量", "单价", "金额", "生产日期", "保质期",
            "储存天数", "过期提醒", "供货商", "地址", "电话", "操作"])
        hdr = self.ledger_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        widths = [50, 120, 120, 80, 120, 80, 80, 80, 100, 120,
                  120, 80, 80, 140, 160, 200, 120, 120]
        for col, w in enumerate(widths):
            self.ledger_table.setColumnWidth(col, w)
        hdr.setStretchLastSection(False)
        self.ledger_table.setAlternatingRowColors(True)
        self.ledger_table.setStyleSheet(TABLE_STYLE)
        self.ledger_table.verticalHeader().setVisible(False)
        self.ledger_table.verticalHeader().setDefaultSectionSize(52)
        self.ledger_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ledger_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.ledger_table)

        self.lbl_ledger_total = QLabel("")
        self.lbl_ledger_total.setStyleSheet(
            f"color: {COLOR['primary']}; font-size: 13px; font-weight: bold; padding: 4px 0;")
        layout.addWidget(self.lbl_ledger_total)
        self.tab_ledger.setLayout(layout)

    # ── Tab: 供货商进货明细 ──
    def _init_supplier_query_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel("供货商："))
        self.cmb_sq_supplier = QComboBox()
        self.cmb_sq_supplier.setStyleSheet(COMBO_STYLE)
        self.cmb_sq_supplier.setFixedWidth(200)
        toolbar.addWidget(self.cmb_sq_supplier)
        toolbar.addWidget(QLabel("从："))
        self.sq_date_from = ModernDateEdit()
        self.sq_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.sq_date_from.setDisplayFormat("yyyy-MM-dd")
        self.sq_date_from.setFixedWidth(160)
        toolbar.addWidget(self.sq_date_from)
        toolbar.addWidget(QLabel("至："))
        self.sq_date_to = ModernDateEdit()
        self.sq_date_to.setDate(QDate.currentDate())
        self.sq_date_to.setDisplayFormat("yyyy-MM-dd")
        self.sq_date_to.setFixedWidth(160)
        toolbar.addWidget(self.sq_date_to)
        btn_query = QPushButton("查询")
        btn_query.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_query.clicked.connect(self.load_supplier_query)
        toolbar.addWidget(btn_query)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.lbl_sq_summary = QLabel("")
        self.lbl_sq_summary.setStyleSheet(
            f"color: {COLOR['text_secondary']}; font-size: 13px; padding: 4px 0;")
        layout.addWidget(self.lbl_sq_summary)

        self.sq_table = QTableWidget()
        self.sq_table.setColumnCount(8)
        self.sq_table.setHorizontalHeaderLabels(
            ["序号", "进货日期", "单号", "品名", "数量", "单价", "金额", "备注"])
        self.sq_table.setColumnWidth(0, 50)
        hdr = self.sq_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setStretchLastSection(False)
        self.sq_table.setAlternatingRowColors(True)
        self.sq_table.setStyleSheet(TABLE_STYLE)
        self.sq_table.verticalHeader().setVisible(False)
        self.sq_table.verticalHeader().setDefaultSectionSize(52)
        self.sq_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sq_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.sq_table)

        layout.addWidget(QLabel("按日期汇总："))
        self.sq_daily_table = QTableWidget()
        self.sq_daily_table.setColumnCount(4)
        self.sq_daily_table.setHorizontalHeaderLabels(
            ["序号", "日期", "进货次数", "金额合计"])
        self.sq_daily_table.setColumnWidth(0, 50)
        hdr = self.sq_daily_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setStretchLastSection(False)
        self.sq_daily_table.setAlternatingRowColors(True)
        self.sq_daily_table.setStyleSheet(TABLE_STYLE)
        self.sq_daily_table.verticalHeader().setVisible(False)
        self.sq_daily_table.verticalHeader().setDefaultSectionSize(52)
        self.sq_daily_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.sq_daily_table)
        self.tab_supplier_query.setLayout(layout)

    # ── Tab: 出库管理 ──
    def _init_inout_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        btn_add = QPushButton("+ 新增出库")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self.add_stockout)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(QLabel("月份："))
        self.inout_month = QComboBox()
        self.inout_month.setStyleSheet(COMBO_STYLE)
        self.inout_month.setFixedWidth(100)
        self.inout_month.currentIndexChanged.connect(self.load_inout)
        toolbar.addWidget(self.inout_month)
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_refresh.clicked.connect(self.load_inout)
        toolbar.addWidget(btn_refresh)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.lbl_inout_warning = QLabel("")
        self.lbl_inout_warning.setStyleSheet(
            f"color: {COLOR['danger']}; font-size: 13px; padding: 4px 0;")
        layout.addWidget(self.lbl_inout_warning)

        self.inout_table = QTableWidget()
        self.inout_table.setColumnCount(12)
        self.inout_table.setHorizontalHeaderLabels([
            "序号", "品名", "规格", "单位", "上月结存", "本月进货",
            "可用库存", "本月出库", "当前库存", "库存状态", "出库记录", "操作"])
        self.inout_table.setColumnWidth(0, 50)
        self.inout_table.setColumnWidth(2, 100)
        self.inout_table.setColumnWidth(3, 60)
        self.inout_table.setColumnWidth(4, 90)
        self.inout_table.setColumnWidth(5, 90)
        self.inout_table.setColumnWidth(6, 90)
        self.inout_table.setColumnWidth(7, 90)
        self.inout_table.setColumnWidth(8, 90)
        self.inout_table.setColumnWidth(9, 80)
        self.inout_table.setColumnWidth(10, 90)
        self.inout_table.setColumnWidth(11, 80)
        hdr = self.inout_table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setStretchLastSection(False)
        self.inout_table.setAlternatingRowColors(True)
        self.inout_table.setStyleSheet(TABLE_STYLE)
        self.inout_table.verticalHeader().setVisible(False)
        self.inout_table.verticalHeader().setDefaultSectionSize(52)
        self.inout_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.inout_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.inout_table)
        self.tab_inout.setLayout(layout)

    # ── Tab: 上月结存 ──
    def _init_prev_balance_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel("查询月份："))
        self.pb_date = ModernMonthEdit()
        self.pb_date.setMinimumDate(QDate(2020, 1, 1))
        self.pb_date.setMaximumDate(QDate(2100, 12, 31))
        self.pb_date.setStyleSheet(INPUT_STYLE)
        toolbar.addWidget(self.pb_date)
        btn_refresh = QPushButton("查询")
        btn_refresh.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_refresh.clicked.connect(self.load_prev_balance)
        toolbar.addWidget(btn_refresh)
        btn_add_pb = QPushButton("+ 录入")
        btn_add_pb.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_add_pb.clicked.connect(self._add_prev_balance)
        toolbar.addWidget(btn_add_pb)
        btn_init = QPushButton("初始化库存")
        btn_init.setStyleSheet(success_btn)
        btn_init.clicked.connect(self._init_stock)
        toolbar.addWidget(btn_init)
        btn_export = QPushButton("导出Excel")
        btn_export.setStyleSheet(
            f"background-color: {COLOR['primary']}; color: white; "
            f"border: none; border-radius: 4px; padding: 8px 16px;")
        btn_export.clicked.connect(self._export_prev_balance)
        toolbar.addWidget(btn_export)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.lbl_pb_summary = QLabel("")
        self.lbl_pb_summary.setStyleSheet(
            f"color: {COLOR['text_secondary']}; font-size: 13px; padding: 4px 0;")
        layout.addWidget(self.lbl_pb_summary)

        self.prev_balance_table = QTableWidget()
        self.prev_balance_table.setColumnCount(10)
        self.prev_balance_table.setHorizontalHeaderLabels(
            ["序号", "品名", "分类", "规格", "单位", "供货商", "上月结存", "单价", "金额", "操作"])
        self.prev_balance_table.setColumnWidth(0, 50)
        self.prev_balance_table.setColumnWidth(1, 140)
        self.prev_balance_table.setColumnWidth(2, 80)
        self.prev_balance_table.setColumnWidth(3, 100)
        self.prev_balance_table.setColumnWidth(4, 60)
        self.prev_balance_table.setColumnWidth(5, 140)
        self.prev_balance_table.setColumnWidth(6, 90)
        self.prev_balance_table.setColumnWidth(7, 80)
        self.prev_balance_table.setColumnWidth(8, 100)
        self.prev_balance_table.setColumnWidth(9, 120)
        hdr = self.prev_balance_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(False)
        self.prev_balance_table.setStyleSheet(TABLE_STYLE)
        self.prev_balance_table.setAlternatingRowColors(True)
        self.prev_balance_table.verticalHeader().setVisible(False)
        self.prev_balance_table.verticalHeader().setDefaultSectionSize(52)
        self.prev_balance_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.prev_balance_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.prev_balance_table)
        self.tab_prev_balance.setLayout(layout)
        self.pb_date.dateChanged.connect(self.load_prev_balance)

    # ═══════════════════════════════════════════════════════════
    # 数据加载
    # ═══════════════════════════════════════════════════════════
    def load_data(self):
        self.load_ingredients()
        self.load_suppliers()
        self.load_ledger()
        self._load_sq_suppliers()
        self._init_inout_months()
        self.load_inout()
        self.load_prev_balance()
        self._update_stock_warning_tab()

    def _update_stock_warning_tab(self):
        low_items = get_low_stock_items()
        idx = self.tabs.indexOf(self.tab_product)
        if low_items:
            self.tabs.setTabText(idx, f"产品数据 ({len(low_items)}项不足)")
        else:
            self.tabs.setTabText(idx, "产品数据")

    def _export(self, table_name):
        _sid, _ = _ctx().get_store_filter()
        export_to_excel(table_name, self, _sid)

    def _export_ledger(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存文件", "进货台账.xlsx", "Excel Files (*.xlsx)")
        if not path:
            return
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "进货台账"
        headers = ["进货日期", "品名", "品类", "规格", "单位", "用途", "数量", "单价", "金额",
                   "生产日期", "保质期", "储存天数", "过期提醒", "供货商"]
        ws.append(headers)
        for row in range(self.ledger_table.rowCount()):
            row_data = []
            for col in range(min(14, self.ledger_table.columnCount())):
                item = self.ledger_table.item(row, col)
                row_data.append(item.text() if item else "")
            ws.append(row_data)
        wb.save(path)
        QMessageBox.information(self, "导出成功", f"已导出到 {path}")

    # ── 产品数据 ──
    def load_ingredients(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        search_text = self.txt_product_search.text().strip()
        cat_filter = self.cmb_product_filter.currentText()
        sql = ("SELECT i.*, s.name as supplier_name FROM ingredients i "
               "LEFT JOIN suppliers s ON i.supplier_id = s.id WHERE 1=1")
        params = []
        if not _all:
            sql += " AND (i.store_id=? OR i.store_id IS NULL)"
            params.append(_sid)
        if search_text:
            sql += " AND (i.name LIKE ? OR i.brand LIKE ? OR i.category LIKE ?)"
            params.extend([f"%{search_text}%"] * 3)
        if cat_filter and cat_filter != "全部":
            sql += " AND i.category=?"
            params.append(cat_filter)
        sql += " ORDER BY i.id"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        self.product_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.product_table.setItem(i, 0, sn)
            _ci15 = QTableWidgetItem(r["name"])
            _ci15.setTextAlignment(Qt.AlignCenter)
            self.product_table.setItem(i, 1, _ci15)
            _ci16 = QTableWidgetItem(r.get("brand", "") or "")
            _ci16.setTextAlignment(Qt.AlignCenter)
            self.product_table.setItem(i, 2, _ci16)
            _ci17 = QTableWidgetItem(r.get("category", "") or "")
            _ci17.setTextAlignment(Qt.AlignCenter)
            self.product_table.setItem(i, 3, _ci17)
            _ci18 = QTableWidgetItem(r.get("spec", "") or "")
            _ci18.setTextAlignment(Qt.AlignCenter)
            self.product_table.setItem(i, 4, _ci18)
            _ci19 = QTableWidgetItem(r.get("unit", "") or "")
            _ci19.setTextAlignment(Qt.AlignCenter)
            self.product_table.setItem(i, 5, _ci19)
            exp_m = r.get("expiry_months", 0) or 0
            exp_d = r.get("expiry_days", 0) or 0
            parts = []
            if exp_m > 0:
                parts.append(f"{exp_m}月")
            if exp_d > 0:
                parts.append(f"{exp_d}天")
            _ci20 = QTableWidgetItem(" ".join(parts) if parts else "")
            _ci20.setTextAlignment(Qt.AlignCenter)
            self.product_table.setItem(i, 6, _ci20)
            widget = QWidget()
            widget.setObjectName("btnCell")
            widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
            hl = QHBoxLayout(widget)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            eid = r["id"]
            btn_edit.clicked.connect(lambda checked, eid=eid: self.edit_ingredient(eid))
            btn_del.clicked.connect(lambda checked, eid=eid: self.delete_ingredient(eid))
            hl.addStretch()
            hl.addWidget(btn_edit)
            hl.addWidget(btn_del)
            hl.addStretch()
            self.product_table.setCellWidget(i, 7, widget)

    def add_ingredient(self):
        dlg = IngredientDialog(self)
        if dlg.exec_():
            self.load_ingredients()
            self.load_inout()
            self._update_stock_warning_tab()

    def edit_ingredient(self, ing_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ingredients WHERE id=?", (ing_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return
        dlg = IngredientDialog(self, data=dict(row))
        if dlg.exec_():
            self.load_ingredients()
            self.load_inout()

    def delete_ingredient(self, ing_id):
        reply = QMessageBox.question(self, "确认", "确定删除该产品吗？")
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ingredients WHERE id=?", (ing_id,))
        conn.commit()
        _sync_cloud()
        self.load_ingredients()
        self.load_inout()
        self._update_stock_warning_tab()

    # ── 供货商 ──
    def load_suppliers(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT * FROM suppliers ORDER BY id")
        else:
            cursor.execute(
                "SELECT * FROM suppliers WHERE store_id=? OR store_id IS NULL ORDER BY id", (_sid,))
        rows = cursor.fetchall()
        conn.close()
        self.supplier_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.supplier_table.setItem(i, 0, sn)
            _ci21 = QTableWidgetItem(r.get("name", ""))
            _ci21.setTextAlignment(Qt.AlignCenter)
            self.supplier_table.setItem(i, 1, _ci21)
            _ci22 = QTableWidgetItem(r.get("contact", ""))
            _ci22.setTextAlignment(Qt.AlignCenter)
            self.supplier_table.setItem(i, 2, _ci22)
            _ci23 = QTableWidgetItem(r.get("phone", ""))
            _ci23.setTextAlignment(Qt.AlignCenter)
            self.supplier_table.setItem(i, 3, _ci23)
            _ci24 = QTableWidgetItem(r.get("payment_method", "") or "")
            _ci24.setTextAlignment(Qt.AlignCenter)
            self.supplier_table.setItem(i, 4, _ci24)
            _ci25 = QTableWidgetItem(r.get("address", ""))
            _ci25.setTextAlignment(Qt.AlignCenter)
            self.supplier_table.setItem(i, 5, _ci25)
            widget = QWidget()
            widget.setObjectName("btnCell")
            widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
            hl = QHBoxLayout(widget)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            sid = r["id"]
            btn_edit.clicked.connect(lambda checked, sid=sid: self.edit_supplier(sid))
            btn_del.clicked.connect(lambda checked, sid=sid: self.delete_supplier(sid))
            hl.addWidget(btn_edit)
            hl.addWidget(btn_del)
            hl.addStretch()
            self.supplier_table.setCellWidget(i, 6, widget)

    def add_supplier(self):
        dlg = SupplierDialog(self)
        if dlg.exec_():
            self.load_suppliers()
            self._load_sq_suppliers()

    def edit_supplier(self, sid):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM suppliers WHERE id=?", (sid,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return
        dlg = SupplierDialog(self, data=dict(row))
        if dlg.exec_():
            self.load_suppliers()
            self._load_sq_suppliers()

    def delete_supplier(self, sid):
        reply = QMessageBox.question(self, "确认", "确定删除该供应商吗？")
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM suppliers WHERE id=?", (sid,))
        conn.commit()
        _sync_cloud()
        self.load_suppliers()
        self._load_sq_suppliers()

    # ── 进货台账 ──
    def load_ledger(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        year = self.ledger_date.date().year()
        month = self.ledger_date.date().month()
        month_str = f"{year}-{month:02d}"
        sql = (
            "SELECT pi.*, p.purchase_no, p.purchase_date, p.supplier_id, p.remark as p_remark, "
            "i.name as ing_name, i.category, i.spec, i.unit, i.expiry_months, i.expiry_days, "
            "s.name as supplier_name, s.address as supplier_addr, s.phone as supplier_phone "
            "FROM purchase_items pi "
            "JOIN purchases p ON pi.purchase_id = p.id "
            "JOIN ingredients i ON pi.ingredient_id = i.id "
            "LEFT JOIN suppliers s ON p.supplier_id = s.id "
            "WHERE (p.purchase_no LIKE 'CG%' OR p.purchase_no LIKE 'TH%') "
            "AND strftime('%Y-%m', p.purchase_date) = ?")
        params = [month_str]
        if not _all:
            sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            params.append(_sid)
        sql += " ORDER BY p.purchase_date DESC, p.id DESC"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        self.ledger_table.setRowCount(len(rows))
        total_amount = 0
        expired_count = 0
        for i, row in enumerate(rows):
            r = dict(row)
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.ledger_table.setItem(i, 0, sn)
            total_amount += r.get("total_price", 0) or 0

            for col, key, fmt in [
                (1, "purchase_date", None), (2, "ing_name", None),
                (3, "category", None), (4, "spec", None), (5, "unit", None),
                (6, "usage", None),
                (7, "quantity", lambda v: f"{-v:.1f}" if r.get("purchase_no","").startswith("TH") else f"{v:.1f}"),
                (8, "unit_price", lambda v: f"¥{v:.2f}"),
                (9, "total_price", lambda v: f"¥{v:.2f}"),
                (10, "production_date", None),
            ]:
                val = r.get(key, "") or ""
                if fmt:
                    val = fmt(r.get(key, 0) or 0)
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                if key in ("ing_name", "spec"):
                    item.setToolTip(str(val))
                self.ledger_table.setItem(i, col, item)

            # 保质期
            exp_m = r.get("expiry_months", 0) or 0
            exp_d = r.get("expiry_days", 0) or 0
            exp_parts = []
            if exp_m > 0:
                exp_parts.append(f"{exp_m}月")
            if exp_d > 0:
                exp_parts.append(f"{exp_d}天")
            _ci26 = QTableWidgetItem(" ".join(exp_parts))
            _ci26.setTextAlignment(Qt.AlignCenter)
            self.ledger_table.setItem(i, 11, _ci26)

            # 储存天数 & 过期提醒
            prod_date = r.get("production_date", "")
            stored_days, exp_str, warning, is_expired = _calc_expiry_info(prod_date, exp_m, exp_d)
            sd_item = QTableWidgetItem(f"{stored_days}天" if stored_days != "" else "")
            sd_item.setTextAlignment(Qt.AlignCenter)
            self.ledger_table.setItem(i, 12, sd_item)
            warn_item = QTableWidgetItem(warning)
            warn_item.setTextAlignment(Qt.AlignCenter)
            if is_expired:
                warn_item.setForeground(QColor(COLOR["danger"]))
                warn_item.setBackground(QColor("#fff0f0"))
                expired_count += 1
            elif warning and "距保质期" in warning:
                try:
                    days = int(warning.replace("距保质期", "").replace("天", ""))
                    if days <= 7:
                        warn_item.setForeground(QColor("#ff9800"))
                except ValueError:
                    pass
            self.ledger_table.setItem(i, 13, warn_item)

            # 供货商信息
            for col, key in [(14, "supplier_name"), (15, "supplier_addr"), (16, "supplier_phone")]:
                val = r.get(key, "") or ""
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                if key in ("supplier_name", "supplier_addr"):
                    item.setToolTip(str(val))
                self.ledger_table.setItem(i, col, item)

            # 退货记录标红
            is_return = r.get("purchase_no", "").startswith("TH")
            if is_return:
                for col in range(17):
                    item = self.ledger_table.item(i, col)
                    if item:
                        item.setForeground(QColor(COLOR["danger"]))

            # 操作按钮
            btn_edit = make_table_button("编辑", "edit")
            btn_del = make_table_button("删除", "delete")
            item_id = r.get("id")
            btn_edit.clicked.connect(lambda checked, pid=item_id: self._edit_ledger_item(pid))
            btn_del.clicked.connect(lambda checked, pid=item_id: self._del_ledger_item(pid))
            op_wrapper = QWidget()
            op_wrapper.setObjectName("btnCell")
            op_wrapper.setStyleSheet("#btnCell { background: transparent; border: none; }")
            op_wl = QHBoxLayout(op_wrapper)
            op_wl.setContentsMargins(0, 0, 0, 0)
            op_wl.setSpacing(4)
            op_wl.setAlignment(Qt.AlignCenter)
            op_wl.addWidget(btn_edit)
            op_wl.addWidget(btn_del)
            self.ledger_table.setCellWidget(i, 17, op_wrapper)

        self.lbl_ledger_total.setText(
            f"共 {len(rows)} 条记录 | 合计金额：¥ {total_amount:.2f}"
            + (f" | <span style='color:{COLOR['danger']}'>过期产品 {expired_count} 项</span>"
               if expired_count else ""))

    def _edit_ledger_item(self, item_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pi.*, p.purchase_date, i.name as ing_name, i.unit "
            "FROM purchase_items pi "
            "JOIN purchases p ON pi.purchase_id = p.id "
            "JOIN ingredients i ON pi.ingredient_id = i.id "
            "WHERE pi.id=?", (item_id,))
        row = cursor.fetchone()
        if not row:
            QMessageBox.warning(self, "提示", "记录不存在")
        conn.close()
        return
        r = dict(row)
        conn.close()

        dlg = QDialog(self)
        dlg.setWindowTitle("编辑进货记录")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(DLG_STYLE)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(20)
        form.addRow("产品：", QLabel(f"{r.get('ing_name', '')} ({r.get('unit', '')})"))
        spin_qty = QLineEdit(str(r.get("quantity", 0)))
        spin_qty.setStyleSheet(INPUT_STYLE)
        spin_qty.setValidator(QDoubleValidator(0.0001, 999999, 10))
        form.addRow("数量：", spin_qty)
        spin_price = QLineEdit(str(r.get("unit_price", 0)))
        spin_price.setStyleSheet(INPUT_STYLE)
        spin_price.setValidator(QDoubleValidator(0, 99999, 2))
        form.addRow("单价：", spin_price)
        edit_usage = QLineEdit(r.get("usage", "") or "")
        edit_usage.setStyleSheet(INPUT_STYLE)
        form.addRow("用途：", edit_usage)
        edit_prod_date = QLineEdit(r.get("production_date", "") or "")
        edit_prod_date.setStyleSheet(INPUT_STYLE)
        edit_prod_date.setPlaceholderText("YYYY-MM-DD")
        form.addRow("生产日期：", edit_prod_date)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setStyleSheet(primary_btn)
        btns.button(QDialogButtonBox.Cancel).setStyleSheet(success_btn)
        form.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return
        try:
            qty = float(spin_qty.text().strip())
            price = float(spin_price.text().strip() or "0")
        except ValueError:
            QMessageBox.warning(self, "提示", "数量和单价必须为数字")
            return
        total = qty * price
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE purchase_items SET quantity=?, unit_price=?, total_price=?, "
            "usage=?, production_date=? WHERE id=?",
            (qty, price, total, edit_usage.text().strip(),
             edit_prod_date.text().strip(), item_id))
        cursor.execute("SELECT purchase_id FROM purchase_items WHERE id=?", (item_id,))
        pid_row = cursor.fetchone()
        if pid_row:
            pid = pid_row["purchase_id"]
            cursor.execute(
                "SELECT COALESCE(SUM(total_price),0) as total FROM purchase_items WHERE purchase_id=?", (pid,))
            new_total = cursor.fetchone()["total"]
            cursor.execute("UPDATE purchases SET total_amount=? WHERE id=?", (new_total, pid))
        conn.commit()
        self.load_ledger()
        _sync_cloud()

    def _del_ledger_item(self, item_id):
        reply = QMessageBox.question(self, "确认", "确定删除该进货记录吗？")
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        # 先查明细信息，用于回退库存
        cursor.execute(
            "SELECT pi.purchase_id, pi.ingredient_id, pi.quantity, p.purchase_no "
            "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
            "WHERE pi.id=?", (item_id,))
        detail = cursor.fetchone()
        pid = dict(detail)["purchase_id"] if detail else None
        if detail:
            d = dict(detail)
            ing_id = d["ingredient_id"]
            qty = d["quantity"]
            pno = d.get("purchase_no", "")
        # 回退库存：CG进货则减库存，TH退货/CK出库则加库存
            if pno.startswith("CG"):
                cursor.execute("UPDATE ingredients SET stock = stock - ? WHERE id=?", (qty, ing_id))
            else:
                cursor.execute("UPDATE ingredients SET stock = stock + ? WHERE id=?", (qty, ing_id))
        cursor.execute("DELETE FROM purchase_items WHERE id=?", (item_id,))
        if pid:
            cursor.execute(
                "SELECT COALESCE(SUM(total_price),0) as total FROM purchase_items WHERE purchase_id=?", (pid,))
            new_total = cursor.fetchone()["total"]
            cursor.execute("UPDATE purchases SET total_amount=? WHERE id=?", (new_total, pid))
        conn.commit()
        self.load_ledger()
        _sync_cloud()

    # ── 供货商进货明细 ──
    def _load_sq_suppliers(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT id, name FROM suppliers ORDER BY name")
        else:
            cursor.execute(
                "SELECT id, name FROM suppliers WHERE store_id=? OR store_id IS NULL ORDER BY name", (_sid,))
        self.cmb_sq_supplier.clear()
        self.cmb_sq_supplier.addItem("全部供货商", None)
        for r in cursor.fetchall():
            self.cmb_sq_supplier.addItem(r["name"], r["id"])
        conn.close()

    def load_supplier_query(self):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        supplier_id = self.cmb_sq_supplier.currentData()
        date_from = self.sq_date_from.date().toString("yyyy-MM-dd")
        date_to = self.sq_date_to.date().toString("yyyy-MM-dd")
        sql = (
            "SELECT pi.*, p.purchase_no, p.purchase_date, p.remark, "
            "i.name as ing_name, s.name as supplier_name "
            "FROM purchase_items pi "
            "JOIN purchases p ON pi.purchase_id = p.id "
            "JOIN ingredients i ON pi.ingredient_id = i.id "
            "LEFT JOIN suppliers s ON p.supplier_id = s.id "
            "WHERE p.purchase_no LIKE 'CG%' "
            "AND p.purchase_date >= ? AND p.purchase_date <= ?")
        params = [date_from, date_to]
        if supplier_id:
            sql += " AND p.supplier_id=?"
            params.append(supplier_id)
        if not _all:
            sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            params.append(_sid)
        sql += " ORDER BY p.purchase_date DESC"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        self.sq_table.setRowCount(len(rows))
        total_amount = 0
        daily_map = {}
        for i, row in enumerate(rows):
            r = dict(row)
            amount = r.get("total_price", 0) or 0
            total_amount += amount
            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 0, sn)
            _ci27 = QTableWidgetItem(r.get("purchase_date", ""))
            _ci27.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 1, _ci27)
            _ci28 = QTableWidgetItem(r.get("purchase_no", ""))
            _ci28.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 2, _ci28)
            _ci29 = QTableWidgetItem(r.get("ing_name", ""))
            _ci29.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 3, _ci29)
            _ci30 = QTableWidgetItem(f"{r.get('quantity', 0):.1f}")
            _ci30.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 4, _ci30)
            _ci31 = QTableWidgetItem(f"¥{r.get('unit_price', 0):.2f}")
            _ci31.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 5, _ci31)
            _ci32 = QTableWidgetItem(f"¥{amount:.2f}")
            _ci32.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 6, _ci32)
            _ci33 = QTableWidgetItem(r.get("remark", ""))
            _ci33.setTextAlignment(Qt.AlignCenter)
            self.sq_table.setItem(i, 7, _ci33)
            pd = r.get("purchase_date", "")
            if pd:
                if pd not in daily_map:
                    daily_map[pd] = {"count": 0, "amount": 0}
                daily_map[pd]["count"] += 1
                daily_map[pd]["amount"] += amount

        sorted_days = sorted(daily_map.keys(), reverse=True)
        self.sq_daily_table.setRowCount(len(sorted_days))
        for j, d in enumerate(sorted_days):
            sn = QTableWidgetItem(str(j + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.sq_daily_table.setItem(j, 0, sn)
            _ci34 = QTableWidgetItem(d)
            _ci34.setTextAlignment(Qt.AlignCenter)
            self.sq_daily_table.setItem(j, 1, _ci34)
            _ci35 = QTableWidgetItem(str(daily_map[d]["count"]))
            _ci35.setTextAlignment(Qt.AlignCenter)
            self.sq_daily_table.setItem(j, 2, _ci35)
            _ci36 = QTableWidgetItem(f"¥{daily_map[d]['amount']:.2f}")
            _ci36.setTextAlignment(Qt.AlignCenter)
            self.sq_daily_table.setItem(j, 3, _ci36)

        supplier_name = self.cmb_sq_supplier.currentText()
        self.lbl_sq_summary.setText(
            f"供货商：{supplier_name} | 共 {len(rows)} 条明细 | "
            f"进货总额：¥ {total_amount:.2f} | 进货天数：{len(sorted_days)}天")

    # ── 出库管理 ──
    def _init_inout_months(self):
        self.inout_month.clear()
        today = QDate.currentDate()
        for i in range(6):
            d = today.addMonths(-i)
            self.inout_month.addItem(f"{d.year()}-{d.month():02d}", (d.year(), d.month()))

    def load_inout(self):
        """出库管理：上月结存 + 本月进货 - 本月出库 = 当前库存
        上月结存 = 截至上月末的累计进货 - 累计出库（无数据按0）
        """
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()

        idx = self.inout_month.currentIndex()
        if idx < 0:
            conn.close()
            return
        year, month = self.inout_month.itemData(idx)

        # 本月第一天（用于截断上月数据）
        month_start = f"{year}-{month:02d}-01"

        # 取所有食材
        if _all:
            cursor.execute("SELECT id, name, spec, unit, min_stock FROM ingredients ORDER BY name")
        else:
            cursor.execute(
                "SELECT id, name, spec, unit, min_stock FROM ingredients "
                "WHERE store_id=? OR store_id IS NULL ORDER BY name", (_sid,))
        ingredients = [dict(r) for r in cursor.fetchall()]

        # 上月结存 = 截至上月末累计进货 - 累计出库
        prev_sql = (
            "SELECT pi.ingredient_id, "
            "SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END) - "
            "SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END) as total_in_before, "
            "SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END) as total_out_before "
            "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
            "WHERE p.purchase_date < ?")
        prev_params = [month_start]
        if not _all:
            prev_sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            prev_params.append(_sid)
        prev_sql += " GROUP BY pi.ingredient_id"
        cursor.execute(prev_sql, prev_params)
        prev_map = {}
        for r in cursor.fetchall():
            d = dict(r)
            prev_map[d["ingredient_id"]] = d["total_in_before"] - d["total_out_before"]

        # 本月进货 + 本月出库
        cur_sql = (
            "SELECT pi.ingredient_id, "
            "SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END) - "
            "SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END) as total_in, "
            "SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END) as total_out "
            "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
            "WHERE strftime('%Y', p.purchase_date)=? AND strftime('%m', p.purchase_date)=?")
        cur_params = [str(year), f"{month:02d}"]
        if not _all:
            cur_sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            cur_params.append(_sid)
        cur_sql += " GROUP BY pi.ingredient_id"
        cursor.execute(cur_sql, cur_params)
        cur_map = {}
        for r in cursor.fetchall():
            cur_map[dict(r)["ingredient_id"]] = dict(r)
        conn.close()

        self.inout_table.setRowCount(len(ingredients))
        warning_count = 0
        for i, ing in enumerate(ingredients):
            ing_id = ing["id"]
            prev_balance = prev_map.get(ing_id, 0) or 0  # 上月结存
            if prev_balance < 0:
                prev_balance = 0
            cur = cur_map.get(ing_id, {})
            in_qty = cur.get("total_in", 0) or 0      # 本月进货
            out_qty = cur.get("total_out", 0) or 0     # 本月出库
            available = prev_balance + in_qty           # 可用库存
            current_stock = available - out_qty         # 当前库存
            min_stock = ing.get("min_stock", 0) or 0

            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 0, sn)
            _ci37 = QTableWidgetItem(ing["name"])
            _ci37.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 1, _ci37)
            _ci38 = QTableWidgetItem(ing.get('spec', '') or '')
            _ci38.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 2, _ci38)
            _ci39 = QTableWidgetItem(ing.get('unit', '') or '')
            _ci39.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 3, _ci39)
            _ci40 = QTableWidgetItem(f"{prev_balance:.2f}")
            _ci40.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 4, _ci40)
            _ci41 = QTableWidgetItem(f"{in_qty:.2f}")
            _ci41.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 5, _ci41)
            _ci42 = QTableWidgetItem(f"{available:.2f}")
            _ci42.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 6, _ci42)
            _ci43 = QTableWidgetItem(f"{out_qty:.2f}")
            _ci43.setTextAlignment(Qt.AlignCenter)
            self.inout_table.setItem(i, 7, _ci43)

            stock_item = QTableWidgetItem(f"{current_stock:.2f}")
            stock_item.setTextAlignment(Qt.AlignCenter)
            if min_stock > 0 and current_stock <= min_stock:
                stock_item.setForeground(QColor(COLOR["danger"]))
            self.inout_table.setItem(i, 8, stock_item)

            # 库存状态
            status_text = ""
            status_color = None
            if min_stock > 0 and current_stock <= 0:
                status_text = "缺货"
                status_color = COLOR["danger"]
                warning_count += 1
            elif min_stock > 0 and current_stock <= min_stock:
                status_text = "库存不足"
                status_color = COLOR["danger"]
                warning_count += 1
            elif current_stock > 0:
                status_text = "正常"
                status_color = COLOR["success"]
            else:
                status_text = "无库存"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status_color:
                status_item.setForeground(QColor(status_color))
            self.inout_table.setItem(i, 9, status_item)

            # 出库记录按钮
            btn_view = make_table_button("查看出库", "view")
            btn_view.clicked.connect(lambda checked, iid=ing_id: self._view_stockout_detail(iid))
            wrapper = QWidget()
            wrapper.setObjectName("btnCell")
            wrapper.setStyleSheet("#btnCell { background: transparent; border: none; }")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_view)
            self.inout_table.setCellWidget(i, 10, wrapper)

            # 出库按钮
            btn_out = make_table_button("出库", "edit")
            btn_out.clicked.connect(lambda checked, iid=ing_id: self._quick_stockout(iid))
            wrapper2 = QWidget()
            wrapper2.setObjectName("btnCell")
            wrapper2.setStyleSheet("#btnCell { background: transparent; border: none; }")
            wl2 = QHBoxLayout(wrapper2)
            wl2.setContentsMargins(0, 0, 0, 0)
            wl2.setAlignment(Qt.AlignCenter)
            wl2.addWidget(btn_out)
            self.inout_table.setCellWidget(i, 11, wrapper2)

        if warning_count > 0:
            self.lbl_inout_warning.setText(
                f"警告：有 {warning_count} 个产品库存不足或缺货，请及时补货！")
        else:
            self.lbl_inout_warning.setText("")

    def _view_stockout_detail(self, ingredient_id):
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        sql = ("SELECT p.id as purchase_id, p.purchase_no, p.purchase_date, p.operator, "
               "p.remark, pi.quantity, i.name as ingredient_name "
               "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
               "JOIN ingredients i ON pi.ingredient_id = i.id "
               "WHERE p.purchase_no LIKE 'CK%' AND pi.ingredient_id=?")
        params = [ingredient_id]
        if not _all:
            sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            params.append(_sid)
        sql += " ORDER BY p.purchase_date DESC LIMIT 20"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.execute("SELECT name FROM ingredients WHERE id=?", (ingredient_id,))
        ing_row = cursor.fetchone()
        ing_name = dict(ing_row)["name"] if ing_row else "未知产品"
        conn.close()
        if not rows:
            QMessageBox.information(self, "出库记录", "暂无出库记录")
            return
        dlg = StockOutRecordDialog(ing_name, rows, self)
        if dlg.exec_() and dlg.data_changed():
            self.load_inout()
            self.load_ingredients()

    def _quick_stockout(self, ingredient_id):
        dlg = StockOutDialog(self, ingredient_id=ingredient_id)
        if dlg.exec_():
            self.load_inout()
            self.load_ingredients()

    def delete_stockout(self, purchase_id):
        """撤销出库单：删除交易记录即可，库存自动从交易记录重新计算"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM purchase_items WHERE purchase_id=?", (purchase_id,))
        cursor.execute("DELETE FROM purchases WHERE id=?", (purchase_id,))
        conn.commit()
        _sync_cloud()

    def edit_stockout(self, purchase_id, new_date, new_operator, new_qty, new_remark):
        """编辑出库记录：修改出库单的日期、经办人、备注，以及明细的数量"""
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE purchases SET purchase_date=?, operator=?, remark=?, "
                "updated_at=datetime('now','localtime') WHERE id=?",
                (new_date, new_operator, new_remark, purchase_id))
            cursor.execute(
                "UPDATE purchase_items SET quantity=? WHERE purchase_id=?",
                (new_qty, purchase_id))
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", "出库记录已更新")
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"更新失败：{e}")
        finally:
            conn.close()

    # ── 上月结存 ──
    def load_prev_balance(self):
        """上月结存：优先读monthly_inventory手动录入，无则从交易记录计算
        上月结存 = 截至上月末累计进货 - 累计出库
        上月进货/出库 = 上月当月的CG/CK单合计
        """
        year = self.pb_date.date().year()
        month = self.pb_date.date().month()
        _sid, _all = _ctx().get_store_filter()
        prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
        self._pb_prev_year = prev_year
        self._pb_prev_month = prev_month
        self._pb_store_id = _sid

        conn = get_connection()
        cursor = conn.cursor()

        # 取所有食材
        if _all:
            cursor.execute(
                "SELECT i.id, i.name, i.spec, i.unit, i.category, i.price, i.supplier_id, "
                "s.name AS supplier_name FROM ingredients i "
                "LEFT JOIN suppliers s ON i.supplier_id = s.id "
                "ORDER BY i.name")
        else:
            cursor.execute(
                "SELECT i.id, i.name, i.spec, i.unit, i.category, i.price, i.supplier_id, "
                "s.name AS supplier_name FROM ingredients i "
                "LEFT JOIN suppliers s ON i.supplier_id = s.id "
                "WHERE i.store_id=? OR i.store_id IS NULL ORDER BY i.name", (_sid,))
        ingredients = [dict(r) for r in cursor.fetchall()]

        # 取每个食材最近一笔进货的实际单价（优先于ingredients.price）
        price_sql = (
            "SELECT pi.ingredient_id, pi.unit_price "
            "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
            "WHERE p.purchase_no LIKE 'CG%' AND pi.unit_price > 0 "
            "AND p.purchase_date < ?")
        price_params = [f"{year}-{month:02d}-01"]
        if not _all:
            price_sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            price_params.append(_sid)
        price_sql += " ORDER BY p.purchase_date DESC"
        cursor.execute(price_sql, price_params)
        price_map = {}
        for r in cursor.fetchall():
            d = dict(r)
            if d["ingredient_id"] not in price_map:
                price_map[d["ingredient_id"]] = d["unit_price"]

        # 1. 优先读monthly_inventory手动录入
        mi_sql = ("SELECT ingredient_id, begin_stock, purchase_amount, end_stock, id "
                  "FROM monthly_inventory WHERE year=? AND month=?")
        mi_params = [prev_year, prev_month]
        if not _all:
            mi_sql += " AND (store_id=? OR store_id IS NULL)"
            mi_params.append(_sid)
        cursor.execute(mi_sql, mi_params)
        mi_map = {}
        for r in cursor.fetchall():
            d = dict(r)
            mi_map[d["ingredient_id"]] = d

        # 2. 从交易记录计算（作为无手动录入时的fallback）
        month_start = f"{prev_year}-{prev_month:02d}-01"
        prev_cum_sql = (
            "SELECT pi.ingredient_id, "
            "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END), 0) - "
            "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END), 0) as cum_in, "
            "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END), 0) as cum_out "
            "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
            "WHERE p.purchase_date < ?")
        prev_cum_params = [month_start]
        if not _all:
            prev_cum_sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            prev_cum_params.append(_sid)
        prev_cum_sql += " GROUP BY pi.ingredient_id"
        cursor.execute(prev_cum_sql, prev_cum_params)
        cum_map = {}
        for r in cursor.fetchall():
            d = dict(r)
            cum_map[d["ingredient_id"]] = d

        # 上月当月进货/出库
        prev_month_sql = (
            "SELECT pi.ingredient_id, "
            "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CG%' THEN pi.quantity ELSE 0 END), 0) - "
            "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'TH%' THEN pi.quantity ELSE 0 END), 0) as month_in, "
            "COALESCE(SUM(CASE WHEN p.purchase_no LIKE 'CK%' THEN pi.quantity ELSE 0 END), 0) as month_out "
            "FROM purchase_items pi JOIN purchases p ON pi.purchase_id = p.id "
            "WHERE strftime('%Y', p.purchase_date)=? AND strftime('%m', p.purchase_date)=?")
        prev_month_params = [str(prev_year), f"{prev_month:02d}"]
        if not _all:
            prev_month_sql += " AND (p.store_id=? OR p.store_id IS NULL)"
            prev_month_params.append(_sid)
        prev_month_sql += " GROUP BY pi.ingredient_id"
        cursor.execute(prev_month_sql, prev_month_params)
        month_map = {}
        for r in cursor.fetchall():
            month_map[dict(r)["ingredient_id"]] = dict(r)
        conn.close()

        # 合并数据：有手动录入用手动的，否则用交易记录算
        display_rows = []
        for ing in ingredients:
            ing_id = ing["id"]
            mi = mi_map.get(ing_id)
            mon = month_map.get(ing_id, {})
            month_in = mon.get("month_in", 0) or 0
            month_out = mon.get("month_out", 0) or 0

            if mi:
                prev_balance = mi.get("end_stock", 0) or 0
                price = price_map.get(ing_id, 0) or ing.get("price", 0) or 0
                display_rows.append({
                    "id": ing_id,
                    "name": ing["name"],
                    "category": ing.get("category", "") or "",
                    "spec": ing.get("spec", "") or "",
                    "unit": ing.get("unit", "") or "",
                    "supplier_name": ing.get("supplier_name", "") or "",
                    "month_in": month_in,
                    "month_out": month_out,
                    "prev_balance": prev_balance,
                    "price": price,
                    "manual": True,
                })
            else:
                cum = cum_map.get(ing_id, {})
                cum_in = cum.get("cum_in", 0) or 0
                cum_out = cum.get("cum_out", 0) or 0
                prev_balance = cum_in - cum_out
                if prev_balance < 0:
                    prev_balance = 0
                if prev_balance > 0 or month_in > 0 or month_out > 0:
                    display_rows.append({
                        "id": ing_id,
                        "name": ing["name"],
                        "category": ing.get("category", "") or "",
                        "spec": ing.get("spec", "") or "",
                        "unit": ing.get("unit", "") or "",
                        "supplier_name": ing.get("supplier_name", "") or "",
                        "month_in": month_in,
                        "month_out": month_out,
                        "prev_balance": prev_balance,
                        "price": price_map.get(ing_id, 0) or ing.get("price", 0) or 0,
                        "manual": False,
                    })

        self.prev_balance_table.setRowCount(len(display_rows))
        total_amount = 0
        for i, r in enumerate(display_rows):
            qty = r["prev_balance"]
            price = r["price"]
            amount = qty * price
            total_amount += amount

            sn = QTableWidgetItem(str(i + 1))
            sn.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 0, sn)
            _ci44 = QTableWidgetItem(r["name"])
            _ci44.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 1, _ci44)
            _ci45 = QTableWidgetItem(r["category"])
            _ci45.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 2, _ci45)
            _ci46 = QTableWidgetItem(r["spec"])
            _ci46.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 3, _ci46)
            _ci47 = QTableWidgetItem(r["unit"])
            _ci47.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 4, _ci47)
            _ci48 = QTableWidgetItem(r.get("supplier_name", ""))
            _ci48.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 5, _ci48)
            balance_item = QTableWidgetItem(f"{qty:.2f}")
            balance_item.setTextAlignment(Qt.AlignCenter)
            if r["manual"]:
                balance_item.setForeground(QColor(COLOR["primary"]))
            self.prev_balance_table.setItem(i, 6, balance_item)
            _ci49 = QTableWidgetItem(f"¥{price:.2f}")
            _ci49.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 7, _ci49)
            _ci50 = QTableWidgetItem(f"¥{amount:.2f}")
            _ci50.setTextAlignment(Qt.AlignCenter)
            self.prev_balance_table.setItem(i, 8, _ci50)

            # 操作列
            wrapper = QWidget()
            wrapper.setObjectName("btnCell")
            wrapper.setStyleSheet("#btnCell { background: transparent; border: none; }")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.setSpacing(4)
            if r["manual"]:
                btn_edit = make_table_button("编辑", "edit")
                btn_edit.clicked.connect(lambda checked, row=i: self._edit_prev_balance(row))
                wl.addWidget(btn_edit)
                btn_del = make_table_button("删除", "delete")
                btn_del.clicked.connect(lambda checked, row=i: self._delete_prev_balance(row))
                wl.addWidget(btn_del)
            else:
                btn_add = make_table_button("录入", "edit")
                btn_add.clicked.connect(lambda checked, ing_id=r["id"]: self._add_prev_balance(ing_id))
                wl.addWidget(btn_add)
            self.prev_balance_table.setCellWidget(i, 9, wrapper)

        manual_count = sum(1 for r in display_rows if r["manual"])
        auto_count = len(display_rows) - manual_count
        self.lbl_pb_summary.setText(
            f"{prev_year}年{prev_month}月结存 | 共 {len(display_rows)} 条 "
            f"(手动录入 {manual_count}，自动计算 {auto_count}) | "
            f"金额合计：¥ {total_amount:.2f}")

    def _add_prev_balance(self, preset_ing_id=None):
        """录入上月结存（手动）"""
        from PyQt5.QtWidgets import QDialog, QFormLayout, QComboBox, QLineEdit, QTextEdit
        from PyQt5.QtGui import QDoubleValidator
        dlg = QDialog(self)
        dlg.setWindowTitle("录入上月结存")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(DLG_STYLE)
        layout = QFormLayout(dlg)

        year = self._pb_prev_year
        month = self._pb_prev_month

        cmb_ing = QComboBox()
        conn = get_connection()
        cursor = conn.cursor()
        _sid, _all = _ctx().get_store_filter()
        if _all:
            cursor.execute("SELECT id, name, spec, unit, price FROM ingredients ORDER BY name")
        else:
            cursor.execute(
                "SELECT id, name, spec, unit, price FROM ingredients "
                "WHERE store_id=? OR store_id IS NULL ORDER BY name", (_sid,))
        ingredients = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for ing in ingredients:
            cmb_ing.addItem(f"{ing['name']} ({ing.get('spec','')}/{ing.get('unit','')})", ing["id"])
        if preset_ing_id:
            idx = cmb_ing.findData(preset_ing_id)
            if idx >= 0:
                cmb_ing.setCurrentIndex(idx)
        layout.addRow("选择产品：", cmb_ing)

        txt_qty = QLineEdit()
        txt_qty.setPlaceholderText("请输入结存数量")
        txt_qty.setStyleSheet("background: #fff; border: 1px solid #d0d0d0; border-radius: 4px; padding: 8px 12px; font-size: 13px; color: #999;")
        txt_qty.setValidator(QDoubleValidator(0, 999999, 2))
        layout.addRow("结存数量：", txt_qty)

        spn_price = QDoubleSpinBox()
        spn_price.setRange(0, 999999)
        spn_price.setDecimals(2)
        spn_price.setSingleStep(0.5)
        spn_price.setStyleSheet(INPUT_STYLE)
        if ingredients and cmb_ing.currentIndex() >= 0:
            spn_price.setValue(ingredients[cmb_ing.currentIndex()].get("price", 0) or 0)
        layout.addRow("单价：", spn_price)

        txt_remark = QTextEdit()
        txt_remark.setMaximumHeight(60)
        txt_remark.setStyleSheet(INPUT_STYLE)
        layout.addRow("备注：", txt_remark)

        info_label = QLabel(f"将录入 {year}年{month}月 的上月结存数据")
        info_label.setStyleSheet(f"color: {COLOR['text_secondary']}; font-size: 12px;")
        layout.addRow(info_label)

        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(primary_btn)
        btn_save.clicked.connect(dlg.accept)
        layout.addRow(btn_save)

        if dlg.exec_() != QDialog.Accepted:
            return

        ing_id = cmb_ing.currentData()
        qty = float(txt_qty.text() or "0")
        price = spn_price.value()

        if qty <= 0:
            QMessageBox.warning(self, "提示", "结存数量必须大于0")
            return

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id FROM monthly_inventory WHERE year=? AND month=? AND ingredient_id=? "
                "AND (store_id=? OR store_id IS NULL)",
                (year, month, ing_id, _sid))
            existing = cursor.fetchone()
            if existing:
                reply = QMessageBox.question(self, "确认覆盖",
                    "该产品本月已有手动录入的上月结存，是否覆盖？")
                if reply != QMessageBox.Yes:
                    conn.close()
                    return
                cursor.execute(
                    "UPDATE monthly_inventory SET end_stock=?, updated_at=datetime('now','localtime') "
                    "WHERE year=? AND month=? AND ingredient_id=? AND (store_id=? OR store_id IS NULL)",
                    (qty, year, month, ing_id, _sid))
            else:
                cursor.execute(
                    "INSERT INTO monthly_inventory (year, month, ingredient_id, begin_stock, "
                    "purchase_amount, end_stock, consumption, store_id) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (year, month, ing_id, 0, 0, qty, 0, _sid))
            # 同步更新食材单价
            cursor.execute(
                "UPDATE ingredients SET price=? WHERE id=?", (price, ing_id))
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", f"已录入 {year}年{month}月 上月结存")
            self.load_prev_balance()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"录入失败：{e}")
        finally:
            conn.close()

    def _edit_prev_balance(self, row):
        """编辑手动录入的上月结存"""
        name = self.prev_balance_table.item(row, 1).text()
        qty_text = self.prev_balance_table.item(row, 6).text()
        price_text = self.prev_balance_table.item(row, 7).text().replace("¥", "")

        from PyQt5.QtWidgets import QDialog, QFormLayout, QDoubleSpinBox, QLabel, QLineEdit
        from PyQt5.QtGui import QDoubleValidator
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑上月结存")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(DLG_STYLE)
        layout = QFormLayout(dlg)

        lbl_name = QLabel(name)
        lbl_name.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLOR['primary']};")
        layout.addRow("产品：", lbl_name)

        txt_qty = QLineEdit()
        txt_qty.setPlaceholderText("请输入结存数量")
        txt_qty.setStyleSheet("background: #fff; border: 1px solid #d0d0d0; border-radius: 4px; padding: 8px 12px; font-size: 13px; color: #999;")
        txt_qty.setValidator(QDoubleValidator(0, 999999, 2))
        try:
            txt_qty.setText(str(qty_text))
        except (ValueError, TypeError):
            pass
        layout.addRow("结存数量：", txt_qty)

        spn_price = QDoubleSpinBox()
        spn_price.setRange(0, 999999)
        spn_price.setDecimals(2)
        spn_price.setStyleSheet(INPUT_STYLE)
        try:
            spn_price.setValue(float(price_text))
        except (ValueError, TypeError):
            spn_price.setValue(0)
        layout.addRow("单价：", spn_price)

        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(primary_btn)
        btn_save.clicked.connect(dlg.accept)
        layout.addRow(btn_save)

        if dlg.exec_() != QDialog.Accepted:
            return

        qty = float(txt_qty.text() or "0")
        price = spn_price.value()
        year = self._pb_prev_year
        month = self._pb_prev_month
        _sid = self._pb_store_id

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT mi.id FROM monthly_inventory mi "
                "JOIN ingredients i ON mi.ingredient_id = i.id "
                "WHERE mi.year=? AND mi.month=? AND i.name=? "
                "AND (mi.store_id=? OR mi.store_id IS NULL)",
                (year, month, name, _sid))
            row_data = cursor.fetchone()
            if row_data:
                mi_id = dict(row_data)["id"]
                price = spn_price.value()
                cursor.execute(
                    "UPDATE monthly_inventory SET end_stock=?, updated_at=datetime('now','localtime') "
                    "WHERE id=?", (qty, mi_id))
        # 同步更新食材单价
                cursor.execute(
                    "UPDATE ingredients SET price=? WHERE name=?", (price, name))
                conn.commit()
                _sync_cloud()
                QMessageBox.information(self, "成功", "已更新上月结存")
                self.load_prev_balance()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"更新失败：{e}")
        finally:
            conn.close()

    def _delete_prev_balance(self, row):
        """删除手动录入的上月结存"""
        name = self.prev_balance_table.item(row, 1).text()
        reply = QMessageBox.question(self, "确认删除",
            f"确定删除 {name} 的手动录入上月结存吗？\n删除后将恢复为自动计算。")
        if reply != QMessageBox.Yes:
            return

        year = self._pb_prev_year
        month = self._pb_prev_month
        _sid = self._pb_store_id

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM monthly_inventory WHERE year=? AND month=? "
                "AND ingredient_id=(SELECT id FROM ingredients WHERE name=?) "
                "AND (store_id=? OR store_id IS NULL)",
                (year, month, name, _sid))
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", "已删除手动录入，恢复自动计算")
            self.load_prev_balance()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"删除失败：{e}")
        finally:
            conn.close()

    def _init_stock(self):
        """初始化库存：创建一笔上月最后一天的初始进货记录（CG单）
        用于首次使用系统时录入现有库存，使后续月份的上月结存有数据来源。
        """
        year = self._pb_prev_year
        month = self._pb_prev_month
        _sid, _all = _ctx().get_store_filter()

        # 上月最后一天
        if month == 12:
            next_first = f"{year + 1}-01-01"
        else:
            next_first = f"{year}-{month + 1:02d}-01"
        # 取上月最后一天日期
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        init_date = f"{year}-{month:02d}-{last_day:02d}"

        reply = QMessageBox.question(
            self, "确认初始化库存",
            f"将在 {year}年{month}月{last_day}日 创建一笔初始进货记录，\n"
            f"将当前所有产品的库存（ingredients.stock）作为初始进货导入。\n\n"
            f"注意：此操作适用于首次使用系统时录入期初库存。\n"
            f"如果该日期已有初始进货记录，将不会重复创建。\n\n"
            f"确定继续吗？")
        if reply != QMessageBox.Yes:
            return

        conn = get_connection()
        cursor = conn.cursor()
        # 检查是否已有初始化进货记录
        cursor.execute(
                "SELECT id FROM purchases WHERE purchase_no=? "
                "AND (store_id=? OR store_id IS NULL)",
                (f"CG-INIT-{year}{month:02d}", _sid))
        existing = cursor.fetchone()
        if existing:
                QMessageBox.warning(self, "提示",
                    f"{year}年{month}月已有初始化库存记录，不可重复创建。\n"
                    f"如需修改，请到进货台账删除旧记录后重新初始化。")
        conn.close()
        return

            # 取所有食材的当前库存
        if _all:
                cursor.execute("SELECT id, name, stock, unit FROM ingredients ORDER BY name")
        else:
                cursor.execute(
                    "SELECT id, name, stock, unit FROM ingredients "
                    "WHERE store_id=? OR store_id IS NULL ORDER BY name", (_sid,))
        ingredients = [dict(r) for r in cursor.fetchall()]

        if not ingredients:
                QMessageBox.warning(self, "提示", "请先添加产品数据")
                conn.close()
                return

            # 创建初始进货单
        init_no = f"CG-INIT-{year}{month:02d}"
        cursor.execute(
                "INSERT INTO purchases (purchase_no, supplier_id, total_amount, "
                "purchase_date, remark, store_id, operator) VALUES (?,?,?,?,?,?,?)",
                (init_no, None, 0, init_date,
                 f"[系统]初始库存导入 {year}年{month}月", _sid, "系统"))
        purchase_id = cursor.lastrowid

        count = 0
        for ing in ingredients:
                qty = ing.get("stock", 0) or 0
                if qty > 0:
                    cursor.execute(
                        "INSERT INTO purchase_items "
                        "(purchase_id, ingredient_id, quantity, unit_price, total_price) "
                        "VALUES (?,?,?,?,?)",
                        (purchase_id, ing["id"], qty, 0, 0))
                    count += 1

        conn.commit()
        _sync_cloud()
        QMessageBox.information(self, "成功",
                f"已创建 {init_date} 的初始进货记录\n"
                f"共导入 {count} 个产品，单号：{init_no}")
        self.load_prev_balance()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "错误", f"初始化库存失败：{e}")
        finally:
            conn.close()

    def _export_prev_balance(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存文件", "上月结存.xlsx", "Excel Files (*.xlsx)")
        if not path:
            return
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "上月结存"
        headers = ["品名", "分类", "规格", "单位", "供货商", "上月结存", "单价", "金额"]
        ws.append(headers)
        for row in range(self.prev_balance_table.rowCount()):
            row_data = []
            for col in range(1, 9):
                item = self.prev_balance_table.item(row, col)
                row_data.append(item.text() if item else "")
            ws.append(row_data)
        wb.save(path)
        QMessageBox.information(self, "导出成功", f"已导出到 {path}")

    # ── 进货操作 ──
    def add_purchase(self):
        dlg = PurchaseDialog(self)
        if dlg.exec_():
            self.load_ledger()
            self.load_inout()
            self.load_ingredients()

    def add_purchase_return(self):
        """进货退货：选择已进货的品项进行退货，单号前缀TH，数量取负"""
        dlg = ReturnPurchaseDialog(self)
        if dlg.exec_():
            self.load_ledger()
            self.load_inout()
            self.load_ingredients()

    def view_purchase_detail(self, purchase_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pi.*, i.name as ing_name, i.unit "
            "FROM purchase_items pi JOIN ingredients i ON pi.ingredient_id = i.id "
            "WHERE pi.purchase_id=?", (purchase_id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            QMessageBox.information(self, "明细", "无明细记录")
            return
        detail = "\n".join(
            f"{dict(r)['ing_name']}  {dict(r)['quantity']:.1f}{dict(r).get('unit', '')}  "
            f"¥{dict(r)['unit_price']:.2f}  小计:¥{dict(r)['total_price']:.2f}"
            for r in rows)
        QMessageBox.information(self, "进货明细", detail)

    def delete_purchase(self, purchase_id):
        reply = QMessageBox.question(self, "确认", "确定删除该进货单吗？")
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ingredient_id, quantity FROM purchase_items WHERE purchase_id=?", (purchase_id,))
        for r in cursor.fetchall():
            d = dict(r)
            cursor.execute("UPDATE ingredients SET stock = stock - ? WHERE id=?",
                           (d["quantity"], d["ingredient_id"]))
        cursor.execute("DELETE FROM purchase_items WHERE purchase_id=?", (purchase_id,))
        cursor.execute("DELETE FROM purchases WHERE id=?", (purchase_id,))
        conn.commit()
        _sync_cloud()
        self.load_ledger()
        self.load_inout()
        self.load_ingredients()

    def add_stockout(self):
        dlg = StockOutDialog(self)
        if dlg.exec_():
            self.load_inout()
            self.load_ingredients()
