"""
module.py — file-toolkit GUI 模块（被 base.gui.shell 装载）

布局
----
FtModule (QWidget)
└── QSplitter (Vertical)
    ├── QTabWidget       — 当前仅 classify 一个子 Tab（tabBarAutoHide）
    └── log_panel        — QStackedWidget：每子 Tab 各有一个 LogView

未来扩展业务（如其他 file 操作）直接 addTab 即可，与 manga 对称。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QPushButton, QSplitter, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from base.gui.config import get_config
from base.gui.log_view import LogView
from artifact.gui.tabs.classify_tab import ClassifyTab


class FtModule(QWidget):
    """file-toolkit 业务模块：装载 classify 子 Tab + 独立日志栈。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        classify_tab = ClassifyTab()
        self._tab_list = [classify_tab]

        self._tabs = QTabWidget()
        self._tabs.setTabBarAutoHide(True)   # 单 Tab 时隐藏 tab bar
        self._tabs.addTab(classify_tab, 'classify')

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
        export_btn.clicked.connect(self._export_current_log)
        clear_btn = QPushButton('清空日志')
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
        self._splitter.setSizes([280, 420])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._splitter)

        self._restore_splitter()

    # ── shell 集成点 ──────────────────────────────────────────────────
    def default_sink(self):
        return self._tab_list[0]._sink

    # ── 日志操作 ──────────────────────────────────────────────────────
    def _clear_current_log(self) -> None:
        self._logs[self._tabs.currentIndex()].clear_log()

    def _export_current_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, '导出日志', 'file-toolkit.log',
            'Text files (*.txt *.log);;All files (*)',
        )
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self._logs[self._tabs.currentIndex()].toPlainText())

    # ── splitter 持久化 ──────────────────────────────────────────────
    def _restore_splitter(self) -> None:
        sizes = get_config().get('artifact.splitter')
        if sizes:
            self._splitter.setSizes(sizes)

    def save_state(self) -> None:
        get_config().set('artifact.splitter', self._splitter.sizes())
