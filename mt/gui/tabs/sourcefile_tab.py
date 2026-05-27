"""
sourcefile_tab.py — sourcefile 子命令的 GUI Tab

复用 mt.workflow.sourcefile 的 plan / apply 函数；不调用 mt.cli.cmd_sourcefile
（cmd_* 内部用 input() 阻塞确认，与 GUI 互斥）。
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from mt.core.models import SourcefilePlan
from mt.gui.tabs.base_tab import BaseTab
from mt.presentation.view import print_sourcefile_preview
from mt.workflow.sourcefile import apply_sourcefile_plans, plan_sourcefiles


class SourcefileTab(BaseTab):
    cmd_name         = 'sourcefile'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    no_change_msg    = '没有可执行的重命名'
    root_label       = '漫画根目录:'
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
        return plan_sourcefiles, (root,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_sourcefile_plans

    def _render_preview(self, plans: list[SourcefilePlan]) -> None:
        print_sourcefile_preview(plans)

    def _count_actionable(self, plans: list[SourcefilePlan]) -> int:
        return sum(1 for p in plans if p.changed and not p.needs_review)

    def _classify_plans(self, plans: list[SourcefilePlan]) -> dict[str, int]:
        actionable = sum(1 for p in plans if p.changed and not p.needs_review)
        review     = sum(1 for p in plans if p.needs_review)
        return {'可重命名': actionable, '需审核': review,
                '无变化': len(plans) - actionable - review}
