"""标题标准化 GUI Tab；复用 :mod:`module.manga.workflow.std_title`。

输入语义与 CLI 对齐：用户增量添加文件 / 目录，每个文件自动推导作者
（``[社团 (作者)]`` 抽取），冲突 / 缺失时弹窗交互。
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QSpinBox, QWidget,
)

from module.manga.core.models import StdTitlePlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.std_title_input import InputListWidget
from module.manga.presentation.view import print_std_title_preview
from module.manga.workflow.std_title import apply_plans, preview_plans_for_inputs


class StdTitleTab(BaseTab):
    cmd_name         = 'std_title'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    no_change_msg    = '没有可执行的重命名'

    def _input_box_title(self) -> str:
        return '输入'

    def _create_input_widget(self) -> QWidget:
        self._input_list = InputListWidget()
        self._input_list.inputs_changed.connect(self._on_inputs_changed)
        return self._input_list

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

    def _validate_scan_target(self) -> Any | None:
        inputs = self._input_list.inputs()
        if not inputs:
            QMessageBox.warning(self, '提示', '请先添加文件或目录')
            return None
        return inputs

    def _format_banner_target(self, target: Any) -> object:
        return f'已添加 {len(target)} 个文件'

    def _plan_call(self, target: Any) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans_for_inputs, (target,), {'jobs': self._jobs.value()}

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

    # ── 输入列表变化：列表清空时直接复位 apply / status ───────────────
    def _on_inputs_changed(self) -> None:
        if not self._input_list.inputs():
            self._plans = None
            self._apply_btn.setEnabled(False)
            self._status.setText('待扫描')

    def _on_applied(self, fail: int) -> None:
        # apply 后所有列表项的 src_path 都已失效（文件被移走 / 改名），
        # 继续保留列表会误导用户「这些文件还在等待处理」。先清列表（会经
        # _on_inputs_changed 暂设「待扫描」），再调 super 覆盖为「写入完成…」。
        self._input_list.clear()
        super()._on_applied(fail)
