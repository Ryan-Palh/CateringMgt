# -*- coding: utf-8 -*-
"""
现代简约设计系统 v5.0 —— 蓝紫青配色（与登录页面统一）
主色取自图标渐变：蓝紫主色 + 亮青强调色 + 深钴蓝侧边栏
"""
import os, tempfile, atexit, struct, zlib
from PyQt5.QtGui import QPalette, QColor, QPixmap
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QPushButton, QWidget, QLabel, QStyledItemDelegate, QStyleOptionViewItem, QStyle

# ═══════════════════════════════════════════
# 箭头图片生成（保持与原系统一致的实现）
# ═══════════════════════════════════════════
_ARROW_DIR = os.path.join(tempfile.gettempdir(), f'ccc_arrows_{os.getpid()}')
_ARROW_DOWN = None
_ARROW_UP = None

def _make_aa_triangle_png(out_w, out_h, points, rgba, ss=4):
    W, H = out_w * ss, out_h * ss
    pts = [(x * ss, y * ss) for x, y in points]
    x0, y0 = pts[0]; x1, y1 = pts[1]; x2, y2 = pts[2]
    min_x = max(0, int(min(x0, x1, x2)))
    max_x = min(W, int(max(x0, x1, x2)) + 1)
    min_y = max(0, int(min(y0, y1, y2)))
    max_y = min(H, int(max(y0, y1, y2)) + 1)
    r, g, b, a = rgba
    hi_buf = bytearray(W * H * 4)
    for py in range(min_y, max_y):
        for px in range(min_x, max_x):
            d1 = (px - x1) * (y0 - y1) - (x0 - x1) * (py - y1)
            d2 = (px - x2) * (y1 - y2) - (x1 - x2) * (py - y2)
            d3 = (px - x0) * (y2 - y0) - (x2 - x0) * (py - y0)
            has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
            has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
            if not (has_neg and has_pos):
                idx = (py * W + px) * 4
                hi_buf[idx] = r; hi_buf[idx+1] = g; hi_buf[idx+2] = b; hi_buf[idx+3] = a
    buf = bytearray(out_w * out_h * 4)
    for oy in range(out_h):
        for ox in range(out_w):
            tot_a = 0
            for sy in range(ss):
                for sx in range(ss):
                    tot_a += hi_buf[((oy*ss+sy) * W + (ox*ss+sx)) * 4 + 3]
            avg_a = tot_a // (ss * ss)
            idx = (oy * out_w + ox) * 4
            buf[idx] = r; buf[idx+1] = g; buf[idx+2] = b; buf[idx+3] = avg_a
    def _png_chunk(ctype, data):
        c = ctype + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', out_w, out_h, 8, 6, 0, 0, 0)
    raw = bytearray()
    for py in range(out_h):
        raw.append(0)
        raw.extend(buf[py * out_w * 4:(py + 1) * out_w * 4])
    idat = zlib.compress(bytes(raw), 9)
    return sig + _png_chunk(b'IHDR', ihdr) + _png_chunk(b'IDAT', idat) + _png_chunk(b'IEND', b'')

def _gen_arrows():
    global _ARROW_DOWN, _ARROW_UP
    if _ARROW_DOWN:
        return
    os.makedirs(_ARROW_DIR, exist_ok=True)
    gray = (0x99, 0xA3, 0xB2, 0xFF)
    down_png = _make_aa_triangle_png(12, 8, [(0, 0), (12, 0), (6, 8)], gray, ss=4)
    _ARROW_DOWN = os.path.join(_ARROW_DIR, 'd.png').replace('\\', '/')
    with open(_ARROW_DOWN, 'wb') as f:
        f.write(down_png)
    up_png = _make_aa_triangle_png(12, 8, [(0, 8), (12, 8), (6, 0)], gray, ss=4)
    _ARROW_UP = os.path.join(_ARROW_DIR, 'u.png').replace('\\', '/')
    with open(_ARROW_UP, 'wb') as f:
        f.write(up_png)

atexit.register(lambda: __import__('shutil').rmtree(_ARROW_DIR, ignore_errors=True))
_gen_arrows()

def get_combo_arrow_qss():
    _gen_arrows()
    return (
        f'QComboBox::down-arrow {{ image: url({_ARROW_DOWN}); width: 12px; height: 8px; subcontrol-position: center; }}\n'
        f'QDateEdit::down-arrow, QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {{ image: url({_ARROW_DOWN}); width: 12px; height: 8px; subcontrol-position: center; }}\n'
        f'QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({_ARROW_UP}); width: 12px; height: 8px; subcontrol-position: center; }}\n'
        f'QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({_ARROW_DOWN}); width: 12px; height: 8px; subcontrol-position: center; }}'
    )

