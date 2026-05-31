"""
module.py — manga-toolkit GUI 模块（被 base.gui.shell 装载）

布局
----
MangaModule (QWidget)
└── QSplitter (Vertical)
    ├── QTabWidget       — pack / name / cover / meta 四个子 Tab
    └── log_panel        — QStackedWidget：每子 Tab 各有一个 LogView

注意:
  - 窗口标题/几何由 shell 持有；本模块只管 splitter 状态持久化
  - 业务键盘快捷键 (Enter/Ctrl+Enter/Ctrl+L) 用 WidgetWithChildrenShortcut
    上下文，避免多模块共存时跨模块触发
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox, QFileDialog, QHBoxLayout, QLineEdit, QPushButton,
    QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from base.console import set_output
from base.gui.config import get_config
from base.gui.log_view import LogView
from manga.gui.tabs.cover_tab import CoverTab
from manga.gui.tabs.metadata_tab import MetadataTab
from manga.gui.tabs.pack_tab import PackTab
from manga.gui.tabs.sourcefile_tab import SourcefileTab


class MangaModule(QWidget):
    """manga-toolkit 业务模块：装载 4 个子 Tab + 独立日志栈。"""

    busy_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._busy_count = 0

        tab0 = PackTab()
        tab1 = SourcefileTab()
        tab2 = CoverTab()
        tab3 = MetadataTab()
        self._tab_list = [tab0, tab1, tab2, tab3]
        for tab in self._tab_list:
            tab.busy_changed.connect(self._on_tab_busy)

        self._tabs = QTabWidget()
        self._tabs.addTab(tab0, '1. pack')
        self._tabs.addTab(tab1, '2. name')
        self._tabs.addTab(tab2, '3. cover')
        self._tabs.addTab(tab3, '4. meta')

        self._log_stack = QStackedWidget()
        self._logs: list[LogView] = []
        for tab in self._tab_list:
            log = LogView()
            tab._sink.text_written.connect(log.append_text)
            self._log_stack.addWidget(log)
            self._logs.append(log)

        self._tabs.currentChanged.connect(self._log_stack.setCurrentIndex)

        log_header = QWidget()
        hh = QHBoxLayout(log_header)
        hh.setContentsMargins(0, 0, 0, 0)
        export_btn = QPushButton('导出日志')
        export_btn.setToolTip('将当前日志保存为 .txt')
        export_btn.clicked.connect(self._export_current_log)
        clear_btn = QPushButton('清空日志')
        clear_btn.setToolTip('清空日志 [Ctrl+L]')
        clear_btn.clicked.connect(self._clear_current_log)
        hh.addStretch(1)
        hh.addWidget(export_btn)
        hh.addWidget(clear_btn)

        log_panel = QWidget()
        lv = QVBoxLayout(log_panel)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(log_header)
        lv.addWidget(self._log_stack, 1)

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.addWidget(self._tabs)
        self._splitter.addWidget(log_panel)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([280, 520])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._splitter)

        self._restore_splitter()
        self._install_shortcuts()

    # ── shell 集成点 ──────────────────────────────────────────────────
    def default_sink(self):
        """供 shell 在首次注册时调 set_output 用的初始 sink。"""
        return self._tab_list[0]._sink

    # ── 状态 ──────────────────────────────────────────────────────────
    def _on_tab_busy(self, busy: bool) -> None:
        self._busy_count += 1 if busy else -1
        self.busy_changed.emit(self._busy_count > 0)

    def _clear_current_log(self) -> None:
        self._logs[self._tabs.currentIndex()].clear_log()

    def _export_current_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, '导出日志', 'manga-toolkit.log',
            'Text files (*.txt *.log);;All files (*)',
        )
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self._logs[self._tabs.currentIndex()].toPlainText())

    # ── 快捷键 ────────────────────────────────────────────────────────
    def _install_shortcuts(self) -> None:
        """Enter / Ctrl+Enter / Ctrl+L —— 限定 module 内（含子）。"""
        def _add(seq: str, cb) -> None:
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(cb)
            self.addAction(act)

        _add('Return', self._on_enter)
        _add('Ctrl+Return', self._on_ctrl_enter)
        _add('Enter', self._on_enter)
        _add('Ctrl+Enter', self._on_ctrl_enter)
        _add('Ctrl+L', self._clear_current_log)

    def _on_enter(self) -> None:
        focused = self.focusWidget()
        if isinstance(focused, (QLineEdit, QAbstractSpinBox)):
            return
        tab = self._tab_list[self._tabs.currentIndex()]
        if tab._scan_btn.isEnabled():
            tab._scan_btn.click()

    def _on_ctrl_enter(self) -> None:
        tab = self._tab_list[self._tabs.currentIndex()]
        if tab._apply_btn.isEnabled():
            tab._apply_btn.click()

    # ── splitter 状态持久化 ──────────────────────────────────────────
    def _restore_splitter(self) -> None:
        sizes = get_config().get('manga.splitter')
        if sizes:
            self._splitter.setSizes(sizes)

    def save_state(self) -> None:
        """由 shell 在 closeEvent 调用（也可由子类显式触发）。"""
        get_config().set('manga.splitter', self._splitter.sizes())
