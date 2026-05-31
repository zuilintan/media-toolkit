"""
classify_tab.py — artifact 的 classify 业务子 Tab

布局
----
ClassifyTab (QWidget)
└── QVBoxLayout
    ├── 按钮行: [刷新别名]
    ├── WorkDirs 摘要 label
    └── DropArea (大块)

业务流
------
启动:  load_config → 显示 WorkDirs；失败弹错并禁用拖入
拖入:  paths_dropped → 逐个 _process_one → 候选 0/1/N 分支 →
       ask_candidate → classify_one
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from base.console import emit, error, set_output, warn
from base.gui.qt_sink import QtSink
from module.artifact.gui.widgets.candidate_dialog import ask_candidate
from module.artifact.gui.widgets.drop_area import DropArea
from module.artifact.workflow.classify.alias import scan_aliases
from module.artifact.workflow.classify.config import Config, load_config
from module.artifact.workflow.classify.matcher import find_candidates
from module.artifact.workflow.classify.ops import classify_one
from module.artifact.workflow.classify.path import path_to_author_name


def _reporter(level: str, msg: str) -> None:
    """适配 base.fs.Reporter → base.console，由 QtSink 路由到 LogView。"""
    {'info': emit, 'warn': warn, 'error': error}.get(level, emit)(msg)


class _AliasThread(QThread):
    """后台别名扫描线程，避免阻塞 GUI 主线程。"""

    scan_done = Signal(object)   # dict[str, Path]

    def __init__(self, workdirs: list[Path], sink, parent=None) -> None:
        super().__init__(parent)
        self._workdirs = workdirs
        self._sink = sink

    def run(self) -> None:
        set_output(self._sink)
        result = scan_aliases(self._workdirs, reporter=_reporter)
        self.scan_done.emit(result)


class ClassifyTab(QWidget):
    """classify 业务 Tab：拖入归类。"""

    busy_changed = Signal(bool)   # 预留：当前无长任务，恒为 False

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._sink = QtSink()

        self._cfg: Config | None = None
        self._workdirs_paths: list[Path] = []
        self._alias_map: dict[str, Path] = {}

        self._refresh_btn = QPushButton('🔄 刷新别名')
        self._refresh_btn.setToolTip('重新扫描所有 WorkDir 下的 [别名]：*.txt')
        self._refresh_btn.clicked.connect(self._on_refresh)

        btn_lay = QHBoxLayout()
        btn_lay.addWidget(self._refresh_btn)
        btn_lay.addStretch(1)

        self._workdirs_label = QLabel('（配置加载中...）')
        self._workdirs_label.setStyleSheet('color: #8a9097;')
        self._workdirs_label.setWordWrap(True)

        self._drop = DropArea()
        self._drop.paths_dropped.connect(self._on_paths_dropped)

        lay = QVBoxLayout(self)
        lay.addLayout(btn_lay)
        lay.addWidget(self._workdirs_label)
        lay.addWidget(self._drop, 1)

        self._load_and_scan()

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
            QMessageBox.critical(self, '配置无效', '配置中 artifact.workdirs 为空')
            self._drop.setEnabled(False)
            return
        self._workdirs_paths = [wd.path for wd in self._cfg.workdirs]
        lines = '\n'.join(f'  • {wd.path}' for wd in self._cfg.workdirs)
        self._workdirs_label.setText(
            f'📁 WorkDirs ({len(self._cfg.workdirs)}):\n{lines}'
        )

    def _do_scan_aliases(self) -> None:
        set_output(self._sink)
        self._refresh_btn.setEnabled(False)
        self._scan_thread = _AliasThread(list(self._workdirs_paths), self._sink, self)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    @Slot(object)
    def _on_scan_done(self, alias_map) -> None:
        self._alias_map = alias_map
        self._refresh_btn.setEnabled(True)

    # ── 回调 ──────────────────────────────────────────────────────────
    def _on_refresh(self) -> None:
        if self._cfg is None:
            return
        self._do_scan_aliases()

    def _on_paths_dropped(self, paths: list[Path]) -> None:
        if self._cfg is None:
            return
        set_output(self._sink)
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
