# -*- coding: utf-8 -*-
"""自定义日历下拉控件

ModernDateEdit: 继承 QDateEdit，复用全局 QSS，弹出自定义日历
CalendarPopup: 继承 QDialog，用 exec_() 模态弹出（打包环境安全）
三级导航: 日期视图 → 月份视图 → 年份视图
"""

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QDateEdit, QDialog
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal
import traceback
from gui.theme import COLOR


class ClickLabel(QLabel):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SelectCell(QLabel):
    clicked = pyqtSignal(int)
    def __init__(self, text, value, parent=None):
        super().__init__(text, parent)
        self._value = value
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(48, 36)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._value)
        super().mousePressEvent(event)


class DateCell(QLabel):
    clicked = pyqtSignal(QDate)
    def __init__(self, date, parent=None):
        super().__init__(str(date.day()), parent)
        self._date = date
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(32, 32)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._date)
        super().mousePressEvent(event)


class CalendarPopup(QDialog):
    """日历下拉面板 —— 继承 QDialog，用 exec_() 模态弹出（打包环境安全）

    不使用 WA_TranslucentBackground（打包环境可能渲染异常），
    直接用 stylesheet 设置白底 + 圆角边框。
    """

    dateSelected = pyqtSignal(QDate)

    PRIMARY = "#5B6CFF"
    PRIMARY_LIGHT = "#EDEFFF"
    TEXT_PRIMARY = "#1E293B"
    TEXT_MUTED = "#CBD5E1"
    BORDER = "#E8EAF0"
    WEEKEND_COLOR = "#EF4444"

    WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]

    def __init__(self, selected_date=None, parent=None, month_only=False):
        super().__init__(parent)
        # Qt.Popup: 点击外部自动关闭，不阻止鼠标事件传播
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        # 不使用 WA_TranslucentBackground，用 stylesheet 设白底
        self.setStyleSheet(
            "CalendarPopup { background-color: #FFFFFF; border: 1px solid #E8EAF0; border-radius: 12px; }"
        )
        self._current_date = selected_date or QDate.currentDate()
        self._selected_date = selected_date
        self._month_only = month_only
        self._view = "month" if month_only else "date"
        self._year_start = (self._current_date.year() // 10) * 10
        self._result_date = None
        self.setFixedSize(280, 340)
        self.init_ui()

    def closeEvent(self, event):
        super().closeEvent(event)

    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- 顶部日期信息栏 ----
        self.info_bar = QFrame()
        self.info_bar.setFixedHeight(48)
        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(16, 8, 16, 8)
        info_layout.setSpacing(0)

        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet(
            "color: #1E293B; font-size: 13px; font-weight: bold; border: none; background: transparent;"
        )
        info_layout.addWidget(self.lbl_info)
        info_layout.addStretch()
        outer.addWidget(self.info_bar)

        # ---- 分隔线 ----
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(
            "QFrame { border: none; border-top: 1px solid #E8EAF0; background: transparent; }"
        )
        outer.addWidget(sep)

        # ---- 导航栏 ----
        self.nav = QFrame()
        self.nav.setFixedHeight(40)
        nav_layout = QHBoxLayout(self.nav)
        nav_layout.setContentsMargins(16, 0, 10, 0)
        nav_layout.setSpacing(0)

        self.lbl_title = ClickLabel()
        self.lbl_title.setCursor(Qt.PointingHandCursor)
        self.lbl_title.setStyleSheet(
            "color: #1E293B; font-size: 14px; font-weight: bold; border: none; background: transparent;"
        )
        self.lbl_title.clicked.connect(self._on_title_click)
        nav_layout.addWidget(self.lbl_title)
        nav_layout.addStretch()

        btn_ss = (
            "QPushButton {"
            " color: #94A3B8; background: transparent;"
            " border: none; border-radius: 4px;"
            " font-size: 9px; font-weight: bold;"
            "}"
            "QPushButton:hover { background: #F0F2F8; color: #5B6CFF; }"
        )
        self.btn_prev = QPushButton("▲")
        self.btn_prev.setFixedSize(24, 24)
        self.btn_prev.setCursor(Qt.PointingHandCursor)
        self.btn_prev.setStyleSheet(btn_ss)
        self.btn_prev.clicked.connect(self._on_prev)
        nav_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("▼")
        self.btn_next.setFixedSize(24, 24)
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet(btn_ss)
        self.btn_next.clicked.connect(self._on_next)
        nav_layout.addWidget(self.btn_next)
        outer.addWidget(self.nav)

        # ---- 内容区 ----
        self.content = QFrame()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        outer.addWidget(self.content)

        self._refresh_view()

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
                item.layout().deleteLater()

    def _refresh_view(self):
        self._update_info_bar()
        if self._view == "date":
            self._update_title_date()
            self._build_date_view()
        elif self._view == "month":
            self._update_title_year()
            self._build_month_view()
        elif self._view == "year":
            self._update_title_year_range()
            self._build_year_view()

    def _update_info_bar(self):
        if self._selected_date:
            d = self._selected_date
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            wd = weekdays[d.dayOfWeek() - 1]
            self.lbl_info.setText(f"{d.month()}月{d.day()}日  星期{wd}")
        else:
            self.lbl_info.setText("")

    # ===== 日期视图 =====
    def _update_title_date(self):
        self.lbl_title.setText(
            f"{self._current_date.year()}年{self._current_date.month()}月"
        )

    def _build_date_view(self):
        self._clear_content()

        header = QFrame()
        header.setFixedHeight(28)
        h_layout = QGridLayout(header)
        h_layout.setContentsMargins(10, 0, 10, 0)
        h_layout.setSpacing(0)
        for i, wd in enumerate(self.WEEKDAY_NAMES):
            lbl = QLabel(wd)
            lbl.setAlignment(Qt.AlignCenter)
            color = self.WEEKEND_COLOR if i >= 5 else "#64748B"
            lbl.setStyleSheet(
                f"color: {color}; font-size: 12px; border: none; background: transparent;"
            )
            h_layout.addWidget(lbl, 0, i)
        self.content_layout.addWidget(header)

        grid = QFrame()
        grid_layout = QGridLayout(grid)
        grid_layout.setContentsMargins(10, 2, 10, 6)
        grid_layout.setSpacing(0)

        first_day = QDate(self._current_date.year(), self._current_date.month(), 1)
        first_weekday = first_day.dayOfWeek() - 1
        days_in_month = first_day.daysInMonth()
        prev_month = first_day.addMonths(-1)
        prev_days = prev_month.daysInMonth()
        today = QDate.currentDate()

        dates = []
        for i in range(first_weekday):
            day = prev_days - first_weekday + 1 + i
            dates.append((QDate(prev_month.year(), prev_month.month(), day), False))
        for day in range(1, days_in_month + 1):
            dates.append((
                QDate(self._current_date.year(), self._current_date.month(), day),
                True,
            ))
        next_month = first_day.addMonths(1)
        while len(dates) < 42:
            day = len(dates) - first_weekday - days_in_month + 1
            dates.append((QDate(next_month.year(), next_month.month(), day), False))

        for i, (date, is_current) in enumerate(dates):
            cell = DateCell(date)
            is_weekend = date.dayOfWeek() >= 6
            is_selected = self._selected_date and date == self._selected_date
            is_today = date == today
            if is_selected:
                bg, color, border = self.PRIMARY, "#FFFFFF", "none"
            elif not is_current:
                bg, color, border = "transparent", self.TEXT_MUTED, "none"
            elif is_today:
                bg, color, border = self.PRIMARY_LIGHT, self.PRIMARY, "1px solid #5B6CFF"
            elif is_weekend:
                bg, color, border = "transparent", self.WEEKEND_COLOR, "none"
            else:
                bg, color, border = "transparent", self.TEXT_PRIMARY, "none"
            cell.setStyleSheet(
                f"color: {color}; background-color: {bg};"
                f"border: {border}; border-radius: 4px; font-size: 13px;"
            )
            cell.clicked.connect(self._on_date_clicked)
            grid_layout.addWidget(cell, i // 7, i % 7)
        self.content_layout.addWidget(grid)

    def _on_date_clicked(self, date):
        self._selected_date = date
        self._result_date = date
        self.dateSelected.emit(date)
        self.accept()

    # ===== 月份视图 =====
    def _update_title_year(self):
        self.lbl_title.setText(f"{self._current_date.year()}年")

    def _build_month_view(self):
        self._clear_content()
        grid = QFrame()
        grid_layout = QGridLayout(grid)
        grid_layout.setContentsMargins(16, 8, 16, 8)
        grid_layout.setSpacing(4)

        months = ["1月", "2月", "3月", "4月", "5月", "6月",
                   "7月", "8月", "9月", "10月", "11月", "12月"]
        current_month = self._current_date.month()
        selected_month = self._selected_date.month() if self._selected_date else -1
        selected_year = self._selected_date.year() if self._selected_date else -1
        for i, name in enumerate(months):
            cell = SelectCell(name, i + 1)
            is_current = (i + 1 == current_month)
            is_selected = (i + 1 == selected_month
                           and self._current_date.year() == selected_year)
            if is_selected:
                bg, color = self.PRIMARY, "#FFFFFF"
            elif is_current:
                bg, color = self.PRIMARY_LIGHT, self.PRIMARY
            else:
                bg, color = "transparent", self.TEXT_PRIMARY
            cell.setStyleSheet(
                f"color: {color}; background-color: {bg};"
                f"border: none; border-radius: 6px; font-size: 13px;"
            )
            cell.clicked.connect(self._on_month_clicked)
            grid_layout.addWidget(cell, i // 3, i % 3)
        self.content_layout.addWidget(grid)

    def _on_month_clicked(self, month):
        self._current_date = QDate(self._current_date.year(), month, 1)
        if self._month_only:
            self._selected_date = self._current_date
            self._result_date = self._current_date
            self.dateSelected.emit(self._current_date)
            self.accept()
        else:
            self._view = "date"
            self._refresh_view()

    # ===== 年份视图 =====
    def _update_title_year_range(self):
        self.lbl_title.setText(f"{self._year_start}年 - {self._year_start + 9}年")

    def _build_year_view(self):
        self._clear_content()
        grid = QFrame()
        grid_layout = QGridLayout(grid)
        grid_layout.setContentsMargins(16, 8, 16, 8)
        grid_layout.setSpacing(4)

        current_year = self._current_date.year()
        selected_year = self._selected_date.year() if self._selected_date else -1
        for i in range(12):
            year = self._year_start + i - 1
            cell = SelectCell(str(year), year)
            is_current = (year == current_year)
            is_selected = (year == selected_year)
            in_range = 0 <= i <= 9
            if is_selected:
                bg, color = self.PRIMARY, "#FFFFFF"
            elif is_current:
                bg, color = self.PRIMARY_LIGHT, self.PRIMARY
            elif not in_range:
                bg, color = "transparent", self.TEXT_MUTED
            else:
                bg, color = "transparent", self.TEXT_PRIMARY
            cell.setStyleSheet(
                f"color: {color}; background-color: {bg};"
                f"border: none; border-radius: 6px; font-size: 13px;"
            )
            cell.clicked.connect(self._on_year_clicked)
            grid_layout.addWidget(cell, i // 3, i % 3)
        self.content_layout.addWidget(grid)

    def _on_year_clicked(self, year):
        self._current_date = QDate(year, self._current_date.month(), 1)
        self._view = "month"
        self._refresh_view()

    # ===== 导航 =====
    def _on_title_click(self):
        if self._view == "date":
            self._view = "month"
        elif self._view == "month":
            self._year_start = (self._current_date.year() // 10) * 10
            self._view = "year"
        self._refresh_view()

    def _on_prev(self):
        if self._view == "date":
            self._current_date = self._current_date.addMonths(-1)
        elif self._view == "month":
            self._current_date = QDate(
                self._current_date.year() - 1, self._current_date.month(), 1
            )
        elif self._view == "year":
            self._year_start -= 10
        self._refresh_view()

    def _on_next(self):
        if self._view == "date":
            self._current_date = self._current_date.addMonths(1)
        elif self._view == "month":
            self._current_date = QDate(
                self._current_date.year() + 1, self._current_date.month(), 1
            )
        elif self._view == "year":
            self._year_start += 10
        self._refresh_view()

    def get_selected_date(self):
        """exec_() 返回后调用，获取选择的日期（None 表示未选择）"""
        return self._result_date


class ModernDateEdit(QDateEdit):
    """日期下拉控件 —— 继承 QDateEdit，弹出自定义三级导航日历

    根本要点：
      - setCalendarPopup(True)：箭头显示为下拉箭头样式
      - 重写 mousePressEvent：不调 super()，阻止 Qt 弹默认 QCalendarWidget
        点击任何位置都弹自定义 CalendarPopup（用 exec_() 模态弹出，打包环境安全）
    """

    def __init__(self, parent=None, default_today=True, placeholder=""):
        super().__init__(parent)
        self._guard = False
        self._allow_empty = not default_today
        self._placeholder = placeholder
        self.setCalendarPopup(True)  # 箭头显示为下拉样式
        self.setDisplayFormat("yyyy-MM-dd")
        self.setMinimumWidth(160)
        if default_today:
            self.setDate(QDate.currentDate())
        else:
            # 不默认当天：用 specialValueText 显示占位符
            self.setMinimumDate(QDate(2000, 1, 1))
            self.setDate(QDate(2000, 1, 1))
            self.setSpecialValueText(placeholder)
            # 空值时灰色字体居中
            self.setAlignment(Qt.AlignCenter)
            self.setStyleSheet("QDateEdit { color: #CBD5E1; }")

    def mousePressEvent(self, event):
        """拦截所有鼠标点击，弹自定义日历，不调 super()"""
        if event.button() == Qt.LeftButton:
            self._toggle_popup()
            return
        super().mousePressEvent(event)

    def _toggle_popup(self):
        try:
            top_window = self.window()
            # 如果是空值模式且未选过日期，不预选
            if self._allow_empty and self.date() == QDate(2000, 1, 1):
                popup = CalendarPopup(None, parent=top_window)
            else:
                popup = CalendarPopup(self.date(), parent=top_window)
            popup.dateSelected.connect(self._on_selected)
            pos = self.mapToGlobal(self.rect().bottomLeft())
            popup.move(pos.x(), pos.y() + 4)
            popup.exec_()
        except Exception:
            try:
                from utils.logger import logger
                logger.error("日期选择弹窗异常:\n" + traceback.format_exc())
            except Exception:
                pass  # 异常已记录日志
    def _on_selected(self, date):
        if self._guard:
            return
        self._guard = True
        self.setDate(date)
        self._allow_empty = False  # 选过日期后不再是空值
        # 选过日期后恢复正常颜色
        self.setStyleSheet("QDateEdit { color: " + COLOR['text_primary'] + "; }")
        self.dateChanged.emit(date)
        self._guard = False

    def is_empty(self):
        """空值模式下是否未选择日期"""
        return self._allow_empty and self.date() == QDate(2000, 1, 1)

    def get_date_str(self):
        """返回日期字符串，未选择时返回空字符串"""
        if self.is_empty():
            return ""
        return self.date().toString("yyyy-MM-dd")


class ModernMonthEdit(QDateEdit):
    """月份选择控件 —— 继承 QDateEdit，弹出自定义三级导航日历（月份模式）

    与 ModernDateEdit 类似，但只选年月，不选具体日期。
    点击后弹出 CalendarPopup(month_only=True)，选中月份后立即关闭。
    """

    def __init__(self, parent=None, default_today=True):
        super().__init__(parent)
        self._guard = False
        self.setCalendarPopup(True)  # 箭头显示为下拉样式
        self.setDisplayFormat("yyyy年MM月")
        if default_today:
            self.setDate(QDate.currentDate())
        self.setFixedWidth(160)

    def mousePressEvent(self, event):
        """拦截所有鼠标点击，弹自定义月份日历，不调 super()"""
        if event.button() == Qt.LeftButton:
            self._toggle_popup()
            return
        super().mousePressEvent(event)

    def _toggle_popup(self):
        try:
            top_window = self.window()
            popup = CalendarPopup(self.date(), parent=top_window, month_only=True)
            popup.dateSelected.connect(self._on_selected)
            pos = self.mapToGlobal(self.rect().bottomLeft())
            popup.move(pos.x(), pos.y() + 4)
            popup.exec_()
        except Exception:
            try:
                from utils.logger import logger
                logger.error("月份选择弹窗异常:\n" + traceback.format_exc())
            except Exception:
                pass

    def _on_selected(self, date):
        if self._guard:
            return
        self._guard = True
        self.setDate(date)
        self.dateChanged.emit(date)
        self._guard = False
