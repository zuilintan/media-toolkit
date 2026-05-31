"""
metadata_tab.py — meta 子命令的 GUI Tab

复用 manga.workflow.metadata 的 plan_metadatas / apply_metadata_plans。
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from manga.core.models import MetadataPlan
from manga.gui.tabs.base_tab import BaseTab
from manga.presentation.view import print_metadata_preview
from manga.workflow.metadata import apply_metadata_plans, plan_metadatas


class MetadataTab(BaseTab):
    cmd_name         = 'meta'
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
        box = QGroupBox('选项')
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel('并行 jobs:'))
        lay.addWidget(self._jobs)
        lay.addStretch(1)
        return box

    def _banner_subtitle(self) -> str:
        return 'CBZ ComicInfo.xml 批量工具'

    def _plan_call(self, root: str) -> tuple[Callable[..., Any], tuple, dict]:
        return plan_metadatas, (root,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_metadata_plans

    def _render_preview(self, plans: list[MetadataPlan]) -> None:
        print_metadata_preview(plans)

    def _count_actionable(self, plans: list[MetadataPlan]) -> int:
        return sum(1 for p in plans if p.writable and p.changed)

    def _classify_plans(self, plans: list[MetadataPlan]) -> dict[str, int]:
        writable = sum(1 for p in plans if p.writable and p.changed)
        unchanged = sum(1 for p in plans if p.writable and not p.changed)
        return {'可写入': writable, '无变化': unchanged,
                '冲突': len(plans) - writable - unchanged}
