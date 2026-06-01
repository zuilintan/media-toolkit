"""跨业务的单窗口宿主（左侧 vertical Tab 切大模块）。

布局：``QMainWindow(Shell)`` → ``QTabWidget(West, tabBarAutoHide)``，
内部装载若干"大模块" QWidget（manga / artifact / ...）。

用法::

    shell = Shell(title='media-toolkit', config_key_prefix='shell')
    shell.register_module('manga', MangaModule())
    shell.register_module('artifact', ArtifactModule())
    shell.show()

关键约定：

- 装载的 module 是任意 ``QWidget``，shell 不约束其内部结构。
- 仅注册一个 module 时，左侧 tab bar 自动隐藏（UX 等价于"独立 module 窗口"）。
- 首次 :meth:`Shell.register_module` 的 module 若提供 ``default_sink``，自动调
  :func:`~base.console.set_output` 让初始输出有去处；后续 module 各自管自己的 sink。
- 几何/侧栏状态用 :mod:`base.gui.config` 持久化，键名带 ``config_key_prefix``，
  避免 manga-only / artifact-only / 双模块场景互相覆盖。
- 左侧 Tab 使用 :class:`_HorizontalTabBar`，让 West 方向的标签文字保持水平阅读，
  替代 Qt 默认侧着旋转 90° 的样式。
- 全局 QSS 由 :func:`~base.gui.palette.stylesheet` 提供，建议在
  :class:`~PySide6.QtWidgets.QApplication` 构造后一次性 ``setStyleSheet``，本类
  本身不再注入，避免每个 ``Shell`` 实例重新解析。
"""

from __future__ import annotations
from typing import Any

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtWidgets import (
    QMainWindow, QStyle, QStyleOptionTab, QStylePainter,
    QTabBar, QTabWidget, QWidget,
)

from base.console import set_output
from base.gui.config import get_config


class _HorizontalTabBar(QTabBar):
    """West/East 方向也水平绘制文字的 ``QTabBar``。

    Qt 默认实现把 East/West tab 的文字旋转 90°（侧着读），用户体验差。
    本类重写 :meth:`tabSizeHint` 转置尺寸 + :meth:`paintEvent` 自绘
    形状后再以水平方向绘制 text/icon。
    """

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802
        # 所有 tab 取统一最大宽高：避免 QSS 让 selected tab 字体加粗后
        # super() 返回不同宽度，进而引起 tab bar 总宽变化、central widget 平移
        max_w = 0
        max_h = 0
        for i in range(self.count()):
            s = super().tabSizeHint(i)
            s.transpose()
            max_w = max(max_w, s.width())
            max_h = max(max_h, s.height())
        return QSize(max_w, max_h)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QStylePainter(self)
        opt = QStyleOptionTab()
        for i in range(self.count()):
            self.initStyleOption(opt, i)
            painter.drawControl(QStyle.ControlElement.CE_TabBarTabShape, opt)
            painter.drawItemText(
                opt.rect, Qt.AlignmentFlag.AlignCenter,
                self.palette(), self.isTabEnabled(i), opt.text,
            )


class Shell(QMainWindow):
    """单窗口宿主：左侧 vertical Tab 切大模块。"""

    def __init__(
        self,
        *,
        title: str,
        config_key_prefix: str = 'shell',
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._cfg_key = config_key_prefix
        self.setWindowTitle(title)
        self.resize(1100, 800)

        self._tabs = QTabWidget()
        self._tabs.setTabBar(_HorizontalTabBar(self._tabs))
        self._tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._tabs.setTabBarAutoHide(True)
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)

        self._sink_set = False
        self._restore_geometry()

    # ── 注册 ──────────────────────────────────────────────────────────
    def register_module(
        self,
        label: str,
        module: QWidget,
        *,
        default_sink: Any | None = None,
    ) -> None:
        """添加一个大模块 Tab。

        :param label:        左侧 Tab 标签。
        :param module:       任意 ``QWidget``；shell 不约束内部结构。
        :param default_sink: 首个注册的 module 若提供，自动调
                             :func:`~base.console.set_output` 让初始输出有归宿；
                             后续 module 即使提供也忽略。
        """
        self._tabs.addTab(module, label)
        if default_sink is not None and not self._sink_set:
            set_output(default_sink)
            self._sink_set = True

    # ── 窗口几何持久化 ────────────────────────────────────────────────
    def _restore_geometry(self) -> None:
        cfg = get_config()
        geo = cfg.get(f'{self._cfg_key}.geometry')
        if geo:
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))

    def closeEvent(self, event) -> None:
        cfg = get_config()
        cfg.set(f'{self._cfg_key}.geometry',
                self.saveGeometry().toBase64().data().decode())
        # 让每个 module 自己保存内部状态（splitter sizes 等）
        for i in range(self._tabs.count()):
            mod = self._tabs.widget(i)
            if hasattr(mod, 'save_state'):
                mod.save_state()
        super().closeEvent(event)

    # ── 内部访问 ──────────────────────────────────────────────────────
    def current_module(self) -> QWidget | None:
        return self._tabs.currentWidget()
