# -*- coding: utf-8 -*-
"""
工资管理 v5.0 —— 餐饮专业版
- 工资配置：基础工资、岗位津贴、考核津贴、住房补贴、加班费率等
- 个税计算（累计预扣法）、工龄工资自动计算
- 工资核算：自动汇总考勤/扣款/补贴，生成工资单
- 工资发放与历史记录查询
"""
import logging
from datetime import date, datetime, timedelta
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QFormLayout, QLineEdit,
                             QComboBox, QMessageBox, QFrame, QSpinBox,
                             QDoubleSpinBox, QTabWidget, QFileDialog, QCheckBox)
from gui.calendar_widget import ModernMonthEdit
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QDoubleValidator
from database.db_manager import get_connection
from gui.theme import (COLOR, DLG_STYLE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
                       primary_btn, success_btn, danger_btn, make_table_button,
                       TABLE_BTN_EDIT, TABLE_BTN_DELETE, TABLE_BTN_VIEW)
from utils.data_io import export_to_excel
from utils.app_context import get_app_context as _ctx
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
# 个税计算（累计预扣法）
# ============================================================
TAX_BRACKETS = [
    (0, 36000, 0.03, 0),
    (36000, 144000, 0.10, 2520),
    (144000, 300000, 0.20, 16920),
    (300000, 420000, 0.25, 31920),
    (420000, 660000, 0.30, 52920),
    (660000, 960000, 0.35, 85920),
    (960000, float('inf'), 0.45, 181920),
]
TAX_THRESHOLD = 5000  # 个税起征点

def calc_income_tax(cumulative_income, cumulative_deduction, cumulative_tax_paid):
    """计算本月应缴个税（累计预扣法）"""
    taxable = cumulative_income - cumulative_deduction - TAX_THRESHOLD
    if taxable <= 0:
        return 0
    for low, high, rate, quick_deduction in TAX_BRACKETS:
        if taxable <= high:
            cumulative_tax = taxable * rate - quick_deduction
            month_tax = max(0, cumulative_tax - cumulative_tax_paid)
            return round(month_tax, 2)
    return 0

# ============================================================
# 工龄工资计算
# ============================================================
def calc_seniority_pay(hire_date_str, base=50):
    """根据入职日期计算工龄工资，每年50元递增"""
    if not hire_date_str:
        return 0
    try:
        if '-' in hire_date_str:
            hd = datetime.strptime(hire_date_str, '%Y-%m-%d').date()
        else:
            hd = datetime.strptime(hire_date_str, '%Y%m%d').date()
        years = (date.today() - hd).days // 365
        return max(0, years * base)
    except Exception:
        return 0

# ============================================================
# 管理层判断
# ============================================================
MANAGEMENT_POSITIONS = ['店长', '副店长', '经理', '厨师长', '主管', '总监']

def is_management(position):
    """判断是否为管理层"""
    if not position:
        return False
    return any(mp in position for mp in MANAGEMENT_POSITIONS)


