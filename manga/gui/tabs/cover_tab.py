"""
cover_tab.py — cover 子命令的 GUI Tab

复用 manga.workflow.cover 的 plan_covers / apply_cover_plans。
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from manga.core.models import CoverPlan
from base.gui.config import get_config
from manga.gui.tabs.base_tab import BaseTab
from manga.presentation.view import print_cover_preview
from manga.workflow.cover import (
    DEFAULT_QUALITY, apply_cover_plans, plan_covers,
)


class CoverTab(BaseTab):
    cmd_name         = 'cover'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    no_change_msg    = '没有需要写入的封面'
    root_label       = 'CBZ 根目录:'
    root_placeholder = '递归扫描所有 .cbz'

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
        if (v := cfg.get('cover.smart')) is not None:
            self._smart.setChecked(bool(v))
        if (v := cfg.get('cover.quality')) is not None:
            self._quality.setValue(int(v))
        self._smart.stateChanged.connect(
            lambda: cfg.set('cover.smart', self._smart.isChecked())
        )
        self._quality.valueChanged.connect(
            lambda v: cfg.set('cover.quality', v)
        )

    def _mode(self) -> str:
        return 'smart' if self._smart.isChecked() else 'center'

    def _banner_subtitle(self) -> str:
        return f'CBZ 封面写入（mode={self._mode()}）'

    def _plan_call(self, root: str) -> tuple[Callable[..., Any], tuple, dict]:
        return plan_covers, (root,), {
            'mode':    self._mode(),
            'quality': self._quality.value(),
            'jobs':    self._jobs.value(),
        }

    def _apply_fn(self):
        return apply_cover_plans

    def _render_preview(self, plans: list[CoverPlan]) -> None:
        print_cover_preview(plans)

    def _count_actionable(self, plans: list[CoverPlan]) -> int:
        return sum(1 for p in plans if p.writable and p.changed)

    def _classify_plans(self, plans: list[CoverPlan]) -> dict[str, int]:
        writable = sum(1 for p in plans if p.writable and p.changed)
        unchanged = sum(1 for p in plans if p.writable and not p.changed)
        return {'可写入': writable, '无变化': unchanged,
                '错误': len(plans) - writable - unchanged}
