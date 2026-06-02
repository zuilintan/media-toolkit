"""单个 :class:`~module.manga.core.models.MakeMetaPlan` 的完整详情对话框。

布局：

- 顶部文件名 + 状态标签
- :class:`~PySide6.QtWidgets.QTableWidget` 三列（Tag / 旧 / 新），新列对差异行
  着色，对齐 LogView 的语义但摆脱等宽字符串拼接
- 底部 warnings / 出版商冲突 / encoding 行（按需可见）
- Close 按钮

模态弹窗，由 :class:`~module.manga.gui.widgets.make_meta_tree.MakeMetaTree`
的双击信号触发。
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

from module.manga.core.config import COMICINFO_TAGS
from module.manga.core.models import MakeMetaPlan

# 差异行新值底色：与 LogView 的红色高亮同语义、不同呈现（避免文本被 ANSI 控制）
_DIFF_BG = QColor('#3a2a2a')


class MakeMetaDetailDialog(QDialog):
    """单 plan 的完整 diff 表格弹窗（QTableWidget 实现）。

    :ivar apply_requested: 「执行写入」按钮点击时发出（仅对 writable + changed
        的 plan 显示）；具体写入由
        :class:`~module.manga.gui.tabs.make_meta_tab.MakeMetaTab` 统一处理，
        成功后会调 :meth:`accept` 关闭本对话框。
    """

    apply_requested = Signal(object)   # MakeMetaPlan

    def __init__(self, plan: MakeMetaPlan, parent=None) -> None:
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle(f'详情 — {plan.filename}')
        self.resize(820, 600)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── 头部：文件名 + 状态 ──────────────────────────────────────
        title = QLabel(f'📄 {plan.filename}')
        f = title.font(); f.setBold(True); title.setFont(f)
        lay.addWidget(title)

        lay.addWidget(QLabel(f'状态: {_status_label(plan)}'))

        # ── diff 表格 ────────────────────────────────────────────────
        table = QTableWidget(len(COMICINFO_TAGS), 3, self)
        table.setHorizontalHeaderLabels(['Tag', '旧值', '新值'])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)

        diff_brush = QBrush(_DIFF_BG)
        for row, tag in enumerate(COMICINFO_TAGS):
            ov = plan.existing_fields.get(tag, '')
            nv = plan.fields.get(tag, '')
            tag_item = QTableWidgetItem(tag)
            old_item = QTableWidgetItem(ov)
            new_item = QTableWidgetItem(nv)
            if ov != nv:
                bold = QFont(); bold.setBold(True)
                tag_item.setFont(bold)
                new_item.setFont(bold)
                new_item.setBackground(diff_brush)
                tag_item.setToolTip('该字段在新旧之间存在差异')
            for it in (old_item, new_item):
                it.setToolTip(it.text())   # 长值悬停看全
            table.setItem(row, 0, tag_item)
            table.setItem(row, 1, old_item)
            table.setItem(row, 2, new_item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        table.resizeRowsToContents()

        # 右键复制单元格内容（QTableWidget 默认无 Ctrl+C / 复制菜单）
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table = table

        lay.addWidget(table, 1)

        # ── 附加信息（按需显示）──────────────────────────────────────
        if plan.mi.warnings:
            lay.addWidget(QLabel(
                '🟡 警告: ' + '; '.join(plan.mi.warnings)
            ))
        if plan.pub_conflict:
            names = ', '.join(os.path.basename(p) for p in plan.pub_conflict)
            warn = QLabel(f'⛔ 出版商冲突文件: {names}')
            warn.setWordWrap(True)
            lay.addWidget(warn)
        cur_enc = plan.existing_encoding or '—'
        new_enc = plan.new_encoding
        enc_line = (f'{cur_enc} → {new_enc}' if cur_enc != new_enc
                    else cur_enc)
        lay.addWidget(QLabel(f'Encoding: {enc_line}'))

        # ── 底部按钮 ─────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        if plan.writable and plan.changed:
            apply_btn = QPushButton('执行写入', self)
            apply_btn.setToolTip('只对当前文件写入 ComicInfo.xml')
            apply_btn.setProperty('primary', True)
            apply_btn.clicked.connect(
                lambda: self.apply_requested.emit(self._plan)
            )
            btns.addButton(apply_btn, QDialogButtonBox.ActionRole)
        lay.addWidget(btns)

    # ── 右键菜单：复制单元格 ──────────────────────────────────────────
    def _on_table_context_menu(self, pos: QPoint) -> None:
        item = self._table.itemAt(pos)
        if item is None:
            return
        text = item.text()
        # 空值也允许复制（避免「为什么右键没反应」的疑惑）
        global_pos = self._table.viewport().mapToGlobal(pos)
        preview    = text if len(text) <= 30 else f'{text[:30]}…'
        label      = f'复制单元格：{preview}' if text else '复制单元格（空值）'

        menu = QMenu(self)
        act  = menu.addAction(label)
        chosen = menu.exec(global_pos)
        if chosen is act:
            QApplication.clipboard().setText(text)
            QToolTip.showText(global_pos, '✅ 已复制', self._table)


def _status_label(p: MakeMetaPlan) -> str:
    if not p.writable:
        return '⛔ 出版商冲突（跳过）'
    if not p.changed:
        return '─ 已是最新（无需写入）'
    if p.existing_xml is None:
        return '✨ 新增 ComicInfo.xml'
    return '✏️ 修改已有 ComicInfo.xml'
