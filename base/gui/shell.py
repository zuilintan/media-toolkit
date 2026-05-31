"""
shell.py — 跨业务的单窗口宿主

UI 布局
-------
QMainWindow (Shell)
└── QTabWidget (West, tabBarAutoHide)   ← 左侧"大模块"切换
    ├── manga module (任意 QWidget)
    ├── artifact module
    └── ...

使用
----
    shell = Shell(title='media-toolkit', config_key_prefix='shell')
    shell.register_module('manga', MangaModule())
    shell.register_module('files', ArtifactModule())
    shell.show()

关键约定
--------
- 装载的 module 是任意 QWidget；shell 不约束其内部结构
- 仅注册一个 module 时，左侧 tab bar 自动隐藏（UX 等价于"独立 module 窗口"）
- 首次 register 的 module 若提供 ``default_sink`` kwarg，自动调
  ``set_output`` 让初始输出有去处；后续 module 各自管自己的 sink
- 几何/侧栏状态用 base.gui.config 持久化，键名带 ``config_key_prefix``
  避免 manga-only / artifact-only / 双模块场景互相覆盖
"""

from __future__ import annotations
from typing import Any

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from base.console import set_output
from base.gui.config import get_config


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
        self._tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._tabs.setTabBarAutoHide(True)
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

        Args:
            label:        左侧 Tab 标签。
            module:       任意 QWidget；shell 不约束内部结构。
            default_sink: 首个注册的 module 若提供，自动 set_output 让
                          初始输出有归宿。同名后续 module 即使提供也忽略。
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
