"""标题标准化 GUI Tab；复用 :mod:`module.manga.workflow.std_title`。

输入语义与 make_meta / make_cover 对齐：
:class:`~base.gui.path_list.PathListWidget` 收路径（拖入或菜单添加，目录在添加时
``rglob`` 展开成 ``.zip`` / ``.cbz``），scan 阶段统一跑
:func:`~module.manga.workflow.std_title.derive_inputs` 推导作者：``auto_author``
直采，缺失 / 冲突弹 :class:`~module.manga.gui.widgets.author_choice.AuthorChoiceDialog`。
自动化管线下改用 :func:`~module.manga.workflow.std_title.auto_fallback` 无弹窗回调。

漫画库根目录是 module 级全局设置（持久化 + UI 在
:class:`~module.manga.gui.module.MangaModule` 顶部工具条），本 Tab 通过
:meth:`set_library_root_getter` 接受 module 注入的取值回调，scan 阶段拉取
当前值给 :func:`~module.manga.workflow.author_library.load_or_scan`，命中即
对齐到库主名，避免简繁两份目录。
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QSpinBox, QWidget,
)

from base.console import emit
from base.gui.path_list import PathListWidget
from module.manga.core.config import FILE_EXTS
from module.manga.core.models import StdTitlePlan
from module.manga.gui.tabs.base_tab import BaseTab
from module.manga.gui.widgets.author_choice import resolve_author_via_dialog
from module.manga.gui.widgets.preview_tree import PreviewTreeBase
from module.manga.gui.widgets.std_title_detail import StdTitleDetailDialog
from module.manga.gui.widgets.std_title_tree import StdTitleTree
from module.manga.presentation.view import print_std_title_preview
from module.manga.workflow.author_library import load_or_scan
from module.manga.workflow.std_title import (
    auto_fallback,
    apply_plan, apply_plans, derive_inputs, preview_plans_for_inputs,
)


class StdTitleTab(BaseTab):
    cmd_name         = 'std_title'
    apply_btn_text   = '执行'
    confirm_verb     = '执行'
    single_verb      = '重命名'
    no_change_msg    = '没有可执行的重命名'

    def __init__(self, parent=None) -> None:
        # 库根取值回调，默认空字符串 → 跳过规范化；
        # :class:`~module.manga.gui.module.MangaModule` 在装配阶段会注入真实的
        # getter（从顶部工具条 PathPicker 读当前路径）
        self._get_library_root: Callable[[], str] = lambda: ''
        super().__init__(parent)

    def set_library_root_getter(self, getter: Callable[[], str]) -> None:
        """供 :class:`~module.manga.gui.module.MangaModule` 注入"当前漫画库根目录"
        的取值回调；scan 阶段调用以拉取最新值。

        以 callable 而非 path string 注入：用户可以在 UI 上随时改库根，scan 时
        才取值即可保证用最新的库做规范化。
        """
        self._get_library_root = getter

    def _input_box_title(self) -> str:
        return '输入'

    def _create_input_widget(self) -> QWidget:
        self._input_list = PathListWidget(
            accept_file_exts=tuple(FILE_EXTS),
            accept_dirs=True,
            expand_dirs_on_add=True,
            file_dialog_filter='ZIP/CBZ (*.zip *.cbz);;所有文件 (*)',
            file_dialog_title='添加漫画文件',
            dir_dialog_title='添加漫画作者文件夹（递归扫描 .zip / .cbz）',
            add_file_label='添加漫画文件…',
            add_dir_label='添加漫画作者文件夹…',
        )
        self._input_list.paths_changed.connect(self._on_inputs_changed)
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
        """主线程跑作者推导：``auto_author`` 直采，缺失 / 冲突按模式分派——
        ``_auto_mode`` 下用 :func:`auto_fallback` 静默回退，交互模式弹
        :class:`~module.manga.gui.widgets.author_choice.AuthorChoiceDialog`。

        返回 ``None`` 时基类 :meth:`~module.manga.gui.tabs.base_tab.BaseTab._on_scan`
        直接退出；auto 管线下必须在此自行 :meth:`_auto_finish` 收尾，否则下游
        会等不到 :attr:`auto_done` 而挂起。
        """
        paths = self._input_list.paths()
        if not paths:
            if self._auto_mode:
                self._auto_finish([])
            else:
                QMessageBox.warning(self, '提示', '请先添加文件或目录')
            return None

        if self._auto_mode:
            resolve_fn = auto_fallback
        else:
            # 闭包持有用户的"全部应用"规则：'parent' / 'bracket' / 未设置。
            # dialog 勾选后，后续待选文件若能从该来源直接取到作者就短路弹窗
            rule: dict[str, str] = {}

            def resolve_fn(path, deriv):
                src = rule.get('source')
                if src == 'parent' and deriv.parent_author:
                    return deriv.parent_author, ''
                if src == 'bracket' and deriv.bracket_author:
                    return deriv.bracket_author, deriv.bracket_publisher
                result = resolve_author_via_dialog(self, path, deriv)
                if result is None:
                    return None
                author, publisher, source = result
                if source:
                    rule['source'] = source
                return author, publisher

        # 漫画库索引（可选）：从 module 顶部工具条注入的 getter 拉当前路径；
        # 空字符串或无效目录都走"跳过规范化"分支（保留旧行为）
        normalize_author = None
        lib_root = self._get_library_root() if self._get_library_root else ''
        if lib_root:
            p = Path(lib_root)
            if p.is_dir():
                lib = load_or_scan(p)
                normalize_author = lib.resolve
            else:
                emit(f'⚠️ 漫画库根目录无效，跳过规范化: {lib_root}')

        inputs = derive_inputs(paths, resolve_fn=resolve_fn,
                               normalize_author=normalize_author)
        skipped = len(paths) - len(inputs)
        if skipped:
            reason = ('作者无法推导' if self._auto_mode
                      else '用户取消或未填作者')
            emit(f'⚠️ 已跳过 {skipped} 个文件（{reason}），未参与本次扫描')
        if not inputs:
            if self._auto_mode:
                self._auto_finish([])
            else:
                QMessageBox.information(
                    self, '提示',
                    '所选文件均无法确定作者，已全部跳过',
                )
            return None
        return inputs

    def _format_banner_target(self, target: Any) -> object:
        return f'已添加 {len(target)} 个文件'

    def _has_inputs(self) -> bool:
        return bool(self._input_list.paths())

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
        """编排器入口：仅收路径，不做推导——scan 阶段
        :meth:`_validate_scan_target` 会用 :func:`auto_fallback` 统一处理。
        """
        self._input_list.clear()
        usable = [Path(p) for p in paths
                  if Path(p).suffix.lower() in FILE_EXTS and Path(p).is_file()]
        self._input_list.add_paths(usable)

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
