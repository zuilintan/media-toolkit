"""``pack_pic`` 预览树（继承
:class:`~module.manga.gui.widgets.preview_tree.PreviewTreeBase`）。

分组（顶层从前往后）：

- 📦 单层 ─ ``writable && kind == 'flat'``
- 🗂 嵌套 ─ ``writable && kind == 'nested'``
- 🔁 覆盖现有 zip ─ ``writable && zip_exists``（独立组方便专项审查）
- ─ 跳过 ─ ``not writable``
"""

from __future__ import annotations

from module.manga.core.models import PackPicPlan
from module.manga.gui.widgets.preview_tree import PreviewTreeBase


class PackPicTree(PreviewTreeBase):
    _COL_WIDTHS_KEY = 'pack_pic.tree_col_widths'

    def _build_groups(
        self, plans: list[PackPicPlan],
    ) -> list[tuple[str, list[PackPicPlan], bool]]:
        flat     = [p for p in plans if p.writable and p.kind == 'flat']
        nested   = [p for p in plans if p.writable and p.kind == 'nested']
        replaced = [p for p in plans if p.writable and p.zip_exists]
        skipped  = [p for p in plans if not p.writable]
        return [
            ('📦 单层',         flat,     False),
            ('🗂 嵌套',         nested,   False),
            ('🔁 覆盖现有 zip', replaced, False),
            ('─ 跳过',          skipped,  False),
        ]

    def _plan_label(self, p: PackPicPlan) -> str:
        return p.name

    def _row_status_text(self, p: PackPicPlan) -> str:
        if not p.writable:
            return f'⛔ {p.error or "无图片"}'
        kind_tag = f'嵌套×{p.n_subdirs}' if p.kind == 'nested' else '单层'
        suffix = ' 🔁' if p.zip_exists else ''
        return f'{kind_tag}  {len(p.renames)} 张{suffix}'

    def _is_actionable(self, p: PackPicPlan) -> bool:
        return p.writable

    def _apply_action_text(self, p: PackPicPlan) -> str:
        return f'打包：{p.name}'
