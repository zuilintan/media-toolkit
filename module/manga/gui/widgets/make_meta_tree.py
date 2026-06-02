"""``make_meta`` 预览的可导航树视图，作为 LogView 文本预览的对照面板。

LogView 是流式文本，万级 plan 时只能采样展示；本树视图把全部 plan 按
**与 LogView 一致的签名分组**组织成可折叠列表，让用户能：

- 一眼看到所有分组及计数（与 LogView 总览一致）
- 展开任一组浏览其下完整文件列表（不受 LogView blockCount 限制）
- 双击单条 → 弹模态详情对话框，看完整 diff 表格

实现要点：

- 顶层组节点用占位（``QTreeWidgetItem`` child=0）+ ``itemExpanded`` 信号
  懒加载，避免一次构建 10k+ 子节点导致 UI 卡顿
- 双击发出 :attr:`MakeMetaTree.plan_double_clicked` 信号；Tab 层负责弹窗
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from module.manga.core.models import MakeMetaPlan
from module.manga.presentation.view import diff_signature, format_signature


# QTreeWidgetItem.data() 用的 role 常量；存放 plan 引用，供双击回调取出
_PLAN_ROLE = Qt.UserRole + 1


class MakeMetaTree(QTreeWidget):
    """预览导航树：顶层 = 分组，子项 = 单个 plan。

    :ivar plan_double_clicked: 双击具体 plan 行时发出，参数为 :class:`MakeMetaPlan`。
    """

    plan_double_clicked = Signal(object)   # MakeMetaPlan

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(['分组 / 文件', '状态'])
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)         # 提速 + 减抖
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)

        self.itemExpanded.connect(self._on_expanded)
        self.itemDoubleClicked.connect(self._on_double_clicked)

        # 记录未懒加载的组：item -> list[plans]
        self._pending: dict[QTreeWidgetItem, list[MakeMetaPlan]] = {}

    # ── 公共 API ──────────────────────────────────────────────────────
    def set_plans(self, plans: list[MakeMetaPlan]) -> None:
        """根据 plans 重建树。空列表会清空树。"""
        self.clear()
        self._pending.clear()
        if not plans:
            return

        changed   = [p for p in plans if p.writable and p.changed]
        unchanged = [p for p in plans if p.writable and not p.changed]
        conflict  = [p for p in plans if not p.writable]
        warns     = [p for p in plans if p.mi.warnings]

        # ── 改动组（按签名分桶，count 降序）────────────────────────────
        groups: dict[tuple[bool, frozenset[str]], list[MakeMetaPlan]] = {}
        for p in changed:
            groups.setdefault(diff_signature(p), []).append(p)

        for (is_new, keys), gp in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            label = format_signature(is_new, keys)
            icon  = '✨' if is_new else '✏️'
            self._add_group(f'{icon} {label}', gp, expand=False)

        if conflict:
            self._add_group('⛔ 出版商冲突', conflict, expand=False)
        if warns:
            # 警告与改动可重叠，独立分组方便用户专项审查
            self._add_group('🟡 有警告', warns, expand=False)
        if unchanged:
            self._add_group('─ 无需处理', unchanged, expand=False)

        # 列宽自动适应首列（限制最大宽度防止挤掉状态列）
        self.resizeColumnToContents(0)

    # ── 构建 ──────────────────────────────────────────────────────────
    def _add_group(
        self,
        title: str,
        plans: list[MakeMetaPlan],
        *,
        expand: bool,
    ) -> None:
        item = QTreeWidgetItem(self, [f'{title} ({len(plans)})', ''])
        item.setExpanded(expand)
        if plans:
            # 懒加载：先挂一个占位 child，等用户展开时再填真子项
            QTreeWidgetItem(item, ['…', ''])
            self._pending[item] = plans

    def _populate(self, parent: QTreeWidgetItem) -> None:
        plans = self._pending.pop(parent, None)
        if plans is None:
            return
        # 先清掉占位子项
        parent.takeChildren()
        for p in plans:
            child = QTreeWidgetItem(parent, [p.filename, _status_text(p)])
            child.setData(0, _PLAN_ROLE, p)

    # ── 信号回调 ──────────────────────────────────────────────────────
    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        if item in self._pending:
            self._populate(item)

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        plan = item.data(0, _PLAN_ROLE)
        if isinstance(plan, MakeMetaPlan):
            self.plan_double_clicked.emit(plan)


def _status_text(p: MakeMetaPlan) -> str:
    """单个 plan 行的状态列：基础类别 + 警告徽标。"""
    if not p.writable:
        base = '⛔ 冲突'
    elif not p.changed:
        base = '─ 已是最新'
    elif p.existing_xml is None:
        base = '✨ 新增'
    else:
        base = '✏️ 修改'
    if p.mi.warnings:
        base += ' 🟡'
    return base
