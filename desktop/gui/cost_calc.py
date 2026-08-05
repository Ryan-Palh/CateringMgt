# -*- coding: utf-8 -*-
"""
成本核算 v5.0 —— 餐饮专业版
- 菜品成本核算：根据原料用量和单价自动计算菜品成本
- 毛利率分析：销售价 vs 成本价
- 成本占比分析：各原料成本占比
"""
import logging
from datetime import date
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QFrame, QDoubleSpinBox,
                             QFileDialog, QSpinBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from database.db_manager import get_connection
from gui.theme import (COLOR, DLG_STYLE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
                       primary_btn, success_btn, TABLE_BTN_EDIT, TABLE_BTN_DELETE)
from utils.data_io import export_to_excel
from utils.logger import logger

_logger = logging.getLogger(__name__)


class CostCalcWidget(QWidget):
    """菜品成本核算与毛利分析"""
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 汇总信息
        self.summary = QLabel()
        self.summary.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR['primary']}; padding: 8px;")
        layout.addWidget(self.summary)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_data)
        toolbar.addWidget(btn_refresh)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.table, "成本核算"))
        toolbar.addWidget(btn_export)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["序号", "菜品名称", "分类", "售价", "原料成本", "毛利", "毛利率", "状态", "原料明细"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self._load_data()

    def _load_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dishes ORDER BY id")
        dishes = [dict(r) for r in cursor.fetchall()]

        total_cost = 0
        total_price = 0
        rows_data = []

        for dish in dishes:
            cursor.execute("""SELECT di.quantity, ing.name, ing.unit, ing.price
                              FROM dish_ingredients di
                              JOIN ingredients ing ON di.ingredient_id = ing.id
                              WHERE di.dish_id = ?""", (dish['id'],))
            ingredients = [dict(r) for r in cursor.fetchall()]

            cost = sum((ing['quantity'] or 0) * (ing['price'] or 0) for ing in ingredients)
            selling_price = dish.get('selling_price', 0) or 0
            gross_profit = selling_price - cost
            margin = (gross_profit / selling_price * 100) if selling_price > 0 else 0

            total_cost += cost
            total_price += selling_price

            ing_detail = '; '.join(f"{ing['name']}×{ing['quantity']}{ing['unit']}"
                                   for ing in ingredients) if ingredients else '无'

            rows_data.append({
                'name': dish['name'],
                'category': dish.get('category', '') or '',
                'selling_price': selling_price,
                'cost': cost,
                'gross_profit': gross_profit,
                'margin': margin,
                'status': dish.get('status', '在售') or '在售',
                'ing_detail': ing_detail,
            })

        conn.close()

        overall_margin = ((total_price - total_cost) / total_price * 100) if total_price > 0 else 0
        self.summary.setText(f"  共 {len(rows_data)} 道菜品 | 总售价：¥{total_price:,.2f} | 总成本：¥{total_cost:,.2f} | 综合毛利率：{overall_margin:.1f}%")

        self.table.setRowCount(len(rows_data))
        for i, d in enumerate(rows_data):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(d['name']))
            self.table.setItem(i, 2, QTableWidgetItem(d['category']))
            sp_item = QTableWidgetItem(f"¥{d['selling_price']:,.2f}")
            sp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, sp_item)
            cost_item = QTableWidgetItem(f"¥{d['cost']:,.2f}")
            cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 4, cost_item)
            gp_item = QTableWidgetItem(f"¥{d['gross_profit']:,.2f}")
            gp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if d['gross_profit'] < 0:
                gp_item.setForeground(QColor(COLOR['danger']))
            else:
                gp_item.setForeground(QColor(COLOR['success']))
            self.table.setItem(i, 5, gp_item)
            margin_item = QTableWidgetItem(f"{d['margin']:.1f}%")
            margin_item.setTextAlignment(Qt.AlignCenter)
            if d['margin'] < 0:
                margin_item.setForeground(QColor(COLOR['danger']))
            elif d['margin'] < 30:
                margin_item.setForeground(QColor(COLOR['warning']))
            else:
                margin_item.setForeground(QColor(COLOR['success']))
            self.table.setItem(i, 6, margin_item)
            status_item = QTableWidgetItem(d['status'])
            if d['status'] != '在售':
                status_item.setForeground(QColor(COLOR['text_secondary']))
            self.table.setItem(i, 7, status_item)
            self.table.setItem(i, 8, QTableWidgetItem(d['ing_detail']))

    def _export_table(self, table, name):
        path, _ = QFileDialog.getSaveFileName(self, "导出", f"{name}_{date.today().strftime('%Y%m%d')}.xlsx",
                                               "Excel (*.xlsx)")
        if path:
            export_to_excel(table, path)
            QMessageBox.information(self, "提示", f"已导出到：{path}")