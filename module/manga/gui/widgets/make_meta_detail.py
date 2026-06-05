"""单个 :class:`~module.manga.core.models.MakeMetaPlan` 的完整详情对话框。

布局：

- 顶部文件名 + 状态标签
- :class:`~PySide6.QtWidgets.QTableWidget` 两列（标签 / 值）。无差异 tag 占 1 行；
  有差异 tag 占 2 行（旧上 / 新下），标签列 ``setSpan(row, 0, 2, 1)`` 跨 2 行
  合并，旧 / 新值上下对齐方便逐字符比对，用底色区分（无需文字标识）
- 底部 warnings / encoding 行（按需可见）
- 「执行写入」（有变化时）+ Close

模态弹窗，由 :class:`~module.manga.gui.widgets.make_meta_tree.MakeMetaTree`
的双击信号触发。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QMenu, QPushButton, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QToolTip, QVBoxLayout,
)

from module.manga.core.config import COMICINFO_TAGS
from module.manga.core.models import MakeMetaPlan

# 差异行底色：
# - 新值（高亮变更）：偏红，对应 LogView 中 highlight_diff 的 RED 语义
# - 旧值（参照对照）：偏暗中性色，凸显二者不同但视觉上不喧宾夺主
_NEW_BG = QColor('#3a2a2a')
_OLD_BG = QColor('#262c34')
# Tag 之间的分隔线颜色（与全局 palette.BORDER 对齐）
_TAG_BORDER = QColor('#363c45')


class _TagBoundaryDelegate(QStyledItemDelegate):
    """画两类细线：

    - 标签起始行上方画水平线（多行合并的 tag 与下一个 tag 明显分隔）；
      判定规则：标签列（0 列）该行的文本非空 → 此行是某 tag 的起始行；
      差异行的「新值」行标签列为空（被 setSpan 合并隐藏），不画线
    - 标签列右侧画竖线（列间分隔，showGrid=False 下手动补）
    """

    def paint(self, painter, option, index) -> None:   # noqa: N802 — Qt API 命名
        super().paint(painter, option, index)
        table = self.parent()
        row, col = index.row(), index.column()
        r = option.rect

        painter.save()
        pen = QPen(_TAG_BORDER)
        pen.setWidth(1)
        painter.setPen(pen)

        # tag 边界横线
        if row > 0 and table is not None:
            head = table.item(row, 0)
            if head is not None and head.text():
                painter.drawLine(r.topLeft(), r.topRight())

        # 列间竖线（仅标签列右侧）
        if col == 0:
            painter.drawLine(r.topRight(), r.bottomRight())

        painter.restore()


class MakeMetaDetailDialog(QDialog):
    """单 plan 的完整 diff 表格弹窗（QTableWidget 实现）。

    :ivar apply_requested: 「执行写入」按钮点击时发出（仅对 changed 的 plan
        显示）；具体写入由
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
        # 先扁平化为行列表：无差异 tag → 1 行；差异 tag → 2 行（旧上 / 新下），
        # Tag 列稍后用 setSpan 跨 2 行合并，使旧 / 新值在「值」列上下对齐
        rows: list[tuple[str, str, str]] = []   # (tag, value, kind: ''/'old'/'new')
        spans: list[int] = []                   # 跨 2 行合并的起始行索引
        for tag in COMICINFO_TAGS:
            ov = plan.existing_fields.get(tag, '')
            nv = plan.fields.get(tag, '')
            if ov == nv:
                rows.append((tag, ov, ''))
            else:
                spans.append(len(rows))
                rows.append((tag, ov, 'old'))
                rows.append(('',  nv, 'new'))

        table = QTableWidget(len(rows), 2, self)
        table.setHorizontalHeaderLabels(['标签', '值'])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        # 不开按行交替色：跨行合并后「按行」alternating 反而混淆同一 tag 的两行
        # 改用 _TagBoundaryDelegate 在 tag 边界画细线，按语义分组
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setItemDelegate(_TagBoundaryDelegate(table))

        bold       = QFont(); bold.setBold(True)
        old_brush  = QBrush(_OLD_BG)
        new_brush  = QBrush(_NEW_BG)
        for r, (tag, val, kind) in enumerate(rows):
            tag_item = QTableWidgetItem(tag)
            val_item = QTableWidgetItem(val)
            val_item.setToolTip(val)            # 长值悬停看全
            if kind == 'old':
                tag_item.setFont(bold)
                tag_item.setToolTip('该字段在新旧之间存在差异')
                val_item.setBackground(old_brush)
            elif kind == 'new':
                val_item.setFont(bold)
                val_item.setBackground(new_brush)
            table.setItem(r, 0, tag_item)
            table.setItem(r, 1, val_item)

        # Tag 列在差异行上跨合并 2 行（视觉上「该 tag 的旧 / 新」共享一个标签）
        for start in spans:
            table.setSpan(start, 0, 2, 1)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
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
        cur_enc = plan.existing_encoding or '—'
        new_enc = plan.new_encoding
        enc_line = (f'{cur_enc} → {new_enc}' if cur_enc != new_enc
                    else cur_enc)
        lay.addWidget(QLabel(f'Encoding: {enc_line}'))

        # ── 底部按钮 ─────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        if plan.changed:
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


def _status_label(p: MakeMetaPlan) -> str:
    if not p.changed:
        return '─ 已是最新（无需写入）'
    if p.existing_xml is None:
        return '✨ 新增 ComicInfo.xml'
    return '✏️ 修改已有 ComicInfo.xml'
