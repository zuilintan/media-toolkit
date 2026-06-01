"""路径选择部件（下拉历史 + 浏览按钮 + 接收拖拽）。

替代 CLI 的 ``--root`` 文本参数，并兼容从资源管理器拖入目录。
传入 ``history_key`` 后，部件自动从 :func:`~base.gui.config.get_config` 读取
历史路径并在下拉列表展示；通过浏览/拖拽/手动输入确认路径时自动推入历史（最近优先）。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from base.gui.config import get_config


class PathPicker(QWidget):
    """路径输入：标签 + 可编辑下拉框（历史） + 浏览按钮；整体接受目录拖拽。"""

    path_changed = Signal(str)

    def __init__(
        self,
        label:       str = '目录:',
        placeholder: str = '',
        history_key: str = '',
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._history_key = history_key
        self.setAcceptDrops(True)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._combo.lineEdit().setPlaceholderText(placeholder or '选择或拖入目录...')
        self._combo.currentTextChanged.connect(self.path_changed)
        # 下拉选择时推入历史（浏览/拖拽已通过 set_path → _push 处理）
        self._combo.activated.connect(lambda: self._push(self.path()))

        # 加载历史，并预填最近一次使用的路径
        if history_key:
            self._reload_items()

        self._btn = QPushButton('浏览…')
        self._btn.clicked.connect(self._pick)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(label))
        lay.addWidget(self._combo, 1)
        lay.addWidget(self._btn)

    # ── 公共 API ──────────────────────────────────────────────────────
    def path(self) -> str:
        return self._combo.currentText().strip().replace('\\', '/')

    def set_path(self, p: str) -> None:
        """设置当前路径，并推入历史。"""
        p = p.replace('\\', '/')
        self._combo.setCurrentText(p)
        self._push(p)

    # ── 拖拽 ──────────────────────────────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).is_dir():
                    self._combo.setStyleSheet(
                        'QComboBox { border: 2px solid #56b6c2; }'
                    )
                    e.acceptProposedAction()
                    return
        e.ignore()

    def dragLeaveEvent(self, e: QDragLeaveEvent) -> None:
        self._combo.setStyleSheet('')
        e.accept()

    def dropEvent(self, e: QDropEvent) -> None:
        self._combo.setStyleSheet('')
        for url in e.mimeData().urls():
            if url.isLocalFile():
                p = Path(url.toLocalFile())
                if p.is_dir():
                    self.set_path(str(p))
                    e.acceptProposedAction()
                    return
        e.ignore()

    # ── 内部 ──────────────────────────────────────────────────────────
    def _pick(self) -> None:
        start = self.path() or ''
        chosen = QFileDialog.getExistingDirectory(self, '选择目录', start)
        if chosen:
            self.set_path(chosen)

    def _push(self, p: str) -> None:
        """推入历史并刷新下拉列表。"""
        if not p or not self._history_key:
            return
        get_config().push_history(self._history_key, p)
        self._reload_items()

    def _reload_items(self) -> None:
        """从配置重新加载历史条目到下拉列表，保持当前文本不变。"""
        hist = get_config().get_history(self._history_key)
        current = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        for item in hist:
            self._combo.addItem(item)
        # 恢复文本；若历史非空且当前为空，则预填最近路径
        self._combo.setCurrentText(current if current else (hist[0] if hist else ''))
        self._combo.blockSignals(False)