# ═══════════════════════════════════════════
# 设计令牌 —— 餐饮暖色系
# ═══════════════════════════════════════════

COLOR = {
    # 主色：蓝紫色（取自图标中间渐变色）
    "primary": "#5B6CFF",
    "primary_hover": "#4F5DE0",
    "primary_pressed": "#424FC7",
    "primary_light": "#EDEFFF",
    "primary_bg": "#F4F5FF",
    "primary_soft": "#EFF0FF",

    # 高亮强调色：亮青色（取自图标折线末端发光点）
    "accent": "#06B6D4",
    "accent_hover": "#0891B2",
    "accent_light": "#ECFEFF",
    "accent_bg": "#CFFAFE",
    "accent_glow": "#22D3EE",

    # 成功色
    "success": "#10B981",
    "success_hover": "#059669",
    "success_pressed": "#047857",
    "success_light": "#ECFDF5",
    "success_bg": "#D1FAE5",

    # 警告色
    "warning": "#F59E0B",
    "warning_hover": "#D97706",
    "warning_light": "#FFFBEB",
    "warning_bg": "#FEF3C7",

    # 危险色
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "danger_pressed": "#B91C1C",
    "danger_light": "#FEF2F2",
    "danger_bg": "#FEE2E2",

    # 信息色
    "info": "#3B82F6",
    "info_hover": "#2563EB",
    "info_light": "#EFF6FF",
    "info_bg": "#DBEAFE",

    # 中性色 - 背景
    "bg_page": "#F0F2F8",
    "bg_card": "#FFFFFF",
    "bg_surface": "#F7F8FB",
    "bg_hover": "#EDF0F5",
    "bg_active": "#E0E4EC",

    # 中性色 - 文字
    "text_primary": "#0F172A",
    "text_secondary": "#475569",
    "text_muted": "#94A3B8",
    "text_placeholder": "#CBD5E1",
    "text_white": "#FFFFFF",
    "text_disabled": "#94A3B8",

    # 中性色 - 边框
    "border": "#E0E4EC",
    "border_light": "#EEF1F6",
    "border_dark": "#C8D0DB",
    "border_focus": "#5B6CFF",

    # 侧边栏（取自图标左上深钴蓝→右下蓝紫渐变）
    "sidebar_bg": "#1A1B3A",
    "sidebar_bg_grad": "#2A1F5C",
    "sidebar_hover": "#2D2E5C",
    "sidebar_selected": "#5B6CFF",
    "sidebar_selected_glow": "#22D3EE",
    "sidebar_text": "#9CA3C4",
    "sidebar_text_hover": "#E2E5F5",
    "sidebar_text_selected": "#FFFFFF",
    "sidebar_border": "#2A2B5C",
    "sidebar_group_header": "#6B7299",

    # 顶部栏
    "header_bg": "#FFFFFF",
    "header_border": "#E2E8F0",
    "header_text": "#0F172A",
    "header_text_muted": "#64748B",
    "header_accent": "#06B6D4",

    # 表格
    "table_header_bg": "#F5F6FA",
    "table_header_text": "#475569",
    "table_header_border": "#E2E8F0",
    "table_row_alt": "#F8F9FB",
    "table_border": "#EEF1F6",
    "table_row_hover": "#EDEFFF",
    "table_row_selected": "#EDEFFF",

    # 图表配色（取自图标渐变色系）
    "chart_1": "#5B6CFF",
    "chart_2": "#06B6D4",
    "chart_3": "#22D3EE",
    "chart_4": "#818CF8",
    "chart_5": "#A78BFA",
    "chart_6": "#F472B6",
    "chart_7": "#38BDF8",
    "chart_8": "#FB923C",

    # 兼容别名（防止模块间命名不一致）
    "text": "#0F172A",
    "bg_light": "#F0F2F8",
    "bg": "#F0F2F8",
}

# --- 圆角 ---
RADIUS = {
    "xs": 4, "sm": 6, "md": 8, "lg": 12, "xl": 16, "2xl": 20, "full": 999,
}

