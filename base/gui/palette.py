"""GUI 调色板（暗色主题）。

集中暴露主色 / 文本 / 边框 / 背景常量，让 :mod:`base.gui.shell` 的全局 QSS 与
分散在各 widget 里的 inline ``setStyleSheet`` 引用同一来源，避免色值漂移。
"""

from __future__ import annotations

# 主色 —— 操作按钮 / 选中态 / 焦点边框 / 高亮拖入区（GitHub Dark blue）
PRIMARY          = '#58a6ff'
PRIMARY_HOVER    = '#4493f8'
PRIMARY_ACTIVE   = '#316dca'
PRIMARY_SOFT     = '#0c2a52'    # 拖入高亮的暗色淡蓝背景
PRIMARY_DISABLED = '#1f3d6e'

# PRIMARY 背景之上的前景色（按钮文字 / 选区文字 —— 深浅主题都恒为白）
ON_PRIMARY = '#ffffff'

# 强调色 —— 跨流水线的「一键自动化」类全局动作按钮（GitHub Dark orange）
# 与 PRIMARY 蓝形成对比，提示「这不是单步操作」
ACCENT          = '#f0883e'
ACCENT_HOVER    = '#d8762e'
ACCENT_ACTIVE   = '#b85c1a'
ACCENT_DISABLED = '#5a3a20'

# 文本（整体去除纯白感，GitHub Dark 标准灰白）
TEXT        = '#c9d1d9'
TEXT_MUTED  = '#8b949e'         # 状态行 / 次要 label
TEXT_DIM    = '#6e7681'         # 禁用 / 占位

# 边框 / 分割
BORDER        = '#363c45'
BORDER_STRONG = '#4a5159'
BORDER_SOFT   = '#262c34'

# 背景（整体提亮 ~5-8%，降低与文本的对比，更柔和）
BG          = '#161a21'         # 窗口底
BG_RAISED   = '#1d222b'         # pane / button / input
BG_SUBTLE   = '#0b0e13'         # drop-area（配 dashed border 仍呈凹陷）
BG_LOG      = '#1a1f29'         # LogView：略凹于 BG_RAISED，呈"代码块"感
BG_HOVER    = '#232934'
BG_PRESSED  = '#2d333d'
BG_BUTTON_HOVER = '#262c36'

# 滚动条
SCROLLBAR        = '#363c45'
SCROLLBAR_HOVER  = '#4a5159'

# Tooltip
TOOLTIP_BG = '#232934'
TOOLTIP_FG = TEXT


def stylesheet() -> str:
    """返回暗色主题的全局 QSS 字符串。

    在 :class:`~PySide6.QtWidgets.QApplication` 启动后调一次
    ``app.setStyleSheet(stylesheet())``，所有顶级窗口与对话框共享同一份解析结果。
    """
    return _QSS


_QSS = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
}}

/* 左侧大模块 Tab —— 配合 base.gui.shell._HorizontalTabBar 水平绘制文字 */
/* Qt QSS 的位置 pseudo-state 关键字是 :left/:right/:top/:bottom（非 :west/:east） */
QTabBar::tab:left {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 10px 14px;
    margin: 2px 0;
    border: none;
    border-left: 3px solid transparent;
    min-width: 96px;
    min-height: 32px;
}}
QTabBar::tab:left:hover {{
    background: {BG_HOVER};
    color: {TEXT};
}}
QTabBar::tab:left:selected {{
    background: {BG_RAISED};
    color: {PRIMARY};
    border-left: 3px solid {PRIMARY};
}}

