"""
main_window.py — ft GUI 主窗口

布局
----
QMainWindow
└── QSplitter (Vertical)
    ├── 上半：操作区（顶部按钮 + WorkDirs 摘要 + DropArea）
    └── 下半：LogView（base.gui.log_view，接收 QtSink 文本流）

业务流
------
启动:  load_config → 显示 WorkDirs → scan_aliases（后台或同步均可，
       本场景 IO 量小不阻塞主线程；用同步实现 + 状态栏文字提示）
拖入:  paths_dropped(list[Path]) → 逐个 _process_one
单文件交互: 0/1/N 候选 → CandidateDialog；0 候选场景 prompt 区别于 N 候选
按钮:  刷新别名 / 清空日志 / 导出日志

阶段 D 会把主体重构为 ModuleWidget 被 shell 装载；当前先 QMainWindow 独立运行。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from base.console import emit, error, set_output, warn
from base.gui.log_view import LogView
from base.gui.qt_sink import QtSink
from ft.gui.widgets.candidate_dialog import ask_candidate
from ft.gui.widgets.drop_area import DropArea
from ft.workflow.classify.alias import scan_aliases
from ft.workflow.classify.config import Config, load_config
from ft.workflow.classify.matcher import find_candidates
from ft.workflow.classify.ops import classify_one
from ft.workflow.classify.path import path_to_author_name


def _reporter(level: str, msg: str) -> None:
    """适配 base.fs.Reporter → base.console（自动走 QtSink 路由到 LogView）。"""
    {'info': emit, 'warn': warn, 'error': error}.get(level, emit)(msg)


class MainWindow(QMainWindow):
    """file-toolkit GUI 主窗口（当前仅 classify 业务，未来可扩展）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle('file-toolkit  —  classify')
        self.resize(900, 700)

        self._sink = QtSink()
        set_output(self._sink)

        self._cfg: Config | None = None
        self._workdirs_paths: list[Path] = []
        self._alias_map: dict[str, Path] = {}

        self._build_ui()

        # 启动时加载配置；失败弹错并禁用拖入区
        self._load_and_scan()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # 顶部按钮行
        self._refresh_btn = QPushButton('🔄 刷新别名')
        self._refresh_btn.setToolTip('重新扫描所有 WorkDir 下的 [别名]：*.txt')
        self._refresh_btn.clicked.connect(self._on_refresh)

        clear_btn = QPushButton('🧹 清空日志')
        clear_btn.clicked.connect(lambda: self._log.clear_log())

        export_btn = QPushButton('💾 导出日志')
        export_btn.clicked.connect(self._on_export_log)

        btn_lay = QHBoxLayout()
        btn_lay.addWidget(self._refresh_btn)
        btn_lay.addWidget(clear_btn)
        btn_lay.addWidget(export_btn)
        btn_lay.addStretch(1)

        # WorkDirs 摘要
        self._workdirs_label = QLabel('（配置加载中...）')
        self._workdirs_label.setStyleSheet('color: #8a9097;')
        self._workdirs_label.setWordWrap(True)

        # 拖入区
        self._drop = DropArea()
        self._drop.paths_dropped.connect(self._on_paths_dropped)

        upper = QWidget()
        upper_lay = QVBoxLayout(upper)
        upper_lay.addLayout(btn_lay)
        upper_lay.addWidget(self._workdirs_label)
        upper_lay.addWidget(self._drop, 1)

        # 日志
        self._log = LogView()
        self._sink.text_written.connect(self._log.append_text)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(upper)
        splitter.addWidget(self._log)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 420])

        self.setCentralWidget(splitter)

        # Ctrl+L 清日志（与 mt 的 GUI 一致）
        clear_action = QAction(self)
        clear_action.setShortcut('Ctrl+L')
        clear_action.triggered.connect(lambda: self._log.clear_log())
        self.addAction(clear_action)

    # ── 启动加载 ─────────────────────────────────────────────────────
    def _load_and_scan(self) -> None:
        try:
            self._cfg = load_config()
        except FileNotFoundError as e:
            QMessageBox.critical(self, '配置缺失', str(e))
            self._workdirs_label.setText('❌ 未加载配置；拖入将无效')
            self._drop.setEnabled(False)
            self._refresh_btn.setEnabled(False)
            return
        if not self._cfg.workdirs:
            QMessageBox.critical(self, '配置无效', '配置中 ft.workdirs 为空')
            self._drop.setEnabled(False)
            return

        self._workdirs_paths = [wd.path for wd in self._cfg.workdirs]
        self._refresh_workdirs_label()
        self._do_scan_aliases()

    def _refresh_workdirs_label(self) -> None:
        lines = '\n'.join(f'  • {wd.path}' for wd in self._cfg.workdirs)
        self._workdirs_label.setText(f'📁 WorkDirs ({len(self._cfg.workdirs)}):\n{lines}')

    def _do_scan_aliases(self) -> None:
        self._alias_map = scan_aliases(self._workdirs_paths, reporter=_reporter)

    # ── 业务回调 ─────────────────────────────────────────────────────
    def _on_refresh(self) -> None:
        if self._cfg is None:
            return
        self._do_scan_aliases()

    def _on_export_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, '导出日志', 'file-toolkit.log',
            'Text files (*.txt *.log);;All files (*)',
        )
        if not path:
            return
        Path(path).write_text(self._log.toPlainText(), encoding='utf-8')

    def _on_paths_dropped(self, paths: list[Path]) -> None:
        if self._cfg is None:
            return
        if len(paths) > 1:
            emit(f'📦 本次共 {len(paths)} 个，逐一处理')
        for p in paths:
            self._process_one(p)

    def _process_one(self, src: Path) -> None:
        emit(f'\n📂 处理: {src}')
        author_name = path_to_author_name(src)
        emit(f'👤 作者: {author_name}')

        candidates = find_candidates(
            author_name, self._workdirs_paths, self._alias_map,
        )

        if len(candidates) == 1:
            target = candidates[0]
            emit(f'✅ 唯一候选: {target}')
        elif len(candidates) > 1:
            target = ask_candidate(
                title='选择目标作者目录',
                prompt=f'"{author_name}" 找到 {len(candidates)} 个候选：',
                candidates=candidates,
                parent=self,
            )
            if target is None:
                warn('已跳过')
                return
        else:
            workdir_paths = [wd.path for wd in self._cfg.workdirs]
            chosen = ask_candidate(
                title='选择创建位置',
                prompt=f'未找到 "{author_name}" 的已有作者目录，请选择 WorkDir：',
                candidates=workdir_paths,
                parent=self,
            )
            if chosen is None:
                warn('已跳过')
                return
            target = chosen / author_name

        classify_one(
            src=src,
            dst=target,
            workdir=self._cfg.find_workdir(target),
            author_name=author_name,
            open_target=True,
            reporter=_reporter,
        )
