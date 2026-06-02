"""元数据写入 GUI Tab；复用 :mod:`module.manga.workflow.make_meta`。"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from module.manga.core.models import MakeMetaPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.presentation.view import print_make_meta_preview
from module.manga.workflow.make_meta import apply_plans, preview_plans


class MakeMetaTab(BaseTab):
    cmd_name         = 'make_meta'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    no_change_msg    = '没有需要写入的文件'
    root_label       = 'CBZ 根目录:'
    root_placeholder = '递归扫描所有 .cbz'

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

    def _plan_call(self, root: str) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans, (root,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

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
