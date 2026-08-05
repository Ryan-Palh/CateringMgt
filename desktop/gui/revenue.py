# -*- coding: utf-8 -*-
"""
营业额录入模块 v5.0 —— 营收明细记账
支持渠道/套餐/类型配置联动，8列表格视图，保存自动生成财务记录
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QMessageBox, QComboBox, QGroupBox,
                             QGridLayout, QSizePolicy)
from gui.calendar_widget import ModernDateEdit, ModernMonthEdit
from PyQt5.QtCore import Qt, QDate, QTimer
from PyQt5.QtGui import QColor, QBrush, QFont
from PyQt5.QtGui import QIntValidator, QDoubleValidator

from database.db_manager import get_connection
from gui.theme import (COLOR, FONT_SIZE, TABLE_STYLE, COMBO_STYLE, INPUT_STYLE,
                       DLG_STYLE, primary_btn, success_btn, make_table_button)
from utils.font_utils import make_font
from utils.helpers import format_money
from utils.data_io import export_to_excel
from utils.app_context import get_app_context as _ctx
from gui.revenue_config import RevenueConfigDialog, create_revenue_config_tables

from utils.nutstore_sync import get_sync as _get_sync
import logging

_logger = logging.getLogger(__name__)


def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception as e:
        _logger.debug(f"云同步失败: {e}")


def _dlg_btn_save():
    btn = QPushButton("  保存营收单  ")
    btn.setStyleSheet(
        f"background-color: {COLOR['primary']}; color: #fff; border: none; "
        f"border-radius: 4px; padding: 10px 36px; font-size: 13px; font-weight: bold;")
    return btn


def _dlg_btn_cancel():
    btn = QPushButton("  取消  ")
    btn.setStyleSheet(
        f"background-color: #fff; color: {COLOR['text_primary']}; "
        f"border: 1px solid {COLOR['border']}; border-radius: 4px; "
        f"padding: 10px 36px; font-size: 13px;")
    return btn


class RevenueDialog(QDialog):
    """营收录入/编辑对话框"""

    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("编辑营收单" if data else "录入营收单")
        self.resize(900, 680)
        self.setMinimumSize(760, 580)
        self.setStyleSheet(DLG_STYLE)
        self._items = []
        self._package_prices = {}
        self._package_types = {}
        self._build_ui()
        if data:
            self._load_edit_data()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # ===== 基本信息 =====
        basic = QGroupBox("基本信息")
        basic_layout = QGridLayout(basic)
        basic_layout.setHorizontalSpacing(20)
        basic_layout.setVerticalSpacing(10)

        # 日期和备注并排，与明细区标签对齐
        lbl_date = QLabel('日期：')
        lbl_date.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        basic_layout.addWidget(lbl_date, 0, 0)
        self.date_record = ModernDateEdit()
        self.date_record.setDate(QDate.currentDate())
        self.date_record.setDisplayFormat("yyyy-MM-dd")
        self.date_record.setFixedSize(160, 38)
        basic_layout.addWidget(self.date_record, 0, 1)

        lbl_remark = QLabel('备注：')
        lbl_remark.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        basic_layout.addWidget(lbl_remark, 0, 2)
        self.txt_remark = QLineEdit()
        self.txt_remark.setPlaceholderText("备注（可选）")
        self.txt_remark.setMinimumWidth(300)
        basic_layout.addWidget(self.txt_remark, 0, 3)

        layout.addWidget(basic)

        # ===== 录入明细 =====
        detail_group = QGroupBox("录入明细")
        detail_layout = QVBoxLayout(detail_group)
        detail_layout.setSpacing(12)

        # 明细输入行
        row1 = QGridLayout()
        row1.setHorizontalSpacing(20)
        row1.setVerticalSpacing(10)

        # 渠道
        lbl_channel = QLabel('渠道<span style="color:red;">*</span>：')
        lbl_channel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(lbl_channel, 0, 0)
        self.cmb_channel = QComboBox()
        self.cmb_channel.setEditable(True)
        self.cmb_channel.setStyleSheet(COMBO_STYLE + "\nQLineEdit { caret-color: transparent; }")
        self.cmb_channel.setPlaceholderText("请选择渠道")
        self.cmb_channel.currentTextChanged.connect(self._on_channel_changed)
        self.cmb_channel.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_channel.setMinimumContentsLength(15)
        self.cmb_channel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cmb_channel.lineEdit().textChanged.connect(
            lambda: QTimer.singleShot(0, lambda: self.cmb_channel.lineEdit().setCursorPosition(0)))
        row1.addWidget(self.cmb_channel, 0, 1)

        # 套餐
        lbl_package = QLabel('套餐<span style="color:red;">*</span>：')
        lbl_package.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(lbl_package, 0, 2)
        self.cmb_package = QComboBox()
        self.cmb_package.setEditable(True)
        self.cmb_package.setStyleSheet(COMBO_STYLE + "\nQLineEdit { caret-color: transparent; }")
        self.cmb_package.setPlaceholderText("请选择套餐")
        self.cmb_package.currentTextChanged.connect(self._on_package_changed)
        self.cmb_package.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_package.setMinimumContentsLength(15)
        self.cmb_package.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cmb_package.lineEdit().textChanged.connect(
            lambda: QTimer.singleShot(0, lambda: self.cmb_package.lineEdit().setCursorPosition(0)))
        row1.addWidget(self.cmb_package, 0, 3)

        # 类型
        lbl_type = QLabel('类型<span style="color:red;">*</span>：')
        lbl_type.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(lbl_type, 1, 0)
        self.cmb_pkg_type = QComboBox()
        self.cmb_pkg_type.setEditable(True)
        self.cmb_pkg_type.setStyleSheet(COMBO_STYLE + "\nQLineEdit { caret-color: transparent; }")
        self.cmb_pkg_type.setPlaceholderText("请选择类型")
        row1.addWidget(self.cmb_pkg_type, 1, 1)

        # 数量
        lbl_qty = QLabel('数量<span style="color:red;">*</span>：')
        lbl_qty.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(lbl_qty, 1, 2)
        self.txt_qty = QLineEdit("1")
        self.txt_qty.setValidator(QIntValidator(1, 99999))
        self.txt_qty.setStyleSheet(INPUT_STYLE)
        self.txt_qty.setAlignment(Qt.AlignLeft)
        row1.addWidget(self.txt_qty, 1, 3)

        # 金额
        lbl_amount = QLabel('金额<span style="color:red;">*</span>：')
        lbl_amount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(lbl_amount, 2, 0)
        self.txt_amount = QLineEdit("0.00")
        self.txt_amount.setValidator(QDoubleValidator(0, 9999999, 2))
        self.txt_amount.setStyleSheet(INPUT_STYLE)
        self.txt_amount.setAlignment(Qt.AlignLeft)
        row1.addWidget(self.txt_amount, 2, 1)

        # 添加按钮
        btn_add = QPushButton("  添加  ")
        btn_add.setStyleSheet(primary_btn)
        btn_add.setFixedHeight(36)
        btn_add.clicked.connect(self._add_item)
        row1.addWidget(btn_add, 2, 3)

        detail_layout.addLayout(row1)

        # 合计
        self.lbl_total = QLabel("合计：¥ 0.00")
        self.lbl_total.setStyleSheet(
            f"color: {COLOR['primary']}; font-size: 14px; font-weight: bold; padding: 8px 0;")
        detail_layout.addWidget(self.lbl_total)

        # 明细表格
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(6)
        self.detail_table.setHorizontalHeaderLabels(
            ("渠道", "套餐", "类型", "数量", "金额", "操作"))
        self.detail_table.setStyleSheet(TABLE_STYLE)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.verticalHeader().setDefaultSectionSize(52)
        self.detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        detail_layout.addWidget(self.detail_table)

        layout.addWidget(detail_group)

        # ===== 按钮 =====
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = _dlg_btn_cancel()
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = _dlg_btn_save()
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # 加载渠道列表
        self._load_channels()

    # ── 数据加载 ──
    def _load_channels(self):
        """加载渠道列表"""
        self.cmb_channel.blockSignals(True)
        self.cmb_channel.clear()
        conn = get_connection()
        cursor = conn.cursor()
        _sid = _ctx().get_store_filter()
        try:
            if _sid[1]:
                cursor.execute("SELECT DISTINCT channel_name FROM revenue_channels ORDER BY sort_order, id")
            else:
                cursor.execute(
                    "SELECT DISTINCT channel_name FROM revenue_channels "
                    "WHERE store_id=? OR store_id IS NULL ORDER BY sort_order, id",
                    (_sid[0],))
            for r in cursor.fetchall():
                name = r["channel_name"] if "channel_name" in r.keys() else r[0]
                if name:
                    self.cmb_channel.addItem(name)
            self.cmb_channel.setCurrentIndex(-1)
        except Exception:
            import traceback; traceback.print_exc()
        finally:
            self.cmb_channel.blockSignals(False)
            conn.close()

    def _load_package_types(self, channel):
        """加载指定渠道的套餐类型"""
        self.cmb_pkg_type.blockSignals(True)
        self.cmb_pkg_type.clear()
        self.cmb_pkg_type.setCurrentIndex(-1)
        if not channel:
            self.cmb_pkg_type.blockSignals(False)
            return
        conn = get_connection()
        cursor = conn.cursor()
        _sid = _ctx().get_store_filter()
        try:
            if _sid[1]:
                cursor.execute(
                    "SELECT DISTINCT type_name FROM revenue_package_types "
                    "WHERE type_name != '' AND channel_name=? ORDER BY id",
                    (channel,))
            else:
                cursor.execute(
                    "SELECT DISTINCT type_name FROM revenue_package_types "
                    "WHERE type_name != '' AND channel_name=? "
                    "AND (store_id=? OR store_id IS NULL) ORDER BY id",
                    (channel, _sid[0]))
            for r in cursor.fetchall():
                name = r["type_name"] if "type_name" in r.keys() else r[0]
                if name:
                    self.cmb_pkg_type.addItem(name)
            self.cmb_pkg_type.setCurrentIndex(0)
        except Exception:
            import traceback; traceback.print_exc()
        finally:
            self.cmb_pkg_type.blockSignals(False)
            conn.close()

    def _load_packages(self, channel):
        """加载指定渠道的套餐列表"""
        self.cmb_package.blockSignals(True)
        self.cmb_package.clear()
        self._package_prices = {}
        self._package_types = {}
        if not channel:
            self.cmb_package.blockSignals(False)
            return
        conn = get_connection()
        cursor = conn.cursor()
        _sid = _ctx().get_store_filter()
        try:
            if _sid[1]:
                cursor.execute(
                    "SELECT DISTINCT package_name, price, type_name "
                    "FROM revenue_packages WHERE channel_name=? ORDER BY id",
                    (channel,))
            else:
                cursor.execute(
                    "SELECT DISTINCT package_name, price, type_name "
                    "FROM revenue_packages WHERE channel_name=? "
                    "AND (store_id=? OR store_id IS NULL) ORDER BY id",
                    (channel, _sid[0]))
            for r in cursor.fetchall():
                pkg_name = r["package_name"] if "package_name" in r.keys() else r[0]
                if pkg_name:
                    self.cmb_package.addItem(pkg_name)
                    self._package_prices[pkg_name] = r["price"] if "price" in r.keys() else r[1]
                    self._package_types[pkg_name] = (
                        r["type_name"] if "type_name" in r.keys()
                        else (r[2] if len(r) > 2 else ""))
            self.cmb_package.setCurrentIndex(0)
            self.cmb_package.lineEdit().setCursorPosition(0)
        except Exception:
            import traceback; traceback.print_exc()
        finally:
            self.cmb_package.blockSignals(False)
            conn.close()

    # ── 事件处理 ──
    def _on_channel_changed(self, channel):
        ch = channel.strip() if channel else ""
        self.cmb_channel.setToolTip(ch)
        try:
            self._load_package_types(ch)
            self._load_packages(ch)
        except Exception:
            import traceback; traceback.print_exc()

    def _on_package_changed(self, pkg):
        pkg = pkg.strip() if pkg else ""
        self.cmb_package.setToolTip(pkg)
        try:
            price = self._package_prices.get(pkg)
            if price:
                self.txt_amount.setText(f"{price:.2f}")
            pkg_type = self._package_types.get(pkg, "")
            if pkg_type:
                self.cmb_pkg_type.blockSignals(True)
                idx = self.cmb_pkg_type.findText(pkg_type)
                if idx >= 0:
                    self.cmb_pkg_type.setCurrentIndex(idx)
                self.cmb_pkg_type.blockSignals(False)
        except Exception:
            import traceback; traceback.print_exc()

    # ── 明细操作 ──
    def _add_item(self):
        """添加一条明细"""
        channel = self.cmb_channel.currentText().strip()
        pkg_type = self.cmb_pkg_type.currentText().strip()
        package = self.cmb_package.currentText().strip()
        qty_text = self.txt_qty.text().strip()
        try:
            qty = int(qty_text) if qty_text else 1
        except ValueError:
            qty = 1
        amount_text = self.txt_amount.text().strip()
        try:
            amount = float(amount_text) if amount_text else 0
        except ValueError:
            amount = 0

        if not channel:
            QMessageBox.warning(self, "提示", "请选择渠道")
            return
        if not package:
            QMessageBox.warning(self, "提示", "请选择套餐")
            return
        if not pkg_type:
            QMessageBox.warning(self, "提示", "请选择类型")
            return
        if not qty_text:
            QMessageBox.warning(self, "提示", "请输入数量")
            return
        if not amount_text:
            QMessageBox.warning(self, "提示", "请输入金额")
            return

        self._items.append({
            "channel": channel,
            "pkg_type": pkg_type,
            "package": package,
            "qty": qty,
            "amount": amount,
        })
        self._refresh_detail_table()

        # 清空输入
        self.txt_qty.setText("1")
        self.txt_amount.setText("0.00")
        self.cmb_package.setCurrentIndex(-1)
        self.cmb_package.lineEdit().blockSignals(True)
        self.cmb_package.clear()
        self.cmb_package.blockSignals(False)

    def _refresh_detail_table(self):
        """刷新明细表格"""
        self.detail_table.setRowCount(len(self._items))
        total = 0
        for i, item in enumerate(self._items):
            total += item["amount"]
            it = QTableWidgetItem(item["channel"])
            it.setTextAlignment(Qt.AlignCenter)
            it.setToolTip(item["channel"])
            self.detail_table.setItem(i, 0, it)
            _ci1 = QTableWidgetItem(item["package"])
            _ci1.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 1, _ci1)
            _ci2 = QTableWidgetItem(item["pkg_type"])
            _ci2.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 2, _ci2)
            qty_item = QTableWidgetItem(str(item["qty"]))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 3, qty_item)
            amt_item = QTableWidgetItem(f"¥{item['amount']:.2f}")
            amt_item.setTextAlignment(Qt.AlignCenter)
            self.detail_table.setItem(i, 4, amt_item)

            btn_del = make_table_button("删除", "delete")
            btn_del.clicked.connect(lambda checked, idx=i: self._remove_item(idx))
            wrapper = QWidget()
            wrapper.setObjectName("btnCell")
            wrapper.setStyleSheet("#btnCell { background: transparent; border: none; }")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(4, 0, 4, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_del)
            self.detail_table.setCellWidget(i, 5, wrapper)

        self.lbl_total.setText(f"合计：¥ {total:.2f}")

    def _remove_item(self, idx):
        """移除一条明细"""
        if 0 <= idx < len(self._items):
            self._items.pop(idx)
            self._refresh_detail_table()

    # ── 编辑加载 ──
    def _load_edit_data(self):
        """加载编辑数据"""
        d = self.data
        self.date_record.setDate(QDate.fromString(d.get("record_date", ""), "yyyy-MM-dd"))
        self.txt_remark.setText(d.get("remark", ""))
        ch = d.get("channel", "")
        pkg_type = d.get("package_type", "")
        pkg = d.get("package_name", "")
        qty = d.get("order_count", 1)
        amt = d.get("amount", 0)
        self._items.append({
            "channel": ch,
            "pkg_type": pkg_type,
            "package": pkg,
            "qty": qty,
            "amount": amt,
        })
        self._refresh_detail_table()

    # ── 保存 ──
    def _save(self):
        """保存营收记录"""
        if not self._items:
            QMessageBox.warning(self, "提示", "请添加营收明细")
            return

        record_date = self.date_record.date().toString("yyyy-MM-dd")
        remark = self.txt_remark.text().strip()
        _sid = _ctx().get_store_filter()
        _store_id = _sid[0]

        conn = get_connection()
        cursor = conn.cursor()
        try:
            if self.data:
        # 编辑模式：删除旧记录，重新插入所有明细
                cursor.execute("DELETE FROM daily_revenue WHERE id=?", (self.data["id"],))
                for item in self._items:
                    cursor.execute(
                        "INSERT INTO daily_revenue "
                        "(record_date, channel, package_type, package_name, "
                        " order_count, amount, remark, store_id) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (record_date, item["channel"], item["pkg_type"], item["package"],
                         item["qty"], item["amount"], remark, _store_id))
            else:
                total = sum(it["amount"] for it in self._items)
                for item in self._items:
                    cursor.execute(
                        "INSERT INTO daily_revenue "
                        "(record_date, channel, package_type, package_name, "
                        " order_count, amount, remark, store_id) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (record_date, item["channel"], item["pkg_type"], item["package"],
                         item["qty"], item["amount"], remark, _store_id))
            conn.commit()
            _sync_cloud()

        # 自动生成财务记录
            try:
                from utils.data_linkage import auto_finance_from_revenue
                total = sum(it["amount"] for it in self._items)
                if not self.data:
                    auto_finance_from_revenue(cursor.lastrowid, total, record_date)
                else:
                    auto_finance_from_revenue(self.data["id"], total, record_date)
            except Exception:
                pass

        # 记录操作人
            try:
                ctx = _ctx()
                op = ctx.current_username or ""
                if op and not self.data:
                    cursor.execute(
                        "UPDATE daily_revenue SET operator=? WHERE id=?",
                        (op, cursor.lastrowid))
                    conn.commit()
                    _sync_cloud()
            except Exception:
                pass

            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存失败：{e}")
        finally:
                conn.close()


class RevenueWidget(QWidget):
    """营业额管理主界面 —— 支持按天分组显示 + 日期/渠道筛选"""

    HEADERS = ("序号", "日期", "渠道", "套餐", "类型", "数量", "金额", "备注", "操作")

    def __init__(self):
        super().__init__()
        create_revenue_config_tables()
        self._migrate_add_package_type()
        self._filter_date = None  # None=全部, "YYYY-MM-DD"=指定日期
        self._filter_channel = "全部渠道"
        self._build_ui()
        # load_data() 延迟到首次切换时调用（懒加载）

    def _migrate_add_package_type(self):
        """迁移：为 daily_revenue 表添加缺失列"""
        conn = get_connection()
        cursor = conn.cursor()
        try:
            for col, sql in (
                ("channel", "ALTER TABLE daily_revenue ADD COLUMN channel TEXT DEFAULT ''"),
                ("package_name", "ALTER TABLE daily_revenue ADD COLUMN package_name TEXT DEFAULT ''"),
                ("package_type", "ALTER TABLE daily_revenue ADD COLUMN package_type TEXT DEFAULT ''"),
                ("order_count", "ALTER TABLE daily_revenue ADD COLUMN order_count INTEGER DEFAULT 1"),
            ):
                cursor.execute("PRAGMA table_info(daily_revenue)")
                cols = {row[1] for row in cursor.fetchall()}
                if col not in cols:
                    cursor.execute(sql)
                    conn.commit()
            _sync_cloud()
        except Exception:
            pass
        finally:
            conn.close()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        title = QLabel("营收明细")
        title.setFont(make_font(14, bold=True))
        layout.addWidget(title)

        # ── 操作工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_add = QPushButton("＋ 录入营收")
        btn_add.setStyleSheet(primary_btn)
        btn_add.clicked.connect(self._add_revenue)
        toolbar.addWidget(btn_add)

        btn_config = QPushButton("⚙ 配置")
        btn_config.setStyleSheet(
            f"background:{COLOR['text_secondary']}; color:white; "
            f"border:none; border-radius:4px; padding:8px 16px;")
        btn_config.clicked.connect(self._open_config)
        toolbar.addWidget(btn_config)

        btn_export = QPushButton("导出Excel")
        btn_export.setStyleSheet(
            f"background:{COLOR['primary']}; color:white; "
            f"border:none; border-radius:4px; padding:8px 16px;")
        btn_export.clicked.connect(self._export_data)
        toolbar.addWidget(btn_export)

        toolbar.addStretch()

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet(
            f"color: {COLOR['primary']}; font-size: 14px; "
            f"font-weight: bold; margin-left: 12px;")
        toolbar.addWidget(self.lbl_total)

        layout.addLayout(toolbar)

        # ── 筛选栏 ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        filter_bar.addWidget(QLabel("日期："))

        self.btn_date_all = QPushButton("全部")
        self.btn_date_all.setCheckable(True)
        self.btn_date_all.setChecked(True)
        self.btn_date_all.setFixedHeight(32)
        self.btn_date_all.setCursor(Qt.PointingHandCursor)
        self._apply_filter_btn_style(self.btn_date_all, True)
        self.btn_date_all.clicked.connect(lambda: self._on_date_filter(None))
        filter_bar.addWidget(self.btn_date_all)

        self.btn_date_today = QPushButton("今天")
        self.btn_date_today.setCheckable(True)
        self.btn_date_today.setFixedHeight(32)
        self.btn_date_today.setCursor(Qt.PointingHandCursor)
        self._apply_filter_btn_style(self.btn_date_today, False)
        self.btn_date_today.clicked.connect(lambda: self._on_date_filter("today"))
        filter_bar.addWidget(self.btn_date_today)

        filter_bar.addWidget(QLabel("指定日期："))
        self.date_filter = ModernDateEdit(default_today=True)
        self.date_filter.setFixedWidth(160)
        self.date_filter.dateChanged.connect(self._on_date_picked)
        filter_bar.addWidget(self.date_filter)

        filter_bar.addSpacing(12)
        filter_bar.addWidget(QLabel("渠道："))
        self.cmb_filter_channel = QComboBox()
        self.cmb_filter_channel.setStyleSheet(COMBO_STYLE)
        self.cmb_filter_channel.setFixedWidth(180)
        self.cmb_filter_channel.addItem("全部渠道")
        self.cmb_filter_channel.currentTextChanged.connect(lambda _: self.load_data())
        filter_bar.addWidget(self.cmb_filter_channel)

        filter_bar.addStretch()

        layout.addLayout(filter_bar)

        # 数据表格 —— 8列：日期/渠道/套餐/类型/数量/金额/备注/操作
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 260)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 120)
        self.table.setColumnWidth(7, 100)
        self.table.setColumnWidth(8, 80)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        self.setLayout(layout)

    # ── 筛选辅助 ──
    def _apply_filter_btn_style(self, btn, active):
        if active:
            btn.setStyleSheet(
                f"background:{COLOR['primary']}; color:white; "
                f"border:none; border-radius:4px; padding:4px 14px; "
                f"font-weight:500;")
        else:
            btn.setStyleSheet(
                f"background:{COLOR['bg_surface']}; color:{COLOR['text_secondary']}; "
                f"border:1px solid {COLOR['border']}; border-radius:4px; padding:4px 14px;")

    def _on_date_filter(self, mode):
        """点击 全部/今天 按钮"""
        if mode is None:
            self._filter_date = None
            self.btn_date_all.setChecked(True)
            self.btn_date_today.setChecked(False)
        elif mode == "today":
            from utils.helpers import get_today
            self._filter_date = get_today()
            self.btn_date_all.setChecked(False)
            self.btn_date_today.setChecked(True)
        self._apply_filter_btn_style(self.btn_date_all, self._filter_date is None)
        self._apply_filter_btn_style(self.btn_date_today, self._filter_date is not None)
        self.load_data()

    def _on_date_picked(self, date):
        """选择指定日期"""
        self._filter_date = date.toString("yyyy-MM-dd")
        self.btn_date_all.setChecked(False)
        self.btn_date_today.setChecked(False)
        self._apply_filter_btn_style(self.btn_date_all, False)
        self._apply_filter_btn_style(self.btn_date_today, False)
        self.load_data()

    def _load_channels(self):
        """加载渠道列表到筛选下拉框"""
        conn = get_connection()
        rows = conn.execute()
        rows = conn.execute(
            "SELECT DISTINCT channel FROM daily_revenue "
            "WHERE channel != '' ORDER BY channel"
        ).fetchall()
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
            try:
            try:
            try:
        except Exception:
            channels = []
            conn.close()
        current = self.cmb_filter_channel.currentText()
        self.cmb_filter_channel.blockSignals(True)
        self.cmb_filter_channel.clear()
        self.cmb_filter_channel.addItem("全部渠道")
        for ch in channels:
            self.cmb_filter_channel.addItem(ch)
        # 恢复之前选中
        idx = self.cmb_filter_channel.findText(current)
        if idx >= 0:
            self.cmb_filter_channel.setCurrentIndex(idx)
        self.cmb_filter_channel.blockSignals(False)

    # ── 数据加载 ──
    def load_data(self):
        """加载数据 —— 按日期分组显示，每天有汇总行"""
        self._load_channels()

        conn = get_connection()
        cursor = conn.cursor()
        _sid = _ctx().get_store_filter()
        try:
            sql = "SELECT * FROM daily_revenue WHERE 1=1"
            params = []
            if not _sid[1]:
                sql += " AND (store_id=? OR store_id IS NULL)"
                params.append(_sid[0])
            if self._filter_date:
                sql += " AND record_date=?"
                params.append(self._filter_date)
            ch = self.cmb_filter_channel.currentText()
            if ch and ch != "全部渠道":
                sql += " AND channel=?"
                params.append(ch)
            sql += " ORDER BY record_date DESC, id DESC LIMIT 500"
            cursor.execute(sql, params)
            rows = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

        # 按日期分组
        from collections import OrderedDict
        groups = OrderedDict()
        for r in rows:
            d = r.get("record_date", "")
            if d not in groups:
                groups[d] = []
            groups[d].append(r)

        # 构建表格行：每天的记录 + 小计行
        self.table.setRowCount(0)
        total = 0
        row_idx = 0
        for date_str, items in groups.items():
            day_total = 0
            day_qty = 0
            for r in items:
                day_total += r.get("amount", 0)
                day_qty += r.get("order_count", 0)
                self.table.insertRow(row_idx)
                self._fill_row(row_idx, r, date_str)
                row_idx += 1
            # 当天小计行（仅当该天有多条记录时显示）
            if len(items) > 1:
                self.table.insertRow(row_idx)
                self._fill_subtotal_row(row_idx, date_str, day_qty, day_total)
                row_idx += 1
            total += day_total

        self.lbl_total.setText(f"合计：¥ {total:.2f}  |  共 {len(rows)} 条记录  {len(groups)} 天")

    def _fill_row(self, i, r, date_str):
        """填写一条普通记录行"""
        sn = QTableWidgetItem(str(i + 1))
        sn.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 0, sn)
        _ci3 = QTableWidgetItem(date_str)
        _ci3.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 1, _ci3)
        _ci4 = QTableWidgetItem(r.get("channel", ""))
        _ci4.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 2, _ci4)
        _ci5 = QTableWidgetItem(r.get("package_name", ""))
        _ci5.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 3, _ci5)
        _ci6 = QTableWidgetItem(r.get("package_type", ""))
        _ci6.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 4, _ci6)

        qty_item = QTableWidgetItem(str(r.get("order_count", 1)))
        qty_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 5, qty_item)

        amt = r.get("amount", 0)
        amt_item = QTableWidgetItem(f"¥{amt:.2f}")
        amt_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 6, amt_item)

        _ci7 = QTableWidgetItem(r.get("remark", ""))
        _ci7.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(i, 7, _ci7)

        # 操作按钮
        widget = QWidget()
        widget.setObjectName("btnCell")
        widget.setStyleSheet("#btnCell { background: transparent; border: none; }")
        hl = QHBoxLayout(widget)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)
        hl.setAlignment(Qt.AlignCenter)
        btn_edit = make_table_button("编辑", "edit")
        rid = r.get("id")
        btn_edit.clicked.connect(lambda checked, rid=rid: self._edit_revenue(rid))
        btn_del = make_table_button("删除", "delete")
        btn_del.clicked.connect(lambda checked, rid=rid: self._delete_revenue(rid))
        hl.addWidget(btn_edit)
        hl.addWidget(btn_del)
        self.table.setCellWidget(i, 8, widget)

    def _fill_subtotal_row(self, i, date_str, qty, total):
        """填写当天小计行"""
        sn = QTableWidgetItem("")
        sn.setTextAlignment(Qt.AlignCenter)
        sn.setBackground(QBrush(QColor(COLOR['primary_light'])))
        self.table.setItem(i, 0, sn)

        label = QTableWidgetItem(f"  \u25b8 {date_str} 小计")
        label.setTextAlignment(Qt.AlignCenter)
        f = QFont()
        f.setBold(True)
        label.setFont(f)
        label.setForeground(QBrush(QColor(COLOR['primary'])))
        self.table.setItem(i, 1, label)

        for col in range(2, 8):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QBrush(QColor(COLOR['primary_light'])))
            self.table.setItem(i, col, item)

        qty_item = QTableWidgetItem(f"{qty} 单")
        qty_item.setTextAlignment(Qt.AlignCenter)
        qty_item.setFont(f)
        qty_item.setForeground(QBrush(QColor(COLOR['primary'])))
        qty_item.setBackground(QBrush(QColor(COLOR['primary_light'])))
        self.table.setItem(i, 5, qty_item)

        amt_item = QTableWidgetItem(f"¥{total:.2f}")
        amt_item.setTextAlignment(Qt.AlignCenter)
        amt_item.setFont(f)
        amt_item.setForeground(QBrush(QColor(COLOR['primary'])))
        amt_item.setBackground(QBrush(QColor(COLOR['primary_light'])))
        self.table.setItem(i, 6, amt_item)

        # 小计行背景色
        self.table.item(i, 1).setBackground(QBrush(QColor(COLOR['primary_light'])))
        self.table.item(i, 7).setBackground(QBrush(QColor(COLOR['primary_light'])))
        # 小计行不显示操作按钮
        empty = QTableWidgetItem("")
        empty.setTextAlignment(Qt.AlignCenter)
        empty.setBackground(QBrush(QColor(COLOR['primary_light'])))
        self.table.setItem(i, 8, empty)
        # 设置行高稍小
        self.table.setRowHeight(i, 36)

    # ── 操作 ──
    def _open_config(self):
        """打开渠道/套餐配置对话框"""
        try:
            dlg = RevenueConfigDialog(self)
            dlg.exec_()
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "配置错误", f"打开配置失败：\n{e}")

    def _add_revenue(self):
        """新增营收"""
        dlg = RevenueDialog(self)
        if dlg.exec_():
            self.load_data()

    def _export_data(self):
        """导出 Excel"""
        _sid = _ctx().get_store_filter()
        export_to_excel("daily_revenue", self, store_filter=_sid[0])

    def _edit_revenue(self, rev_id):
        """编辑营收记录"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_revenue WHERE id=?", (rev_id,))
        row = dict(cursor.fetchone())
        conn.close()
        dlg = RevenueDialog(self, data=row)
        if dlg.exec_():
            self.load_data()

    def _delete_revenue(self, rev_id):
        """删除营收记录"""
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除该营收记录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM daily_revenue WHERE id=?", (rev_id,))
            conn.commit()
            _sync_cloud()
        except Exception as e:
            QMessageBox.warning(self, "删除失败", str(e))
        finally:
        conn.close()
        self.load_data()
