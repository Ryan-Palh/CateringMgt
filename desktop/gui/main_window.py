# -*- coding: utf-8 -*-
"""
主窗口 v5.0 —— 餐饮专业版
- 深咖啡木纹色侧边栏，暖橙高亮选中态
- 无边框圆角窗口，可拖拽、可最大化
- 门店选择器、用户信息、修改密码
- 15个功能模块导航（含桌台管理）
"""
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFrame, QStatusBar,
                             QMessageBox, QStackedWidget,
                             QSplitter, QSizePolicy, QScrollArea,
                             QComboBox, QDialog, QLineEdit, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QRectF, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QIcon, QPainter, QPen, QColor, QBrush, QFont, QLinearGradient
import os, sys, threading

from gui.theme import get_combo_arrow_qss, COLOR, RADIUS, FONT_SIZE, CenterAlignDelegate
from gui.purchase import PurchaseWidget
from gui.reimbursement import ReimbursementWidget
from gui.approval import ApprovalWidget
from gui.attendance import AttendanceWidget
from gui.salary import SalaryWidget
from gui.revenue import RevenueWidget
from gui.cost_calc import CostCalcWidget
from gui.finance import FinanceWidget
from gui.dashboard import DashboardWidget
from gui.employee import EmployeeWidget
from gui.store_manager import StoreWidget
from gui.authorization import AuthorizationWidget
from gui.shift_mgt import ShiftWidget
from gui.report_center import ReportWidget
from gui.table_mgt import TableWidget

from utils.auth_manager import ADMIN_ROLES, ROLE_DISPLAY
from utils.app_context import get_app_context
from database.db_manager import get_connection
from utils.logger import logger

# ═══════════════════════════════════════════
# 导航项配置
# ═══════════════════════════════════════════

NAV_GROUPS = [
    {
        "group": "概览",
        "items": [
            ("🏠", "工作台", "dashboard"),
        ]
    },
    {
        "group": "经营管理",
        "items": [
            ("📊", "营业额", "revenue"),
            ("📦", "进销存管理", "purchase"),
            ("🪑", "桌台管理", "table_mgt"),
            ("💰", "收支管理", "finance"),
        ]
    },
    {
        "group": "人事管理",
        "items": [
            ("👥", "员工管理", "employee"),
            ("📅", "排班管理", "shifts"),
            ("⏰", "考勤管理", "attendance"),
            ("💵", "工资管理", "salary"),
        ]
    },
    {
        "group": "审批流程",
        "items": [
            ("📝", "报销管理", "reimbursement"),
            ("✅", "审批中心", "approval"),
        ]
    },
    {
        "group": "数据分析",
        "items": [
            ("📈", "成本核算", "cost_calc"),
            ("📋", "报表中心", "reports"),
        ]
    },
    {
        "group": "系统设置",
        "items": [
            ("🏪", "门店管理", "store_manager"),
            ("🔐", "授权管理", "authorization"),
        ]
    },
]

ALL_NAV_ITEMS = []
for group in NAV_GROUPS:
    for icon, name, key in group["items"]:
        ALL_NAV_ITEMS.append((f"{icon}  {name}", key))


# ═══════════════════════════════════════════
# 窗口控制按钮（自绘，不依赖字体渲染）
# ═══════════════════════════════════════════

class WinButton(QPushButton):
    def __init__(self, icon_type, parent=None):
        super().__init__(parent)
        self._icon_type = icon_type
        self._hovered = False
        self.setFixedSize(40, 34)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()

        if self._hovered:
            if self._icon_type == "close":
                painter.fillRect(rect, QColor(COLOR['danger']))
            else:
                painter.fillRect(rect, QColor(COLOR['bg_hover']))
        else:
            painter.fillRect(rect, QColor(COLOR['header_bg']))

        pen_color = QColor("#FFFFFF") if (self._hovered and self._icon_type == "close") else QColor(COLOR['text_primary'])
        pen = QPen(pen_color)
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        cx = rect.width() / 2
        cy = rect.height() / 2
        s = 6

        if self._icon_type == "min":
            painter.drawLine(int(cx - s), int(cy + 2), int(cx + s), int(cy + 2))
        elif self._icon_type == "max":
            from PyQt5.QtCore import QRectF
            painter.drawRoundedRect(QRectF(cx - s, cy - s, s * 2, s * 2), 2.0, 2.0)
        elif self._icon_type == "close":
            painter.drawLine(int(cx - s), int(cy - s), int(cx + s), int(cy + s))
            painter.drawLine(int(cx + s), int(cy - s), int(cx - s), int(cy + s))
        elif self._icon_type == "restore":
            from PyQt5.QtCore import QRectF
            painter.drawRoundedRect(QRectF(cx - s + 3, cy - s, s * 2 - 3, s * 2 - 3), 2.0, 2.0)
            painter.drawRoundedRect(QRectF(cx - s, cy - s + 3, s * 2 - 3, s * 2 - 3), 2.0, 2.0)
        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def set_icon_type(self, icon_type):
        self._icon_type = icon_type
        self.update()


