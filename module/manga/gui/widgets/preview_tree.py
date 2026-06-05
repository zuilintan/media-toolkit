"""四个子命令 Tab 共用的预览树基类 :class:`PreviewTreeBase`。

承担共性:

- 顶层组 + 占位 child 懒加载（避免万级 plan 一次性 materialize 卡顿）
- 用户展开 / 折叠状态记忆 + 过滤回滚（filter 自身的 setExpanded 不污染）
- 顶部搜索框（外部传入）：按文件名 / 分组标题大小写不敏感子串过滤
- 列宽跨会话持久化 + 同进程内所有预览树之间实时同步（共享 key
  ``preview_tree.col_widths``，由 :class:`_ColWidthSync` 信号广播）
- 右键 → ``plan_apply_requested``、双击 → ``plan_double_clicked``、
  局部 :meth:`remove_plan` 单条执行成功后调用

子类只需重写 :meth:`_build_groups` / :meth:`_row_status_text` /
:meth:`_is_actionable` / :meth:`_plan_label`。
"""

from __future__ import annotations
from abc import abstractmethod
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from base.gui.config import get_config


# 子项 QTreeWidgetItem 上挂 plan 引用所用的 role
_PLAN_ROLE = Qt.UserRole + 1


class _ColWidthSync(QObject):
    """进程内列宽变更广播。

    任一 :class:`PreviewTreeBase` 实例被拖宽列时发出，其他实例同步应用，
    实现「在打包改列宽 → 命名 / 封面 / 元数据预览树立即跟上」。
    """

    widths_changed = Signal(list, object)   # widths, sender


# 模块级单例：所有预览树共享同一个广播器
_sync = _ColWidthSync()


