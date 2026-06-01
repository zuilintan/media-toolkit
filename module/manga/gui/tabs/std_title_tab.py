"""标题标准化 GUI Tab；复用 :mod:`module.manga.workflow.std_title`。"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from module.manga.core.models import StdTitlePlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.presentation.view import print_std_title_preview
from module.manga.workflow.std_title import apply_plans, preview_plans


class StdTitleTab(BaseTab):
    cmd_name         = 'std_title'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    no_change_msg    = '没有可执行的重命名'
    root_label       = 'ZIP/CBZ根目录:'
    root_placeholder = '作者目录所在的根目录'

    def _build_options_box(self) -> QWidget:
        self._jobs = QSpinBox()
        self._jobs.setRange(0, 32)
        self._jobs.setValue(1)
        self._jobs.setToolTip(
            'plan 阶段并行进程数；1=串行（默认），0=自动 min(cpu, 4)'
        )
        box = QGroupBox('选项')
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel('并行 jobs:'))
        lay.addWidget(self._jobs)
        lay.addStretch(1)
        return box

    def _banner_subtitle(self) -> str:
        return '源文件批量重命名'

    def _plan_call(self, root: str) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans, (root,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

    def _render_preview(self, plans: list[StdTitlePlan]) -> None:
        print_std_title_preview(plans)

    def _count_actionable(self, plans: list[StdTitlePlan]) -> int:
        return sum(1 for p in plans if p.changed and not p.needs_review)

    def _classify_plans(self, plans: list[StdTitlePlan]) -> dict[str, int]:
        actionable = sum(1 for p in plans if p.changed and not p.needs_review)
        review     = sum(1 for p in plans if p.needs_review)
        return {'可重命名': actionable, '需审核': review,
                '无变化': len(plans) - actionable - review}