# --- 阴影 ---
SHADOW = {
    "sm": "0 1px 2px rgba(0, 0, 0, 0.05)",
    "md": "0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.06)",
    "lg": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.08)",
    "xl": "0 20px 25px -5px rgba(0, 0, 0, 0.12), 0 8px 10px -6px rgba(0, 0, 0, 0.08)",
    "card": "0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)",
    "card_hover": "0 4px 12px rgba(0, 0, 0, 0.08)",
    "dialog": "0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
}

# --- 间距 ---
SPACING = {
    "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "2xl": 24, "3xl": 32, "4xl": 40,
}

# --- 字体大小 ---
FONT_SIZE = {
    "xs": 11, "sm": 12, "base": 13, "md": 14, "lg": 16, "xl": 18,
    "2xl": 20, "3xl": 24, "4xl": 28, "5xl": 32,
}

# --- 字体粗细 ---
FONT_WEIGHT = {
    "normal": 400, "medium": 500, "semibold": 600, "bold": 700,
}

# ═══════════════════════════════════════════
# 全局样式表
# ═══════════════════════════════════════════

GLOBAL_STYLESHEET = f"""
/* ===== 基础 ===== */
QMainWindow {{ background-color: {COLOR['bg_page']}; }}
QWidget {{
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: {FONT_SIZE['base']}px;
    color: {COLOR['text_primary']};
}}
QLabel {{ color: {COLOR['text_primary']}; background: transparent; }}

/* ===== 输入框 ===== */
QLineEdit {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 10px 14px;
    font-size: {FONT_SIZE['base']}px;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
    selection-background-color: {COLOR['primary_light']};
    min-height: 22px;
}}
QLineEdit:focus {{ border: 1px solid {COLOR['primary']}; background-color: #FFFFFF; }}
QLineEdit:disabled {{ background-color: {COLOR['bg_surface']}; color: {COLOR['text_muted']}; }}
QLineEdit:hover:!focus {{ border-color: {COLOR['border_dark']}; }}

/* ===== 数字输入框 ===== */
QSpinBox, QDoubleSpinBox {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 10px 14px;
    padding-right: 36px;
    font-size: {FONT_SIZE['base']}px;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
    min-height: 22px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {COLOR['primary']}; background-color: #FFFFFF; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 28px; height: 17px; border: none;
    border-bottom: 1px solid {COLOR['border_light']};
    background-color: transparent;
    border-top-right-radius: {RADIUS['md']}px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{ background-color: {COLOR['primary_light']}; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: padding; subcontrol-position: bottom right;
    width: 28px; height: 17px; border: none;
    background-color: transparent;
    border-bottom-right-radius: {RADIUS['md']}px;
}}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background-color: {COLOR['primary_light']}; }}

/* ===== 下拉框 ===== */
QComboBox {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 8px 36px 8px 14px;
    font-size: {FONT_SIZE['base']}px;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
    min-height: 22px;
}}
QComboBox:hover {{ border-color: {COLOR['primary']}; }}
QComboBox:focus {{ border: 1.5px solid {COLOR['primary']}; }}
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
    outline: none; padding: 6px;
    border-radius: {RADIUS['md']}px;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 14px; border-radius: {RADIUS['sm']}px; min-height: 24px;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {COLOR['primary_light']}; color: {COLOR['primary']};
}}

/* ===== 日期/时间选择器 ===== */
QDateEdit, QTimeEdit, QDateTimeEdit {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 8px 36px 8px 14px;
    font-size: {FONT_SIZE['base']}px;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
    min-height: 22px;
}}
QDateEdit:hover, QTimeEdit:hover, QDateTimeEdit:hover {{ border-color: {COLOR['primary']}; }}
QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {{ border: 1.5px solid {COLOR['primary']}; }}
QDateEdit::drop-down, QTimeEdit::drop-down, QDateTimeEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 28px; border: none; background-color: transparent;
}}
QDateEdit::up-button, QTimeEdit::up-button, QDateTimeEdit::up-button {{
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 28px; height: 17px; border: none;
    border-bottom: 1px solid {COLOR['border_light']};
    background-color: transparent;
    border-top-right-radius: {RADIUS['md']}px;
}}
QDateEdit::up-button:hover, QTimeEdit::up-button:hover, QDateTimeEdit::up-button:hover {{ background-color: {COLOR['primary_light']}; }}
QDateEdit::down-button, QTimeEdit::down-button, QDateTimeEdit::down-button {{
    subcontrol-origin: padding; subcontrol-position: bottom right;
    width: 28px; height: 17px; border: none;
    background-color: transparent;
    border-bottom-right-radius: {RADIUS['md']}px;
}}
QDateEdit::down-button:hover, QTimeEdit::down-button:hover, QDateTimeEdit::down-button:hover {{ background-color: {COLOR['primary_light']}; }}

/* ===== 文本域 ===== */
QTextEdit, QPlainTextEdit {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 8px 12px;
    font-size: {FONT_SIZE['base']}px;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
    selection-background-color: {COLOR['primary_light']};
}}
QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {COLOR['primary']}; background-color: #FFFFFF; }}

/* ===== 按钮 ===== */
QPushButton {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 8px 16px;
    font-size: {FONT_SIZE['base']}px;
    font-weight: 500;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
}}
QPushButton:hover {{ border-color: {COLOR['primary']}; color: {COLOR['primary']}; background-color: {COLOR['primary_light']}; }}
QPushButton:pressed {{ background-color: {COLOR['primary_soft']}; }}
QPushButton:disabled {{ background-color: {COLOR['bg_surface']}; color: {COLOR['text_disabled']}; border-color: {COLOR['border_light']}; }}

/* ===== 表格 ===== */
QTableWidget {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    background-color: {COLOR['bg_card']};
    alternate-background-color: {COLOR['table_row_alt']};
    selection-background-color: {COLOR['primary_light']};
    selection-color: {COLOR['text_primary']};
    gridline-color: {COLOR['table_border']};
    outline: none;
}}
QTableWidget::item {{ padding: 6px 10px; border: none; }}
QTableWidget::item:selected {{ background-color: {COLOR['primary_light']}; color: {COLOR['text_primary']}; }}
QTableWidget::item:hover {{ background-color: {COLOR['table_row_hover']}; }}
QHeaderView::section {{
    background-color: {COLOR['table_header_bg']};
    color: {COLOR['table_header_text']};
    font-weight: 600;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid {COLOR['primary']};
    border-right: 1px solid {COLOR['table_border']};
}}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{ background-color: {COLOR['table_header_bg']}; border: none; border-bottom: 2px solid {COLOR['primary']}; }}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 0;
    border-radius: {RADIUS['full']}px;
}}
QScrollBar::handle:vertical {{
    background-color: {COLOR['border_dark']};
    border-radius: {RADIUS['full']}px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {COLOR['text_muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 8px; margin: 0;
    border-radius: {RADIUS['full']}px;
}}
QScrollBar::handle:horizontal {{
    background-color: {COLOR['border_dark']};
    border-radius: {RADIUS['full']}px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background-color: {COLOR['text_muted']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ===== 分组框 ===== */
QGroupBox {{
    font-size: {FONT_SIZE['base']}px; font-weight: 600;
    color: {COLOR['text_primary']};
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['lg']}px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    background-color: {COLOR['bg_card']};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 8px; left: 12px;
    color: {COLOR['primary']};
}}

/* ===== 标签页 ===== */
QTabWidget::pane {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    background-color: {COLOR['bg_card']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {COLOR['bg_surface']};
    color: {COLOR['text_secondary']};
    padding: 8px 18px;
    margin-right: 2px;
    border: 1px solid {COLOR['border']};
    border-bottom: none;
    border-top-left-radius: {RADIUS['md']}px;
    border-top-right-radius: {RADIUS['md']}px;
    font-size: {FONT_SIZE['base']}px; font-weight: 500;
}}
QTabBar::tab:selected {{
    background-color: {COLOR['bg_card']};
    color: {COLOR['primary']};
    border-color: {COLOR['border']};
    border-bottom: 2px solid {COLOR['primary']};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ background-color: {COLOR['bg_hover']}; color: {COLOR['text_primary']}; }}

/* ===== 复选框 ===== */
QCheckBox {{ color: {COLOR['text_secondary']}; font-size: {FONT_SIZE['base']}px; spacing: 6px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1.5px solid {COLOR['border_dark']};
    border-radius: 3px;
    background: {COLOR['bg_card']};
}}
QCheckBox::indicator:checked {{ background-color: {COLOR['primary']}; border-color: {COLOR['primary']}; }}
QCheckBox::indicator:hover {{ border-color: {COLOR['primary']}; }}

/* ===== 单选框 ===== */
QRadioButton {{ color: {COLOR['text_secondary']}; font-size: {FONT_SIZE['base']}px; spacing: 6px; }}
QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1.5px solid {COLOR['border_dark']};
    border-radius: {RADIUS['full']}px;
    background: {COLOR['bg_card']};
}}
QRadioButton::indicator:checked {{ background-color: {COLOR['primary']}; border-color: {COLOR['primary']}; }}

/* ===== 对话框 ===== */
QDialog {{ background-color: {COLOR['bg_card']}; }}

/* ===== 工具提示 ===== */
QToolTip {{
    background-color: #1A1A1A; color: #FFFFFF;
    border: none; border-radius: {RADIUS['xs']}px;
    padding: 6px 10px; font-size: {FONT_SIZE['sm']}px;
}}

/* ===== 菜单 ===== */
QMenu {{
    background-color: {COLOR['bg_card']};
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px; border-radius: {RADIUS['sm']}px;
    font-size: {FONT_SIZE['base']}px;
}}
QMenu::item:selected {{ background-color: {COLOR['primary_light']}; color: {COLOR['primary']}; }}
QMenu::separator {{ height: 1px; background-color: {COLOR['border']}; margin: 4px 8px; }}
"""

