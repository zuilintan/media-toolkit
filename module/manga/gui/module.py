"""manga-toolkit GUI 模块（被 :class:`base.gui.shell.Shell` 装载）。

布局::

    MangaModule (QWidget)
    └── QVBoxLayout
        ├── QSplitter (Vertical)
        │   ├── QTabWidget       — 打包 / 命名 / 封面 / 元数据 四个子 Tab
        │   └── log_panel        — QStackedWidget + 日志按钮列
        └── status_bar           — IDE 风格底栏（左侧主状态 + 预留可扩展位）

注意:

- 窗口标题 / 几何由 ``Shell`` 持有；本模块只管 splitter 状态持久化
- 业务快捷键（Enter / Ctrl+Enter / Ctrl+L）用 ``WidgetWithChildrenShortcut`` 上下文，
  避免多模块共存时跨模块触发
- 各 Tab 的状态文本走 :attr:`BaseTab.status_changed` 推到底栏，切 Tab 时同步当前
  Tab 的最近状态
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from base.gui import make_btn_col
from base.gui.config import get_config
from base.gui.log_view import LogView
from module.manga.gui.tabs.make_cover_tab import MakeCoverTab
from module.manga.gui.tabs.make_meta_tab import MakeMetaTab
from module.manga.gui.tabs.pack_pic_tab import PackPicTab
from module.manga.gui.tabs.std_title_tab import StdTitleTab


class MangaModule(QWidget):
    """业务模块：4 个子命令 Tab + 独立日志栈。"""

    busy_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._busy_count = 0

        tab0 = PackPicTab()
        tab1 = StdTitleTab()
        tab2 = MakeCoverTab()
        tab3 = MakeMetaTab()
        self._tab_list = [tab0, tab1, tab2, tab3]
        for tab in self._tab_list:
            tab.busy_changed.connect(self._on_tab_busy)
            tab.status_changed.connect(
                lambda text, t=tab: self._on_tab_status(t, text)
            )

        self._tabs = QTabWidget()
        self._tabs.addTab(tab0, '1. 打包')
        self._tabs.addTab(tab1, '2. 命名')
        self._tabs.addTab(tab2, '3. 封面')
        self._tabs.addTab(tab3, '4. 元数据')

        self._log_stack = QStackedWidget()
        self._logs: list[LogView] = []
        for tab in self._tab_list:
            log = LogView()
            tab._sink.text_written.connect(log.append_text)
            self._log_stack.addWidget(log)
            self._logs.append(log)

        self._tabs.currentChanged.connect(self._log_stack.setCurrentIndex)
        self._tabs.currentChanged.connect(self._sync_status_to_current)

        export_btn = QPushButton('导出日志')
        export_btn.setToolTip('将当前日志保存为 .txt')
        export_btn.clicked.connect(self._export_current_log)
        clear_btn = QPushButton('清空日志')
        clear_btn.setToolTip('清空日志 [Ctrl+L]')
        clear_btn.clicked.connect(self._clear_current_log)

        # LogView 没 GroupBox 包裹，按钮列顶部不留 GroupBox 偏移
        log_btn_wrap = make_btn_col([export_btn, clear_btn], top_margin=0)

        # 横向 margins 与 BaseTab 内容一致（root_lay 用 10），让 LogView 宽度对齐
        # 输入框 / 选项框 / 预览框，按钮列右边界对齐 Tab 内按钮列。
        # objectName=LogPanel：QSS 添加 border-left 延续 QTabWidget pane 的左竖线
        log_panel = QWidget()
        log_panel.setObjectName('LogPanel')
        lh = QHBoxLayout(log_panel)
        lh.setContentsMargins(10, 0, 10, 0)
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
        # 左侧主状态文本；右侧用 stretch 撑住，后续可在右边 addWidget 追加
        # 更多字段（进度、模式、cwd 等）
        self._status_label = QLabel(self._tab_list[0].status_text())
        self._status_label.setProperty('muted', True)
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
        self._install_shortcuts()

    # ── shell 集成点 ──────────────────────────────────────────────────
    def default_sink(self):
        """供 ``Shell`` 在首次注册时调 :func:`base.console.set_output` 的初始 sink。"""
        return self._tab_list[0]._sink

    # ── 状态 ──────────────────────────────────────────────────────────
    def _on_tab_busy(self, busy: bool) -> None:
        self._busy_count += 1 if busy else -1
        self.busy_changed.emit(self._busy_count > 0)

    def _on_tab_status(self, tab, text: str) -> None:
        """仅当 ``tab`` 是当前选中 Tab 时把文本推到底栏——避免后台 Tab 的状态
        在用户切到别的 Tab 后还覆盖底栏。"""
        if self._tab_list[self._tabs.currentIndex()] is tab:
            self._status_label.setText(text)

    def _sync_status_to_current(self, idx: int) -> None:
        """切 Tab 后把底栏文本同步成新当前 Tab 的最近状态。"""
        self._status_label.setText(self._tab_list[idx].status_text())

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
        """Enter / Ctrl+Enter / Ctrl+L —— 限定 ``WidgetWithChildrenShortcut`` 上下文。"""
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
    # 使用全局 key ``module.splitter``，与
    # :class:`~module.artifact.gui.module.ArtifactModule` 共享；
    # 切换大模块时 :meth:`showEvent` 重新拉取最新值，保持视觉一致
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
        """由 ``Shell`` 在 ``closeEvent`` 调用（也可由子类显式触发）。"""
        self._save_splitter()
