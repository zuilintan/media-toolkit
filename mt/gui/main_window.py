"""
main_window.py — 主窗口：上方 QTabWidget，下方每 Tab 独立日志面板

布局
----
QSplitter (Vertical)
├── QTabWidget       — sourcefile / metadata / cover 三个 Tab
└── log_panel        — QStackedWidget：每个 Tab 各有一个 LogView

每个 Tab 持有自己的 QtSink（BaseTab._sink）；Tab 上的用户操作（扫描/写入）
在启动前调用 set_output(self._sink)，将后续 emit() 路由到该 Tab 的日志。
切换 Tab 时只切换可见 LogView，不切换 set_output，正在运行的 worker
依旧写入发起它的那个 Tab 的日志。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QMainWindow, QPushButton, QSplitter, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from mt import __version__
from mt.gui.tabs.cover_tab import CoverTab
from mt.gui.tabs.metadata_tab import MetadataTab
from mt.gui.tabs.sourcefile_tab import SourcefileTab
from mt.gui.widgets.log_view import LogView
from mt.infra.console import set_output


class MainWindow(QMainWindow):
    """manga-toolkit GUI 主窗口。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f'manga-toolkit  —  {__version__}')
        self.resize(1100, 800)

        # ── Tab ──────────────────────────────────────────────────────
        tab0 = SourcefileTab()
        tab1 = MetadataTab()
        tab2 = CoverTab()
        self._tab_list = [tab0, tab1, tab2]

        self._tabs = QTabWidget()
        self._tabs.addTab(tab0, 'sourcefile')
        self._tabs.addTab(tab1, 'metadata')
        self._tabs.addTab(tab2, 'cover')

        # ── 每 Tab 独立 LogView，叠放在 QStackedWidget ────────────────
        self._log_stack = QStackedWidget()
        self._logs: list[LogView] = []
        for tab in self._tab_list:
            log = LogView()
            tab._sink.text_written.connect(log.append_text)
            self._log_stack.addWidget(log)
            self._logs.append(log)

        # Tab 切换 → 切换可见 LogView
        self._tabs.currentChanged.connect(self._log_stack.setCurrentIndex)

        # 初始输出路由到第一个 Tab
        set_output(tab0._sink)

        # ── 日志头：清空按钮 ──────────────────────────────────────────
        log_header = QWidget()
        hh = QHBoxLayout(log_header)
        hh.setContentsMargins(0, 0, 0, 0)
        clear_btn = QPushButton('清空日志')
        clear_btn.clicked.connect(self._clear_current_log)
        hh.addStretch(1)
        hh.addWidget(clear_btn)

        log_panel = QWidget()
        lv = QVBoxLayout(log_panel)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(log_header)
        lv.addWidget(self._log_stack, 1)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._tabs)
        splitter.addWidget(log_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 520])

        self.setCentralWidget(splitter)

    def _clear_current_log(self) -> None:
        self._logs[self._tabs.currentIndex()].clear_log()