# ═══════════════════════════════════════════
# 组件样式常量
# ═══════════════════════════════════════════

COMBO_STYLE = f"""
QComboBox {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 8px 36px 8px 14px;
    font-size: {FONT_SIZE['base']}px;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
    min-height: 22px;
}}
QComboBox:hover {{ border-color: {COLOR['primary']}; }}
QComboBox:focus {{ border: 1.5px solid {COLOR['primary']}; }}
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
    outline: none; padding: 6px;
    border-radius: {RADIUS['md']}px;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 14px; border-radius: {RADIUS['sm']}px; min-height: 24px;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {COLOR['primary_light']}; color: {COLOR['primary']};
}}
"""

INPUT_STYLE = f"""
QLineEdit {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    padding: 8px 14px;
    font-size: {FONT_SIZE['base']}px;
    background-color: {COLOR['bg_card']};
    color: {COLOR['text_primary']};
    min-height: 22px;
}}
QLineEdit:focus {{ border: 1.5px solid {COLOR['primary']}; background-color: #FFFFFF; }}
"""

TABLE_STYLE = f"""
QTableWidget {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['md']}px;
    background-color: {COLOR['bg_card']};
    alternate-background-color: {COLOR['table_row_alt']};
    selection-background-color: {COLOR['primary_light']};
    selection-color: {COLOR['text_primary']};
    gridline-color: {COLOR['table_border']};
    outline: none;
}}
QTableWidget::item {{ padding: 6px 10px; border: none; }}
QTableWidget::item:selected {{ background-color: {COLOR['primary_light']}; color: {COLOR['text_primary']}; }}
QHeaderView::section {{
    background-color: {COLOR['table_header_bg']};
    color: {COLOR['table_header_text']};
    font-weight: 600;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid {COLOR['primary']};
    border-right: 1px solid {COLOR['table_border']};
    text-align: center;
}}
"""

