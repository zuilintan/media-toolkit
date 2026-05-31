"""``pack-kit`` 子命令的 GUI Tab；复用 :mod:`module.manga.workflow.pack_kit`。"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from module.manga.core.models import PackKitPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.presentation.view import print_pack_preview
from module.manga.workflow.pack_kit import apply_plans, preview_plans


class PackKitTab(BaseTab):
    cmd_name         = 'pack-kit'
    apply_btn_text   = '打包'
    confirm_verb     = '打包并删除源目录'
    no_change_msg    = '没有可打包的目录'
    root_label       = '图片根目录:'
    root_placeholder = '递归识别打包单位（单层 / 嵌套分话）'

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
        return '图片目录序号化重命名 + STORED zip 打包'

    def _plan_call(self, root: str) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans, (root,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

    def _render_preview(self, plans: list[PackKitPlan]) -> None:
        print_pack_preview(plans)

    def _count_actionable(self, plans: list[PackKitPlan]) -> int:
        return sum(1 for p in plans if p.writable)

    def _classify_plans(self, plans: list[PackKitPlan]) -> dict[str, int]:
        flat     = sum(1 for p in plans if p.writable and p.kind == 'flat')
        nested   = sum(1 for p in plans if p.writable and p.kind == 'nested')
        replaced = sum(1 for p in plans if p.writable and p.zip_exists)
        skipped  = sum(1 for p in plans if not p.writable)
        return {'单层': flat, '嵌套': nested,
                '覆盖现有 zip': replaced, '跳过': skipped}
