"""单个 :class:`~module.manga.core.models.MakeCoverPlan` 的详情对话框。

布局：

- 顶部 cbz 路径 + 状态标签
- 源图 / 目标 字段表（文件名、尺寸、mode）
- WebP 缩略图预览（直接用 ``plan.webp_bytes`` 加载到 ``QPixmap``）
- 「写入封面」（writable && changed 时）+ Close
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QMenu, QPushButton, QTableWidget, QTableWidgetItem, QToolTip,
    QVBoxLayout,
)

from module.manga.core.models import MakeCoverPlan


class MakeCoverDetailDialog(QDialog):
    """单 plan 的完整封面详情弹窗。

    :ivar apply_requested: 「写入封面」按钮点击时发出（仅 ``writable && changed`` 显示）。
    """

    apply_requested = Signal(object)   # MakeCoverPlan

    def __init__(self, plan: MakeCoverPlan, parent=None) -> None:
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle(f'详情 — {plan.filename}')
        self.resize(720, 720)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── 头部 ────────────────────────────────────────────────────
        title = QLabel(f'📄 {plan.cbz_path}')
        f = title.font(); f.setBold(True); title.setFont(f)
        title.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(QLabel(f'状态: {_status_label(plan)}'))

        # ── 字段表 ──────────────────────────────────────────────────
        sw, sh = plan.src_size or (0, 0)
        dw, dh = plan.dst_size or (0, 0)
        rows: list[tuple[str, str, bool]] = [
            ('源文件', plan.src_name or '—', False),
            ('源尺寸', f'{sw}×{sh}' if plan.src_size else '—', False),
            ('目标文件', plan.dst_name or '—', True),
            ('目标尺寸', f'{dw}×{dh}' if plan.dst_size else '—', True),
            ('裁剪模式', plan.mode, False),
        ]
        if plan.error:
            rows.append(('错误', plan.error, False))

        table = QTableWidget(len(rows), 2, self)
        table.setHorizontalHeaderLabels(['字段', '值'])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)

        bold = QFont(); bold.setBold(True)
        for r, (lab, val, hl) in enumerate(rows):
            lab_item = QTableWidgetItem(lab)
            val_item = QTableWidgetItem(val)
            val_item.setToolTip(val)
            if hl:
                val_item.setFont(bold)
            table.setItem(r, 0, lab_item)
            table.setItem(r, 1, val_item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        table.resizeRowsToContents()

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table = table
        lay.addWidget(table)

        # ── WebP 缩略图（按需）─────────────────────────────────────
        if plan.webp_bytes:
            pix = QPixmap()
            if pix.loadFromData(plan.webp_bytes, 'WEBP'):
                scaled = pix.scaled(
                    400, 600,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                preview = QLabel(self)
                preview.setPixmap(scaled)
                preview.setAlignment(Qt.AlignCenter)
                lay.addWidget(preview, 1)
            else:
                lay.addWidget(QLabel('🟡 无法解码 WebP 预览（缺 imageformats 插件？）'))

        # ── 底部按钮 ────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        if plan.writable and plan.changed:
            apply_btn = QPushButton('写入封面', self)
            apply_btn.setToolTip('只对当前 CBZ 写入 0000.webp 封面')
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


def _status_label(p: MakeCoverPlan) -> str:
    if not p.writable:
        return f'⛔ 错误 — {p.error or "无源图"}'
    if not p.changed:
        return '─ 已是最新（无需写入）'
    if p.replaced:
        return '🔁 替换现有封面'
    return '✨ 新增封面'
