"""图片打包 GUI Tab；复用 :mod:`module.manga.workflow.pack_pic`。

输入语义：双源 —— 打包根目录列表（递归识别其下单位）+ 打包单位列表（单本漫画
目录，直接喂入 workflow 识别）。两类均仅接受目录、添加阶段不展开。
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QSpinBox, QVBoxLayout, QWidget,
)

from base.gui.path_list import PathListWidget
from module.manga.core.models import PackPicPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.presentation.view import print_pack_pic_preview
from module.manga.workflow.pack_pic import apply_plans, preview_plans_for_targets


class PackPicTab(BaseTab):
    cmd_name        = 'pack_pic'
    apply_btn_text  = '打包'
    confirm_verb    = '打包并删除源目录'
    no_change_msg   = '没有可打包的目录'

    def _create_input_widget(self) -> QWidget:
        self._roots = PathListWidget(
            accept_file_exts=(), accept_dirs=True, expand_dirs_on_add=False,
            dir_dialog_title='添加打包根目录',
            add_dir_label='添加打包根目录…',
        )
        self._units = PathListWidget(
            accept_file_exts=(), accept_dirs=True, expand_dirs_on_add=False,
            dir_dialog_title='添加打包单位',
            add_dir_label='添加打包单位…',
        )
        self._roots.paths_changed.connect(self._on_inputs_changed)
        self._units.paths_changed.connect(self._on_inputs_changed)

        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        box_r = QGroupBox('打包根目录（递归识别其下打包单位）')
        QVBoxLayout(box_r).addWidget(self._roots)
        box_u = QGroupBox('打包单位（直接指定单本漫画目录）')
        QVBoxLayout(box_u).addWidget(self._units)
        lay.addWidget(box_r, 1)
        lay.addWidget(box_u, 1)
        return wrap

    def _validate_scan_target(self) -> Any | None:
        roots = [str(p) for p in self._roots.paths()]
        units = [str(p) for p in self._units.paths()]
        if not roots and not units:
            QMessageBox.warning(self, '提示', '请先添加打包根目录或打包单位')
            return None
        return roots, units

    def _format_banner_target(self, target: Any) -> object:
        roots, units = target
        return f'根 {len(roots)} / 单位 {len(units)}'

    def _has_inputs(self) -> bool:
        return bool(self._roots.paths() or self._units.paths())

    def _on_applied(self, fail: int) -> None:
        # 打包单位目录被 rmtree，列表中的路径已失效；apply 后清空
        self._roots.clear()
        self._units.clear()
        super()._on_applied(fail)

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

    def _plan_call(self, target: Any) -> tuple[Callable[..., Any], tuple, dict]:
        roots, units = target
        return preview_plans_for_targets, (roots, units), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

    def _render_preview(self, plans: list[PackPicPlan]) -> None:
        print_pack_pic_preview(plans)

    def _count_actionable(self, plans: list[PackPicPlan]) -> int:
        return sum(1 for p in plans if p.writable)

    def _classify_plans(self, plans: list[PackPicPlan]) -> dict[str, int]:
        flat     = sum(1 for p in plans if p.writable and p.kind == 'flat')
        nested   = sum(1 for p in plans if p.writable and p.kind == 'nested')
        replaced = sum(1 for p in plans if p.writable and p.zip_exists)
        skipped  = sum(1 for p in plans if not p.writable)
        return {'单层': flat, '嵌套': nested,
                '覆盖现有 zip': replaced, '跳过': skipped}
