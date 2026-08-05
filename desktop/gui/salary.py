# -*- coding: utf-8 -*-
"""
工资管理模块 v5.0 — 餐饮专业版
功能：
  1. 全局配置（考勤扣款 / 试用期工龄 / 补贴扣款 / 社保个税）
  2. 薪资明细查看（完整计算项展示）
  3. 员工薪资设置（基本工资 / 岗位补贴 / 考核补贴 / 住房补贴 等）
  4. SalaryCalculator 计算引擎
     应发 = 基本工资/30×计薪天数(试用期70%折算) + 全勤 + 岗位补贴 + 考核补贴 + 住房补贴 + 工龄工资 + 上月补发 - 工服退款
     实发 = 应发 - 迟到扣款 - 旷工扣款 - 罚赔款 - 急辞扣款 - 水电扣款 - 预支工资 - 社保 - 个税
  5. 个税 7 级累进、工龄工资、试用期折算、考勤自动取数
  6. 批量发放，联动 auto_finance_from_salary 自动创建财务支出记录
"""
import calendar
from datetime import datetime, date

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QLineEdit, QComboBox,
    QMessageBox, QCheckBox, QGroupBox, QGridLayout, QSpinBox, QDoubleSpinBox,
    QTabWidget, QTextEdit, QSplitter, QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QDoubleValidator

from database.db_manager import get_connection, _safe_sql_identifier
from gui.theme import (
    COLOR, RADIUS, FONT_SIZE, TABLE_STYLE, INPUT_STYLE, COMBO_STYLE,
    DLG_STYLE, BTN_PRIMARY, BTN_SUCCESS, BTN_DANGER,
    COMPACT_TABLE_STYLE, make_table_button, TABLE_BTN_EDIT, TABLE_BTN_DELETE, TABLE_BTN_VIEW, primary_btn, success_btn, danger_btn
)
from gui.calendar_widget import ModernMonthEdit
from utils.app_context import get_app_context as _ctx
from utils.data_linkage import auto_finance_from_salary
from utils.helpers import get_today
from utils.logger import logger
from utils.nutstore_sync import get_sync as _get_sync

def _sync_cloud():
    try:
        _get_sync().trigger_sync()
    except Exception:
        pass

# ========== 常量 ==========

# 个税 7 级累进税率表
TAX_BRACKETS = [
    (3000, 0.03, 0),
    (12000, 0.10, 210),
    (25000, 0.20, 1410),
    (35000, 0.25, 2660),
    (55000, 0.30, 4410),
    (80000, 0.35, 7160),
    (float('inf'), 0.45, 15160),
]

# 餐饮管理岗（不享受全勤和工龄工资）
MGMT_POSITIONS = {"店长", "厨师长", "前厅主管", "后厨主管", "经理", "副经理"}

# 餐饮岗位补贴建议（可被 salary_config 覆盖）
DEFAULT_POSITION_ALLOWANCE = {
    "店长": 800, "厨师长": 800, "前厅主管": 500, "后厨主管": 500,
    "炒锅": 400, "切配": 200, "打荷": 150, "面点师": 300,
    "传菜员": 100, "服务员": 100, "迎宾": 100, "收银员": 200,
    "吧台": 150, "采购": 300, "保洁": 100, "会计": 500,
}


# ========== 工具函数 ==========

def calc_income_tax(taxable):
    """个税 7 级累进计算"""
    if taxable <= 0:
        return 0.0
    for limit, rate, deduction in TAX_BRACKETS:
        if taxable <= limit:
            return round(taxable * rate - deduction, 2)
    return 0.0