# ============================================================
# 全局配置对话框
# ============================================================
class GlobalConfigDialog(QDialog):
    """全局工资配置：个税起征点、税率表、工龄工资基数"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局工资配置")
        self.resize(480, 360)
        self.setMinimumSize(420, 320)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("全局工资配置")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)

        self.sp_threshold = QDoubleSpinBox()
        self.sp_threshold.setRange(0, 99999)
        self.sp_threshold.setValue(TAX_THRESHOLD)
        self.sp_threshold.setPrefix("¥ ")
        self.sp_threshold.setFixedHeight(36)
        form.addRow("个税起征点：", self.sp_threshold)

        self.sp_seniority_base = QSpinBox()
        self.sp_seniority_base.setRange(0, 500)
        self.sp_seniority_base.setValue(50)
        self.sp_seniority_base.setSuffix(" 元/年")
        self.sp_seniority_base.setFixedHeight(36)
        form.addRow("工龄工资基数：", self.sp_seniority_base)

        self.sp_overtime_rate = QDoubleSpinBox()
        self.sp_overtime_rate.setRange(1.0, 3.0)
        self.sp_overtime_rate.setValue(1.5)
        self.sp_overtime_rate.setDecimals(1)
        self.sp_overtime_rate.setSingleStep(0.5)
        self.sp_overtime_rate.setFixedHeight(36)
        form.addRow("加班费率：", self.sp_overtime_rate)

        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(primary_btn)
        btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)


# ============================================================
# 工资明细查看对话框
# ============================================================
class SalaryDetailDialog(QDialog):
    """查看工资明细"""
    def __init__(self, parent=None, record=None):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle("工资明细")
        self.resize(500, 560)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        title = QLabel("工资明细")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        d = self.record or {}
        items = [
            ("基础工资", d.get('base_salary', 0)),
            ("加班工资", d.get('overtime_pay', 0)),
            ("奖金", d.get('bonus', 0)),
            ("扣款", d.get('deduction', 0)),
            ("实发工资", d.get('actual_salary', 0)),
        ]
        for label, val in items:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size: 14px; color: {COLOR['text_secondary']};")
            row.addWidget(lbl)
            row.addStretch()
            val_lbl = QLabel(f"¥ {val:,.2f}")
            val_lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {COLOR['text_primary']};")
            row.addWidget(val_lbl)
            layout.addLayout(row)

        layout.addWidget(QFrame().setFrameShape(QFrame.HLine))
        layout.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet(primary_btn)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
        self.setLayout(layout)


# ============================================================
# 员工工资配置对话框
# ============================================================
class EmployeeSalaryDialog(QDialog):
    def __init__(self, parent=None, employee=None, config=None):
        super().__init__(parent)
        self.employee = employee
        self.config = config
        self.setWindowTitle(f"工资配置 - {employee['name']}" if employee else "工资配置")
        self.resize(560, 620)
        self.setMinimumSize(500, 560)
        self.setStyleSheet(DLG_STYLE)
        self._build_ui()
        if config:
            self._load_config()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        title = QLabel(f"工资配置 - {self.employee['name']}" if self.employee else "工资配置")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.sp_base = QDoubleSpinBox()
        self.sp_base.setRange(0, 999999)
        self.sp_base.setDecimals(2)
        self.sp_base.setPrefix("¥ ")
        self.sp_base.setFixedHeight(36)
        form.addRow("基础工资：", self.sp_base)

        self.sp_position = QDoubleSpinBox()
        self.sp_position.setRange(0, 999999)
        self.sp_position.setDecimals(2)
        self.sp_position.setPrefix("¥ ")
        self.sp_position.setFixedHeight(36)
        form.addRow("岗位津贴：", self.sp_position)

        self.sp_assessment = QDoubleSpinBox()
        self.sp_assessment.setRange(0, 999999)
        self.sp_assessment.setDecimals(2)
        self.sp_assessment.setPrefix("¥ ")
        self.sp_assessment.setFixedHeight(36)
        form.addRow("考核津贴：", self.sp_assessment)

        self.sp_housing = QDoubleSpinBox()
        self.sp_housing.setRange(0, 99999)
        self.sp_housing.setDecimals(2)
        self.sp_housing.setPrefix("¥ ")
        self.sp_housing.setFixedHeight(36)
        form.addRow("住房补贴：", self.sp_housing)

        self.sp_uniform = QDoubleSpinBox()
        self.sp_uniform.setRange(0, 99999)
        self.sp_uniform.setDecimals(2)
        self.sp_uniform.setPrefix("¥ ")
        self.sp_uniform.setFixedHeight(36)
        form.addRow("工服退还：", self.sp_uniform)

        self.sp_prev_supplement = QDoubleSpinBox()
        self.sp_prev_supplement.setRange(0, 99999)
        self.sp_prev_supplement.setDecimals(2)
        self.sp_prev_supplement.setPrefix("¥ ")
        self.sp_prev_supplement.setFixedHeight(36)
        form.addRow("上月补发：", self.sp_prev_supplement)

        self.sp_advance = QDoubleSpinBox()
        self.sp_advance.setRange(0, 99999)
        self.sp_advance.setDecimals(2)
        self.sp_advance.setPrefix("¥ ")
        self.sp_advance.setFixedHeight(36)
        form.addRow("借支扣除：", self.sp_advance)

        self.sp_fine = QDoubleSpinBox()
        self.sp_fine.setRange(0, 99999)
        self.sp_fine.setDecimals(2)
        self.sp_fine.setPrefix("¥ ")
        self.sp_fine.setFixedHeight(36)
        form.addRow("罚款赔偿：", self.sp_fine)

        self.sp_deduction_per_day = QDoubleSpinBox()
        self.sp_deduction_per_day.setRange(0, 99999)
        self.sp_deduction_per_day.setDecimals(2)
        self.sp_deduction_per_day.setPrefix("¥ ")
        self.sp_deduction_per_day.setFixedHeight(36)
        form.addRow("日扣款标准：", self.sp_deduction_per_day)

        self.chk_housing = QCheckBox("是否提供住房")
        form.addRow("", self.chk_housing)

        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet(primary_btn)
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_config(self):
        c = self.config
        self.sp_base.setValue(c.get('base_salary', 0) or 0)
        self.sp_position.setValue(c.get('position_allowance', 0) or 0)
        self.sp_assessment.setValue(c.get('assessment_allowance', 0) or 0)
        self.sp_housing.setValue(c.get('housing_allowance', 0) or 0)
        self.sp_uniform.setValue(c.get('uniform_refund', 0) or 0)
        self.sp_prev_supplement.setValue(c.get('prev_supplement', 0) or 0)
        self.sp_advance.setValue(c.get('salary_advance', 0) or 0)
        self.sp_fine.setValue(c.get('fine_compensation', 0) or 0)
        self.sp_deduction_per_day.setValue(c.get('deduction_per_day', 0) or 0)
        self.chk_housing.setChecked(c.get('is_housing', '否') == '是')

    def _save(self):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""INSERT OR REPLACE INTO salary_config
                              (employee_id, base_salary, position_allowance, assessment_allowance,
                               housing_allowance, uniform_refund, prev_supplement, salary_advance,
                               fine_compensation, is_housing, deduction_per_day)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                           (self.employee['id'], self.sp_base.value(), self.sp_position.value(),
                            self.sp_assessment.value(), self.sp_housing.value(),
                            self.sp_uniform.value(), self.sp_prev_supplement.value(),
                            self.sp_advance.value(), self.sp_fine.value(),
                            '是' if self.chk_housing.isChecked() else '否',
                            self.sp_deduction_per_day.value()))
            conn.commit()
            _sync_cloud()
            self.accept()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")


# ============================================================
# 工资计算器
# ============================================================
class SalaryCalculator:
    """工资计算引擎"""
    def __init__(self, year, month):
        self.year = year
        self.month = month

    def calculate_all(self):
        """计算所有员工工资"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT e.id, e.name, e.position, e.hire_date, e.store_id,
                                 sc.base_salary, sc.position_allowance, sc.assessment_allowance,
                                 sc.housing_allowance, sc.uniform_refund, sc.prev_supplement,
                                 sc.salary_advance, sc.fine_compensation, sc.is_housing,
                                 sc.deduction_per_day
                          FROM employees e
                          LEFT JOIN salary_config sc ON e.id = sc.employee_id
                          WHERE e.status = '在职'
                          ORDER BY e.id""")
        employees = [dict(r) for r in cursor.fetchall()]
        conn.close()

        results = []
        for emp in employees:
            salary = self._calc_employee(emp)
            results.append(salary)

        input(f"计算结果：{len(results)} 人")
        return results

    def _calc_employee(self, emp):
        base = emp.get('base_salary', 0) or 0
        position = emp.get('position_allowance', 0) or 0
        assessment = emp.get('assessment_allowance', 0) or 0
        housing = emp.get('housing_allowance', 0) or 0
        uniform = emp.get('uniform_refund', 0) or 0
        prev = emp.get('prev_supplement', 0) or 0
        advance = emp.get('salary_advance', 0) or 0
        fine = emp.get('fine_compensation', 0) or 0
        seniority = calc_seniority_pay(emp.get('hire_date', ''))

        total_income = base + position + assessment + housing + uniform + prev + seniority
        total_deduction = advance + fine

        actual = total_income - total_deduction
        return {
            'employee_id': emp['id'],
            'name': emp['name'],
            'position': emp.get('position', ''),
            'base_salary': base,
            'position_allowance': position,
            'assessment_allowance': assessment,
            'housing_allowance': housing,
            'uniform_refund': uniform,
            'prev_supplement': prev,
            'seniority_pay': seniority,
            'salary_advance': advance,
            'fine_compensation': fine,
            'overtime_pay': 0,
            'bonus': 0,
            'deduction': total_deduction,
            'actual_salary': actual,
            'total_income': total_income,
        }


# ============================================================
# 工资管理主界面
# ============================================================
class SalaryWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLOR['bg_page']};")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"QTabWidget::pane {{ border: none; }}")

        self.tab_config = QWidget()
        self._build_config_tab()
        self.tabs.addTab(self.tab_config, "工资配置")

        self.tab_calc = QWidget()
        self._build_calc_tab()
        self.tabs.addTab(self.tab_calc, "工资核算")

        self.tab_records = QWidget()
        self._build_records_tab()
        self.tabs.addTab(self.tab_records, "工资记录")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self._loaded_tabs = {0: True}
        self._load_config()

    def _on_tab_changed(self, index):
        if index in self._loaded_tabs:
            return
        loaders = {0: self._load_config, 1: self._load_calc, 2: self._load_records}
        if index in loaders:
            loaders[index]()
            self._loaded_tabs[index] = True

    # ========== 工资配置 ==========
    def _build_config_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        btn_global = QPushButton("全局配置")
        btn_global.setStyleSheet(success_btn)
        btn_global.clicked.connect(self._global_config)
        toolbar.addWidget(btn_global)
        toolbar.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet(primary_btn)
        btn_refresh.clicked.connect(self._load_config)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self.config_table = QTableWidget()
        self.config_table.setColumnCount(10)
        self.config_table.setHorizontalHeaderLabels(["序号", "姓名", "职位", "基础工资", "岗位津贴", "考核津贴", "住房补贴", "提供住房", "日扣款", "操作"])
        self.config_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.config_table.setStyleSheet(TABLE_STYLE)
        self.config_table.verticalHeader().setVisible(False)
        self.config_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.config_table)
        self.tab_config.setLayout(layout)

    def _load_config(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT e.id, e.name, e.position,
                                 sc.base_salary, sc.position_allowance, sc.assessment_allowance,
                                 sc.housing_allowance, sc.is_housing, sc.deduction_per_day,
                                 sc.id as config_id
                          FROM employees e
                          LEFT JOIN salary_config sc ON e.id = sc.employee_id
                          WHERE e.status = '在职'
                          ORDER BY e.id""")
        rows = cursor.fetchall()
        conn.close()
        self.config_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            self.config_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.config_table.setItem(i, 1, QTableWidgetItem(d['name']))
            self.config_table.setItem(i, 2, QTableWidgetItem(d.get('position', '') or ''))
            self.config_table.setItem(i, 3, QTableWidgetItem(f"{d.get('base_salary', 0) or 0:,.0f}"))
            self.config_table.setItem(i, 4, QTableWidgetItem(f"{d.get('position_allowance', 0) or 0:,.0f}"))
            self.config_table.setItem(i, 5, QTableWidgetItem(f"{d.get('assessment_allowance', 0) or 0:,.0f}"))
            self.config_table.setItem(i, 6, QTableWidgetItem(f"{d.get('housing_allowance', 0) or 0:,.0f}"))
            self.config_table.setItem(i, 7, QTableWidgetItem(d.get('is_housing', '否') or '否'))
            self.config_table.setItem(i, 8, QTableWidgetItem(f"{d.get('deduction_per_day', 0) or 0:,.0f}"))
            btn_edit = QPushButton("编辑")
            btn_edit.setStyleSheet(TABLE_BTN_EDIT)
            btn_edit.clicked.connect(lambda checked, eid=d['id'], ename=d['name']: self._edit_config(eid, ename))
            self.config_table.setCellWidget(i, 9, btn_edit)

    def _global_config(self):
        dlg = GlobalConfigDialog(self)
        dlg.exec_()

    def _edit_config(self, eid, ename):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM salary_config WHERE employee_id = ?", (eid,))
        config = dict(cursor.fetchone()) if cursor.rowcount > 0 else None
        cursor.execute("SELECT * FROM employees WHERE id = ?", (eid,))
        emp = dict(cursor.fetchone()) if cursor.rowcount > 0 else None
        conn.close()
        dlg = EmployeeSalaryDialog(self, emp, config)
        if dlg.exec_() == QDialog.Accepted:
            self._load_config()

    # ========== 工资核算 ==========
    def _build_calc_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("核算月份："))
        self.calc_month = ModernMonthEdit()
        self.calc_month.setFixedWidth(180)
        toolbar.addWidget(self.calc_month)
        toolbar.addStretch()
        btn_calc = QPushButton("计算工资")
        btn_calc.setStyleSheet(primary_btn)
        btn_calc.clicked.connect(self._calc_salary)
        toolbar.addWidget(btn_calc)
        btn_save_all = QPushButton("保存工资单")
        btn_save_all.setStyleSheet(success_btn)
        btn_save_all.clicked.connect(self._save_salary)
        toolbar.addWidget(btn_save_all)
        layout.addLayout(toolbar)

        self.calc_summary = QLabel()
        self.calc_summary.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR['primary']}; padding: 8px;")
        layout.addWidget(self.calc_summary)

        self.calc_table = QTableWidget()
        self.calc_table.setColumnCount(11)
        self.calc_table.setHorizontalHeaderLabels(["序号", "姓名", "职位", "基础工资", "岗位津贴", "考核津贴", "工龄工资", "扣款", "实发工资", "状态", "操作"])
        self.calc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.calc_table.setStyleSheet(TABLE_STYLE)
        self.calc_table.verticalHeader().setVisible(False)
        self.calc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.calc_table)
        self.tab_calc.setLayout(layout)

    def _load_calc(self):
        month_str = self.calc_month.date().toString('yyyy-MM')
        year, month = month_str.split('-')
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT sr.*, e.name, e.position
                          FROM salary_records sr
                          JOIN employees e ON sr.employee_id = e.id
                          WHERE sr.year = ? AND sr.month = ?
                          ORDER BY e.id""", (int(year), int(month)))
        rows = cursor.fetchall()
        conn.close()
        self._calc_results = [dict(r) for r in rows]
        self._display_calc(self._calc_results)

    def _calc_salary(self):
        month_str = self.calc_month.date().toString('yyyy-MM')
        year, month = month_str.split('-')
        calc = SalaryCalculator(int(year), int(month))
        self._calc_results = calc.calculate_all()
        self._display_calc(self._calc_results)

    def _display_calc(self, results):
        total_salary = sum(r['actual_salary'] for r in results)
        self.calc_summary.setText(f"  共 {len(results)} 人，工资合计：¥ {total_salary:,.2f}")
        self.calc_table.setRowCount(len(results))
        for i, r in enumerate(results):
            self.calc_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.calc_table.setItem(i, 1, QTableWidgetItem(r['name']))
            self.calc_table.setItem(i, 2, QTableWidgetItem(r.get('position', '') or ''))
            self.calc_table.setItem(i, 3, QTableWidgetItem(f"{r['base_salary']:,.0f}"))
            self.calc_table.setItem(i, 4, QTableWidgetItem(f"{r.get('position_allowance', 0):,.0f}"))
            self.calc_table.setItem(i, 5, QTableWidgetItem(f"{r.get('assessment_allowance', 0):,.0f}"))
            self.calc_table.setItem(i, 6, QTableWidgetItem(f"{r.get('seniority_pay', 0):,.0f}"))
            self.calc_table.setItem(i, 7, QTableWidgetItem(f"{r.get('deduction', 0):,.0f}"))
            actual = r['actual_salary']
            actual_item = QTableWidgetItem(f"{actual:,.2f}")
            actual_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.calc_table.setItem(i, 8, actual_item)
            status = r.get('status', '未发放')
            status_item = QTableWidgetItem(status)
            if status == '已发放':
                status_item.setForeground(QColor(COLOR['success']))
            self.calc_table.setItem(i, 9, status_item)
            btn_detail = QPushButton("明细")
            btn_detail.setStyleSheet(TABLE_BTN_VIEW)
            btn_detail.clicked.connect(lambda checked, rd=r: self._view_detail(rd))
            self.calc_table.setCellWidget(i, 10, btn_detail)

    def _save_salary(self):
        if not self._calc_results:
            QMessageBox.warning(self, "提示", "请先计算工资")
            return
        month_str = self.calc_month.date().toString('yyyy-MM')
        year, month = month_str.split('-')
        conn = get_connection()
        cursor = conn.cursor()
        try:
            for r in self._calc_results:
                cursor.execute("""INSERT OR REPLACE INTO salary_records
                                  (employee_id, year, month, base_salary, overtime_pay, bonus,
                                   deduction, actual_salary, status, store_id)
                                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
                               (r['employee_id'], int(year), int(month),
                                r['base_salary'], r.get('overtime_pay', 0),
                                r.get('bonus', 0), r.get('deduction', 0),
                                r['actual_salary'], '未发放',
                                _ctx().current_store_id if hasattr(_ctx(), 'current_store_id') else None))
            conn.commit()
            _sync_cloud()
            QMessageBox.information(self, "提示", f"已保存 {len(self._calc_results)} 条工资记录")
            self._loaded_tabs.pop(2, None)
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")

    def _view_detail(self, record):
        dlg = SalaryDetailDialog(self, record)
        dlg.exec_()

    # ========== 工资记录 ==========
    def _build_records_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("月份："))
        self.rec_month = ModernMonthEdit()
        self.rec_month.setFixedWidth(180)
        toolbar.addWidget(self.rec_month)
        toolbar.addStretch()
        btn_query = QPushButton("查询")
        btn_query.setStyleSheet(primary_btn)
        btn_query.clicked.connect(self._load_records)
        toolbar.addWidget(btn_query)
        btn_export = QPushButton("导出")
        btn_export.setStyleSheet(success_btn)
        btn_export.clicked.connect(lambda: self._export_table(self.rec_table, "工资记录"))
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.rec_summary = QLabel()
        self.rec_summary.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR['primary']}; padding: 8px;")
        layout.addWidget(self.rec_summary)

        self.rec_table = QTableWidget()
        self.rec_table.setColumnCount(10)
        self.rec_table.setHorizontalHeaderLabels(["序号", "姓名", "基础工资", "加班", "奖金", "扣款", "实发", "状态", "发放日期", "操作"])
        self.rec_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rec_table.setStyleSheet(TABLE_STYLE)
        self.rec_table.verticalHeader().setVisible(False)
        self.rec_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.rec_table)
        self.tab_records.setLayout(layout)

    def _load_records(self):
        month_str = self.rec_month.date().toString('yyyy-MM')
        year, month = month_str.split('-')
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT sr.*, e.name
                          FROM salary_records sr
                          JOIN employees e ON sr.employee_id = e.id
                          WHERE sr.year = ? AND sr.month = ?
                          ORDER BY e.id""", (int(year), int(month)))
        rows = cursor.fetchall()
        conn.close()
        records = [dict(r) for r in rows]
        total = sum(r['actual_salary'] or 0 for r in records)
        self.rec_summary.setText(f"  共 {len(records)} 人，实发合计：¥ {total:,.2f}")
        self.rec_table.setRowCount(len(records))
        for i, r in enumerate(records):
            self.rec_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.rec_table.setItem(i, 1, QTableWidgetItem(r['name']))
            self.rec_table.setItem(i, 2, QTableWidgetItem(f"{r.get('base_salary', 0) or 0:,.0f}"))
            self.rec_table.setItem(i, 3, QTableWidgetItem(f"{r.get('overtime_pay', 0) or 0:,.0f}"))
            self.rec_table.setItem(i, 4, QTableWidgetItem(f"{r.get('bonus', 0) or 0:,.0f}"))
            self.rec_table.setItem(i, 5, QTableWidgetItem(f"{r.get('deduction', 0) or 0:,.0f}"))
            actual = r.get('actual_salary', 0) or 0
            actual_item = QTableWidgetItem(f"{actual:,.2f}")
            actual_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.rec_table.setItem(i, 6, actual_item)
            status = r.get('status', '未发放')
            status_item = QTableWidgetItem(status)
            if status == '已发放':
                status_item.setForeground(QColor(COLOR['success']))
            self.rec_table.setItem(i, 7, status_item)
            self.rec_table.setItem(i, 8, QTableWidgetItem(r.get('paid_date', '') or ''))
            if status == '未发放':
                btn_pay = QPushButton("发放")
                btn_pay.setStyleSheet(success_btn + "padding: 2px 10px;")
                btn_pay.clicked.connect(lambda checked, rid=r['id']: self._pay(rid))
                self.rec_table.setCellWidget(i, 9, btn_pay)
            else:
                btn_detail = QPushButton("明细")
                btn_detail.setStyleSheet(TABLE_BTN_VIEW)
                btn_detail.clicked.connect(lambda checked, rd=r: self._view_detail(rd))
                self.rec_table.setCellWidget(i, 9, btn_detail)

    def _pay(self, record_id):
        reply = QMessageBox.question(self, "确认", "确认发放该笔工资？")
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""UPDATE salary_records SET status='已发放', paid_date=? WHERE id=?""",
                           (date.today().strftime('%Y-%m-%d'), record_id))
            conn.commit()
            _sync_cloud()
            self._load_records()
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "错误", f"发放失败：{e}")

    def _export_table(self, table, name):
        path, _ = QFileDialog.getSaveFileName(self, "导出", f"{name}_{date.today().strftime('%Y%m%d')}.xlsx",
                                               "Excel (*.xlsx)")
        if path:
            export_to_excel(table, path)
            QMessageBox.information(self, "提示", f"已导出到：{path}")