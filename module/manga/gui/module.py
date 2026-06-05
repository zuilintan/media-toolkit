"""manga-toolkit GUI 模块（被 :class:`base.gui.shell.Shell` 装载）。

布局::

    MangaModule (QWidget)
    └── QVBoxLayout
        ├── library_row          — 漫画库根目录 (全模块共享) + 重建索引按钮
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
- 漫画库根目录是 module 级全局状态（持久化 key ``manga.library_root``）：
  std_title Tab 在 scan 阶段会读它做作者规范化（详见
  :mod:`module.manga.workflow.author_library`）；其它 Tab 暂未消费但保留扩展
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from base.console import emit, set_output
from base.gui import apply_col_btn_style, make_btn_col
from base.gui.config import get_config
from base.gui.log_view import LogView
from base.gui.path_picker import PathPicker
from module.manga.gui.tabs.make_cover_tab import MakeCoverTab
from module.manga.gui.tabs.make_meta_tab import MakeMetaTab
from module.manga.gui.tabs.pack_pic_tab import PackPicTab
from module.manga.gui.tabs.std_title_tab import StdTitleTab
from module.manga.workflow.author_library import scan_library


class MangaModule(QWidget):
    """业务模块：4 个子命令 Tab + 独立日志栈。"""

    busy_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._busy_count = 0
        # 自动化管线状态：running 期间禁掉按钮 / 禁切 Tab 由各 Tab 自身的
        # busy 控制；编排器只需记一个 flag 防止重入
        self._auto_running: bool = False

        # ── 漫画库根目录（module 级全局，先建好供 std_title Tab 绑回调） ──
        self._migrate_legacy_library_history()
        self._library_picker = PathPicker(
            '漫画库根目录:',
            '可选：留空跳过；指定后扫一级子目录建作者索引',
            history_key='manga.library_root',
        )
        self._library_picker.setToolTip(
            '指向 {root}/{作者}/ 组织的漫画库根。\n'
            'std_title Tab 推导作者后会按简繁归一对齐到库里既有主名 / 别名 '
            '([别名]：xxx.txt)，命中即归入库主名目录。\n'
            '留空则跳过规范化（保留旧行为，可能出现简繁两份同名作者目录）。'
        )
        self._rebuild_btn = QPushButton('重建索引')
        self._rebuild_btn.setToolTip('强制重新扫描漫画库（默认懒加载已落盘的 cache）')
        self._rebuild_btn.clicked.connect(self._on_rebuild_library)
        # 顶部库工具条按钮与各 Tab 内按钮列右边界对齐（含 ⚡ 自动化角部按钮）
        for btn in (self._library_picker.browse_btn, self._rebuild_btn):
            apply_col_btn_style(btn)

        tab0 = PackPicTab()
        tab1 = StdTitleTab()
        tab1.set_library_root_getter(self._library_picker.path)
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

        # ── 「一键自动化」按钮（贴齐 tab 栏右端，靠窗口右侧） ────────
        # corner widget 由 QTabWidget 放到 tab bar 同行的右上角，整行天然
        # 与最右一个 tab 共占同一水平带；橙色 accent 属性让按钮与流水线动作
        # （蓝色 primary）有视觉区分
        # accent 已带 font-weight: 600 + 橙色，不再加 emoji 以免在 80px 宽里被裁
        self._auto_btn = QPushButton('自动化')
        self._auto_btn.setToolTip(
            '从当前 Tab 开始顺序执行到末尾，期间不再确认。\n'
            '上一个 Tab 的产物自动作为下一个 Tab 的输入。'
        )
        self._auto_btn.setProperty('accent', True)
        self._auto_btn.clicked.connect(self._on_auto_click)
        apply_col_btn_style(self._auto_btn)
        # 外层 wrapper 提供 10px 右留白，对齐上方 library_row 的右 margin，
        # 让 corner widget 按钮右边界与「重建索引」右边界对齐
        auto_wrap = QWidget()
        auto_layout = QHBoxLayout(auto_wrap)
        auto_layout.setContentsMargins(0, 0, 10, 0)
        auto_layout.addWidget(self._auto_btn)
        self._tabs.setCornerWidget(auto_wrap, Qt.TopRightCorner)

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

        # ── 顶部：漫画库根目录工具条 ──────────────────────────────────
        # 模块级全局：四个 Tab 都能复用，目前仅 std_title 真正消费。横向 margins
        # 与各 Tab 内容对齐（root_lay 用 10），让 picker 左边界与下方一致
        library_row = QWidget()
        lib_lay = QHBoxLayout(library_row)
        lib_lay.setContentsMargins(10, 6, 10, 4)
        lib_lay.addWidget(self._library_picker, 1)
        lib_lay.addWidget(self._rebuild_btn)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(library_row)
        outer.addWidget(self._splitter, 1)
        outer.addWidget(status_bar)

        self._restore_splitter()
        self._install_shortcuts()

    # ── shell 集成点 ──────────────────────────────────────────────────
    def default_sink(self):
        """供 ``Shell`` 在首次注册时调 :func:`base.console.set_output` 的初始 sink。"""
        return self._tab_list[0]._sink

    # ── 漫画库 ────────────────────────────────────────────────────────
    def _migrate_legacy_library_history(self) -> None:
        """老版本把库根目录历史存在 ``std_title.library_root`` 下；module 级提升
        后改用 ``manga.library_root``。首次启动把老历史搬过来（一次性，幂等：
        新 key 已有内容时不动）。
        """
        cfg = get_config()
        if cfg.get_history('manga.library_root'):
            return
        old = cfg.get_history('std_title.library_root')
        if not old:
            return
        for p in reversed(old):
            cfg.push_history('manga.library_root', p)

    def _on_rebuild_library(self) -> None:
        """「重建索引」按钮：把当前 picker 路径交给 :func:`scan_library` 重扫并落盘。

        日志走当前 Tab 的 sink；操作通常毫秒级，同步执行无需开线程。
        """
        root = self._library_picker.path()
        if not root:
            QMessageBox.warning(self, '提示', '请先选择漫画库根目录')
            return
        p = Path(root)
        if not p.is_dir():
            QMessageBox.warning(self, '提示', f'不是有效目录:\n{root}')
            return
        # 日志落到当前 Tab —— 用户能看到扫描进度反馈
        current_tab = self._tab_list[self._tabs.currentIndex()]
        set_output(current_tab._sink)
        emit('')
        lib = scan_library(p)
        QMessageBox.information(
            self, '完成', f'已重建索引：{len(lib)} 个作者',
        )

    # ── 一键自动化编排器 ──────────────────────────────────────────────
    # 用户在哪个 Tab 点击就从哪开始，逐级把 ``auto_done`` 输出注入下一 Tab：
    # PackPic.zip_path → StdTitle 文件输入 → StdTitle 改名后路径 → MakeCover
    # cbz 输入 → MakeMeta cbz 输入。途中任一段 emit 空列表（无产出 / 失败 /
    # 用户取消）即终止管线，按钮恢复可点。
    def _on_auto_click(self) -> None:
        if self._auto_running:
            return
        start = self._tabs.currentIndex()
        tail  = len(self._tab_list) - 1
        if start >= tail:
            QMessageBox.information(
                self, '一键自动化',
                f'当前在末尾 Tab「{self._tabs.tabText(start)}」，无后续步骤可串接。',
            )
            return
        names = ' → '.join(
            self._tabs.tabText(i) for i in range(start, len(self._tab_list))
        )
        ans = QMessageBox.question(
            self, '一键自动化',
            f'即将从「{self._tabs.tabText(start)}」开始顺序执行到末尾：\n\n'
            f'  {names}\n\n'
            '期间不再弹出确认对话框，上一步产物自动作为下一步输入。\n'
            '继续？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
            return
        self._auto_running = True
        self._auto_btn.setEnabled(False)
        self._auto_btn.setText('运行中')
        self._chain_at(start, inputs=None)

    def _chain_at(self, idx: int, *, inputs) -> None:
        """在 ``idx`` Tab 上启动 :meth:`auto_start`；完成时挂一次性回调串下一段。"""
        self._tabs.setCurrentIndex(idx)
        tab = self._tab_list[idx]

        if inputs is not None:
            try:
                tab.auto_set_inputs(inputs)
            except Exception as e:
                QMessageBox.warning(
                    self, '自动化终止',
                    f'第 {idx + 1} 步「{self._tabs.tabText(idx)}」注入输入失败：\n{e}',
                )
                self._auto_pipeline_finish()
                return

        def _on_done(outputs):
            try:
                tab.auto_done.disconnect(_on_done)
            except (RuntimeError, TypeError):
                pass
            next_idx = idx + 1
            if next_idx >= len(self._tab_list):
                self._auto_pipeline_finish()
                return
            # 空产出：起点无上游可沿用直接终止；中段询问是否跳过本步、把上一
            # 步产物 pass-through 给下一步
            if not outputs:
                if inputs is None:
                    self._auto_pipeline_finish()
                    return
                ans = QMessageBox.question(
                    self, '一键自动化',
                    f'「{self._tabs.tabText(idx)}」没有可处理的产物。\n\n'
                    '继续到下一步（沿用上一步产物作为输入）？\n'
                    '否则将终止管线。',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
                )
                if ans != QMessageBox.Yes:
                    self._auto_pipeline_finish()
                    return
                outputs = inputs
            # 上一 Tab 的 thread.quit() 是 async，延后到当前栈展开后再启动下一段
            QTimer.singleShot(0, lambda: self._chain_at(next_idx, inputs=outputs))

        tab.auto_done.connect(_on_done)
        tab.auto_start()

    def _auto_pipeline_finish(self) -> None:
        self._auto_running = False
        self._auto_btn.setEnabled(True)
        self._auto_btn.setText('自动化')

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
