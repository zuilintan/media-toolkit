"""
pack_tab.py — pack 子命令的 GUI Tab

复用 mt.workflow.pack 的 plan_packs / apply_pack_plans / move_zip。

与其他 Tab 不同点：apply 成功后源目录已被删除，``--move-to`` 移动的是
打包产物 zip 文件而非目录，所以覆盖 ``_mover()`` 提供自定义策略。
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from mt.core.models import PackPlan
from mt.gui.tabs.base_tab import BaseTab
from mt.presentation.view import print_pack_preview
from mt.workflow.pack import apply_pack_plans, move_zip, plan_packs


def _pack_mover(plans: list[PackPlan], root: str, move_to: str) -> None:
    """pack 专用 mover：把每个 plan 的产物 zip 移动到 move_to。

    源目录在 apply 阶段已被 rmtree，因此不再适用「移 root 下子目录」的
    默认策略。
    """
    for p in plans:
        if p.writable:
            move_zip(Path(p.zip_path), move_to)


class PackTab(BaseTab):
    cmd_name         = 'pack'
    apply_btn_text   = '打包'
    confirm_verb     = '打包并删除源目录'
    no_change_msg    = '没有可打包的目录'
    root_label       = '图片根目录:'
    root_placeholder = '其下每个直接子目录视为一本漫画'

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
        return plan_packs, (root,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_pack_plans

    def _render_preview(self, plans: list[PackPlan]) -> None:
        print_pack_preview(plans)

    def _count_actionable(self, plans: list[PackPlan]) -> int:
        return sum(1 for p in plans if p.writable)

    def _classify_plans(self, plans: list[PackPlan]) -> dict[str, int]:
        writable = sum(1 for p in plans if p.writable)
        replaced = sum(1 for p in plans if p.writable and p.zip_exists)
        skipped  = len(plans) - writable
        return {'可打包': writable, '覆盖现有 zip': replaced, '跳过': skipped}

    def _mover(self):
        return _pack_mover
