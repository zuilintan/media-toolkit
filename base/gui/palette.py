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

# 文本
TEXT        = '#e6edf3'
TEXT_MUTED  = '#8b949e'         # 状态行 / 次要 label
TEXT_DIM    = '#6e7681'         # 禁用 / 占位
TEXT_LOG    = '#c9d1d9'         # LogView：去除纯白感，缓解长时间阅读疲劳

# 边框 / 分割
BORDER        = '#30363d'
BORDER_STRONG = '#484f58'
BORDER_SOFT   = '#21262d'

# 背景
BG          = '#0d1117'         # 窗口底
BG_RAISED   = '#161b22'         # pane / button / input
BG_SUBTLE   = '#010409'         # drop-area（凹陷感，配 dashed border）
BG_LOG      = '#1a1f29'         # LogView：柔和深灰，配 TEXT_LOG 对比度 ~10.5:1
BG_HOVER    = '#1c2128'
BG_PRESSED  = '#272d36'
BG_BUTTON_HOVER = '#1f242c'

# 滚动条
SCROLLBAR        = '#30363d'
SCROLLBAR_HOVER  = '#484f58'

# Tooltip
TOOLTIP_BG = '#1f242c'
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
/* LogView 专用：柔和深灰背景 + 非纯白文本，对比度 ~10.5:1 */
QPlainTextEdit#LogView {{
    background: {BG_LOG};
    color: {TEXT_LOG};
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
}}

/* 次要文本 label：setProperty('muted', True) */
QLabel[muted="true"] {{ color: {TEXT_MUTED}; }}

QCheckBox, QRadioButton {{ spacing: 6px; }}

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
"""
