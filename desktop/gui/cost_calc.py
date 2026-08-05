# -*- coding: utf-8 -*-
"""
成本核算模块 v5.0 — 餐饮专业版
功能：
  Tab1 菜品成本核算：菜品CRUD + 配方管理(dish_ingredients) → 成本 → 毛利 / 毛利率
  Tab2 月度产品耗用：耗用 = 上月结存 + 本月采购 - 本月结存 (monthly_inventory)
                    4张汇总卡片 + 按毛利率排序的成本分析报告
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QLineEdit, QComboBox,
    QMessageBox, QCheckBox, QGroupBox, QGridLayout, QDoubleSpinBox, QTabWidget,
    QSplitter, QFrame, QSpinBox, QHeaderView as QHV
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QDoubleValidator

from database.db_manager import get_connection
from gui.theme import (
    COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
    DLG_STYLE, BTN_PRIMARY, BTN_SUCCESS, BTN_DANGER,
    COMPACT_TABLE_STYLE, TABLE_BTN_EDIT, TABLE_BTN_DELETE, TABLE_BTN_VIEW, make_table_button
)
from gui.calendar_widget import ModernMonthEdit
from utils.app_context import get_app_context as _ctx
from utils.helpers import get_today
from utils.logger import logger
from utils.nutstore_sync import get_sync as _get_sync

def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        logger.debug(f"云同步失败: {e}")


# ========== 菜品对话框（含配方管理） ==========

class DishDialog(QDialog):
    """菜品CRUD + 配方管理：实时计算成本/毛利/毛利率"""

    def __init__(self, dish_id=None, parent=None):
        super().__init__(parent)
        self.dish_id = dish_id
        self.setWindowTitle("编辑菜品" if dish_id else "新增菜品")
        self.setMinimumSize(620, 560)
        self.setStyleSheet(DLG_STYLE)

        self._recipe = []  # [{ingredient_id, name, unit, quantity, price, subtotal}]

        layout = QVBoxLayout(self)
        title = QLabel("编辑菜品" if dish_id else "新增菜品")
        title.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: bold; color: {COLOR['primary']};")
        layout.addWidget(title)

        # ---- 基本信息区 ----
        info_group = QGroupBox("基本信息")
        info_form = QFormLayout(info_group)
        info_form.setLabelAlignment(Qt.AlignRight)

        self.name_edit = QLineEdit()
        self.name_edit.setStyleSheet(INPUT_STYLE)
        self.name_edit.setPlaceholderText("如：宫保鸡丁")
        info_form.addRow("菜品名称 *:", self.name_edit)

        self.category_edit = QComboBox()
        self.category_edit.setStyleSheet(COMBO_STYLE)
        self.category_edit.setEditable(True)
        self.category_edit.addItems(["热菜", "凉菜", "汤品", "主食", "小吃", "饮品", "甜品", "套餐"])
        info_form.addRow("分类:", self.category_edit)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 99999)
        self.price_spin.setSingleStep(1)
        self.price_spin.setDecimals(2)
        self.price_spin.setSuffix(" 元")
        info_form.addRow("售价 *:", self.price_spin)

        self.status_combo = QComboBox()
        self.status_combo.setStyleSheet(COMBO_STYLE)
        self.status_combo.addItems(["在售", "停售", "季节限定"])
        info_form.addRow("状态:", self.status_combo)

        self.remark_edit = QLineEdit()
        self.remark_edit.setStyleSheet(INPUT_STYLE)
        info_form.addRow("备注:", self.remark_edit)

        layout.addWidget(info_group)

        # ---- 配方管理区 ----
        recipe_group = QGroupBox("配方（食材用量）")
        rl = QVBoxLayout(recipe_group)

        # 添加食材行
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("选择食材:"))
        self.ingredient_combo = QComboBox()
        self.ingredient_combo.setStyleSheet(COMBO_STYLE)
        self._load_ingredients()
        add_row.addWidget(self.ingredient_combo, 2)

        add_row.addWidget(QLabel("用量:"))
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setRange(0, 99999)
        self.qty_spin.setSingleStep(0.1)
        self.qty_spin.setDecimals(3)
        add_row.addWidget(self.qty_spin)

        btn_add_ing = QPushButton("添加")
        btn_add_ing.setStyleSheet(BTN_SUCCESS)
        btn_add_ing.clicked.connect(self._add_ingredient)
        add_row.addWidget(btn_add_ing)
        rl.addLayout(add_row)

        # 配方表格
        self.recipe_table = QTableWidget()
        self.recipe_table.setStyleSheet(COMPACT_TABLE_STYLE)
        self.recipe_table.setColumnCount(6)
        self.recipe_table.setHorizontalHeaderLabels(["食材", "单位", "用量", "单价(元)", "小计(元)", "操作"])
        self.recipe_table.horizontalHeader().setSectionResizeMode(QHV.Stretch)
        self.recipe_table.horizontalHeader().setSectionResizeMode(5, QHV.ResizeToContents)
        self.recipe_table.verticalHeader().setVisible(False)
        self.recipe_table.verticalHeader().setDefaultSectionSize(32)
        self.recipe_table.setEditTriggers(QTableWidget.NoEditTriggers)
        rl.addWidget(self.recipe_table)

        # 成本/毛利显示
        self.lbl_cost = QLabel("成本: ¥0.00")
        self.lbl_cost.setStyleSheet(f"font-size: {FONT_SIZE['md']}px; font-weight: bold; color: {COLOR['danger']};")
        self.lbl_margin = QLabel("毛利: ¥0.00  |  毛利率: 0%")
        self.lbl_margin.setStyleSheet(f"font-size: {FONT_SIZE['md']}px; font-weight: bold; color: {COLOR['success']};")
        cost_row = QHBoxLayout()
        cost_row.addWidget(self.lbl_cost)
        cost_row.addWidget(self.lbl_margin)
        cost_row.addStretch()
        rl.addLayout(cost_row)

        layout.addWidget(recipe_group)

        # ---- 按钮 ----
        btn_lay = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(BTN_SUCCESS)
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(BTN_DANGER)
        btn_cancel.clicked.connect(self.reject)
        btn_lay.addStretch()
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_cancel)
        layout.addLayout(btn_lay)

        if dish_id:
            self._load_dish()

    def _load_ingredients(self):
        self.ingredient_combo.clear()
        conn = get_connection()
        store_id, is_all = _ctx().get_store_filter()
        if is_all:
            rows = conn.execute("SELECT id, name, unit, price FROM ingredients ORDER BY name").fetchall()
        else:
            rows = conn.execute(
        "SELECT id, name, unit, price FROM ingredients WHERE store_id=? OR store_id IS NULL ORDER BY name",
        (store_id,)
    ).fetchall()
        for r in rows:
            label = f"{r['name']} ({r['unit']}, ¥{r['price']:.2f})"
    self.ingredient_combo.addItem(label, (r["id"], r["name"], r["unit"], r["price"]))
    conn.close()

    def _add_ingredient(self):
        idx = self.ingredient_combo.currentIndex()
        if idx < 0:
            return
        ing_id, ing_name, ing_unit, ing_price = self.ingredient_combo.itemData(idx)
        qty = self.qty_spin.value()
        if qty <= 0:
            QMessageBox.warning(self, "提示", "用量必须大于0")
            return
        subtotal = round(qty * ing_price, 2)
        self._recipe.append({
            "ingredient_id": ing_id,
            "name": ing_name,
            "unit": ing_unit,
            "quantity": qty,
            "price": ing_price,
            "subtotal": subtotal,
        })
        self._refresh_recipe_table()
        self.qty_spin.setValue(0)

    def _remove_ingredient(self, idx):
        if 0 <= idx < len(self._recipe):
            self._recipe.pop(idx)
            self._refresh_recipe_table()

    def _refresh_recipe_table(self):
        self.recipe_table.setRowCount(len(self._recipe))
        total = 0.0
        for i, r in enumerate(self._recipe):
            self._set_cell(i, 0, r["name"])
            self._set_cell(i, 1, r["unit"])
            self._set_cell(i, 2, f"{r['quantity']:.3f}")
            self._set_cell(i, 3, f"¥{r['price']:.2f}")
            self._set_cell(i, 4, f"¥{r['subtotal']:.2f}")

            btn = QPushButton("删除")
            btn.setFixedWidth(50)
            btn.setStyleSheet(TABLE_BTN_DELETE)
            btn.clicked.connect(lambda _, ii=i: self._remove_ingredient(ii))
            self.recipe_table.setCellWidget(i, 5, btn)
            total += r["subtotal"]

        self.lbl_cost.setText(f"成本: ¥{total:.2f}")
        price = self.price_spin.value()
        margin = round(price - total, 2)
        margin_rate = round(margin / price * 100, 1) if price > 0 else 0
        margin_color = COLOR['danger'] if margin_rate < 40 else COLOR['success']
        self.lbl_margin.setText(f"毛利: ¥{margin:.2f}  |  毛利率: {margin_rate}%")
        self.lbl_margin.setStyleSheet(f"font-size: {FONT_SIZE['md']}px; font-weight: bold; color: {margin_color};")

    def _set_cell(self, row, col, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        self.recipe_table.setItem(row, col, item)

    def _load_dish(self):
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM dishes WHERE id=?", (self.dish_id,)).fetchone()
            if not row:
                return
            d = dict(row)
            self.name_edit.setText(d.get("name", ""))
            self.category_edit.setCurrentText(d.get("category", "") or "热菜")
            self.price_spin.setValue(d.get("selling_price", 0) or 0)
            self.status_combo.setCurrentText(d.get("status", "在售") or "在售")
            self.remark_edit.setText(d.get("remark", "") or "")

            # 加载配方
            recipes = conn.execute(
                """SELECT di.*, i.name, i.unit, i.price
                   FROM dish_ingredients di
                   JOIN ingredients i ON di.ingredient_id = i.id
                   WHERE di.dish_id=?""",
                (self.dish_id,)
            ).fetchall()
            self._recipe = []
            for r in recipes:
                rd = dict(r)
                qty = rd.get("quantity", 0) or 0
                price = rd.get("price", 0) or 0
                self._recipe.append({
                    "ingredient_id": rd["ingredient_id"],
                    "name": rd["name"],
                    "unit": rd["unit"],
                    "quantity": qty,
                    "price": price,
                    "subtotal": round(qty * price, 2),
                })
            self._refresh_recipe_table()
        except Exception as e:
            logger.error(f"DishDialog _load_dish: {e}", exc_info=True)
            conn.close()
    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入菜品名称")
            return
        price = self.price_spin.value()
        if price <= 0:
            QMessageBox.warning(self, "提示", "请输入售价")
            return

        cost = round(sum(r["subtotal"] for r in self._recipe), 2)
        store_id, _ = _ctx().get_store_filter()

        conn = get_connection()
        try:
            if self.dish_id:
                conn.execute(
                    "UPDATE dishes SET name=?, category=?, selling_price=?, cost_price=?, status=?, remark=? WHERE id=?",
                    (name, self.category_edit.currentText(), price, cost,
                     self.status_combo.currentText(), self.remark_edit.text().strip(), self.dish_id)
                )
                conn.execute("DELETE FROM dish_ingredients WHERE dish_id=?", (self.dish_id,))
                dish_id = self.dish_id
            else:
                cur = conn.execute(
                    "INSERT INTO dishes (name, category, selling_price, cost_price, status, remark, store_id) VALUES (?,?,?,?,?,?,?)",
                    (name, self.category_edit.currentText(), price, cost,
                     self.status_combo.currentText(), self.remark_edit.text().strip(), store_id)
                )
                dish_id = cur.lastrowid

            for r in self._recipe:
                conn.execute(
                    "INSERT INTO dish_ingredients (dish_id, ingredient_id, quantity) VALUES (?,?,?)",
                    (dish_id, r["ingredient_id"], r["quantity"])
                )

            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "成功", "菜品已保存")
            self.accept()
        except Exception as e:
            logger.error(f"DishDialog _save: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"保存失败: {e}")
        finally:
            conn.close()


# ========== 成本核算主界面 ==========

class CostCalcWidget(QWidget):
    """成本核算主界面：2个Tab"""

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabBar::tab {{
                background: {COLOR['bg_card']};
                color: {COLOR['text_secondary']};
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: {RADIUS['sm']}px;
                border-top-right-radius: {RADIUS['sm']}px;
                font-size: {FONT_SIZE['md']}px;
            }}
            QTabBar::tab:selected {{
                background: {COLOR['primary']};
                color: white;
            }}
        """)

        tab1 = self._build_dish_tab()
        tabs.addTab(tab1, "菜品成本核算")

        tab2 = self._build_monthly_tab()
        tabs.addTab(tab2, "月度产品耗用")

        layout.addWidget(tabs)

    # ---- Tab1: 菜品成本核算 ----

    def _build_dish_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 8)

        # 工具栏
        toolbar = QHBoxLayout()
        title = QLabel("菜品成本核算")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: bold; color: {COLOR['text']};")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setStyleSheet(INPUT_STYLE)
        self.search_edit.setPlaceholderText("搜索菜品名称...")
        self.search_edit.setFixedWidth(200)
        self.search_edit.textChanged.connect(self._load_dishes)
        toolbar.addWidget(self.search_edit)

        btn_add = QPushButton("新增菜品")
        btn_add.setStyleSheet(BTN_PRIMARY)
        btn_add.clicked.connect(lambda: self._edit_dish(None))
        toolbar.addWidget(btn_add)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(BTN_PRIMARY)
        btn_refresh.clicked.connect(self._load_dishes)
        toolbar.addWidget(btn_refresh)

        layout.addLayout(toolbar)

        # 汇总卡片
        card_row = QHBoxLayout()
        self.lbl_dish_count = self._mk_card(card_row, "菜品总数", "0", COLOR['primary'])
        self.lbl_avg_margin = self._mk_card(card_row, "平均毛利率", "0%", COLOR['success'])
        self.lbl_low_margin = self._mk_card(card_row, "低毛利菜品(<40%)", "0", COLOR['danger'])
        layout.addLayout(card_row)

        # 表格
        self.dish_table = QTableWidget()
        self.dish_table.setStyleSheet(TABLE_STYLE)
        self.dish_table.setAlternatingRowColors(True)
        self.dish_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.dish_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dish_table.setColumnCount(8)
        self.dish_table.setHorizontalHeaderLabels(
            ["菜品名称", "分类", "售价(元)", "成本(元)", "毛利(元)", "毛利率", "状态", "操作"]
        )
        header = self.dish_table.horizontalHeader()
        widths = [120, 70, 80, 80, 80, 70, 60, 120]
        for i, w in enumerate(widths):
            header.resizeSection(i, w)
        header.setStretchLastSection(True)
        self.dish_table.verticalHeader().setVisible(False)
        self.dish_table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.dish_table)

        self._load_dishes()
        return widget

    def _mk_card(self, parent_layout, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {COLOR['bg_card']};
                border-radius: {RADIUS['sm']}px;
                padding: 8px 16px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 8, 16, 8)
        tl = QLabel(title)
        tl.setStyleSheet(f"color: {COLOR['text_secondary']}; font-size: {FONT_SIZE['xs']}px;")
        vl = QLabel(value)
        vl.setStyleSheet(f"color: {color}; font-size: {FONT_SIZE['lg']}px; font-weight: bold;")
        cl.addWidget(tl)
        cl.addWidget(vl)
        parent_layout.addWidget(card)
        return vl

    def load_data(self):
        """统一刷新入口（导航切换时调用）"""
        try:
            self._load_dishes()
            self._load_monthly()
        except Exception as e:
            logger.error(f"CostCalcWidget load_data: {e}", exc_info=True)
    def _load_dishes(self):
        keyword = self.search_edit.text().strip()
        conn = get_connection()
        store_id, is_all = _ctx().get_store_filter()
        try:
            if is_all:
                if keyword:
                    rows = conn.execute(
                        "SELECT * FROM dishes WHERE name LIKE ? ORDER BY name",
                        (f"%{keyword}%",)
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM dishes ORDER BY name").fetchall()
            else:
                if keyword:
                    rows = conn.execute(
                        "SELECT * FROM dishes WHERE name LIKE ? AND (store_id=? OR store_id IS NULL) ORDER BY name",
                        (f"%{keyword}%", store_id)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM dishes WHERE store_id=? OR store_id IS NULL ORDER BY name",
                        (store_id,)
                    ).fetchall()

            self.dish_table.setRowCount(len(rows))
            total_margin_rate = 0.0
            low_count = 0
            count = len(rows)

            for i, r in enumerate(rows):
                d = dict(r)
                price = d.get("selling_price", 0) or 0
                cost = d.get("cost_price", 0) or 0
                margin = round(price - cost, 2)
                margin_rate = round(margin / price * 100, 1) if price > 0 else 0
                total_margin_rate += margin_rate
                if margin_rate < 40:
                    low_count += 1

                vals = [
                    d.get("name", ""),
                    d.get("category", "") or "",
                    f"¥{price:.2f}",
                    f"¥{cost:.2f}",
                    f"¥{margin:.2f}",
                    f"{margin_rate}%",
                    d.get("status", "在售") or "在售",
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignCenter)
                    if j == 5:
                        if margin_rate < 40:
                            item.setForeground(QColor(COLOR['danger']))
                            f = item.font()
                            f.setBold(True)
                            item.setFont(f)
                        else:
                            item.setForeground(QColor(COLOR['success']))
                    self.dish_table.setItem(i, j, item)

                cell = QWidget()
                cl = QHBoxLayout(cell)
                cl.setContentsMargins(2, 2, 2, 2)
                btn_edit = QPushButton("编辑")
                btn_edit.setFixedWidth(42)
                btn_edit.setStyleSheet(TABLE_BTN_EDIT)
                btn_edit.clicked.connect(lambda _, did=d["id"]: self._edit_dish(did))
                cl.addWidget(btn_edit)
                btn_del = QPushButton("删除")
                btn_del.setFixedWidth(42)
                btn_del.setStyleSheet(TABLE_BTN_DELETE)
                btn_del.clicked.connect(lambda _, did=d["id"], dn=d["name"]: self._delete_dish(did, dn))
                cl.addWidget(btn_del)
                self.dish_table.setCellWidget(i, 7, cell)

            self.lbl_dish_count.setText(str(count))
            avg = round(total_margin_rate / count, 1) if count > 0 else 0
            self.lbl_avg_margin.setText(f"{avg}%")
            self.lbl_low_margin.setText(str(low_count))
        except Exception as e:
            logger.error(f"CostCalcWidget _load_dishes: {e}", exc_info=True)
        conn.close()

    def _edit_dish(self, dish_id):
        dlg = DishDialog(dish_id, self)
        if dlg.exec_():
            self._load_dishes()

    def _delete_dish(self, dish_id, name):
        reply = QMessageBox.question(
            self, "确认删除", f"确认删除菜品「{name}」？\n关联的配方也将一并删除。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        try:
            conn.execute("DELETE FROM dish_ingredients WHERE dish_id=?", (dish_id,))
            conn.execute("DELETE FROM dishes WHERE id=?", (dish_id,))
            conn.commit()
            _sync_cloud()
            self._load_dishes()
        except Exception as e:
            logger.error(f"CostCalcWidget _delete_dish: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"删除失败: {e}")

    # ---- Tab2: 月度产品耗用 ----

    def _build_monthly_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 8)

        # 工具栏
        toolbar = QHBoxLayout()
        title = QLabel("月度产品耗用")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: bold; color: {COLOR['text']};")
        toolbar.addWidget(title)
        toolbar.addStretch()

        toolbar.addWidget(QLabel("月份:"))
        self.month_edit = ModernMonthEdit()
        self.month_edit.setDate(QDate.currentDate())
        self.month_edit.dateChanged.connect(self._load_monthly)
        toolbar.addWidget(self.month_edit)

        toolbar.addStretch()

        btn_calc = QPushButton("计算耗用")
        btn_calc.setStyleSheet(BTN_PRIMARY)
        btn_calc.clicked.connect(self._calc_monthly)
        toolbar.addWidget(btn_calc)

        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(BTN_PRIMARY)
        btn_export.clicked.connect(self._export_monthly)
        toolbar.addWidget(btn_export)

        layout.addLayout(toolbar)

        # 汇总卡片：上月结存/本月采购/本月结存/本月耗用
        card_row = QHBoxLayout()
        self.lbl_begin = self._mk_card(card_row, "上月结存合计", "¥0.00", COLOR['text_secondary'])
        self.lbl_purchase = self._mk_card(card_row, "本月采购合计", "¥0.00", COLOR['primary'])
        self.lbl_end = self._mk_card(card_row, "本月结存合计", "¥0.00", COLOR['text_secondary'])
        self.lbl_consumption = self._mk_card(card_row, "本月耗用合计", "¥0.00", COLOR['danger'])
        layout.addLayout(card_row)

        # 表格
        self.monthly_table = QTableWidget()
        self.monthly_table.setStyleSheet(TABLE_STYLE)
        self.monthly_table.setAlternatingRowColors(True)
        self.monthly_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.monthly_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.monthly_table.setColumnCount(8)
        self.monthly_table.setHorizontalHeaderLabels(
            ["食材", "单位", "上月结存", "本月采购", "本月结存", "本月耗用", "耗用金额(元)", "操作"]
        )
        header = self.monthly_table.horizontalHeader()
        widths = [120, 50, 80, 80, 80, 80, 100, 80]
        for i, w in enumerate(widths):
            header.resizeSection(i, w)
        header.setStretchLastSection(True)
        self.monthly_table.verticalHeader().setVisible(False)
        self.monthly_table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.monthly_table)

        self._load_monthly()
        return widget

    def _load_monthly(self):
        d = self.month_edit.date()
        year, month = d.year(), d.month()
        conn = get_connection()
        store_id, is_all = _ctx().get_store_filter()
        if is_all:
            rows = conn.execute(
        """SELECT mi.*, i.name, i.unit, i.price
           FROM monthly_inventory mi
           JOIN ingredients i ON mi.ingredient_id = i.id
           WHERE mi.year=? AND mi.month=?
           ORDER BY i.name""",
        (year, month)
    ).fetchall()
        else:
            rows = conn.execute(
        """SELECT mi.*, i.name, i.unit, i.price
           FROM monthly_inventory mi
           JOIN ingredients i ON mi.ingredient_id = i.id
           WHERE mi.year=? AND mi.month=? AND (mi.store_id=? OR mi.store_id IS NULL)
           ORDER BY i.name""",
        (year, month, store_id)
    ).fetchall()

        self.monthly_table.setRowCount(len(rows))
        total_begin = 0.0
        total_purchase = 0.0
        total_end = 0.0
        total_consumption = 0.0

        for i, r in enumerate(rows):
            rd = dict(r)
    begin = rd.get("begin_stock", 0) or 0
    purchase = rd.get("purchase_amount", 0) or 0
    end = rd.get("end_stock", 0) or 0
    consumption = rd.get("consumption", 0) or 0
    price = rd.get("price", 0) or 0
    consumption_amt = round(consumption * price, 2)

    total_begin += begin * price
    total_purchase += purchase * price
    total_end += end * price
    total_consumption += consumption_amt

    vals = [
        rd.get("name", ""),
        rd.get("unit", "") or "",
        f"{begin:.2f}",
        f"{purchase:.2f}",
        f"{end:.2f}",
        f"{consumption:.2f}",
        f"¥{consumption_amt:.2f}",
    ]
    for j, v in enumerate(vals):
        item = QTableWidgetItem(str(v))
        item.setTextAlignment(Qt.AlignCenter)
        if j == 6:
            item.setForeground(QColor(COLOR['danger']))
        self.monthly_table.setItem(i, j, item)

    btn_edit = QPushButton("编辑")
    btn_edit.setFixedWidth(50)
    btn_edit.setStyleSheet(TABLE_BTN_EDIT)
    btn_edit.clicked.connect(lambda _, rid=rd["id"]: self._edit_monthly(rid))
    self.monthly_table.setCellWidget(i, 7, btn_edit)

    self.lbl_begin.setText(f"¥{total_begin:.2f}")
    self.lbl_purchase.setText(f"¥{total_purchase:.2f}")
    self.lbl_end.setText(f"¥{total_end:.2f}")
    self.lbl_consumption.setText(f"¥{total_consumption:.2f}")

    try:
        try:
            try:
                try:
                    try:
                        try:
                            try:
                                try:
                                    try:
                                        try:
                                            try:
                                                try:
                                                    try:
                                                        try:
                                try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
            try:
        except Exception as e:
        logger.error(f"CostCalcWidget _load_monthly: {e}", exc_info=True)
        conn.close()

    def _calc_monthly(self):
        """计算月度耗用 = 上月结存 + 本月采购 - 本月结存"""
        d = self.month_edit.date()
        year, month = d.year(), d.month()
        store_id, is_all = _ctx().get_store_filter()

        reply = QMessageBox.question(
            self, "确认计算",
            f"将计算 {year}年{month}月 的产品耗用数据。\n"
            f"公式：耗用 = 上月结存 + 本月采购 - 本月结存\n\n确认继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        conn = get_connection()
    # 获取所有食材
        if is_all:
            ings = conn.execute("SELECT id, name FROM ingredients ORDER BY name").fetchall()
        else:
            ings = conn.execute(
                "SELECT id, name FROM ingredients WHERE store_id=? OR store_id IS NULL ORDER BY name",
                (store_id,)
            ).fetchall()

    # 计算上月月份
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        count = 0
        for ing in ings:
            ing_id = ing["id"]

    # 上月结存 = 上月月末结存
            prev = conn.execute(
                "SELECT end_stock FROM monthly_inventory WHERE year=? AND month=? AND ingredient_id=?",
                (prev_year, prev_month, ing_id)
            ).fetchone()
            begin_stock = prev["end_stock"] if prev else 0

    # 本月采购 = purchase_items 中的采购量
            purchase = conn.execute(
                """SELECT COALESCE(SUM(pi.quantity), 0) as total
                   FROM purchase_items pi
                   JOIN purchases p ON pi.purchase_id = p.id
                   WHERE pi.ingredient_id=? AND strftime('%Y', p.purchase_date)=? AND strftime('%m', p.purchase_date)=?""",
                (ing_id, str(year), f"{month:02d}")
            ).fetchone()
            purchase_amt = purchase["total"] if purchase else 0

    # 本月结存 = 手动输入或默认0（需用户盘点后录入）
            existing = conn.execute(
                "SELECT end_stock FROM monthly_inventory WHERE year=? AND month=? AND ingredient_id=?",
                (year, month, ing_id)
            ).fetchone()
            end_stock = existing["end_stock"] if existing else 0

    # 耗用 = 上月结存 + 本月采购 - 本月结存
            consumption = round(begin_stock + purchase_amt - end_stock, 2)

    # upsert
            conn.execute("""
                INSERT INTO monthly_inventory (year, month, ingredient_id, begin_stock, purchase_amount, end_stock, consumption, store_id)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(year, month, ingredient_id, store_id) DO UPDATE SET
                    begin_stock=excluded.begin_stock,
                    purchase_amount=excluded.purchase_amount,
                    consumption=excluded.consumption,
                    updated_at=datetime('now','localtime')
            """, (year, month, ing_id, begin_stock, purchase_amt, end_stock, consumption, store_id))
            count += 1

        conn.commit()
        _sync_cloud()
        QMessageBox.information(self, "成功", f"已计算 {count} 种食材的月度耗用")
        self._load_monthly()
    except Exception as e:
        logger.error(f"CostCalcWidget _calc_monthly: {e}", exc_info=True)
        QMessageBox.warning(self, "错误", f"计算失败: {e}")

    def _edit_monthly(self, record_id):
        """编辑月度盘点记录（主要是修改本月结存）"""
        conn = get_connection()
        row = conn.execute(
    """SELECT mi.*, i.name, i.unit
       FROM monthly_inventory mi JOIN ingredients i ON mi.ingredient_id=i.id
       WHERE mi.id=?""",
    (record_id,)
        ).fetchone()
        if not row:
    return
        d = dict(row)
        conn.close()

        dlg = QDialog(self)
        dlg.setWindowTitle("编辑月度盘点")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(DLG_STYLE)
        dl = QVBoxLayout(dlg)
        dl.addWidget(QLabel(f"食材: {d['name']} ({d['unit']})"))
        dl.addWidget(QLabel(f"月份: {d['year']}-{d['month']:02d}"))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        begin_lbl = QLabel(f"{d.get('begin_stock', 0):.2f}")
        form.addRow("上月结存:", begin_lbl)

        purchase_lbl = QLabel(f"{d.get('purchase_amount', 0):.2f}")
        form.addRow("本月采购:", purchase_lbl)

        end_spin = QDoubleSpinBox()
        end_spin.setRange(-99999, 99999)
        end_spin.setSingleStep(1)
        end_spin.setDecimals(2)
        end_spin.setValue(d.get("end_stock", 0) or 0)
        form.addRow("本月结存 *:", end_spin)

        consumption_lbl = QLabel(f"{d.get('consumption', 0):.2f}")
        consumption_lbl.setStyleSheet(f"font-weight: bold; color: {COLOR['danger']};")
        form.addRow("本月耗用:", consumption_lbl)

        def update_consumption():
            begin = d.get("begin_stock", 0) or 0
            purchase = d.get("purchase_amount", 0) or 0
            end = end_spin.value()
            consumption_lbl.setText(f"{round(begin + purchase - end, 2):.2f}")

        end_spin.valueChanged.connect(update_consumption)
        dl.addLayout(form)

        btn_lay = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(BTN_SUCCESS)
        btn_save.clicked.connect(lambda: self._save_monthly(dlg, record_id, end_spin.value(), d))
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(BTN_DANGER)
        btn_cancel.clicked.connect(dlg.reject)
        btn_lay.addStretch()
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_cancel)
        dl.addLayout(btn_lay)

        dlg.exec_()

    def _save_monthly(self, dlg, record_id, end_stock, orig):
        begin = orig.get("begin_stock", 0) or 0
        purchase = orig.get("purchase_amount", 0) or 0
        consumption = round(begin + purchase - end_stock, 2)
        conn = get_connection()
        conn.execute(
            "UPDATE monthly_inventory SET end_stock=?, consumption=?, updated_at=datetime('now','localtime') WHERE id=?",
            (end_stock, consumption, record_id)
        )
        conn.commit()
        _sync_cloud()
        QMessageBox.information(dlg, "成功", "盘点记录已更新")
        dlg.accept()
        self._load_monthly()
    except Exception as e:
        logger.error(f"CostCalcWidget _save_monthly: {e}", exc_info=True)
        QMessageBox.warning(dlg, "错误", f"保存失败: {e}")

    def _export_monthly(self):
        """导出月度耗用Excel"""
        try:
            from utils.data_io import export_data_to_excel
            d = self.month_edit.date()
            year, month = d.year(), d.month()
            filename = f"月度耗用_{year}_{month:02d}.xlsx"

            headers = ["食材", "单位", "上月结存", "本月采购", "本月结存", "本月耗用", "耗用金额(元)"]
            data = []
            for i in range(self.monthly_table.rowCount()):
                row = []
                for j in range(7):
                    item = self.monthly_table.item(i, j)
                    row.append(item.text() if item else "")
                data.append(row)

            filepath = export_data_to_excel(data, headers, filename)
            if filepath:
                QMessageBox.information(self, "成功", f"已导出: {filepath}")
        except Exception as e:
            logger.error(f"CostCalcWidget _export_monthly: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"导出失败: {e}")
