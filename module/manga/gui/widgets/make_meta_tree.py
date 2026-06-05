"""``make_meta`` 预览的可导航树视图（继承
:class:`~module.manga.gui.widgets.preview_tree.PreviewTreeBase`）。

作为 LogView 文本预览的对照面板：LogView 是流式文本，万级 plan 时只能采样
展示；本树视图把全部 plan 按 **与 LogView 一致的签名分组** 组织成可折叠列表。

分组逻辑（顶层从前往后）：

- 改动组：按 ``diff_signature(p)`` 分桶，count 降序
- 🟡 有警告：``p.mi.warnings`` 非空（与改动可重叠，独立分组方便专项审查）
- ─ 无需处理：``not changed``
"""

from __future__ import annotations

from module.manga.core.models import MakeMetaPlan
from module.manga.gui.widgets.preview_tree import PreviewTreeBase
from module.manga.presentation.view import diff_signature, format_signature


class MakeMetaTree(PreviewTreeBase):
    def _build_groups(
        self, plans: list[MakeMetaPlan],
    ) -> list[tuple[str, list[MakeMetaPlan], bool]]:
        changed   = [p for p in plans if p.changed]
        unchanged = [p for p in plans if not p.changed]
        warns     = [p for p in plans if p.mi.warnings]

        # 按签名分桶，count 降序——与 LogView 输出顺序一致
        buckets: dict[tuple[bool, frozenset[str]], list[MakeMetaPlan]] = {}
        for p in changed:
            buckets.setdefault(diff_signature(p), []).append(p)

        out: list[tuple[str, list[MakeMetaPlan], bool]] = []
        for (is_new, keys), gp in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            icon  = '✨' if is_new else '✏️'
            label = format_signature(is_new, keys)
            out.append((f'{icon} {label}', gp, False))
        out.append(('🟡 有警告',     warns,     False))
        out.append(('─ 无需处理',    unchanged, False))
        return out

    def _row_status_text(self, p: MakeMetaPlan) -> str:
        if not p.changed:
            base = '─ 已是最新'
        elif p.existing_xml is None:
            base = '✨ 新增'
        else:
            base = '✏️ 修改'
        if p.mi.warnings:
            base += ' 🟡'
        return base

    def _is_actionable(self, p: MakeMetaPlan) -> bool:
        return p.changed

    def _apply_action_text(self, p: MakeMetaPlan) -> str:
        return f'生成元数据：{p.filename}'
