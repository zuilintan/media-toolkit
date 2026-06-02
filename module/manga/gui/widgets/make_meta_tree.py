"""``make_meta`` 预览的可导航树视图，作为 LogView 文本预览的对照面板。

LogView 是流式文本，万级 plan 时只能采样展示；本树视图把全部 plan 按
**与 LogView 一致的签名分组**组织成可折叠列表，让用户能：

- 一眼看到所有分组及计数（与 LogView 总览一致）
- 展开任一组浏览其下完整文件列表（不受 LogView blockCount 限制）
- 双击单条 → 弹模态详情对话框，看完整 diff 表格
- 顶部搜索框：按文件名 / 分组标题大小写不敏感子串过滤

实现要点：

- 顶层组节点用占位（``QTreeWidgetItem`` child=0）+ ``itemExpanded`` 信号
  懒加载，避免一次构建 10k+ 子节点导致 UI 卡顿
- 过滤时若需匹配单条文件名，惰性强制 materialize 一次（避免每次过滤都重建）
- 列宽通过 :func:`~base.gui.config.get_config` 跨会话持久化
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from base.gui.config import get_config
from module.manga.core.models import MakeMetaPlan
from module.manga.presentation.view import diff_signature, format_signature


# QTreeWidgetItem.data() 用的 role 常量；存放 plan 引用，供双击回调取出
_PLAN_ROLE = Qt.UserRole + 1

_COL_WIDTHS_KEY = 'make_meta.tree_col_widths'


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
        self.header().sectionResized.connect(self._on_section_resized)

        # 所有组的 plan 列表（构建时填，重建时清）
        self._groups: dict[QTreeWidgetItem, list[MakeMetaPlan]] = {}
        # 已 materialize 出真子项的组
        self._populated: set[QTreeWidgetItem] = set()
        # 当前过滤词（lower）
        self._filter_text: str = ''

        self._restore_column_widths()

    # ── 公共 API ──────────────────────────────────────────────────────
    def set_plans(self, plans: list[MakeMetaPlan]) -> None:
        """根据 plans 重建树。空列表会清空树。"""
        self.clear()
        self._groups.clear()
        self._populated.clear()
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

        # 应用既有过滤词（若用户重新扫描时搜索框仍有值）
        if self._filter_text:
            self._apply_filter_now()

    def apply_filter(self, text: str) -> None:
        """按子串过滤可见项；空串恢复全部。

        匹配规则（大小写不敏感）：

        - 分组标题命中 → 该组全部子项可见
        - 否则按文件名匹配；至少一项命中则该组可见，只展示命中子项
        - 全部不命中 → 该组隐藏

        命中子项时若组尚未 materialize，立即填充（不再惰性），避免「展开后才发现没命中」。
        """
        self._filter_text = text.strip().lower()
        self._apply_filter_now()

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
        self._groups[item] = plans
        if plans:
            # 懒加载：先挂一个占位 child，等用户展开时再填真子项
            QTreeWidgetItem(item, ['…', ''])

    def _populate(self, parent: QTreeWidgetItem) -> None:
        if parent in self._populated:
            return
        plans = self._groups.get(parent)
        if not plans:
            return
        parent.takeChildren()   # 清掉占位
        for p in plans:
            child = QTreeWidgetItem(parent, [p.filename, _status_text(p)])
            child.setData(0, _PLAN_ROLE, p)
        self._populated.add(parent)

    # ── 过滤 ──────────────────────────────────────────────────────────
    def _apply_filter_now(self) -> None:
        text = self._filter_text
        for group, plans in self._groups.items():
            if not text:
                group.setHidden(False)
                if group in self._populated:
                    for j in range(group.childCount()):
                        group.child(j).setHidden(False)
                group.setExpanded(False)   # 复位
                continue

            title_match = text in group.text(0).lower()
            if title_match:
                group.setHidden(False)
                if group in self._populated:
                    for j in range(group.childCount()):
                        group.child(j).setHidden(False)
                group.setExpanded(True)
                continue

            # 文件名匹配 → 需要 materialize
            matching = {id(p) for p in plans if text in p.filename.lower()}
            if not matching:
                group.setHidden(True)
                continue
            group.setHidden(False)
            self._populate(group)
            for j in range(group.childCount()):
                child = group.child(j)
                plan  = child.data(0, _PLAN_ROLE)
                child.setHidden(id(plan) not in matching)
            group.setExpanded(True)

    # ── 列宽持久化 ────────────────────────────────────────────────────
    def _restore_column_widths(self) -> None:
        widths = get_config().get(_COL_WIDTHS_KEY)
        if not widths or not isinstance(widths, list):
            return
        for i, w in enumerate(widths):
            if i < self.columnCount() and isinstance(w, int) and w > 0:
                self.setColumnWidth(i, w)

    def _on_section_resized(self, *_args) -> None:
        widths = [self.columnWidth(i) for i in range(self.columnCount())]
        get_config().set(_COL_WIDTHS_KEY, widths)

    # ── 信号回调 ──────────────────────────────────────────────────────
    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        if item in self._groups and item not in self._populated:
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