DLG_STYLE = f"QDialog {{ background-color: {COLOR['bg_card']}; }}"

BTN_PRIMARY = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {COLOR['primary']}, stop:1 {COLOR['accent_glow']});
        color: {COLOR['text_white']};
        border: none;
        border-radius: {RADIUS['md']}px;
        padding: 8px 20px;
        font-size: {FONT_SIZE['base']}px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR['primary_hover']}, stop:1 {COLOR['primary']}); }}
    QPushButton:pressed {{ background-color: {COLOR['primary_pressed']}; }}
    QPushButton:disabled {{ background-color: {COLOR['border_dark']}; color: {COLOR['text_muted']}; }}
"""

BTN_SUCCESS = f"""
    QPushButton {{
        background-color: {COLOR['success']};
        color: {COLOR['text_white']};
        border: none;
        border-radius: {RADIUS['md']}px;
        padding: 8px 20px;
        font-size: {FONT_SIZE['base']}px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {COLOR['success_hover']}; }}
    QPushButton:pressed {{ background-color: {COLOR['success_pressed']}; }}
"""

BTN_DANGER = f"""
    QPushButton {{
        background-color: {COLOR['danger']};
        color: {COLOR['text_white']};
        border: none;
        border-radius: {RADIUS['md']}px;
        padding: 8px 20px;
        font-size: {FONT_SIZE['base']}px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {COLOR['danger_hover']}; }}
    QPushButton:pressed {{ background-color: {COLOR['danger_pressed']}; }}
