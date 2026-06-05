"""跨业务通用的 Qt 部件与基础设施。

子模块按需懒导入（避免未装 PySide6 时 :mod:`base` 包整体不可用）；
本子包内的所有模块都依赖 PySide6，仅在 GUI 路径下被引用。
"""

#: 所有「内容区右侧按钮列」（输入 / 选项 / 树面板 / 日志）共用宽度，使各内容区
#: 右边界对齐到同一 x。按钮单列排列，宽度约 80 px。
BUTTON_COL_WIDTH = 80

#: GroupBox 内容区相对 box 顶部的偏移（QSS：``margin-top: 12px``
#: + ``padding-top: 6px``）。按钮列容器顶部留出同样的高度，使按钮顶部
#: 与同行 GroupBox 内容顶部对齐。
GROUPBOX_CONTENT_TOP = 18


def make_btn_col(btns, *, top_margin: int = GROUPBOX_CONTENT_TOP):
    """把若干按钮排成单列；外裹固定宽度 :data:`BUTTON_COL_WIDTH` 的
    :class:`~PySide6.QtWidgets.QWidget`，便于让每行内容区右边界对齐到同一 x。

    :param btns: 按钮序列；从上到下依次排列。
    :param top_margin: 列容器顶部留白；默认 :data:`GROUPBOX_CONTENT_TOP`，
        让按钮顶部与同行 :class:`QGroupBox` 内容顶部齐平。同行内容不带 box
        框（如 LogView）时传 ``0``。
    """
    # 按需 import：避免未装 PySide6 时 `import base.gui` 整体失败
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    wrap = QWidget()
    wrap.setFixedWidth(BUTTON_COL_WIDTH)
    col = QVBoxLayout(wrap)
    col.setContentsMargins(0, top_margin, 0, 0)
    col.setSpacing(4)
    for b in btns:
        b.setStyleSheet('QPushButton { padding: 2px 4px; }')
        b.setFixedWidth(BUTTON_COL_WIDTH)
        col.addWidget(b)
    col.addStretch(1)
    return wrap