class PreviewTreeBase(QTreeWidget):
    """预览导航树通用骨架：顶层 = 分组，子项 = 单个 plan。

    :ivar plan_double_clicked: 双击具体 plan 行时发出，参数为 plan 对象。
    :ivar plan_apply_requested: 在 plan 行右键 → 「执行」时发出；由
        :class:`~module.manga.gui.tabs.base_tab.BaseTab` 统一做 confirm /
        写入 / 状态刷新。
    """

    plan_double_clicked  = Signal(object)
    plan_apply_requested = Signal(object)

    #: 所有预览树共享同一份列宽配置，跨 Tab 同步
    _COL_WIDTHS_KEY: str = 'preview_tree.col_widths'

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(['分组 / 文件', '状态'])
        self.setColumnCount(2)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)

        self.itemExpanded.connect(self._on_expanded)
        self.itemCollapsed.connect(self._on_collapsed)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.header().sectionResized.connect(self._on_section_resized)

        # 各组的 plan 列表（构建时填，重建时清）
        self._groups: dict[QTreeWidgetItem, list[Any]] = {}
        # 已 materialize 出真子项的组
        self._populated: set[QTreeWidgetItem] = set()
        # 用户手动展开 / 折叠状态；filter 自身驱动的 setExpanded 经
        # _in_filter_update 屏蔽不计入。清空过滤词时按此回滚浏览上下文
        self._user_expanded: dict[QTreeWidgetItem, bool] = {}
        self._in_filter_update: bool = False
        # 当前过滤词（lower）
        self._filter_text: str = ''
        # 屏蔽外部同步触发的 sectionResized 反弹（避免广播环）
        self._applying_widths: bool = False

        self._restore_column_widths()
        _sync.widths_changed.connect(self._on_external_widths)

    # ── 子类钩子 ──────────────────────────────────────────────────────
    @abstractmethod
    def _build_groups(
        self, plans: list[Any],
    ) -> list[tuple[str, list[Any], bool]]:
        """返回 ``[(title, plans, expand_default), ...]``。

        ``title`` 末尾会被基类自动加 ``(count)``；``expand_default`` 仅作初次
        默认值，用户折叠 / 展开后由 :attr:`_user_expanded` 接管。
        """

    @abstractmethod
    def _row_status_text(self, plan: Any) -> str:
        """单个 plan 行右侧「状态」列的文本。"""

    @abstractmethod
    def _is_actionable(self, plan: Any) -> bool:
        """plan 是否可单条执行（决定右键菜单是否弹出）。"""

    def _plan_label(self, plan: Any) -> str:
        """子项左侧文本；默认取 ``plan.filename``。"""
        return plan.filename

    def _apply_action_text(self, plan: Any) -> str:
        """右键单条菜单文本。"""
        return f'执行：{self._plan_label(plan)}'

    # ── 公共 API ──────────────────────────────────────────────────────
    def set_plans(self, plans: list[Any]) -> None:
        """根据 plans 重建树。空列表会清空树。"""
        self.clear()
        self._groups.clear()
        self._populated.clear()
        self._user_expanded.clear()
        if not plans:
            return
        for title, gp, expand in self._build_groups(plans):
            if gp:
                self._add_group(title, gp, expand=expand)
        if self._filter_text:
            self._apply_filter_now()

    def apply_filter(self, text: str) -> None:
        """按子串过滤可见项；空串恢复全部。

        匹配规则（大小写不敏感）：

        - 分组标题命中 → 该组全部子项可见
        - 否则按 ``_plan_label`` 匹配；至少一项命中则该组可见，只展示命中子项
        - 全部不命中 → 该组隐藏

        命中子项时若组尚未 materialize，立即填充（不再惰性），避免
        「展开后才发现没命中」。
        """
        self._filter_text = text.strip().lower()
        self._apply_filter_now()

    def remove_plan(self, plan: Any) -> None:
        """从树中移除指定 plan：保留过滤 / 展开状态，避免整树重建。

        同一 plan 可能出现在多个组里（如 changed 组 + 警告组），逐组扫描。
        组内最后一项被移除 → 整组从顶层移除。
        """
        for group in list(self._groups.keys()):
            plans = self._groups[group]
            if plan not in plans:
                continue
            new_plans = [p for p in plans if p is not plan]
            self._groups[group] = new_plans

            title = group.text(0)
            idx   = title.rfind(' (')
            if idx > 0:
                group.setText(0, f'{title[:idx]} ({len(new_plans)})')

            if group in self._populated:
                for j in range(group.childCount()):
                    child = group.child(j)
                    if child.data(0, _PLAN_ROLE) is plan:
                        group.removeChild(child)
                        break

            if not new_plans:
                top_idx = self.indexOfTopLevelItem(group)
                if top_idx >= 0:
                    self.takeTopLevelItem(top_idx)
                self._groups.pop(group, None)
                self._populated.discard(group)

    # ── 构建 ──────────────────────────────────────────────────────────
    def _add_group(
        self, title: str, plans: list[Any], *, expand: bool,
    ) -> None:
        item = QTreeWidgetItem(self, [f'{title} ({len(plans)})', ''])
        item.setExpanded(expand)
        self._groups[item] = plans
        if plans:
            # 懒加载占位：用户展开时再填真子项
            QTreeWidgetItem(item, ['…', ''])

    def _populate(self, parent: QTreeWidgetItem) -> None:
        if parent in self._populated:
            return
        plans = self._groups.get(parent)
        if not plans:
            return
        parent.takeChildren()
        for p in plans:
            child = QTreeWidgetItem(
                parent, [self._plan_label(p), self._row_status_text(p)],
            )
            child.setData(0, _PLAN_ROLE, p)
        self._populated.add(parent)

    # ── 过滤 ──────────────────────────────────────────────────────────
    def _apply_filter_now(self) -> None:
        self._in_filter_update = True
        try:
            text = self._filter_text
            for group, plans in self._groups.items():
                if not text:
                    group.setHidden(False)
                    if group in self._populated:
                        for j in range(group.childCount()):
                            group.child(j).setHidden(False)
                    group.setExpanded(self._user_expanded.get(group, False))
                    continue

                title_match = text in group.text(0).lower()
                if title_match:
                    group.setHidden(False)
                    if group in self._populated:
                        for j in range(group.childCount()):
                            group.child(j).setHidden(False)
                    group.setExpanded(True)
                    continue

                matching = {
                    id(p) for p in plans
                    if text in self._plan_label(p).lower()
                }
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
        finally:
            self._in_filter_update = False

    # ── 列宽持久化 + 跨树同步 ────────────────────────────────────────
    def _apply_widths(self, widths: list) -> None:
        """把 ``widths`` 套到当前 header；屏蔽期间 ``sectionResized`` 不回写。"""
        self._applying_widths = True
        try:
            for i, w in enumerate(widths):
                if i < self.columnCount() and isinstance(w, int) and w > 0:
                    self.setColumnWidth(i, w)
        finally:
            self._applying_widths = False

    def _restore_column_widths(self) -> None:
        widths = get_config().get(self._COL_WIDTHS_KEY)
        if not widths or not isinstance(widths, list):
            return
        self._apply_widths(widths)

    def _on_section_resized(self, *_args) -> None:
        if self._applying_widths:
            return                  # 外部同步触发的 resize，不回写不广播
        widths = [self.columnWidth(i) for i in range(self.columnCount())]
        get_config().set(self._COL_WIDTHS_KEY, widths)
        _sync.widths_changed.emit(widths, self)

    def _on_external_widths(self, widths: list, sender: object) -> None:
        """收到其他预览树发出的列宽变更：本树非源头就跟随应用。"""
        if sender is self:
            return
        self._apply_widths(widths)

    # ── 信号回调 ──────────────────────────────────────────────────────
    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        if item not in self._groups:
            return
        if item not in self._populated:
            self._populate(item)
        if not self._in_filter_update:
            self._user_expanded[item] = True

    def _on_collapsed(self, item: QTreeWidgetItem) -> None:
        if item in self._groups and not self._in_filter_update:
            self._user_expanded[item] = False

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        plan = item.data(0, _PLAN_ROLE)
        if plan is not None:
            self.plan_double_clicked.emit(plan)

    # ── 右键菜单：单条执行 ─────────────────────────────────────────────
    def contextMenuEvent(self, event) -> None:   # noqa: N802 — Qt API 命名
        item = self.itemAt(event.pos())
        if item is None:
            return
        plan = item.data(0, _PLAN_ROLE)
        if plan is None:
            return                  # 分组节点不响应
        if not self._is_actionable(plan):
            return                  # 不可执行 → 不弹菜单，避免「点了没反应」
        menu = QMenu(self)
        act  = menu.addAction(self._apply_action_text(plan))
        if menu.exec(event.globalPos()) is act:
            self.plan_apply_requested.emit(plan)
