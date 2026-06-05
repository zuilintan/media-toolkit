"""元数据写入 GUI Tab；复用 :mod:`module.manga.workflow.make_meta`。

输入语义：PathListWidget（接受 .cbz 文件 + 目录；目录在添加时 rglob 展开成 .cbz）。
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QSpinBox, QWidget,
)

from base.gui.path_list import PathListWidget
from module.manga.core.models import MakeMetaPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.make_meta_detail import MakeMetaDetailDialog
from module.manga.gui.widgets.make_meta_tree import MakeMetaTree
from module.manga.gui.widgets.preview_tree import PreviewTreeBase
from module.manga.presentation.view import print_make_meta_preview
from module.manga.workflow.make_meta import (
    apply_plan, apply_plans, preview_plans_for_files,
)


class MakeMetaTab(BaseTab):
    cmd_name        = 'make_meta'
    apply_btn_text  = '执行'
    confirm_verb    = '执行'
    single_verb     = '写入'
    no_change_msg   = '没有需要写入的文件'

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
        self._jobs = QSpinBox()
        self._jobs.setRange(0, 32)
        self._jobs.setValue(1)
        self._jobs.setToolTip(
            'plan 阶段并行进程数；1=串行（默认），0=自动 min(cpu, 4)'
        )
        self._sample_per_group = QSpinBox()
        self._sample_per_group.setRange(0, 999)
        self._sample_per_group.setValue(3)
        self._sample_per_group.setToolTip(
            '预览阶段每类差异展示的样本卡数（默认 3；0=全量，不折叠）'
        )
        self._rare_threshold = QSpinBox()
        self._rare_threshold.setRange(0, 999)
        self._rare_threshold.setValue(5)
        self._rare_threshold.setToolTip(
            '出现 ≤ N 次的差异类视为稀有，强制全量渲染（默认 5）'
        )
        box = QGroupBox('选项')
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel('并行 jobs:'))
        lay.addWidget(self._jobs)
        lay.addSpacing(16)
        lay.addWidget(QLabel('每组样本:'))
        lay.addWidget(self._sample_per_group)
        lay.addWidget(QLabel('稀有阈值:'))
        lay.addWidget(self._rare_threshold)
        lay.addStretch(1)
        return box

    def _banner_subtitle(self) -> str:
        return 'CBZ ComicInfo.xml 批量工具'

    def _plan_call(self, target: Any) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans_for_files, (target,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

    def _apply_one(self, plan: MakeMetaPlan) -> str:
        return apply_plan(plan)

    def _create_preview_tree(self) -> PreviewTreeBase:
        return MakeMetaTree(self)

    def _create_detail_dialog(self, plan: MakeMetaPlan) -> QDialog:
        return MakeMetaDetailDialog(plan, parent=self)

    def _render_preview(self, plans: list[MakeMetaPlan]) -> None:
        print_make_meta_preview(
            plans,
            sample_per_group=self._sample_per_group.value(),
            rare_threshold=self._rare_threshold.value(),
        )

    def _count_actionable(self, plans: list[MakeMetaPlan]) -> int:
        return sum(1 for p in plans if p.writable and p.changed)

    def _classify_plans(self, plans: list[MakeMetaPlan]) -> dict[str, int]:
        writable = sum(1 for p in plans if p.writable and p.changed)
        unchanged = sum(1 for p in plans if p.writable and not p.changed)
        return {'可写入': writable, '无变化': unchanged,
                '冲突': len(plans) - writable - unchanged}
