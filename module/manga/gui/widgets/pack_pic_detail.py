"""单个 :class:`~module.manga.core.models.PackPicPlan` 的详情对话框。

布局：

- 顶部 src_dir + 状态标签
- ``zip:`` 目标路径行
- 图片列表表格（旧名 → 新名 两列；nested 模式带子目录前缀）
- ``extras`` 警告区（按需可见）
- 「打包」（writable 时）+ Close
"""

from __future__ import annotations
import os

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QMenu, QPushButton, QTableWidget, QTableWidgetItem, QToolTip,
    QVBoxLayout,
)

from module.manga.core.models import PackPicPlan


class PackPicDetailDialog(QDialog):
    """单 plan 的完整打包详情弹窗。

    :ivar apply_requested: 「打包」按钮点击时发出（仅 writable 时显示）；
        具体写入由 :class:`~module.manga.gui.tabs.pack_pic_tab.PackPicTab`
        统一处理，成功后会调 :meth:`accept` 关闭本对话框。
    """

    apply_requested = Signal(object)   # PackPicPlan

    def __init__(self, plan: PackPicPlan, parent=None) -> None:
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle(f'详情 — {plan.name}')
        self.resize(720, 560)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── 头部 ────────────────────────────────────────────────────
        title = QLabel(f'📁 {plan.src_dir}')
        f = title.font(); f.setBold(True); title.setFont(f)
        title.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(QLabel(f'状态: {_status_label(plan)}'))
        lay.addWidget(QLabel(f'zip:  {plan.zip_path}'))

        n_pic   = len(plan.renames)
        renamed = plan.n_renamed
        info_line = f'图片: {n_pic} 张（实际改名 {renamed} 张）'
        if plan.kind == 'nested':
            info_line += f'；嵌套子目录: {plan.n_subdirs}'
        lay.addWidget(QLabel(info_line))

        # ── 改名表格 ────────────────────────────────────────────────
        table = QTableWidget(len(plan.renames), 2, self)
        table.setHorizontalHeaderLabels(['旧名', '新名'])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)

        bold = QFont(); bold.setBold(True)
        for r, (old, new) in enumerate(plan.renames):
            old_item = QTableWidgetItem(old)
            new_item = QTableWidgetItem(new)
            old_item.setToolTip(old)
            new_item.setToolTip(new)
            if old != new:
                new_item.setFont(bold)
            table.setItem(r, 0, old_item)
            table.setItem(r, 1, new_item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        table.resizeRowsToContents()

        # 右键复制单元格
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table = table

        lay.addWidget(table, 1)

        # ── extras 警告（按需）─────────────────────────────────────
        if plan.extras:
            preview_extras = ', '.join(plan.extras[:5])
            more = f'，… 等 {len(plan.extras)} 项' if len(plan.extras) > 5 else ''
            warn = QLabel(
                f'🟡 {len(plan.extras)} 项非图片不进 zip，将随源目录一并删除: '
                f'{preview_extras}{more}'
            )
            warn.setWordWrap(True)
            lay.addWidget(warn)

        if plan.zip_exists:
            lay.addWidget(QLabel(f'🔁 目标 zip 已存在，写入会覆盖: {os.path.basename(plan.zip_path)}'))

        # ── 底部按钮 ────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        if plan.writable:
            apply_btn = QPushButton('打包', self)
            apply_btn.setToolTip('只对当前单位打包并删除源目录')
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


def _status_label(p: PackPicPlan) -> str:
    if not p.writable:
        return f'⛔ 跳过 — {p.error or "无图片"}'
    kind_tag = f'嵌套×{p.n_subdirs}' if p.kind == 'nested' else '单层'
    note = '；🔁 将覆盖现有 zip' if p.zip_exists else ''
    return f'✅ 可打包（{kind_tag}）{note}'
