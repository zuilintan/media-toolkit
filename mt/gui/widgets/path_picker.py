"""
path_picker.py — 路径选择部件（输入框 + 浏览按钮 + 接收拖拽）

替代 CLI 的 --root / --move-to 文本参数，并兼容把目录从资源管理器拖入。
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget,
)


class PathPicker(QWidget):
    """单行路径输入：标签 + 输入框 + 浏览按钮；整体接受目录拖拽。"""

    path_changed = Signal(str)

    def __init__(self, label: str = '目录:', placeholder: str = '', parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder or '选择或拖入目录...')
        self._edit.textChanged.connect(self.path_changed)

        self._btn = QPushButton('浏览…')
        self._btn.clicked.connect(self._pick)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(label))
        lay.addWidget(self._edit, 1)
        lay.addWidget(self._btn)

    # ── 公共 API ──
    def path(self) -> str:
        return self._edit.text().strip()

    def set_path(self, p: str) -> None:
        self._edit.setText(p)

    # ── 拖拽 ──
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).is_dir():
                    e.acceptProposedAction()
                    return
        e.ignore()

    def dropEvent(self, e: QDropEvent) -> None:
        for url in e.mimeData().urls():
            if url.isLocalFile():
                p = Path(url.toLocalFile())
                if p.is_dir():
                    self.set_path(str(p))
                    e.acceptProposedAction()
                    return
        e.ignore()

    # ── 内部 ──
    def _pick(self) -> None:
        start = self._edit.text().strip() or ''
        chosen = QFileDialog.getExistingDirectory(self, '选择目录', start)
        if chosen:
            self.set_path(chosen)