def calc_seniority_pay(hire_date_str, per_year, half_year, ref_date=None):
    """工龄工资：每满1年 per_year 元，满半年不满1年加 half_year 元"""
    if not hire_date_str:
        return 0.0
    try:
        hd = datetime.strptime(hire_date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0.0
    ref = ref_date or date.today()
    years = ref.year - hd.year
    months = ref.month - hd.month
    total_months = years * 12 + months
    if hd.day > ref.day:
        total_months -= 1
    if total_months < 0:
        return 0.0
    full_years = total_months // 12
    remainder = total_months % 12
    pay = full_years * per_year
    if remainder >= 6:
        pay += half_year
    return round(pay, 2)


def is_management(position):
    """判断是否管理岗"""
    return (position or "").strip() in MGMT_POSITIONS


# ========== 全局配置对话框 ==========

class GlobalConfigDialog(QDialog):
    """全局工资配置（4 组：考勤扣款 / 试用期工龄 / 补贴扣款 / 社保个税）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("工资全局配置")
        self.setMinimumWidth(560)
        self.setStyleSheet(DLG_STYLE)

        self._spin_widgets = {}
        self._check_widgets = {}

        layout = QVBoxLayout(self)
        title = QLabel("工资全局配置")
        title.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: bold; color: {COLOR['primary']};")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QVBoxLayout(inner)

        # ---- 第1组：考勤扣款 ----
        g1 = QGroupBox("考勤扣款")
        g1l = QGridLayout(g1)
        g1l.addWidget(QLabel("迟到每分钟扣(元):"), 0, 0)
        g1l.addWidget(self._mk_spin("late_deduction_per_minute", 0, 9999, 0.1), 0, 1)
        g1l.addWidget(QLabel("全勤奖(元):"), 1, 0)
        g1l.addWidget(self._mk_spin("full_attendance_amount", 0, 99999, 10), 1, 1)
        g1l.addWidget(QLabel("标准计薪天数:"), 2, 0)
        g1l.addWidget(self._mk_spin("standard_work_days", 1, 31, 1, True), 2, 1)
        g1l.addWidget(QLabel("水电扣款标准(元):"), 3, 0)
        g1l.addWidget(self._mk_spin("utility_deduction_amount", 0, 9999, 1), 3, 1)
        form.addWidget(g1)

        # ---- 第2组：试用期 & 工龄 ----
        g2 = QGroupBox("试用期 & 工龄")
        g2l = QGridLayout(g2)
        g2l.addWidget(QLabel("试用期折算比例:"), 0, 0)
        w = self._mk_spin("probation_rate", 0, 1, 0.05)
        w.setSingleStep(0.05)
        w.setDecimals(2)
        g2l.addWidget(w, 0, 1)
        g2l.addWidget(QLabel("工龄每满1年(元):"), 1, 0)
        g2l.addWidget(self._mk_spin("seniority_per_year", 0, 9999, 10), 1, 1)
        g2l.addWidget(QLabel("工龄满半年(元):"), 2, 0)
        g2l.addWidget(self._mk_spin("seniority_half_year", 0, 9999, 5), 2, 1)
        form.addWidget(g2)

        # ---- 第3组：补贴 ----
        g3 = QGroupBox("补贴标准")
        g3l = QGridLayout(g3)
        g3l.addWidget(QLabel("加班-工作日倍率:"), 0, 0)
        w = self._mk_spin("overtime_multiplier_weekday", 0, 10, 0.1)
        w.setDecimals(2)
        g3l.addWidget(w, 0, 1)
        g3l.addWidget(QLabel("加班-周末倍率:"), 1, 0)
        w = self._mk_spin("overtime_multiplier_weekend", 0, 10, 0.1)
        w.setDecimals(2)
        g3l.addWidget(w, 1, 1)
        g3l.addWidget(QLabel("加班-法定假日倍率:"), 2, 0)
        w = self._mk_spin("overtime_multiplier_holiday", 0, 10, 0.5)
        w.setDecimals(2)
        g3l.addWidget(w, 2, 1)
        form.addWidget(g3)

        # ---- 第4组：社保个税 ----
        g4 = QGroupBox("社保 & 个税")
        g4l = QGridLayout(g4)
        g4l.addWidget(QLabel("养老比例:"), 0, 0)
        w = self._mk_spin("social_pension_rate", 0, 1, 0.005)
        w.setDecimals(4)
        g4l.addWidget(w, 0, 1)
        g4l.addWidget(QLabel("医疗比例:"), 1, 0)
        w = self._mk_spin("social_medical_rate", 0, 1, 0.005)
        w.setDecimals(4)
        g4l.addWidget(w, 1, 1)
        g4l.addWidget(QLabel("失业比例:"), 2, 0)
        w = self._mk_spin("social_unemployment_rate", 0, 1, 0.005)
        w.setDecimals(4)
        g4l.addWidget(w, 2, 1)
        g4l.addWidget(QLabel("个税起征点(元):"), 3, 0)
        g4l.addWidget(self._mk_spin("tax_threshold", 0, 999999, 500), 3, 1)
        g4l.addWidget(QLabel("启用社保:"), 4, 0)
        g4l.addWidget(self._mk_check("enable_social_insurance"), 4, 1)
        g4l.addWidget(QLabel("启用个税:"), 5, 0)
        g4l.addWidget(self._mk_check("enable_income_tax"), 5, 1)
        form.addWidget(g4)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

        # ---- 按钮 ----
        btn_lay = QHBoxLayout()
        btn_save = QPushButton("保存配置")
        btn_save.setStyleSheet(BTN_SUCCESS)
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet(BTN_DANGER)
        btn_cancel.clicked.connect(self.reject)
        btn_lay.addStretch()
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_cancel)
        layout.addLayout(btn_lay)

        self._load()

    def _mk_spin(self, key, mn, mx, step, is_int=False):
        if is_int:
            w = QSpinBox()
            w.setRange(int(mn), int(mx))
            w.setSingleStep(int(step))
        else:
            w = QDoubleSpinBox()
            w.setRange(mn, mx)
            w.setSingleStep(step)
            w.setDecimals(2)
        self._spin_widgets[key] = (w, is_int)
        return w

    def _mk_check(self, key):
        w = QCheckBox()
        self._check_widgets[key] = w
        return w

    def _load(self):
        try:
            conn = get_connection()
            row = conn.execute("SELECT * FROM salary_global_config WHERE id=1").fetchone()
            if not row:
                return
            d = dict(row)
            for key, (w, is_int) in self._spin_widgets.items():
                val = d.get(key, 0)
                if is_int:
                    w.setValue(int(val or 0))
                else:
                    w.setValue(float(val or 0))
            for key, w in self._check_widgets.items():
                w.setChecked(bool(d.get(key, 0)))
        except Exception as e:
            logger.error(f"GlobalConfigDialog load: {e}", exc_info=True)
            conn.close()
    def _save(self):
        conn = get_connection()
        sets = {}
        for key, (w, is_int) in self._spin_widgets.items():
            sets[key] = int(w.value()) if is_int else round(w.value(), 4)
        for key, w in self._check_widgets.items():
            sets[key] = 1 if w.isChecked() else 0
        cols = ", ".join(f"{_safe_sql_identifier(k)}=?" for k in sets)
        vals = list(sets.values()) + [1]
        conn.execute(f"UPDATE salary_global_config SET {cols} WHERE id=?", vals)
        conn.commit()
        _sync_cloud()
        QMessageBox.information(self, "成功", "全局配置已保存")
        self.accept()
    except Exception as e:
        logger.error(f"GlobalConfigDialog save: {e}", exc_info=True)
        QMessageBox.warning(self, "错误", f"保存失败: {e}")


# ========== 工资明细对话框 ==========

class SalaryDetailDialog(QDialog):
    """工资明细查看（只读）"""

    def __init__(self, record_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("工资明细")
        self.setMinimumSize(520, 640)
        self.setStyleSheet(DLG_STYLE)

        layout = QVBoxLayout(self)
        title = QLabel("工资明细")
        title.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: bold; color: {COLOR['primary']};")
        layout.addWidget(title)

        conn = get_connection()
        row = conn.execute("SELECT * FROM salary_records WHERE id=?", (record_id,)).fetchone()
        if not row:
    QLabel("记录不存在")
    return
        d = dict(row)
        emp = conn.execute("SELECT name, position, hire_date FROM employees WHERE id=?", (d.get("employee_id"),)).fetchone()
        emp_name = emp["name"] if emp else "未知"
        emp_pos = emp["position"] if emp else ""
        conn.close()

        info = QLabel(f"员工: {emp_name}  |  岗位: {emp_pos}  |  {d.get('year', '')}年{d.get('month', '')}月")
        info.setStyleSheet(f"font-size: {FONT_SIZE['md']}px; color: {COLOR['text_secondary']}; padding: 4px 0;")
        layout.addWidget(info)

        # 收入部分
        income_group = QGroupBox("收入项目")
        il = QFormLayout(income_group)
        il.setLabelAlignment(Qt.AlignRight)
        income_items = [
            ("基本工资", d.get("base_salary", 0)),
            ("计薪天数", f'{d.get("pay_days", 0)} 天'),
            ("全勤奖", d.get("full_attendance", 0)),
            ("岗位补贴", d.get("position_allowance", 0)),
            ("考核补贴", d.get("assessment_allowance", 0)),
            ("住房补贴", d.get("housing_allowance", 0)),
            ("工龄工资", d.get("seniority_pay", 0)),
            ("上月补发", d.get("prev_supplement", 0)),
            ("工服退款", d.get("uniform_refund", 0)),
        ]
        for label, val in income_items:
            if isinstance(val, (int, float)):
                v = f"¥{val:.2f}"
            else:
                v = str(val)
            lbl = QLabel(v)
            lbl.setStyleSheet(f"color: {COLOR['text']};")
            il.addRow(label, lbl)
        gross = d.get("gross_salary", 0)
        gross_lbl = QLabel(f"¥{gross:.2f}")
        gross_lbl.setStyleSheet(f"font-weight: bold; color: {COLOR['success']}; font-size: {FONT_SIZE['md']}px;")
        il.addRow("应发合计", gross_lbl)
        layout.addWidget(income_group)

        # 扣款部分
        ded_group = QGroupBox("扣款项目")
        dl = QFormLayout(ded_group)
        dl.setLabelAlignment(Qt.AlignRight)
        ded_items = [
            ("迟到扣款", d.get("late_deduction", 0)),
            ("旷工扣款", d.get("absent_deduction", 0)),
            ("罚赔款", d.get("fine_compensation", 0)),
            ("急辞扣款", d.get("urgent_deduction", 0)),
            ("水电扣款", d.get("utility_deduction", 0)),
            ("预支工资", d.get("salary_advance", 0)),
            ("社保", d.get("social_insurance", 0)),
            ("公积金", d.get("housing_fund", 0)),
            ("个税", d.get("income_tax", 0)),
        ]
        for label, val in ded_items:
            lbl = QLabel(f"¥{val:.2f}")
            lbl.setStyleSheet(f"color: {COLOR['text']};")
            dl.addRow(label, lbl)
        total_ded = d.get("total_deduction", 0)
        ded_lbl = QLabel(f"¥{total_ded:.2f}")
        ded_lbl.setStyleSheet(f"font-weight: bold; color: {COLOR['danger']}; font-size: {FONT_SIZE['md']}px;")
        dl.addRow("扣款合计", ded_lbl)
        layout.addWidget(ded_group)

        # 实发
        actual = d.get("actual_salary", 0)
        actual_lbl = QLabel(f"实发工资: ¥{actual:.2f}")
        actual_lbl.setStyleSheet(
            f"font-size: {FONT_SIZE['xl']}px; font-weight: bold; color: {COLOR['primary']}; "
            f"padding: 8px; background: {COLOR['bg_card']}; border-radius: {RADIUS['sm']}px;"
        )
        actual_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(actual_lbl)

        status = d.get("status", "未发放")
        st_lbl = QLabel(f"状态: {status}" + (f"  |  发放日期: {d.get('paid_date', '')}" if d.get("paid_date") else ""))
        st_lbl.setStyleSheet(f"color: {COLOR['text_secondary']}; padding: 4px;")
        layout.addWidget(st_lbl)

        if d.get("remark"):
            rmk = QLabel(f"备注: {d['remark']}")
            rmk.setStyleSheet(f"color: {COLOR['text_secondary']}; padding: 4px;")
            rmk.setWordWrap(False)
            layout.addWidget(rmk)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet(BTN_PRIMARY)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ========== 员工薪资设置对话框 ==========

class EmployeeSalaryDialog(QDialog):
    """员工薪资设置：基本工资、岗位补贴、考核补贴、住房补贴等"""

    def __init__(self, employee_id, parent=None):
        super().__init__(parent)
        self.employee_id = employee_id
        self.setWindowTitle("薪资设置")
        self.setMinimumWidth(460)
        self.setStyleSheet(DLG_STYLE)

        layout = QVBoxLayout(self)
        title = QLabel("员工薪资设置")
        title.setStyleSheet(f"font-size: {FONT_SIZE['lg']}px; font-weight: bold; color: {COLOR['primary']};")
        layout.addWidget(title)

        conn = get_connection()
        emp_info = None
        try:
            emp_info = conn.execute(
                "SELECT name, position, base_salary, hire_date FROM employees WHERE id=?",
                (employee_id,)
            ).fetchone()
        finally:
            conn.close()

        if emp_info:
            info = QLabel(f"员工: {emp_info['name']}  |  岗位: {emp_info['position'] or '未设置'}  |  入职: {emp_info['hire_date'] or '未设置'}")
            info.setStyleSheet(f"color: {COLOR['text_secondary']}; padding: 4px 0;")
            layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.base_salary = QDoubleSpinBox()
        self.base_salary.setRange(0, 999999)
        self.base_salary.setSingleStep(100)
        self.base_salary.setDecimals(2)
        self.base_salary.setValue(emp_info["base_salary"] if emp_info else 0)
        form.addRow("基本工资(元):", self.base_salary)

        self.position_allowance = QDoubleSpinBox()
        self.position_allowance.setRange(0, 99999)
        self.position_allowance.setSingleStep(50)
        self.position_allowance.setDecimals(2)
        pos = emp_info["position"] if emp_info else ""
        self.position_allowance.setValue(DEFAULT_POSITION_ALLOWANCE.get(pos, 0))
        form.addRow("岗位补贴(元):", self.position_allowance)

        self.assessment_allowance = QDoubleSpinBox()
        self.assessment_allowance.setRange(0, 99999)
        self.assessment_allowance.setSingleStep(50)
        self.assessment_allowance.setDecimals(2)
        self.assessment_allowance.setValue(0)
        form.addRow("考核补贴(元):", self.assessment_allowance)

        self.housing_allowance = QDoubleSpinBox()
        self.housing_allowance.setRange(0, 99999)
        self.housing_allowance.setSingleStep(100)
        self.housing_allowance.setDecimals(2)
        self.housing_allowance.setValue(0)
        form.addRow("住房补贴(元):", self.housing_allowance)

        self.uniform_refund = QDoubleSpinBox()
        self.uniform_refund.setRange(0, 99999)
        self.uniform_refund.setSingleStep(50)
        self.uniform_refund.setDecimals(2)
        self.uniform_refund.setValue(0)
        form.addRow("工服退款(元):", self.uniform_refund)

        self.prev_supplement = QDoubleSpinBox()
        self.prev_supplement.setRange(0, 99999)
        self.prev_supplement.setSingleStep(50)
        self.prev_supplement.setDecimals(2)
        self.prev_supplement.setValue(0)
        form.addRow("上月补发(元):", self.prev_supplement)

        self.salary_advance = QDoubleSpinBox()
        self.salary_advance.setRange(0, 999999)
        self.salary_advance.setSingleStep(100)
        self.salary_advance.setDecimals(2)
        self.salary_advance.setValue(0)
        form.addRow("预支工资(元):", self.salary_advance)

        self.fine_compensation = QDoubleSpinBox()
        self.fine_compensation.setRange(0, 99999)
        self.fine_compensation.setSingleStep(50)
        self.fine_compensation.setDecimals(2)
        self.fine_compensation.setValue(0)
        form.addRow("罚赔款(元):", self.fine_compensation)

        self.is_housing = QComboBox()
        self.is_housing.addItems(["否", "是"])
        form.addRow("提供住宿:", self.is_housing)

        self.remark = QLineEdit()
        self.remark.setStyleSheet(INPUT_STYLE)
        form.addRow("备注:", self.remark)

        layout.addLayout(form)

        # 加载已有数据
        conn = get_connection()
        row = conn.execute("SELECT * FROM salary_config WHERE employee_id=?", (employee_id,)).fetchone()
        if row:
    d = dict(row)
    self.position_allowance.setValue(d.get("position_allowance", 0) or self.position_allowance.value())
    self.assessment_allowance.setValue(d.get("assessment_allowance", 0) or 0)
    self.housing_allowance.setValue(d.get("housing_allowance", 0) or 0)
    self.uniform_refund.setValue(d.get("uniform_refund", 0) or 0)
    self.prev_supplement.setValue(d.get("prev_supplement", 0) or 0)
    self.salary_advance.setValue(d.get("salary_advance", 0) or 0)
    self.fine_compensation.setValue(d.get("fine_compensation", 0) or 0)
    self.is_housing.setCurrentText(d.get("is_housing", "否") or "否")
    self.remark.setText(d.get("remark", "") or "")
        except Exception as e:
        logger.error(f"EmployeeSalaryDialog load: {e}", exc_info=True)
        conn.close()

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

    def _save(self):
        conn = get_connection()
        data = {
            "employee_id": self.employee_id,
            "base_salary": round(self.base_salary.value(), 2),
            "position_allowance": round(self.position_allowance.value(), 2),
            "assessment_allowance": round(self.assessment_allowance.value(), 2),
            "housing_allowance": round(self.housing_allowance.value(), 2),
            "uniform_refund": round(self.uniform_refund.value(), 2),
            "prev_supplement": round(self.prev_supplement.value(), 2),
            "salary_advance": round(self.salary_advance.value(), 2),
            "fine_compensation": round(self.fine_compensation.value(), 2),
            "is_housing": self.is_housing.currentText(),
            "remark": self.remark.text().strip(),
        }
        cols = list(data.keys())
        placeholders = ", ".join(["?"] * len(cols))
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "employee_id")
        sql = f"INSERT INTO salary_config ({', '.join(cols)}) VALUES ({placeholders})"
        if updates:
            sql += f" ON CONFLICT(employee_id) DO UPDATE SET {updates}"
        conn.execute(sql, [data[c] for c in cols])

    # 同步更新 employees.base_salary
        conn.execute("UPDATE employees SET base_salary=? WHERE id=?",
                     (data["base_salary"], self.employee_id))

        conn.commit()
        _sync_cloud()
        QMessageBox.information(self, "成功", "薪资设置已保存")
        self.accept()
    except Exception as e:
        logger.error(f"EmployeeSalaryDialog save: {e}", exc_info=True)
        QMessageBox.warning(self, "错误", f"保存失败: {e}")


# ========== 薪资计算引擎 ==========

class SalaryCalculator:
    """薪资计算引擎"""

    def __init__(self, config: dict):
        self.cfg = config or {}

    def get_global(self, key, default=0):
        return float(self.cfg.get(key, default) or 0)

    def calculate(self, employee: dict, attendance: dict, salary_cfg: dict, year, month):
        """
        计算单个员工工资
        :param employee: employees 表行
        :param attendance: 考勤统计 {attend_days, late_count, late_minutes, absent_days, leave_days}
        :param salary_cfg: salary_config 表行
        :param year, month: 工资年月
        :return: dict 完整工资数据
        """
        position = employee.get("position", "") or ""
        hire_date = employee.get("hire_date", "") or ""
        is_mgmt = is_management(position)
        std_days = self.get_global("standard_work_days", 30)
        probation_rate = self.get_global("probation_rate", 0.7)

        # ---- 基本工资 ----
        base_salary = float(salary_cfg.get("base_salary", 0) or employee.get("base_salary", 0) or 0)

        # ---- 计薪天数 ----
        attend_days = int(attendance.get("attend_days", std_days))
        late_count = int(attendance.get("late_count", 0))
        late_minutes = int(attendance.get("late_minutes", 0))
        absent_days = float(attendance.get("absent_days", 0))
        leave_days = float(attendance.get("leave_days", 0))
        # 实际计薪天数 = 出勤 - 旷工
        pay_days = max(attend_days - absent_days, 0)

        # 试用期折算
        probation_days = 0
        if hire_date:
            try:
                hd = datetime.strptime(hire_date[:10], "%Y-%m-%d").date()
                ref = date(year, month, 15)
                months = (ref.year - hd.year) * 12 + (ref.month - hd.month)
                if months < 2:
                    probation_days = pay_days
            except (ValueError, TypeError):
                pass

        effective_days = pay_days
        if probation_days > 0:
            effective_days = pay_days * probation_rate
        else:
            effective_days = pay_days

        base_pay = round(base_salary / std_days * effective_days, 2)

        # ---- 全勤奖（管理岗不享受）----
        full_attendance = 0.0
        if not is_mgmt and late_count == 0 and absent_days == 0 and leave_days == 0:
            full_attendance = self.get_global("full_attendance_amount", 200)

        # ---- 岗位补贴 ----
        position_allowance = float(salary_cfg.get("position_allowance", 0) or 0)

        # ---- 考核补贴 ----
        assessment_allowance = float(salary_cfg.get("assessment_allowance", 0) or 0)

        # ---- 住房补贴 ----
        housing_allowance = float(salary_cfg.get("housing_allowance", 0) or 0)

        # ---- 工龄工资（管理岗不享受）----
        seniority_pay = 0.0
        if not is_mgmt:
            seniority_pay = calc_seniority_pay(
                hire_date,
                self.get_global("seniority_per_year", 100),
                self.get_global("seniority_half_year", 50),
                ref_date=date(year, month, 15)
            )

        # ---- 上月补发 ----
        prev_supplement = float(salary_cfg.get("prev_supplement", 0) or 0)

        # ---- 工服退款 ----
        uniform_refund = float(salary_cfg.get("uniform_refund", 0) or 0)

        # ---- 应发合计 ----
        gross_salary = round(
            base_pay + full_attendance + position_allowance + assessment_allowance +
            housing_allowance + seniority_pay + prev_supplement - uniform_refund,
            2
        )

        # ---- 扣款 ----
        late_deduction = round(late_minutes * self.get_global("late_deduction_per_minute", 1.0), 2)
        absent_deduction = round(base_salary / std_days * absent_days, 2)
        fine_compensation = float(salary_cfg.get("fine_compensation", 0) or 0)

        # 急辞扣款
        urgent_deduction = 0.0
        urgent_quit = salary_cfg.get("urgent_quit", "") or ""
        if urgent_quit:
            urgent_deduction = round(base_salary * 0.3, 2)  # 急辞扣30%基本工资

        # 水电扣款（按计薪天数比例）
        utility_std = self.get_global("utility_deduction_amount", 30)
        utility_deduction = round(utility_std / std_days * pay_days, 2) if pay_days > 0 else 0

        # 预支工资
        salary_advance = float(salary_cfg.get("salary_advance", 0) or 0)

        # 社保
        social_insurance = 0.0
        if self.get_global("enable_social_insurance", 0):
            pension = base_salary * self.get_global("social_pension_rate", 0.08)
            medical = base_salary * self.get_global("social_medical_rate", 0.02)
            unemploy = base_salary * self.get_global("social_unemployment_rate", 0.005)
            social_insurance = round(pension + medical + unemploy, 2)

        # 个税
        income_tax = 0.0
        if self.get_global("enable_income_tax", 0):
            threshold = self.get_global("tax_threshold", 5000)
            taxable = gross_salary - social_insurance - threshold
            income_tax = calc_income_tax(taxable)

        total_deduction = round(
            late_deduction + absent_deduction + fine_compensation + urgent_deduction +
            utility_deduction + salary_advance + social_insurance + income_tax,
            2
        )

        actual_salary = round(gross_salary - total_deduction, 2)

        return {
            "employee_id": employee["id"],
            "year": year,
            "month": month,
            "base_salary": base_salary,
            "pay_days": round(pay_days, 1),
            "probation_days": round(probation_days, 1),
            "full_attendance": full_attendance,
            "position_allowance": position_allowance,
            "assessment_allowance": assessment_allowance,
            "housing_allowance": housing_allowance,
            "seniority_pay": seniority_pay,
            "prev_supplement": prev_supplement,
            "uniform_refund": uniform_refund,
            "gross_salary": gross_salary,
            "late_count": late_count,
            "late_minutes": late_minutes,
            "late_deduction": late_deduction,
            "absent_days": absent_days,
            "absent_deduction": absent_deduction,
            "fine_compensation": fine_compensation,
            "urgent_quit": urgent_quit,
            "urgent_deduction": urgent_deduction,
            "utility_deduction": utility_deduction,
            "salary_advance": salary_advance,
            "social_insurance": social_insurance,
            "income_tax": income_tax,
            "total_deduction": total_deduction,
            "actual_salary": actual_salary,
            "status": "未发放",
            "is_housing": salary_cfg.get("is_housing", "否") or "否",
            "attend_days": attend_days,
            "leave_days": leave_days,
            "remark": salary_cfg.get("remark", "") or "",
        }


# ========== 工资管理主界面 ==========

class SalaryWidget(QWidget):
    """工资管理主界面"""

    COLUMNS = [
        ("员工", 80), ("岗位", 70), ("基本工资", 80), ("计薪天数", 70),
        ("全勤奖", 60), ("岗位补贴", 70), ("考核补贴", 70), ("住房补贴", 70),
        ("工龄工资", 70), ("应发合计", 80), ("迟到扣款", 70),
        ("旷工扣款", 70), ("水电扣款", 70), ("社保", 60), ("个税", 60),
        ("扣款合计", 80), ("实发工资", 90), ("状态", 60), ("操作", 100),
    ]

    def __init__(self):
        super().__init__()
        self._records = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 8, 12, 4)

        title = QLabel("工资管理")
        title.setStyleSheet(f"font-size: {FONT_SIZE['xl']}px; font-weight: bold; color: {COLOR['text']};")
        toolbar.addWidget(title)

        toolbar.addStretch()

        # 月份选择
        toolbar.addWidget(QLabel("工资月份:"))
        self.month_edit = ModernMonthEdit()
        self.month_edit.setDate(QDate.currentDate())
        self.month_edit.dateChanged.connect(self.refresh)
        toolbar.addWidget(self.month_edit)

        toolbar.addSpacing(8)

        # 门店筛选
        self.store_combo = QComboBox()
        self.store_combo.setStyleSheet(COMBO_STYLE)
        self._load_stores()
        self.store_combo.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(QLabel("门店:"))
        toolbar.addWidget(self.store_combo)

        toolbar.addStretch()

        btn_calc = QPushButton("计算工资")
        btn_calc.setStyleSheet(BTN_PRIMARY)
        btn_calc.clicked.connect(self._calc_all)
        toolbar.addWidget(btn_calc)

        btn_config = QPushButton("全局配置")
        btn_config.setStyleSheet(BTN_PRIMARY)
        btn_config.clicked.connect(self._open_config)
        toolbar.addWidget(btn_config)

        btn_export = QPushButton("导出Excel")
        btn_export.setStyleSheet(BTN_PRIMARY)
        btn_export.clicked.connect(self._export)
        toolbar.addWidget(btn_export)

        layout.addLayout(toolbar)

        # ---- 汇总卡片 ----
        self.summary_layout = QHBoxLayout()
        self.summary_layout.setContentsMargins(12, 4, 12, 4)
        self.lbl_count = self._mk_summary_card("应发人数", "0", COLOR['primary'])
        self.lbl_gross = self._mk_summary_card("应发合计", "¥0.00", COLOR['success'])
        self.lbl_deduction = self._mk_summary_card("扣款合计", "¥0.00", COLOR['danger'])
        self.lbl_actual = self._mk_summary_card("实发合计", "¥0.00", COLOR['primary'])
        layout.addLayout(self.summary_layout)

        # ---- 表格 ----
        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        header = self.table.horizontalHeader()
        for i, (_, w) in enumerate(self.COLUMNS):
            header.resizeSection(i, w)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.table)

        self.refresh()

    def _mk_summary_card(self, title, value, color):
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
        vl.setObjectName("value_label")
        cl.addWidget(tl)
        cl.addWidget(vl)
        self.summary_layout.addWidget(card)
        return vl

    def _load_stores(self):
        self.store_combo.blockSignals(True)
        self.store_combo.clear()
        self.store_combo.addItem("全部门店", None)
        conn = get_connection()
        rows = conn.execute("SELECT id, name FROM stores ORDER BY id").fetchall()
        for r in rows:
    self.store_combo.addItem(r["name"], r["id"])
        conn.close()
        self.store_combo.blockSignals(False)

    def _get_store_filter(self):
        """返回 (store_id, is_all)"""
        sid = self.store_combo.currentData()
        return sid, (sid is None)

    def _get_year_month(self):
        d = self.month_edit.date()
        return d.year(), d.month()

    def load_data(self):
        """统一刷新入口（导航切换时调用）"""
        self.refresh()

    def refresh(self):
        year, month = self._get_year_month()
        store_id, is_all = self._get_store_filter()

        conn = get_connection()
        if is_all:
    rows = conn.execute(
        "SELECT * FROM salary_records WHERE year=? AND month=? ORDER BY employee_id",
        (year, month)
    ).fetchall()
        else:
    rows = conn.execute(
        "SELECT * FROM salary_records WHERE year=? AND month=? AND (store_id=? OR store_id IS NULL) ORDER BY employee_id",
        (year, month, store_id)
    ).fetchall()

        # 获取员工名称和岗位
        emp_map = {}
        if rows:
    emp_ids = set(r["employee_id"] for r in rows if r["employee_id"])
    if emp_ids:
        placeholders = ",".join("?" * len(emp_ids))
        emps = conn.execute(
            f"SELECT id, name, position FROM employees WHERE id IN ({placeholders})",
            list(emp_ids)
        ).fetchall()
        emp_map = {e["id"]: e for e in emps}

        self._records = [dict(r) for r in rows]
        self.table.setRowCount(len(rows))

        total_gross = 0.0
        total_ded = 0.0
        total_actual = 0.0
        count = len(rows)

        for i, r in enumerate(rows):
    d = dict(r)
    emp = emp_map.get(d.get("employee_id"), {})
    name = emp.get("name", "未知")
    position = emp.get("position", "")

    vals = [
        name,
        position,
        f"{d.get('base_salary', 0):.0f}",
        f"{d.get('pay_days', 0):.0f}",
        f"{d.get('full_attendance', 0):.0f}",
        f"{d.get('position_allowance', 0):.0f}",
        f"{d.get('assessment_allowance', 0):.0f}",
        f"{d.get('housing_allowance', 0):.0f}",
        f"{d.get('seniority_pay', 0):.0f}",
        f"{d.get('gross_salary', 0):.2f}",
        f"{d.get('late_deduction', 0):.0f}",
        f"{d.get('absent_deduction', 0):.0f}",
        f"{d.get('utility_deduction', 0):.0f}",
        f"{d.get('social_insurance', 0):.0f}",
        f"{d.get('income_tax', 0):.0f}",
        f"{d.get('total_deduction', 0):.2f}",
        f"{d.get('actual_salary', 0):.2f}",
        d.get("status", "未发放"),
    ]
    for j, v in enumerate(vals):
        item = QTableWidgetItem(str(v))
        item.setTextAlignment(Qt.AlignCenter)
        if j == 9 or j == 16:  # 应发 / 实发
            item.setForeground(QColor(COLOR['primary']))
            f = item.font()
            f.setBold(True)
            item.setFont(f)
        if j == 15:  # 扣款合计
            item.setForeground(QColor(COLOR['danger']))
        self.table.setItem(i, j, item)

    # 操作按钮
    cell = QWidget()
    cl = QHBoxLayout(cell)
    cl.setContentsMargins(2, 2, 2, 2)
    btn_detail = QPushButton("明细")
    btn_detail.setFixedWidth(42)
    btn_detail.setStyleSheet(TABLE_BTN_EDIT)
    btn_detail.clicked.connect(lambda _, rid=d["id"]: self._show_detail(rid))
    cl.addWidget(btn_detail)

    btn_salary = QPushButton("薪资设置")
    btn_salary.setFixedWidth(58)
    btn_salary.setStyleSheet(TABLE_BTN_VIEW)
    btn_salary.clicked.connect(lambda _, eid=d["employee_id"]: self._set_salary(eid))
    cl.addWidget(btn_salary)

    status = d.get("status", "未发放")
    if status == "未发放":
        btn_pay = QPushButton("发放")
        btn_pay.setFixedWidth(42)
        btn_pay.setStyleSheet(TABLE_BTN_VIEW)
        btn_pay.clicked.connect(lambda _, rid=d["id"]: self._pay_one(rid))
        cl.addWidget(btn_pay)
    else:
        lbl_paid = QLabel("已发放")
        lbl_paid.setStyleSheet(f"color: {COLOR['success']}; font-size: {FONT_SIZE['xs']}px;")
        lbl_paid.setAlignment(Qt.AlignCenter)
        cl.addWidget(lbl_paid)

    self.table.setCellWidget(i, len(self.COLUMNS) - 1, cell)

    total_gross += d.get("gross_salary", 0) or 0
    total_ded += d.get("total_deduction", 0) or 0
    total_actual += d.get("actual_salary", 0) or 0

        self.lbl_count.setText(str(count))
        self.lbl_gross.setText(f"¥{total_gross:.2f}")
        self.lbl_deduction.setText(f"¥{total_ded:.2f}")
        self.lbl_actual.setText(f"¥{total_actual:.2f}")

        except Exception as e:
        logger.error(f"SalaryWidget refresh: {e}", exc_info=True)
        QMessageBox.warning(self, "错误", f"加载失败: {e}")
        conn.close()

    def _calc_all(self):
        """计算当月所有员工工资"""
        year, month = self._get_year_month()
        store_id, is_all = self._get_store_filter()

        reply = QMessageBox.question(
            self, "确认计算",
            f"将计算 {year}年{month}月 的工资数据，\n已有的记录将被覆盖。\n\n确认继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        conn = get_connection()
    # 加载全局配置
        cfg_row = conn.execute("SELECT * FROM salary_global_config WHERE id=1").fetchone()
        cfg = dict(cfg_row) if cfg_row else {}
        calc = SalaryCalculator(cfg)

    # 获取门店范围内的员工
        if is_all:
            emps = conn.execute(
                "SELECT * FROM employees WHERE status='在职' ORDER BY id"
            ).fetchall()
        else:
            emps = conn.execute(
                "SELECT * FROM employees WHERE status='在职' AND (store_id=? OR store_id IS NULL) ORDER BY id",
                (store_id,)
            ).fetchall()

        if not emps:
            QMessageBox.information(self, "提示", "没有在职员工")
            return

    # 计算月份的天数
        _, days_in_month = calendar.monthrange(year, month)

        count = 0
        for emp_row in emps:
            emp = dict(emp_row)
            emp_id = emp["id"]

    # 获取薪资配置
            sc_row = conn.execute("SELECT * FROM salary_config WHERE employee_id=?", (emp_id,)).fetchone()
            salary_cfg = dict(sc_row) if sc_row else {}
            if not salary_cfg.get("base_salary"):
                salary_cfg["base_salary"] = emp.get("base_salary", 0)

    # 获取考勤数据
            att_data = self._get_attendance(conn, emp_id, year, month, days_in_month)

    # 计算
            result = calc.calculate(emp, att_data, salary_cfg, year, month)
            result["store_id"] = emp.get("store_id")
            result["operator"] = _ctx().current_username or ""

    # 保存/更新
            self._save_record(conn, result)
            count += 1

        conn.commit()
        _sync_cloud()
        QMessageBox.information(self, "成功", f"已计算 {count} 名员工的工资")
        self.refresh()

    except Exception as e:
        logger.error(f"SalaryWidget _calc_all: {e}", exc_info=True)
        QMessageBox.warning(self, "错误", f"计算失败: {e}")

    def _get_attendance(self, conn, emp_id, year, month, days_in_month):
        """从考勤表取当月数据"""
        start = f"{year:04d}-{month:02d}-01"
        if month == 12:
            end = f"{year:04d}-12-31"
        else:
            end = f"{year:04d}-{month+1:02d}-01"

        rows = conn.execute(
            "SELECT * FROM attendance WHERE employee_id=? AND record_date>=? AND record_date<?",
            (emp_id, start, end)
        ).fetchall()

        attend_days = len(rows)
        late_count = 0
        late_minutes = 0
        absent_days = 0.0
        leave_days = 0.0

        for r in rows:
            d = dict(r)
            status = d.get("status", "")
            if status == "迟到":
                late_count += 1
                # 尝试从备注中提取迟到分钟数
                remark = d.get("remark", "") or ""
                try:
                    import re
                    m = re.search(r'(\d+)\s*分钟', remark)
                    if m:
                        late_minutes += int(m.group(1))
                    else:
                        late_minutes += 10  # 默认10分钟
                except Exception:
                    late_minutes += 10
            elif status == "旷工":
                absent_days += 1
            elif status in ("请假", "事假", "病假"):
                leave_days += 1

        return {
            "attend_days": attend_days,
            "late_count": late_count,
            "late_minutes": late_minutes,
            "absent_days": absent_days,
            "leave_days": leave_days,
        }

    def _save_record(self, conn, data):
        """保存工资记录（upsert）"""
        cols = [k for k in data.keys() if k not in ("employee_id", "year", "month")]
        all_cols = ["employee_id", "year", "month"] + cols
        placeholders = ", ".join(["?"] * len(all_cols))
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols)
        sql = (
            f"INSERT INTO salary_records ({', '.join(all_cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(employee_id, year, month) DO UPDATE SET {updates}"
        )
        conn.execute(sql, [data[c] for c in all_cols])

    def _show_detail(self, record_id):
        dlg = SalaryDetailDialog(record_id, self)
        dlg.exec_()

    def _set_salary(self, emp_id):
        dlg = EmployeeSalaryDialog(emp_id, self)
        dlg.exec_()

    def _open_config(self):
        dlg = GlobalConfigDialog(self)
        dlg.exec_()

    def _pay_one(self, record_id):
        """单个发放"""
        reply = QMessageBox.question(
            self, "确认发放", "确认发放此员工的工资？\n将自动创建财务支出记录。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        conn = get_connection()
        row = conn.execute("SELECT * FROM salary_records WHERE id=?", (record_id,)).fetchone()
        if not row:
            return
        d = dict(row)
        if d.get("status") == "已发放":
            QMessageBox.information(self, "提示", "该工资已发放")
            return

        today = get_today()
        conn.execute(
            "UPDATE salary_records SET status='已发放', paid_date=? WHERE id=?",
            (today, record_id)
        )
        conn.commit()
        _sync_cloud()

    # 联动财务
        operator = _ctx().current_username or ""
        month_str = f"{d['year']}-{d['month']:02d}"
        auto_finance_from_salary(record_id, d.get("actual_salary", 0), month_str, operator)

        QMessageBox.information(self, "成功", "工资已发放，财务支出记录已创建")
        self.refresh()
    except Exception as e:
        logger.error(f"SalaryWidget _pay_one: {e}", exc_info=True)
        QMessageBox.warning(self, "错误", f"发放失败: {e}")

    def _pay_batch(self):
        """批量发放所有未发放的"""
        year, month = self._get_year_month()
        store_id, is_all = self._get_store_filter()

        conn = get_connection()
        if is_all:
            rows = conn.execute(
                "SELECT * FROM salary_records WHERE year=? AND month=? AND status='未发放'",
                (year, month)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM salary_records WHERE year=? AND month=? AND status='未发放' AND (store_id=? OR store_id IS NULL)",
                (year, month, store_id)
            ).fetchall()

        if not rows:
            QMessageBox.information(self, "提示", "没有待发放的工资")
            return

        total = sum(r["actual_salary"] for r in rows)
        reply = QMessageBox.question(
            self, "确认批量发放",
            f"共 {len(rows)} 名员工，合计 ¥{total:.2f}\n确认批量发放？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        today = get_today()
        operator = _ctx().current_username or ""
        month_str = f"{year}-{month:02d}"
        count = 0
        for r in rows:
            d = dict(r)
            conn.execute(
                "UPDATE salary_records SET status='已发放', paid_date=? WHERE id=?",
                (today, d["id"])
            )
            auto_finance_from_salary(d["id"], d.get("actual_salary", 0), month_str, operator)
            count += 1

        conn.commit()
        _sync_cloud()
        QMessageBox.information(self, "成功", f"已发放 {count} 名员工的工资")
        self.refresh()
    except Exception as e:
        logger.error(f"SalaryWidget _pay_batch: {e}", exc_info=True)
        QMessageBox.warning(self, "错误", f"批量发放失败: {e}")

    def _export(self):
        """导出Excel"""
        if not self._records:
            QMessageBox.information(self, "提示", "没有数据可导出")
            return

        try:
            from utils.data_io import export_data_to_excel
            year, month = self._get_year_month()
            filename = f"工资表_{year}_{month:02d}.xlsx"

            headers = [c[0] for c in self.COLUMNS[:-1]]  # 不含操作列
            data = []
            conn = get_connection()
            for r in self._records:
    d = dict(r)
    emp = conn.execute("SELECT name, position FROM employees WHERE id=?", (d["employee_id"],)).fetchone()
    name = emp["name"] if emp else ""
    pos = emp["position"] if emp else ""
    data.append([
        name, pos, d.get("base_salary", 0), d.get("pay_days", 0),
        d.get("full_attendance", 0), d.get("position_allowance", 0),
        d.get("assessment_allowance", 0), d.get("housing_allowance", 0),
        d.get("seniority_pay", 0), d.get("gross_salary", 0),
        d.get("late_deduction", 0), d.get("absent_deduction", 0),
        d.get("utility_deduction", 0), d.get("social_insurance", 0),
        d.get("income_tax", 0), d.get("total_deduction", 0),
        d.get("actual_salary", 0), d.get("status", ""),
    ])
            conn.close()

            filepath = export_data_to_excel(data, headers, filename)
            if filepath:
                QMessageBox.information(self, "成功", f"已导出: {filepath}")
        except Exception as e:
            logger.error(f"SalaryWidget _export: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"导出失败: {e}")
