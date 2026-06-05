"""``make_cover`` 预览树（继承
:class:`~module.manga.gui.widgets.preview_tree.PreviewTreeBase`）。

分组（顶层从前往后，互斥）：

- ✨ 新增封面 ─ ``writable && changed && !replaced``
- 🔁 替换现有 ─ ``writable && changed && replaced``
- ─ 无变化 ─ ``writable && !changed``
- ⛔ 错误 ─ ``!writable``
"""

from __future__ import annotations

from module.manga.core.models import MakeCoverPlan
from module.manga.gui.widgets.preview_tree import PreviewTreeBase


class MakeCoverTree(PreviewTreeBase):
    def _build_groups(
        self, plans: list[MakeCoverPlan],
    ) -> list[tuple[str, list[MakeCoverPlan], bool]]:
        new       = [p for p in plans if p.writable and p.changed and not p.replaced]
        replaced  = [p for p in plans if p.writable and p.changed and p.replaced]
        unchanged = [p for p in plans if p.writable and not p.changed]
        errors    = [p for p in plans if not p.writable]
        return [
            ('✨ 新增封面', new,       False),
            ('🔁 替换现有', replaced,  False),
            ('─ 无变化',    unchanged, False),
            ('⛔ 错误',     errors,    False),
        ]

    def _row_status_text(self, p: MakeCoverPlan) -> str:
        if not p.writable:
            return f'⛔ {p.error or "无源图"}'
        if not p.changed:
            return '─ 已是最新'
        return '🔁 替换' if p.replaced else '✨ 新增'

    def _is_actionable(self, p: MakeCoverPlan) -> bool:
        return p.writable and p.changed

    def _apply_action_text(self, p: MakeCoverPlan) -> str:
        return f'生成封面：{p.filename}'
