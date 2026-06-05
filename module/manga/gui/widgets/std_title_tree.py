"""``std_title`` 预览树（继承
:class:`~module.manga.gui.widgets.preview_tree.PreviewTreeBase`）。

分组（顶层从前往后）：

- 📝 可重命名 ─ ``changed && !needs_review``
- 🟡 需审核 ─ ``needs_review``（独立组方便专项审查）
- 🟡 有警告 ─ ``info.warnings`` 非空（与改动可重叠，独立分组）
- ─ 无变化 ─ ``!changed``
"""

from __future__ import annotations

from module.manga.core.models import StdTitlePlan
from module.manga.gui.widgets.preview_tree import PreviewTreeBase


class StdTitleTree(PreviewTreeBase):
    def _build_groups(
        self, plans: list[StdTitlePlan],
    ) -> list[tuple[str, list[StdTitlePlan], bool]]:
        changed   = [p for p in plans if p.changed and not p.needs_review]
        reviews   = [p for p in plans if p.needs_review]
        warns     = [p for p in plans if p.info and p.info.warnings]
        unchanged = [p for p in plans if not p.changed]
        return [
            ('📝 可重命名', changed,   False),
            ('🟡 需审核',  reviews,   False),
            ('🟡 有警告',  warns,     False),
            ('─ 无变化',   unchanged, False),
        ]

    def _plan_label(self, p: StdTitlePlan) -> str:
        return p.old_name

    def _row_status_text(self, p: StdTitlePlan) -> str:
        if p.needs_review:
            base = '🟡 需审核'
        elif not p.changed:
            base = '─ 无变化'
        else:
            base = '📝 改名'
        if p.info and p.info.warnings:
            base += ' 🟡'
        return base

    def _is_actionable(self, p: StdTitlePlan) -> bool:
        return p.changed and not p.needs_review

    def _apply_action_text(self, p: StdTitlePlan) -> str:
        return f'规范标题：{p.old_name}'
