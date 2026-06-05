"""artifact-toolkit GUI 模块（被 :class:`~base.gui.shell.Shell` 装载）。

布局::

    ArtifactModule (QWidget)
    └── QVBoxLayout
        ├── QSplitter (Vertical)
        │   ├── QTabWidget       — classify 子 Tab（tabBarAutoHide）
        │   └── log_panel        — QStackedWidget + 日志按钮列
        └── status_bar           — IDE 风格底栏（workdirs / 别名摘要，悬浮显示完整路径）

未来扩展业务直接 ``addTab`` 即可，与 manga 对称。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QSplitter, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from base.gui import make_btn_col
from base.gui.config import get_config
from base.gui.log_view import LogView
from module.artifact.gui.tabs.classify_tab import ClassifyTab


class ArtifactModule(QWidget):
    """artifact-toolkit 业务模块：装载 classify 子 Tab + 独立日志栈。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._classify_tab = ClassifyTab()
        self._tab_list = [self._classify_tab]

        self._tabs = QTabWidget()
        self._tabs.setTabBarAutoHide(True)   # 单 Tab 时隐藏 tab bar
        self._tabs.addTab(self._classify_tab, 'classify')

        self._log_stack = QStackedWidget()
        self._logs: list[LogView] = []
        for tab in self._tab_list:
            log = LogView()
            tab._sink.text_written.connect(log.append_text)
            self._log_stack.addWidget(log)
            self._logs.append(log)

        self._tabs.currentChanged.connect(self._log_stack.setCurrentIndex)

        export_btn = QPushButton('导出日志')
        export_btn.setToolTip('将当前日志保存为 .txt')
        export_btn.clicked.connect(self._export_current_log)
        clear_btn = QPushButton('清空日志')
        clear_btn.setToolTip('清空日志')
        clear_btn.clicked.connect(self._clear_current_log)

        # LogView 没 GroupBox 包裹，按钮列顶部不留 GroupBox 偏移
        log_btn_wrap = make_btn_col([export_btn, clear_btn], top_margin=0)

        # 横向 margins / spacing 与 ClassifyTab 内容一致，让 LogView 宽度对齐
        # 拖入区、按钮列右边界对齐 Tab 内按钮列。
        # objectName=LogPanel：QSS 添加 border-left 延续 QTabWidget pane 的左竖线
        log_panel = QWidget()
        log_panel.setObjectName('LogPanel')
        lh = QHBoxLayout(log_panel)
        lh.setContentsMargins(10, 0, 10, 0)
        lh.setSpacing(8)
        lh.addWidget(self._log_stack, 1)
        lh.addWidget(log_btn_wrap)

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.addWidget(self._tabs)
        self._splitter.addWidget(log_panel)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([280, 520])
        # 拖动后立即落盘，让 manga / artifact 切换时能即时同步
        self._splitter.splitterMoved.connect(self._save_splitter)

        # ── 底部状态栏（IDE 风格）─────────────────────────────────────
        self._status_label = QLabel(self._classify_tab.status_text())
        self._status_label.setProperty('muted', True)
        self._status_label.setToolTip(self._classify_tab.status_tooltip())
        self._classify_tab.status_changed.connect(self._on_status_changed)
        status_bar = QWidget()
        status_bar.setObjectName('StatusBar')
        sb_lay = QHBoxLayout(status_bar)
        sb_lay.setContentsMargins(10, 3, 10, 3)
        sb_lay.addWidget(self._status_label)
        sb_lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._splitter, 1)
        outer.addWidget(status_bar)

        self._restore_splitter()

    # ── shell 集成点 ──────────────────────────────────────────────────
    def default_sink(self):
        return self._tab_list[0]._sink

    # ── 状态栏 ────────────────────────────────────────────────────────
    def _on_status_changed(self, text: str) -> None:
        self._status_label.setText(text)
        self._status_label.setToolTip(self._classify_tab.status_tooltip())

    # ── 日志操作 ──────────────────────────────────────────────────────
    def _clear_current_log(self) -> None:
        self._logs[self._tabs.currentIndex()].clear_log()

    def _export_current_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, '导出日志', 'artifact-toolkit.log',
            'Text files (*.txt *.log);;All files (*)',
        )
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self._logs[self._tabs.currentIndex()].toPlainText())

    # ── splitter 持久化 ──────────────────────────────────────────────
    # 使用全局 key ``module.splitter``，与 :class:`~module.manga.gui.module.MangaModule`
    # 共享；切换大模块时 :meth:`showEvent` 重新拉取最新值，保持视觉一致
    def _restore_splitter(self) -> None:
        sizes = get_config().get('module.splitter')
        if sizes:
            self._splitter.setSizes(sizes)

    def _save_splitter(self, *_) -> None:
        get_config().set('module.splitter', self._splitter.sizes())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._restore_splitter()

    def save_state(self) -> None:
        self._save_splitter()
