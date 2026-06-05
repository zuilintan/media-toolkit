"""单个 :class:`~module.manga.core.models.StdTitlePlan` 的详情对话框。

布局：

- 顶部源文件路径 + 状态标签
- 旧名 / 新名 两列表格（差异时新名红底加粗）
- 归入目录 + 旧标识清理（按需）
- MangaInfo 解析字段表（作者 / 社团 / 主标题 / 卷 / 话 / 系列 / 翻译 / 语言 / 章节标题 / 修饰）
- warnings 行（按需）
- 「重命名」（可执行时）+ Close
"""

from __future__ import annotations
import os

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QMenu, QPushButton, QTableWidget, QTableWidgetItem, QToolTip,
    QVBoxLayout,
)

from module.manga.core.models import StdTitlePlan

# 与 make_meta_detail 对齐的新值高亮色
_NEW_BG = QColor('#3a2a2a')


class StdTitleDetailDialog(QDialog):
    """单 plan 的完整详情弹窗。

    :ivar apply_requested: 「重命名」按钮点击时发出（仅 ``changed && !needs_review`` 显示）。
    """

    apply_requested = Signal(object)   # StdTitlePlan

    def __init__(self, plan: StdTitlePlan, parent=None) -> None:
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle(f'详情 — {plan.old_name}')
        self.resize(720, 560)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── 头部 ────────────────────────────────────────────────────
        title = QLabel(f'📄 {plan.src_path}')
        f = title.font(); f.setBold(True); title.setFont(f)
        title.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(QLabel(f'状态: {_status_label(plan)}'))

        # ── 字段表 ──────────────────────────────────────────────────
        rows: list[tuple[str, str, bool]] = []  # (label, value, highlight_new)
        rows.append(('旧名', plan.old_name, False))
        if plan.old_name != plan.new_name:
            rows.append(('新名', plan.new_name, True))
        else:
            rows.append(('新名', plan.new_name, False))
        rows.append(('归入目录', _author_dir_display(plan), False))
        if plan.legacy_publisher_txt:
            rows.append(('待清理', os.path.basename(plan.legacy_publisher_txt), False))

        mi = plan.info
        if mi is not None:
            rows.append(('作者', mi.author, False))
            if mi.publisher:
                rows.append(('社团', mi.publisher, False))
            rows.append(('主标题', mi.main_title, False))
            if mi.volume is not None:
                rows.append(('卷', str(mi.volume), False))
            if mi.chapter is not None:
                rows.append(('话', str(mi.chapter), False))
            if mi.chapter_title:
                rows.append(('章节标题', mi.chapter_title, False))
            if mi.series:
                rows.append(('系列', mi.series, False))
            if mi.translation:
                rows.append(('翻译', mi.translation, False))
            rows.append(('语言', mi.language or '—', False))
            modifiers = []
            if mi.is_uncensored:  modifiers.append('无修')
            if mi.is_colorized:   modifiers.append('全彩')
            if mi.is_ongoing:     modifiers.append('连载')
            if mi.part_tag:       modifiers.append(mi.part_tag)
            if modifiers:
                rows.append(('修饰', ' / '.join(modifiers), False))

        table = QTableWidget(len(rows), 2, self)
        table.setHorizontalHeaderLabels(['字段', '值'])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)

        bold      = QFont(); bold.setBold(True)
        new_brush = QBrush(_NEW_BG)
        for r, (lab, val, hl) in enumerate(rows):
            lab_item = QTableWidgetItem(lab)
            val_item = QTableWidgetItem(val)
            val_item.setToolTip(val)
            if hl:
                lab_item.setFont(bold)
                val_item.setFont(bold)
                val_item.setBackground(new_brush)
            table.setItem(r, 0, lab_item)
            table.setItem(r, 1, val_item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        table.resizeRowsToContents()

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table = table

        lay.addWidget(table, 1)

        # ── 警告（按需）─────────────────────────────────────────────
        if mi is not None and mi.warnings:
            warn = QLabel('🟡 警告: ' + '; '.join(mi.warnings))
            warn.setWordWrap(True)
            lay.addWidget(warn)

        # ── 底部按钮 ────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        if plan.changed and not plan.needs_review:
            apply_btn = QPushButton('重命名', self)
            apply_btn.setToolTip('只对当前文件执行重命名')
            apply_btn.setProperty('primary', True)
            apply_btn.clicked.connect(
                lambda: self.apply_requested.emit(self._plan)
            )
            btns.addButton(apply_btn, QDialogButtonBox.ActionRole)
        lay.addWidget(btns)

    # ── 右键菜单：复制单元格 ─────────────────────────────────────────
    def _on_table_context_menu(self, pos: QPoint) -> None:
        item = self._table.itemAt(pos)
        if item is None:
            return
        text       = item.text()
        global_pos = self._table.viewport().mapToGlobal(pos)
        preview    = text if len(text) <= 30 else f'{text[:30]}…'
        label      = f'复制单元格：{preview}' if text else '复制单元格（空值）'

        menu = QMenu(self)
        act  = menu.addAction(label)
        chosen = menu.exec(global_pos)
        if chosen is act:
            QApplication.clipboard().setText(text)
            QToolTip.showText(global_pos, '✅ 已复制', self._table)


def _status_label(p: StdTitlePlan) -> str:
    if p.needs_review:
        return '🟡 需审核（主标题过短）'
    if not p.changed:
        return '─ 无变化'
    return '📝 待重命名'


def _author_dir_display(p: StdTitlePlan) -> str:
    """归入目录展示：父目录未变时显示 ``./``，否则显示作者子目录名。"""
    src_parent = os.path.dirname(p.src_path)
    if os.path.normcase(src_parent) == os.path.normcase(p.author_dir):
        return p.author_dir
    return f'./{os.path.basename(p.author_dir)}/  (将新建)'