# ═══════════════════════════════════════════
# 侧边导航列表
# ═══════════════════════════════════════════

# ── 自绘侧边栏（彻底弃用 QListWidget，消除圆角渲染 bug）──

class NavItem:
    """侧边栏条目数据"""
    __slots__ = ('icon', 'text', 'tab_key', 'is_header')
    def __init__(self, icon='', text='', tab_key='', is_header=False):
        self.icon = icon
        self.text = text
        self.tab_key = tab_key
        self.is_header = is_header

class NavList(QWidget):
    """自绘侧边栏：QPainter 直接绘制，圆角完全可控，无 QListWidget bug"""
    nav_changed = pyqtSignal(str)  # 发出 tab_key

    ITEM_H = 40
    HEADER_H = 30
    TOP_PAD = 12
    BOTTOM_PAD = 12
    SIDE_PAD = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setMouseTracking(True)

        self._items = []          # [NavItem, ...]
        self._selectable = []     # [_items index, ...]
        self._selected = -1
        self._hovered = -1
        self._y_offsets = []

    # ── 数据构建 ──

    def add_group_header(self, text):
        self._items.append(NavItem(text=text.upper(), is_header=True))

    def add_nav_item(self, icon, text, tab_key):
        self._items.append(NavItem(icon=icon, text=text, tab_key=tab_key))
        self._selectable.append(len(self._items) - 1)

    def finalize(self):
        y = self.TOP_PAD
        self._y_offsets = []
        for item in self._items:
            self._y_offsets.append(y)
            y += self.HEADER_H if item.is_header else self.ITEM_H

    @property
    def current_tab_key(self):
        if 0 <= self._selected < len(self._selectable):
            return self._items[self._selectable[self._selected]].tab_key
        return ''

    def setCurrentRow(self, row):
        if 0 <= row < len(self._selectable):
            self._selected = row
            self.update()
            self.nav_changed.emit(self.current_tab_key)

    def _first_selectable_row(self):
        return 0 if self._selectable else -1

    # ── 事件 ──

    def _hit_test(self, y):
        for si, idx in enumerate(self._selectable):
            oy = self._y_offsets[idx]
            if oy <= y <= oy + self.ITEM_H:
                return si
        return -1

    def mouseMoveEvent(self, event):
        hit = self._hit_test(event.pos().y())
        if hit != self._hovered:
            self._hovered = hit
            self.setCursor(Qt.PointingHandCursor if hit >= 0 else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, event):
        hit = self._hit_test(event.pos().y())
        if hit >= 0 and hit != self._selected:
            self._selected = hit
            self.update()
            self.nav_changed.emit(self.current_tab_key)

    def leaveEvent(self, event):
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    # ── 自绘 ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 背景：深钴蓝渐变
        grad = QLinearGradient(0, 0, self.width() * 0.3, self.height())
        grad.setColorAt(0, QColor(COLOR['sidebar_bg']))
        grad.setColorAt(0.5, QColor(COLOR['sidebar_bg_grad']))
        grad.setColorAt(1, QColor(COLOR['sidebar_bg']))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())

        # 右边框
        painter.setPen(QPen(QColor(COLOR['sidebar_border']), 1))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        # 绘制条目
        w = self.width()
        font = QFont("Microsoft YaHei UI", FONT_SIZE['base'])
        painter.setFont(font)

        for i, item in enumerate(self._items):
            y = self._y_offsets[i]
            if item.is_header:
                self._draw_header(painter, item, y, w)
            else:
                si = self._selectable.index(i) if i in self._selectable else -1
                selected = (si == self._selected)
                hovered = (si == self._hovered and not selected)
                self._draw_item(painter, item, y, w, selected, hovered)

        painter.end()

    def _draw_header(self, painter, item, y, w):
        font = painter.font()
        font.setPointSize(FONT_SIZE['xs'])
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(COLOR['sidebar_group_header']))
        painter.drawText(
            QRectF(self.SIDE_PAD + 8, y, w - self.SIDE_PAD * 2, self.HEADER_H),
            Qt.AlignLeft | Qt.AlignVCenter, item.text
        )

    def _draw_item(self, painter, item, y, w, selected, hovered):
        x = self.SIDE_PAD
        iw = w - self.SIDE_PAD * 2
        ih = self.ITEM_H
        rect = QRectF(x, y, iw, ih)
        radius = float(RADIUS['md'])

        if selected:
            grad = QLinearGradient(x, y, x + iw, y)
            grad.setColorAt(0, QColor(COLOR['sidebar_selected']))
            grad.setColorAt(1, QColor(COLOR['accent_glow']))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, radius, radius)
        elif hovered:
            painter.setBrush(QColor(COLOR['sidebar_hover']))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, radius, radius)

        font = painter.font()
        font.setPointSize(FONT_SIZE['base'])
        font.setBold(selected)
        painter.setFont(font)

        if selected:
            painter.setPen(QColor(COLOR['sidebar_text_selected']))
        elif hovered:
            painter.setPen(QColor(COLOR['sidebar_text_hover']))
        else:
            painter.setPen(QColor(COLOR['sidebar_text']))

        text = f"  {item.icon}    {item.text}"
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)


