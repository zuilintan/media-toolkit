"""
main_window.py — 主窗口：上方 QTabWidget，下方共享日志面板

布局
----
QSplitter (Vertical)
├── QTabWidget    — sourcefile / metadata / cover 三个 Tab
└── LogView       — 三个 Tab 共享的日志输出（接收 QtSink）

QtSink 在 app.py 全局安装到 mt.infra.console.set_output；
LogView.append_text 在主线程接收 text_written 信号（Qt 自动跨线程派发）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QMainWindow, QPushButton, QSplitter, QTabWidget, QVBoxLayout,
    QWidget,
)

from mt import __version__
from mt.gui.qt_sink import QtSink
from mt.gui.tabs.cover_tab import CoverTab
from mt.gui.tabs.metadata_tab import MetadataTab
from mt.gui.tabs.sourcefile_tab import SourcefileTab
from mt.gui.widgets.log_view import LogView


class MainWindow(QMainWindow):
    """manga-toolkit GUI 主窗口。"""

    def __init__(self, sink: QtSink, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f'manga-toolkit  —  {__version__}')
        self.resize(1100, 800)

        # ── 中央：上 Tab / 下 Log，可拖动 splitter ───────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(SourcefileTab(), 'sourcefile')
        self._tabs.addTab(MetadataTab(),   'metadata')
        self._tabs.addTab(CoverTab(),      'cover')

        self._log = LogView()
        # QtSink 在 app.py 安装；信号在这里连接，方便 LogView 与 sink 解耦
        sink.text_written.connect(self._log.append_text)

        # 日志区头：清空按钮（不放工具栏，保持简洁）
        log_header = QWidget()
        hh = QHBoxLayout(log_header)
        hh.setContentsMargins(0, 0, 0, 0)
        clear_btn = QPushButton('清空日志')
        clear_btn.clicked.connect(self._log.clear_log)
        hh.addStretch(1)
        hh.addWidget(clear_btn)

        log_panel = QWidget()
        lv = QVBoxLayout(log_panel)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(log_header)
        lv.addWidget(self._log, 1)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._tabs)
        splitter.addWidget(log_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 520])

        self.setCentralWidget(splitter)
