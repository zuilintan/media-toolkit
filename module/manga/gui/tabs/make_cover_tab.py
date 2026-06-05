"""封面写入 GUI Tab；复用 :mod:`module.manga.workflow.make_cover`。

输入语义：PathListWidget（接受 .cbz 文件 + 目录；目录在添加时 rglob 展开成 .cbz）。
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QSpinBox,
    QWidget,
)

from base.gui.config import get_config
from base.gui.path_list import PathListWidget
from module.manga.core.models import MakeCoverPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.make_cover_detail import MakeCoverDetailDialog
from module.manga.gui.widgets.make_cover_tree import MakeCoverTree
from module.manga.gui.widgets.preview_tree import PreviewTreeBase
from module.manga.presentation.view import print_make_cover_preview
from module.manga.workflow.make_cover import (
    DEFAULT_QUALITY, apply_plan, apply_plans, preview_plans_for_files,
)


class MakeCoverTab(BaseTab):
    cmd_name        = 'make_cover'
    apply_btn_text  = '执行'
    confirm_verb    = '执行'
    single_verb     = '写入封面'
    no_change_msg   = '没有需要写入的封面'

    def _create_input_widget(self) -> QWidget:
        self._input_list = PathListWidget(
            accept_file_exts=('.cbz',),
            accept_dirs=True,
            expand_dirs_on_add=True,
            file_dialog_filter='CBZ (*.cbz);;所有文件 (*)',
            file_dialog_title='添加 CBZ 文件',
            dir_dialog_title='添加 CBZ 根目录（递归扫描 .cbz）',
            add_file_label='添加 CBZ 文件…',
            add_dir_label='添加 CBZ 根目录…',
        )
        self._input_list.paths_changed.connect(self._on_inputs_changed)
        return self._input_list

    def _validate_scan_target(self) -> Any | None:
        files = [str(p) for p in self._input_list.paths()]
        if not files:
            QMessageBox.warning(self, '提示', '请先添加 .cbz 文件或包含 .cbz 的目录')
            return None
        return files

    def _format_banner_target(self, target: Any) -> object:
        return f'已添加 {len(target)} 个文件'

    def _has_inputs(self) -> bool:
        return bool(self._input_list.paths())

    def _build_options_box(self) -> QWidget:
        self._smart = QCheckBox('smartcrop 显著性裁剪')
        self._smart.setToolTip('启用后用 smartcrop 库做主体保留；横图更稳')

        self._quality = QSpinBox()
        self._quality.setRange(1, 100)
        self._quality.setValue(DEFAULT_QUALITY)
        self._quality.setToolTip(f'WebP 质量（1-100，默认 {DEFAULT_QUALITY}）')

        self._jobs = QSpinBox()
        self._jobs.setRange(0, 32)
        self._jobs.setValue(1)
        self._jobs.setToolTip(
            'plan 阶段并行进程数；1=串行（默认），0=自动 min(cpu, 4)'
        )

        box = QGroupBox('选项')
        lay = QHBoxLayout(box)
        lay.addWidget(self._smart)
        lay.addSpacing(16)
        lay.addWidget(QLabel('WebP 质量:'))
        lay.addWidget(self._quality)
        lay.addSpacing(16)
        lay.addWidget(QLabel('并行 jobs:'))
        lay.addWidget(self._jobs)
        lay.addStretch(1)
        return box

    def _load_settings(self) -> None:
        super()._load_settings()
        cfg = get_config()
        if (v := cfg.get(f'{self.cmd_name}.smart')) is not None:
            self._smart.setChecked(bool(v))
        if (v := cfg.get(f'{self.cmd_name}.quality')) is not None:
            self._quality.setValue(int(v))
        self._smart.stateChanged.connect(
            lambda: cfg.set(f'{self.cmd_name}.smart', self._smart.isChecked())
        )
        self._quality.valueChanged.connect(
            lambda v: cfg.set(f'{self.cmd_name}.quality', v)
        )

    def _mode(self) -> str:
        return 'smart' if self._smart.isChecked() else 'center'

    def _banner_subtitle(self) -> str:
        return f'CBZ 封面写入（mode={self._mode()}）'

    def _plan_call(self, target: Any) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans_for_files, (target,), {
            'mode':    self._mode(),
            'quality': self._quality.value(),
            'jobs':    self._jobs.value(),
        }

    def _apply_fn(self):
        return apply_plans

    def _apply_one(self, plan: MakeCoverPlan) -> str:
        return apply_plan(plan)

    def _create_preview_tree(self) -> PreviewTreeBase:
        return MakeCoverTree(self)

    def _create_detail_dialog(self, plan: MakeCoverPlan) -> QDialog:
        return MakeCoverDetailDialog(plan, parent=self)

    def _render_preview(self, plans: list[MakeCoverPlan]) -> None:
        print_make_cover_preview(plans)

    def _count_actionable(self, plans: list[MakeCoverPlan]) -> int:
        return sum(1 for p in plans if p.writable and p.changed)

    # ── 自动化管线钩子 ────────────────────────────────────────────────
    def auto_set_inputs(self, paths: list[Path]) -> None:
        self._input_list.clear()
        self._input_list.add_paths([Path(p) for p in paths])

    def auto_collect_outputs(self) -> list[Path]:
        """产出 = 处理过的 cbz 路径透传（写封面不改文件名）。读 snapshot 与
        其它 Tab 对齐——确保 super().on_applied 取到的是 apply 启动时的 plans。"""
        plans = self._auto_snapshot or []
        return [Path(p.cbz_path) for p in plans if p.writable]

    def _classify_plans(self, plans: list[MakeCoverPlan]) -> dict[str, int]:
        writable = sum(1 for p in plans if p.writable and p.changed)
        unchanged = sum(1 for p in plans if p.writable and not p.changed)
        return {'可写入': writable, '无变化': unchanged,
                '错误': len(plans) - writable - unchanged}