# ═══════════════════════════════════════════
# 门店选择器
# ═══════════════════════════════════════════

class StoreSelector(QComboBox):
    store_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setMinimumWidth(180)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLOR['bg_surface']};
                color: {COLOR['text_primary']};
                border: 1px solid {COLOR['border']};
                border-radius: {RADIUS['md']}px;
                padding: 4px 38px 4px 14px;
                font-size: {FONT_SIZE['base']}px;
                font-weight: 500;
                combobox-popup: 0;
            }}
            QComboBox:hover {{ border-color: {COLOR['primary']}; background-color: {COLOR['bg_card']}; }}
            QComboBox:focus {{ border: 1.5px solid {COLOR['primary']}; padding: 3px 37px 3px 13px; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: center right;
                width: 28px; border: none; background-color: transparent;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLOR['bg_card']};
                color: {COLOR['text_primary']};
                border: 1px solid {COLOR['border']};
                selection-background-color: {COLOR['primary_light']};
                selection-color: {COLOR['primary']};
                font-size: {FONT_SIZE['base']}px;
                outline: none; border-radius: {RADIUS['md']}px; padding: 6px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 10px 14px; border-radius: {RADIUS['sm']}px; min-height: 24px;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {COLOR['primary_light']}; color: {COLOR['primary']};
            }}
        """ + get_combo_arrow_qss())
        self.currentIndexChanged.connect(self._on_changed)

    def _on_changed(self, index):
        if index < 0:
            return
        store_id = self.itemData(index)
        ctx = get_app_context()
        if store_id == 0 or store_id is None:
            ctx.set_store(None, "全部门店")
            self.store_changed.emit(0)
        else:
            store_name = self.itemText(index)
            ctx.set_store(store_id, store_name)
            self.store_changed.emit(store_id)

    def load_stores(self, allowed_store_names=None, is_admin=False):
        self.blockSignals(True)
        self.clear()
        if is_admin:
            self.addItem("🏢  全部门店", 0)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, status FROM stores ORDER BY id")
        stores = cursor.fetchall()
        conn.close()
        for s in stores:
            d = dict(s)
            if not is_admin and allowed_store_names:
                if d["name"] not in allowed_store_names:
                    continue
            status_icon = "✅" if not d.get('status') or d['status'] == '正常' else "⚠️"
            label = f"{status_icon}  {d['name']}"
            if d.get('status') and d['status'] != '正常':
                label += f"（{d['status']}）"
            self.addItem(label, d["id"])
        self.blockSignals(False)
        if self.count() > 0:
            self._on_changed(self.currentIndex())


# ═══════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self, user, session=None):
        super().__init__()
        self.current_user = user
        self.session = session
        self.is_admin = (session is not None and session.role in ADMIN_ROLES)
        self.visible_tabs = set(session.visibleTabs) if session else set()
        self._widgets = {}
        self._drag_pos = None
        self._is_maximized = False
        self._normal_geometry = None
        ctx = get_app_context()
        ctx.set_current_user(user.get("username", "") if user else "")
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("餐饮综合管理系统")
        self.setMinimumSize(1200, 760)
        self.setWindowFlags(Qt.FramelessWindowHint)
        # 不使用 WA_TranslucentBackground：它在 DWM 合成异常时会导致布局错乱/桌面穿透
        # 改为 paintEvent 直接填充背景色，彻底消除透明合成层依赖

        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, 'assets', 'app_icon.ico')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'app_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._corner_radius = 10

        central = QWidget()
        central.setObjectName("centralWidget")
        central.setStyleSheet(f"#centralWidget {{ background-color: {COLOR['bg_page']}; border-radius: 0px; }}")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._init_header(main_layout)

        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(0)
        body.setChildrenCollapsible(False)

        self._init_sidebar(body)
        self._init_content(body)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        main_layout.addWidget(body, 1)

        self._init_statusbar()

        self.nav.setCurrentRow(self._first_selectable_row())
        self.showMaximized()
        self._is_maximized = True

    def _init_header(self, parent_layout):
        header = QFrame()
        header.setFixedHeight(52)
        header.setObjectName("headerFrame")
        header.setStyleSheet(f"""
            #headerFrame {{
                background-color: {COLOR['header_bg']};
                border-bottom: 1px solid {COLOR['border']};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
            }}
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 8, 0)
        hl.setSpacing(16)

        title = QLabel("🍽  餐饮综合管理系统")
        title.setStyleSheet(f"""
            color: {COLOR['text_primary']};
            font-size: 15px; font-weight: 700;
            background: transparent; letter-spacing: 1px;
        """)
        hl.addWidget(title)
        hl.addSpacing(24)

        store_label = QLabel("门店")
        store_label.setStyleSheet(f"color: {COLOR['header_text_muted']}; font-size: {FONT_SIZE['sm']}px; background: transparent;")
        hl.addWidget(store_label)

        self.store_selector = StoreSelector()
        allowed = self.session.allowedStores if self.session else []
        self.store_selector.load_stores(allowed_store_names=allowed, is_admin=self.is_admin)
        self.store_selector.store_changed.connect(self.on_store_changed)
        hl.addWidget(self.store_selector)

        hl.addStretch()

        # 用户信息
        role_text = ROLE_DISPLAY.get(self.current_user.get("role", ""), self.current_user.get("position", ""))
        user_text_layout = QVBoxLayout()
        user_text_layout.setSpacing(0)
        user_name = QLabel(self.current_user['name'])
        user_name.setAlignment(Qt.AlignCenter)
        user_name.setStyleSheet(f"color: {COLOR['header_text']}; font-size: {FONT_SIZE['sm']}px; font-weight: 600; background: transparent;")
        user_role = QLabel(role_text)
        user_role.setAlignment(Qt.AlignCenter)
        user_role.setStyleSheet(f"color: {COLOR['header_text_muted']}; font-size: {FONT_SIZE['xs']}px; background: transparent;")
        user_text_layout.addWidget(user_name)
        user_text_layout.addWidget(user_role)
        hl.addLayout(user_text_layout)

        hl.addSpacing(8)

        btn_change_pwd = QPushButton("🔑 修改密码")
        btn_change_pwd.setFixedHeight(34)
        btn_change_pwd.setCursor(Qt.PointingHandCursor)
        btn_change_pwd.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {COLOR['text_secondary']};
                border: 1px solid {COLOR['border']}; border-radius: {RADIUS['md']}px;
                font-size: {FONT_SIZE['sm']}px; padding: 4px 14px;
            }}
            QPushButton:hover {{ background-color: {COLOR['accent_light']}; border-color: {COLOR['accent']}; color: {COLOR['accent']}; }}
        """)
        btn_change_pwd.clicked.connect(self.open_change_password)
        hl.addWidget(btn_change_pwd)

        btn_logout = QPushButton("退出")
        btn_logout.setFixedSize(64, 34)
        btn_logout.setCursor(Qt.PointingHandCursor)
        btn_logout.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {COLOR['text_secondary']};
                border: 1px solid {COLOR['border']}; border-radius: {RADIUS['md']}px;
                font-size: {FONT_SIZE['sm']}px; padding: 4px 12px;
            }}
            QPushButton:hover {{ background-color: {COLOR['danger_light']}; border-color: {COLOR['danger']}; color: {COLOR['danger']}; }}
        """)
        btn_logout.clicked.connect(self.logout)
        hl.addWidget(btn_logout)

        hl.addSpacing(4)

        # 窗口控制按钮
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(2)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        btn_min = WinButton("min")
        btn_min.clicked.connect(self.showMinimized)
        controls_layout.addWidget(btn_min)
        self.btn_max = WinButton("max")
        self.btn_max.clicked.connect(self._toggle_maximize)
        controls_layout.addWidget(self.btn_max)
        btn_close = WinButton("close")
        btn_close.clicked.connect(self.close)
        controls_layout.addWidget(btn_close)
        hl.addLayout(controls_layout)

        parent_layout.addWidget(header)
        self._header = header

    def _init_sidebar(self, parent_splitter):
        self.nav = NavList()

        visible_groups = []
        for group in NAV_GROUPS:
            visible_items = []
            for icon, name, tab_key in group["items"]:
                if self.is_admin:
                    visible_items.append((icon, name, tab_key))
                elif tab_key == "authorization":
                    continue
                elif tab_key in self.visible_tabs:
                    visible_items.append((icon, name, tab_key))
            if visible_items:
                visible_groups.append({"group": group["group"], "items": visible_items})

        if not self.session:
            visible_groups = NAV_GROUPS

        self.tab_key_to_idx = {}
        for group in visible_groups:
            self.nav.add_group_header(group["group"])
            for icon, name, tab_key in group["items"]:
                self.nav.add_nav_item(icon, name, tab_key)
                self.tab_key_to_idx[tab_key] = len(self.nav._selectable) - 1

        self.nav.finalize()
        self.nav.nav_changed.connect(self.on_nav)
        parent_splitter.addWidget(self.nav)

    def _first_selectable_row(self):
        return self.nav._first_selectable_row()

    def _install_center_delegate(self, widget):
        """递归为 widget 及其子控件中的所有 QTableWidget/QTableView 安装居中 delegate + 列宽自适应"""
        from PyQt5.QtWidgets import QTableWidget, QTableView, QHeaderView
        tables = []
        if isinstance(widget, (QTableWidget, QTableView)):
            tables.append(widget)
        tables.extend(widget.findChildren(QTableWidget))
        tables.extend(widget.findChildren(QTableView))
        for table in tables:
            # 居中 delegate
            table.setItemDelegate(self._center_delegate)
            # 单行显示，不换行
            table.setWordWrap(False)
            # 文字超出时显示省略号
            table.setTextElideMode(Qt.ElideRight)
            # 固定行高，不拉伸
            vh = table.verticalHeader()
            if vh:
                vh.setSectionResizeMode(QHeaderView.Fixed)
                vh.setDefaultSectionSize(38)
            # 列宽：不强制自适应，保留各模块自行设定的列宽
            header = table.horizontalHeader()
            if header:
                header.setStretchLastSection(True)

    def _init_content(self, parent_splitter):
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(24, 16, 24, 16)
        content_layout.setSpacing(0)

        self.page_title = QLabel("工作台")
        self.page_title.setStyleSheet(f"""
            color: {COLOR['text_primary']};
            font-size: {FONT_SIZE['2xl']}px; font-weight: 700;
            background: transparent; padding-left: 12px;
            border-left: 4px solid {COLOR['primary']};
        """)
        self.page_subtitle = QLabel("欢迎使用餐饮综合管理系统")
        self.page_subtitle.setStyleSheet(f"color: {COLOR['text_muted']}; font-size: {FONT_SIZE['sm']}px; background: transparent;")

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        title_layout.addWidget(self.page_title)
        title_layout.addWidget(self.page_subtitle)
        content_layout.addLayout(title_layout)
        content_layout.addSpacing(16)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")

        self._page_factory = {
            "dashboard":     lambda: DashboardWidget(self.current_user),
            "finance":       FinanceWidget,
            "employee":      EmployeeWidget,
            "purchase":      PurchaseWidget,
            "revenue":       RevenueWidget,
            "reimbursement": lambda: ReimbursementWidget(self.current_user),
            "approval":      lambda: ApprovalWidget(self.current_user),
            "attendance":    lambda: AttendanceWidget(self.current_user),
            "salary":        SalaryWidget,
            "shifts":        ShiftWidget,
            "cost_calc":     CostCalcWidget,
            "reports":       ReportWidget,
            "store_manager": StoreWidget,
            "authorization": AuthorizationWidget,
            "table_mgt":     TableWidget,
        }
        self._loaded_tabs = set()  # 已懒加载的tab
        self._center_delegate = CenterAlignDelegate()

        # 只创建 Dashboard（首页必须立即可用），其余延迟到首次切换时创建
        for tab_key in self.tab_key_to_idx.keys():
            if tab_key == "dashboard":
                factory = self._page_factory.get(tab_key)
                if factory:
                    page = factory()
                    self.stack.addWidget(page)
                    self._widgets[tab_key] = page
                    self._loaded_tabs.add(tab_key)
                    self._install_center_delegate(page)
            else:
                # 占位：空Widget，首次切换时替换
                placeholder = QWidget()
                self.stack.addWidget(placeholder)
                self._widgets[tab_key] = placeholder  # 临时占位

        content_layout.addWidget(self.stack, 1)
        parent_splitter.addWidget(content_container)

    def _init_statusbar(self):
        self.sb = QStatusBar()
        self.sb.setFixedHeight(28)
        self.sb.setStyleSheet(f"""
            QStatusBar {{
                background-color: {COLOR['header_bg']};
                color: {COLOR['text_muted']};
                font-size: {FONT_SIZE['xs']}px;
                border-top: 1px solid {COLOR['border']};
                padding: 0 24px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QStatusBar::item {{ border: none; }}
        """)
        self.setStatusBar(self.sb)
        ctx = get_app_context()
        self.sb.showMessage(f"当前门店：{ctx.store_name}")

    def on_nav(self, tab_key):
        """收到自绘侧边栏发出的 tab_key"""
        if tab_key and tab_key in self.tab_key_to_idx:
            stack_idx = list(self._widgets.keys()).index(tab_key)
            self.stack.setCurrentIndex(stack_idx)

            # 从 NavList 取显示文本
            si = self.tab_key_to_idx[tab_key]
            if 0 <= si < len(self.nav._selectable):
                item_idx = self.nav._selectable[si]
                nav_item = self.nav._items[item_idx]
                self.page_title.setText(nav_item.text)

            subtitles = {
                "dashboard": "欢迎使用餐饮综合管理系统",
                "revenue": "查看门店营业数据与趋势分析",
                "purchase": "管理食材库存、采购进货与盘点",
                "table_mgt": "管理餐厅桌台与区域",
                "finance": "记录收支流水与财务分析",
                "employee": "管理员工信息与档案",
                "shifts": "排班计划与班次管理",
                "attendance": "考勤记录与统计",
                "salary": "工资核算与发放管理",
                "reimbursement": "报销申请与审批流程",
                "approval": "待审批事项与审批记录",
                "cost_calc": "菜品成本与毛利分析",
                "reports": "各类经营报表与数据分析",
                "store_manager": "门店信息与配置管理",
                "authorization": "用户权限与角色管理",
            }
            self.page_subtitle.setText(subtitles.get(tab_key, ""))

            # 懒加载：首次切换到该页时才创建真实Widget
            if tab_key not in self._loaded_tabs:
                factory = self._page_factory.get(tab_key)
                if factory:
                    try:
                        real_page = factory()
                        stack_idx = list(self._widgets.keys()).index(tab_key)
                        self.stack.removeWidget(self._widgets[tab_key])
                        self._widgets[tab_key].deleteLater()
                        self.stack.insertWidget(stack_idx, real_page)
                        self._widgets[tab_key] = real_page
                        self._loaded_tabs.add(tab_key)
                        self.stack.setCurrentIndex(stack_idx)
                        # 为新页面中的所有表格安装居中 delegate
                        self._install_center_delegate(real_page)
                    except Exception as e:
                        logger.error(f"懒加载页面失败 [{tab_key}]: {e}")

            # 刷新目标页数据（确保从其他页面切回时看到最新数据）
            widget = self._widgets.get(tab_key)
            if widget and hasattr(widget, 'load_data'):
                try:
                    widget.load_data()
                except Exception as e:
                    logger.error(f"切换页面刷新失败 [{tab_key}]: {e}")

    def on_store_changed(self, store_id):
        ctx = get_app_context()
        self.sb.showMessage(f"当前门店：{ctx.store_name}")
        error_count = 0
        # 只刷新已懒加载的页面，未加载的会在首次切换时自动加载最新数据
        for tab_key, widget in self._widgets.items():
            if tab_key in self._loaded_tabs and hasattr(widget, 'load_data'):
                try:
                    widget.load_data()
                except Exception as e:
                    error_count += 1
                    logger.error(f"刷新页面失败 [{tab_key}]: {e}")
        if error_count > 0:
            self.sb.showMessage(f"门店切换完成，{error_count} 个页面刷新失败，数据可能过期", 8000)

    def logout(self):
        reply = QMessageBox.question(self, "确认退出", "确定要退出登录吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                from utils.auth_manager import get_auth
                get_auth().clear_session()
                logger.info("用户退出登录，会话已清除")
            except Exception as e:
                logger.error(f"清除会话失败: {e}")
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(COLOR['border']), 1)
        painter.setPen(pen)
        painter.setBrush(QColor(COLOR['bg_page']))
        # 统一画矩形：不使用圆角，避免 WA_TranslucentBackground 缺失时圆角区域露出黑色
        painter.drawRect(self.rect())
        painter.end()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            self._is_maximized = False
            self.btn_max.set_icon_type("max")
        else:
            self._normal_geometry = self.geometry()
            self.showMaximized()
            self._is_maximized = True
            self.btn_max.set_icon_type("restore")
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.y() < 56:
            child = self.childAt(event.pos())
            if child and (isinstance(child, QPushButton) or isinstance(child, QComboBox)):
                return
            self._drag_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and self._drag_pos and event.buttons() == Qt.LeftButton:
            if self.isMaximized():
                self.showNormal()
                self._is_maximized = False
                self.btn_max.set_icon_type("max")
                self._drag_pos = event.globalPos()
                self.move(event.globalPos().x() - self.width() // 2, event.globalPos().y() - 10)
                return
            self.move(self.pos() + event.globalPos() - self._drag_pos)
            self._drag_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        pass

    def resizeEvent(self, event):
        """窗口大小变化时强制重绘 NavList，防止侧边栏内容不同步"""
        super().resizeEvent(event)
        if hasattr(self, 'nav'):
            self.nav.update()

    def changeEvent(self, event):
        if event.type() == event.WindowStateChange:
            central = self.centralWidget()
            r = 0  # 不再使用圆角，避免无 WA_TranslucentBackground 时圆角区域露出黑色
            if self.isMaximized():
                self._is_maximized = True
                self.btn_max.set_icon_type("restore")
            else:
                self._is_maximized = False
                self.btn_max.set_icon_type("max")
            if central:
                central.setStyleSheet(f"#centralWidget {{ background-color: {COLOR['bg_page']}; border-radius: {r}px; }}")
            header = self.findChild(QFrame, "headerFrame")
            if header:
                header.setStyleSheet(f"""
                    QFrame {{
                        background-color: {COLOR['header_bg']};
                        border-bottom: 1px solid {COLOR['border']};
                        border-top-left-radius: {r}px;
                        border-top-right-radius: {r}px;
                    }}
                """)
            if hasattr(self, 'sb'):
                self.sb.setStyleSheet(f"""
                    QStatusBar {{
                        background-color: {COLOR['header_bg']};
                        color: {COLOR['text_muted']};
                        font-size: {FONT_SIZE['xs']}px;
                        border-top: 1px solid {COLOR['border']};
                        padding: 0 24px;
                        border-bottom-left-radius: {r}px;
                        border-bottom-right-radius: {r}px;
                    }}
                """)
            self.update()
        super().changeEvent(event)

    def closeEvent(self, event):
        """窗口关闭时：停止自动同步线程 + 后台最终上传（不阻塞UI） + 安全退出"""
        try:
            from utils.nutstore_sync import get_sync
            sync = get_sync()
            sync.stop_auto_sync()
            # 取消防抖定时器（避免关闭瞬间触发上传竞争锁）
            if sync._debounce_timer is not None:
                sync._debounce_timer.cancel()
            # 最终上传放守护线程，进程退出时自动终止，不阻塞UI
            if sync.is_connected:
                def _final_upload():
                    try:
                        sync.upload_db()
                        logger.info("窗口关闭后后台同步完成")
                    except Exception as e:
                        logger.warning(f"关闭后后台同步失败: {e}")
                threading.Thread(target=_final_upload, daemon=True).start()
        except Exception as e:
            logger.warning(f"关闭前同步失败: {e}")
        event.accept()

    def open_change_password(self):
        dlg = ChangePasswordDialog(self, self.current_user.get("username", ""))
        dlg.exec_()


# ═══════════════════════════════════════════
# 修改密码对话框
# ═══════════════════════════════════════════

class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None, username=""):
        super().__init__(parent)
        self._username = username
        self._result = {}
        self._poll_timer = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("修改密码")
        self.resize(440, 480)
        self.setStyleSheet(f"QDialog {{ background-color: {COLOR['bg_card']}; }}")

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(0)

        title = QLabel("修改密码")
        title.setStyleSheet(f"font-size: {FONT_SIZE['3xl']}px; font-weight: 700; color: {COLOR['text_primary']};")
        layout.addWidget(title)

        subtitle = QLabel("当前账号：" + self._username)
        subtitle.setStyleSheet(f"font-size: {FONT_SIZE['sm']}px; color: {COLOR['text_muted']}; margin-top: 6px; margin-bottom: 28px;")
        layout.addWidget(subtitle)

        input_label_style = f"font-size: {FONT_SIZE['sm']}px; color: {COLOR['text_secondary']}; margin-bottom: 6px; font-weight: 500;"

        lbl_old = QLabel("原密码")
        lbl_old.setStyleSheet(input_label_style)
        layout.addWidget(lbl_old)
        from gui.login_dialog import IconLineEdit
        self.txt_old_widget = IconLineEdit("请输入原密码", "🔒", is_password=True)
        self.txt_old = self.txt_old_widget.input
        layout.addWidget(self.txt_old_widget)
        layout.addSpacing(18)

        lbl_new = QLabel("新密码")
        lbl_new.setStyleSheet(input_label_style)
        layout.addWidget(lbl_new)
        self.txt_new_widget = IconLineEdit("请输入新密码（至少6位）", "🔒", is_password=True)
        self.txt_new = self.txt_new_widget.input
        layout.addWidget(self.txt_new_widget)
        layout.addSpacing(18)

        lbl_confirm = QLabel("确认新密码")
        lbl_confirm.setStyleSheet(input_label_style)
        layout.addWidget(lbl_confirm)
        self.txt_confirm_widget = IconLineEdit("请再次输入新密码", "🔒", is_password=True)
        self.txt_confirm = self.txt_confirm_widget.input
        layout.addWidget(self.txt_confirm_widget)

        layout.addSpacing(16)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"""
            color: {COLOR['danger']}; font-size: {FONT_SIZE['sm']}px;
            background: {COLOR['danger_light']}; padding: 8px 12px;
            border-radius: {RADIUS['sm']}px;
        """)
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        layout.addSpacing(20)
        self.btn_submit = QPushButton("确认修改")
        self.btn_submit.setFixedHeight(44)
        self.btn_submit.setCursor(Qt.PointingHandCursor)
        self.btn_submit.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR['primary']}; color: {COLOR['text_white']};
                border: none; border-radius: {RADIUS['md']}px;
                font-size: {FONT_SIZE['lg']}px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {COLOR['primary_hover']}; }}
            QPushButton:pressed {{ background-color: {COLOR['primary_pressed']}; }}
            QPushButton:disabled {{ background-color: {COLOR['border_dark']}; color: {COLOR['text_muted']}; }}
        """)
        self.btn_submit.clicked.connect(self.do_submit)
        layout.addWidget(self.btn_submit)

        layout.addStretch()
        self.setLayout(layout)

    def show_error(self, msg):
        self.lbl_error.setText(msg)
        self.lbl_error.setVisible(True)

    def do_submit(self):
        old_pwd = self.txt_old.text()
        new_pwd = self.txt_new.text()
        confirm = self.txt_confirm.text()

        self.txt_old_widget.set_error(False)
        self.txt_new_widget.set_error(False)
        self.txt_confirm_widget.set_error(False)

        if not old_pwd:
            self.show_error("请输入原密码")
            self.txt_old_widget.set_error(True)
            self.txt_old_widget.setFocus()
            return
        if not new_pwd:
            self.show_error("请输入新密码")
            self.txt_new_widget.set_error(True)
            self.txt_new_widget.setFocus()
            return
        if len(new_pwd) < 6:
            self.show_error("新密码至少6位")
            self.txt_new_widget.set_error(True)
            self.txt_new_widget.setFocus()
            return
        if new_pwd != confirm:
            self.show_error("两次密码输入不一致")
            self.txt_confirm_widget.set_error(True)
            self.txt_confirm_widget.setFocus()
            return
        if old_pwd == new_pwd:
            self.show_error("新密码不能与原密码相同")
            self.txt_new_widget.set_error(True)
            self.txt_new_widget.setFocus()
            return

        self.lbl_error.setVisible(False)
        self.btn_submit.setEnabled(False)
        self.btn_submit.setText("修改中...")
        self._result = {}

        def thread_func():
            try:
                from utils.auth_manager import get_auth
                auth = get_auth()
                success, msg = auth.change_password(self._username, old_pwd, new_pwd)
                if success:
                    self._result = {"success": True}
                else:
                    self._result = {"error": msg}
            except Exception as e:
                self._result = {"error": str(e)}

        t = threading.Thread(target=thread_func, daemon=True)
        t.start()

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._check_result)
        self._poll_timer.start(200)

    def _check_result(self):
        if not self._result:
            return
        self._poll_timer.stop()
        if "success" in self._result:
            QMessageBox.information(self, "成功", "密码修改成功，下次登录请使用新密码")
            self.accept()
        else:
            self.show_error(self._result.get("error", "修改失败"))
            self.txt_old_widget.set_error(True)
            self.btn_submit.setEnabled(True)
            self.btn_submit.setText("确认修改")