"""

# 表格内操作按钮
TABLE_BTN_EDIT = f"""
    QPushButton {{
        background-color: {COLOR['primary_light']};
        color: {COLOR['primary']};
        border: none;
        border-radius: {RADIUS['sm']}px;
        padding: 3px 8px;
        font-size: {FONT_SIZE['sm']}px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {COLOR['primary']}; color: {COLOR['text_white']}; }}
"""

TABLE_BTN_DELETE = f"""
    QPushButton {{
        background-color: {COLOR['danger_light']};
        color: {COLOR['danger']};
        border: none;
        border-radius: {RADIUS['sm']}px;
        padding: 3px 8px;
        font-size: {FONT_SIZE['sm']}px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {COLOR['danger']}; color: {COLOR['text_white']}; }}
"""

TABLE_BTN_VIEW = f"""
    QPushButton {{
        background-color: {COLOR['accent_light']};
        color: {COLOR['accent']};
        border: none;
        border-radius: {RADIUS['sm']}px;
        padding: 3px 8px;
        font-size: {FONT_SIZE['sm']}px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {COLOR['accent']}; color: {COLOR['text_white']}; }}
"""

# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def make_table_button(text, variant="edit"):
    """创建表格内操作按钮"""
    styles = {"edit": TABLE_BTN_EDIT, "delete": TABLE_BTN_DELETE, "view": TABLE_BTN_VIEW}
    btn = QPushButton(text)
    btn.setStyleSheet(styles.get(variant, TABLE_BTN_EDIT))
    btn.setFixedHeight(28)
    btn.setMinimumWidth(44)
    btn.setCursor(Qt.PointingHandCursor)
    return btn

def apply_global_theme(app):
    """应用全局主题"""
    _gen_arrows()
    popup_fix = 'QComboBox, QDateEdit, QTimeEdit, QDateTimeEdit { combobox-popup: 0; }\n'
    arrow_css = (
        f'QComboBox::down-arrow {{ image: url({_ARROW_DOWN}); width: 12px; height: 8px; subcontrol-position: center; }}\n'
        f'QDateEdit::down-arrow, QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {{ image: url({_ARROW_DOWN}); width: 12px; height: 8px; subcontrol-position: center; }}\n'
        f'QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({_ARROW_UP}); width: 12px; height: 8px; subcontrol-position: center; }}\n'
        f'QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({_ARROW_DOWN}); width: 12px; height: 8px; subcontrol-position: center; }}'
    )
    app.setStyleSheet(GLOBAL_STYLESHEET + popup_fix + arrow_css)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLOR['bg_page']))
    palette.setColor(QPalette.WindowText, QColor(COLOR['text_primary']))
    palette.setColor(QPalette.Base, QColor(COLOR['bg_card']))
    palette.setColor(QPalette.AlternateBase, QColor(COLOR['bg_surface']))
    palette.setColor(QPalette.Text, QColor(COLOR['text_primary']))
    palette.setColor(QPalette.Button, QColor(COLOR['bg_card']))
    palette.setColor(QPalette.ButtonText, QColor(COLOR['text_primary']))
    palette.setColor(QPalette.Highlight, QColor(COLOR['primary']))
    palette.setColor(QPalette.HighlightedText, QColor(COLOR['text_white']))
    palette.setColor(QPalette.ToolTipBase, QColor("#1A1A1A"))
    palette.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
    app.setPalette(palette)

COMPACT_TABLE_STYLE = f"""
QTableWidget {{
    border: 1px solid {COLOR['border']};
    border-radius: {RADIUS['sm']}px;
    background-color: {COLOR['bg_card']};
    alternate-background-color: {COLOR['table_row_alt']};
    selection-background-color: {COLOR['primary_light']};
    selection-color: {COLOR['text_primary']};
    gridline-color: {COLOR['table_border']};
    outline: none;
}}
QTableWidget::item {{ padding: 4px 8px; border: none; }}
QHeaderView::section {{
    background-color: {COLOR['table_header_bg']};
    color: {COLOR['table_header_text']};
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-bottom: 2px solid {COLOR['primary']};
    border-right: 1px solid {COLOR['table_border']};
    text-align: center;
}}
"""

# ═══════════════════════════════════════════
# 全局居中 ItemDelegate：所有表格单元格内容自动居中
# ═══════════════════════════════════════════
class CenterAlignDelegate(QStyledItemDelegate):
    """QItemDelegate 子类：强制所有单元格文本水平+垂直居中"""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter

# 旧版兼容别名
primary_btn = BTN_PRIMARY
success_btn = BTN_SUCCESS
danger_btn = BTN_DANGER
