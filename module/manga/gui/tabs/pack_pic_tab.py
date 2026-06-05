"""图片打包 GUI Tab；复用 :mod:`module.manga.workflow.pack_pic`。

输入语义：单 :class:`~base.gui.path_list.PathListWidget`（仅目录）。workflow 层
按 FLAT / NESTED / CONTAINER 智能识别 —— 用户传根目录还是单本漫画目录皆可。
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QSpinBox, QWidget,
)

from base.gui.path_list import PathListWidget
from module.manga.core.models import PackPicPlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.pack_pic_detail import PackPicDetailDialog
from module.manga.gui.widgets.pack_pic_tree import PackPicTree
from module.manga.gui.widgets.preview_tree import PreviewTreeBase
from module.manga.presentation.view import print_pack_pic_preview
from module.manga.workflow.pack_pic import (
    apply_plan, apply_plans, preview_plans_for_dirs,
)


class PackPicTab(BaseTab):
    cmd_name        = 'pack_pic'
    apply_btn_text  = '执行'
    confirm_verb    = '打包并删除源目录'
    single_verb     = '打包'
    no_change_msg   = '没有可打包的目录'

    def _create_input_widget(self) -> QWidget:
        self._input_list = PathListWidget(
            accept_file_exts=(), accept_dirs=True, expand_dirs_on_add=False,
            dir_dialog_title='添加目录（智能识别根 / 单本漫画）',
            # 按钮列窄（2 列 grid，约 53 px），仅展示精炼文本；菜单 / 弹窗仍含语义
            add_dir_label='添加…',
        )
        self._input_list.paths_changed.connect(self._on_inputs_changed)
        return self._input_list

    def _validate_scan_target(self) -> Any | None:
        dirs = [str(p) for p in self._input_list.paths()]
        if not dirs:
            QMessageBox.warning(self, '提示', '请先添加目录')
            return None
        return dirs

    def _format_banner_target(self, target: Any) -> object:
        return f'已添加 {len(target)} 个目录'

    def _has_inputs(self) -> bool:
        return bool(self._input_list.paths())

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
        return preview_plans_for_dirs, (target,), {'jobs': self._jobs.value()}

    def _apply_fn(self):
        return apply_plans

    def _apply_one(self, plan: PackPicPlan) -> str:
        return apply_plan(plan)

    def _create_preview_tree(self) -> PreviewTreeBase:
        return PackPicTree(self)

    def _create_detail_dialog(self, plan: PackPicPlan) -> QDialog:
        return PackPicDetailDialog(plan, parent=self)

    def _render_preview(self, plans: list[PackPicPlan]) -> None:
        print_pack_pic_preview(plans)

    def _count_actionable(self, plans: list[PackPicPlan]) -> int:
        return sum(1 for p in plans if p.writable)

    # ── 自动化管线钩子 ────────────────────────────────────────────────
    def auto_set_inputs(self, paths: list[Path]) -> None:
        """编排器入口：通常本 Tab 是管线起点，但仍支持外部注入目录。"""
        self._input_list.clear()
        self._input_list.add_paths([Path(p) for p in paths])

    def auto_collect_outputs(self) -> list[Path]:
        """产出 = 已成功生成的 zip 路径；apply 后 rmtree 源目录但 zip 独立落盘。
        以文件存在过滤本次成功项；读 :attr:`_auto_snapshot`：基类
        :meth:`_on_applied` 会先 clear input list 把 ``_plans`` 置 None。"""
        plans = self._auto_snapshot or []
        return [
            Path(p.zip_path) for p in plans
            if p.writable and Path(p.zip_path).exists()
        ]

    def _classify_plans(self, plans: list[PackPicPlan]) -> dict[str, int]:
        flat     = sum(1 for p in plans if p.writable and p.kind == 'flat')
        nested   = sum(1 for p in plans if p.writable and p.kind == 'nested')
        replaced = sum(1 for p in plans if p.writable and p.zip_exists)
        skipped  = sum(1 for p in plans if not p.writable)
        return {'单层': flat, '嵌套': nested,
                '覆盖现有 zip': replaced, '跳过': skipped}
