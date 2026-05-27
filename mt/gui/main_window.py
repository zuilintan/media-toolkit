"""
main_window.py — 主窗口：上方 QTabWidget，下方每 Tab 独立日志面板

布局
----
QSplitter (Vertical)
├── QTabWidget       — sourcefile / cover / metadata 三个 Tab
└── log_panel        — QStackedWidget：每个 Tab 各有一个 LogView

每个 Tab 持有自己的 QtSink（BaseTab._sink）；Tab 上的用户操作（扫描/写入）
在启动前调用 set_output(self._sink)，将后续 emit() 路由到该 Tab 的日志。
切换 Tab 时只切换可见 LogView，不切换 set_output，正在运行的 worker
依旧写入发起它的那个 Tab 的日志。
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox, QHBoxLayout, QLineEdit, QMainWindow, QPushButton,
    QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from mt import __version__
from mt.gui.gui_config import get_config
from mt.gui.tabs.cover_tab import CoverTab
from mt.gui.tabs.metadata_tab import MetadataTab
from mt.gui.tabs.sourcefile_tab import SourcefileTab
from mt.gui.widgets.log_view import LogView
from mt.infra.console import set_output


class MainWindow(QMainWindow):
    """manga-toolkit GUI 主窗口。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._base_title = f'manga-toolkit  —  {__version__}'
        self.setWindowTitle(self._base_title)
        self.resize(1100, 800)
        self._busy_count = 0

        # ── Tab ──────────────────────────────────────────────────────
        tab0 = SourcefileTab()
        tab1 = CoverTab()
        tab2 = MetadataTab()
        self._tab_list = [tab0, tab1, tab2]
        for tab in self._tab_list:
            tab.busy_changed.connect(self._on_tab_busy)

        self._tabs = QTabWidget()
        self._tabs.addTab(tab0, '1. sourcefile')
        self._tabs.addTab(tab1, '2. cover')
        self._tabs.addTab(tab2, '3. metadata')

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

        # ── 日志头：导出 / 清空 ──────────────────────────────────────
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

        self.setCentralWidget(self._splitter)

        # 恢复窗口几何与 splitter 状态
        cfg = get_config()
        geo = cfg.get('window.geometry')
        if geo:
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
        sizes = cfg.get('window.splitter')
        if sizes:
            self._splitter.setSizes(sizes)

    def _on_tab_busy(self, busy: bool) -> None:
        self._busy_count += 1 if busy else -1
        if self._busy_count > 0:
            self.setWindowTitle(f'[处理中] {self._base_title}')
        else:
            self.setWindowTitle(self._base_title)

    def _clear_current_log(self) -> None:
        self._logs[self._tabs.currentIndex()].clear_log()

    def _export_current_log(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, '导出日志', 'manga-toolkit.log',
            'Text files (*.txt *.log);;All files (*)',
        )
        if not path:
            return
        text = self._logs[self._tabs.currentIndex()].toPlainText()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = self.focusWidget()
            if isinstance(focused, (QLineEdit, QAbstractSpinBox)):
                super().keyPressEvent(event)
                return
            tab = self._tab_list[self._tabs.currentIndex()]
            if event.modifiers() & Qt.ControlModifier:
                if tab._apply_btn.isEnabled():
                    tab._apply_btn.click()
            else:
                if tab._scan_btn.isEnabled():
                    tab._scan_btn.click()
        elif event.key() == Qt.Key_L and event.modifiers() & Qt.ControlModifier:
            self._clear_current_log()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        cfg = get_config()
        cfg.set('window.geometry',
                self.saveGeometry().toBase64().data().decode())
        cfg.set('window.splitter', self._splitter.sizes())
        super().closeEvent(event)
