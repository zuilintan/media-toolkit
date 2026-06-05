"""标题标准化 GUI Tab；复用 :mod:`module.manga.workflow.std_title`。

输入语义与 CLI 对齐：用户增量添加文件 / 目录，每个文件自动推导作者
（``[社团 (作者)]`` 抽取），冲突 / 缺失时弹窗交互。
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QSpinBox, QWidget,
)

from base.console import emit
from module.manga.core.config import FILE_EXTS
from module.manga.core.models import StdTitlePlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.preview_tree import PreviewTreeBase
from module.manga.gui.widgets.std_title_detail import StdTitleDetailDialog
from module.manga.gui.widgets.std_title_input import InputListWidget
from module.manga.gui.widgets.std_title_tree import StdTitleTree
from module.manga.presentation.view import print_std_title_preview
from module.manga.workflow.std_title import (
    apply_plan, apply_plans, build_input, derive_author, preview_plans_for_inputs,
)


class StdTitleTab(BaseTab):
    cmd_name         = 'std_title'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    single_verb      = '重命名'
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

    def _has_inputs(self) -> bool:
        return bool(self._input_list.inputs())

    def _plan_call(self, target: Any) -> tuple[Callable[..., Any], tuple, dict]:
        return preview_plans_for_inputs, (target,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

    def _apply_one(self, plan: StdTitlePlan) -> str:
        result = apply_plan(plan)
        # apply_plan 返回 'skip' 表示需审核 / 无变化 / 目标已存在；GUI 不视为失败
        return 'ok' if result in ('ok', 'skip') else 'error'

    def _create_preview_tree(self) -> PreviewTreeBase:
        return StdTitleTree(self)

    def _create_detail_dialog(self, plan: StdTitlePlan) -> QDialog:
        return StdTitleDetailDialog(plan, parent=self)

    def _render_preview(self, plans: list[StdTitlePlan]) -> None:
        print_std_title_preview(plans)

    def _count_actionable(self, plans: list[StdTitlePlan]) -> int:
        return sum(1 for p in plans if p.changed and not p.needs_review)

    def _classify_plans(self, plans: list[StdTitlePlan]) -> dict[str, int]:
        actionable = sum(1 for p in plans if p.changed and not p.needs_review)
        review     = sum(1 for p in plans if p.needs_review)
        return {'可重命名': actionable, '需审核': review,
                '无变化': len(plans) - actionable - review}

    # ── 自动化管线钩子 ────────────────────────────────────────────────
    def auto_set_inputs(self, paths: list[Path]) -> None:
        """编排器入口：为上游 zip/cbz 推导作者并构造
        :class:`~module.manga.workflow.std_title.StdTitleInput`，无可用推导即跳过。

        Fallback 顺序：``auto_author`` → ``bracket_author`` → ``parent_author``。
        pack_pic 产出的 zip 通常落在「漫画根目录」（如 ``Comic/`` 下）而非作者
        目录，``parent_author = 'Comic'`` 不可用——文件名里的 ``[社团 (作者)]``
        bracket 头才是可靠来源，故 bracket 优先于 parent。
        """
        self._input_list.clear()
        inputs = []
        for p in paths:
            p = Path(p)
            if p.suffix.lower() not in FILE_EXTS or not p.is_file():
                continue
            deriv  = derive_author(str(p))
            author = (deriv.auto_author or deriv.bracket_author
                      or deriv.parent_author)
            if not author:
                emit(f'⚠️ std_title 自动化跳过（无作者推导）: {p.name}')
                continue
            publisher = (deriv.bracket_publisher
                         if author == deriv.bracket_author else '')
            inputs.append(build_input(str(p), author, publisher))
        self._input_list.add_inputs(inputs)

    def auto_collect_outputs(self) -> list[Path]:
        """产出 = 重命名后的目标路径（``author_dir / new_name``）。
        以文件存在与否过滤本次成功项。读 :attr:`_auto_snapshot`：基类
        :meth:`_on_applied` 会先 clear input list 把 ``_plans`` 置 None。
        """
        plans = self._auto_snapshot or []
        out: list[Path] = []
        for p in plans:
            np = Path(p.author_dir) / p.new_name
            if np.exists():
                out.append(np)
        return out