/* 子 Tab（顶部 horizontal） */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {BG_RAISED};
    top: -1px;
}}
QTabBar::tab:top {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 7px 14px;
    margin-right: 4px;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;   /* 留位给 selected 的下划线，避免错位 */
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 64px;
}}
QTabBar::tab:top:hover {{
    background: {BG_HOVER};
    color: {TEXT};
}}
QTabBar::tab:top:selected {{
    background: {BG_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-bottom: 2px solid {PRIMARY};
    font-weight: 600;
}}

QPushButton {{
    background: {BG_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 22px;
}}
QPushButton:hover   {{ background: {BG_BUTTON_HOVER}; border-color: {BORDER_STRONG}; }}
QPushButton:pressed {{ background: {BG_PRESSED}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background: {BG}; border-color: {BORDER_SOFT}; }}
QPushButton[primary="true"] {{
    background: {PRIMARY};
    color: {ON_PRIMARY};
    border-color: {PRIMARY_HOVER};
}}
QPushButton[primary="true"]:hover   {{ background: {PRIMARY_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background: {PRIMARY_ACTIVE}; }}
QPushButton[primary="true"]:disabled {{
    background: {PRIMARY_DISABLED}; color: {TEXT_DIM}; border-color: {PRIMARY_DISABLED};
}}
QPushButton[accent="true"] {{
    background: {ACCENT};
    color: {ON_PRIMARY};
    border-color: {ACCENT_HOVER};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover   {{ background: {ACCENT_HOVER}; }}
QPushButton[accent="true"]:pressed {{ background: {ACCENT_ACTIVE}; }}
QPushButton[accent="true"]:disabled {{
    background: {ACCENT_DISABLED}; color: {TEXT_DIM}; border-color: {ACCENT_DISABLED};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 3px 8px;
    selection-background-color: {PRIMARY};
    selection-color: {ON_PRIMARY};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {PRIMARY};
}}

QPlainTextEdit {{
    background: {BG_SUBTLE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: {PRIMARY};
    selection-color: {ON_PRIMARY};
}}
/* LogView 专用：略凹于 BG_RAISED 的"代码块"背景 */
QPlainTextEdit#LogView {{
    background: {BG_LOG};
}}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    margin-left: 8px;
    color: {TEXT_MUTED};
    font-weight: 600;
    /* 与 GroupBox 实际背景（继承自父 QWidget 的 BG）同色，让 title 文字遮住
       下方边框线又无色差。BG_RAISED 是 pane 自身的色，但子 GroupBox 仍以 BG
       作底，用 BG_RAISED 会反而显得突兀。 */
    background: {BG};
}}

/* 次要文本 label：setProperty('muted', True) */
QLabel[muted="true"] {{ color: {TEXT_MUTED}; }}

QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    background: {BG_RAISED};
    border: 1px solid {BORDER_STRONG};
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator    {{ border-radius: 3px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {PRIMARY};
}}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5,
        stop:0 {PRIMARY}, stop:0.45 {PRIMARY},
        stop:0.55 {BG_RAISED}, stop:1 {BG_RAISED});
    border-color: {PRIMARY};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {BORDER};
    background: {BG};
}}

QSplitter::handle:vertical   {{ background: {BORDER}; height: 1px; }}
QSplitter::handle:horizontal {{ background: {BORDER}; width: 1px; }}
QSplitter::handle:hover      {{ background: {PRIMARY}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {SCROLLBAR}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {SCROLLBAR_HOVER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {SCROLLBAR}; border-radius: 5px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {SCROLLBAR_HOVER}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QToolTip {{
    background: {TOOLTIP_BG};
    color: {TOOLTIP_FG};
    border: 1px solid {BORDER};
    padding: 4px 8px;
}}

/* 日志面板 + IDE 风格底部状态栏：左边框延续上方 QTabWidget pane 的左边竖线，
   让侧边栏与右侧详情页的分割线一路贯穿整高（避免到 LogView 就断掉） */
QWidget#LogPanel {{
    border-left: 1px solid {BORDER};
}}
QWidget#StatusBar {{
    background: {BG_SUBTLE};
    border-top: 1px solid {BORDER};
    border-left: 1px solid {BORDER};
}}
"""
