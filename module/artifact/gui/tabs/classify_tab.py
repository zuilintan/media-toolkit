"""``artifact`` 的 ``classify`` 业务子 Tab。

布局：``QVBoxLayout`` → 按钮行（修改配置 + 重载配置 + 刷新别名）+ WorkDirs
摘要 label + :class:`~module.artifact.gui.widgets.drop_area.DropArea`（大块）。

业务流：启动时 :func:`~module.artifact.core.runtime_config.load_config`
→ 显示 WorkDirs（空则提示且禁用拖入）；三个按钮职责单一互不联动：

- 「修改配置」用关联程序打开 artifact.json
- 「重载配置」仅重读 workdirs 并刷新 UI（不动 alias_map）
- 「刷新别名」仅 re-scan ``[别名]：*.txt`` 写入 alias_map（不动 workdirs）

拖入 → 逐个 :meth:`ClassifyTab._process_one` → 候选 0/1/N 分支 →
:func:`~module.artifact.gui.widgets.candidate_dialog.ask_candidate`
→ :func:`~module.artifact.workflow.classify.ops.classify_one`。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from base.console import emit, error, set_output, warn
from base.gui.qt_sink import QtSink
from module.artifact.gui.widgets.candidate_dialog import ask_candidate
from module.artifact.gui.widgets.drop_area import DropArea
from module.artifact.workflow.classify.alias import scan_aliases
from module.artifact.core.runtime_config import Config, config_path, load_config
from module.artifact.workflow.classify.matcher import find_candidates
from module.artifact.workflow.classify.ops import classify_one
from module.artifact.workflow.classify.path import path_to_author_name


def _reporter(level: str, msg: str) -> None:
    """适配 :data:`~base.fs.Reporter` → :mod:`base.console`，由 :class:`~base.gui.qt_sink.QtSink` 路由到 :class:`~base.gui.log_view.LogView`。"""
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
    """``classify`` 业务 Tab：拖入归类。

    :ivar busy_changed: 预留信号；当前无长任务，恒为 ``False``。
    """

    busy_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._sink = QtSink()

        self._cfg: Config | None = None
        self._workdirs_paths: list[Path] = []
        self._alias_map: dict[str, Path] = {}

        self._edit_cfg_btn = QPushButton('📝 修改配置')
        self._edit_cfg_btn.setToolTip(
            f'用关联程序打开配置文件：\n{config_path()}\n'
            '编辑保存后点「重载配置」生效。'
        )
        self._edit_cfg_btn.clicked.connect(self._on_edit_config)

        self._reload_cfg_btn = QPushButton('🔁 重载配置')
        self._reload_cfg_btn.setToolTip(
            '重新读取 artifact.json（workdirs）；'
            '别名需要时另点「🔄 刷新别名」'
        )
        self._reload_cfg_btn.clicked.connect(self._on_reload_config)

        self._refresh_alias_btn = QPushButton('🔄 刷新别名')
        self._refresh_alias_btn.setToolTip(
            '仅重新扫描所有 WorkDir 下的 [别名]：*.txt（不重读 artifact.json）'
        )
        self._refresh_alias_btn.clicked.connect(self._on_refresh_alias)

        btn_lay = QHBoxLayout()
        btn_lay.addWidget(self._edit_cfg_btn)
        btn_lay.addWidget(self._reload_cfg_btn)
        btn_lay.addWidget(self._refresh_alias_btn)
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

        self._load_workdirs()

    # ── 配置加载 & UI 同步 ────────────────────────────────────────────
    def _load_workdirs(self) -> None:
        """读取 artifact.json → 更新 self._cfg / self._workdirs_paths / label / 拖入区可用性。"""
        self._cfg = load_config()
        if not self._cfg.workdirs:
            self._workdirs_paths = []
            self._workdirs_label.setText(
                '⚠️ artifact.workdirs 为空 —— 点「📝 修改配置」'
                '编辑后再点「🔁 重载配置」。'
            )
            self._drop.setEnabled(False)
            return
        self._workdirs_paths = [wd.path for wd in self._cfg.workdirs]
        lines = '\n'.join(f'  • {wd.path}' for wd in self._cfg.workdirs)
        self._workdirs_label.setText(
            f'📁 WorkDirs ({len(self._cfg.workdirs)}):\n{lines}'
        )
        self._drop.setEnabled(True)

    def _do_scan_aliases(self) -> None:
        set_output(self._sink)
        self._reload_cfg_btn.setEnabled(False)
        self._refresh_alias_btn.setEnabled(False)
        self._scan_thread = _AliasThread(list(self._workdirs_paths), self._sink, self)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    @Slot(object)
    def _on_scan_done(self, alias_map) -> None:
        self._alias_map = alias_map
        self._reload_cfg_btn.setEnabled(True)
        self._refresh_alias_btn.setEnabled(True)

    # ── 按钮回调 ──────────────────────────────────────────────────────
    def _on_edit_config(self) -> None:
        """用 OS 关联程序打开 artifact.json（不存在则给提示）。"""
        path = config_path()
        if not path.exists():
            # load_config() 启动时已落盘；走到这里通常是被人为删除
            QMessageBox.warning(
                self, '配置缺失',
                f'未找到 {path}\n点「🔁 重载配置」会自动重建空配置。',
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_reload_config(self) -> None:
        """仅重读 artifact.json → 更新 workdirs / UI；不触发别名扫描。"""
        self._load_workdirs()

    def _on_refresh_alias(self) -> None:
        """仅重新扫描别名（workdirs 未变时使用，省略一次 IO）。"""
        if not self._workdirs_paths:
            return
        self._do_scan_aliases()

    # ── 拖入归类 ──────────────────────────────────────────────────────
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
