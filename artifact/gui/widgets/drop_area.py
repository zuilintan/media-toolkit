"""
drop_area.py — 大块文件/目录拖入区

QFrame 形态，接受 file/dir 拖入；解析 MimeData URLs → 本地 Path 列表，
emit ``paths_dropped(list)`` 信号交给上层业务处理。

设计:
  - 接受文件 ∧ 接受目录（ps1 的 classify 拖入两者都允许）
  - 拖入悬停时高亮边框（与 base.gui.path_picker 风格一致）
  - 解析逻辑独立为模块函数 ``urls_to_paths`` 便于单测
"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


_HILITE_QSS = 'QFrame { border: 2px solid #56b6c2; background: #2c3033; }'
_NORMAL_QSS = 'QFrame { border: 2px dashed #555; background: #25292c; }'


def urls_to_paths(urls) -> list[Path]:
    """从 QMimeData.urls() 提取本地 Path 列表（过滤非本地 / 不存在的）。"""
    out: list[Path] = []
    for url in urls:
        if not url.isLocalFile():
            continue
        p = Path(url.toLocalFile())
        if p.exists():
            out.append(p)
    return out


class DropArea(QFrame):
    """大块文件/目录拖入区域；拖入后 emit paths_dropped(list[Path])。"""

    paths_dropped = Signal(list)

    def __init__(self, hint: str = '将文件或文件夹拖入此处', parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setStyleSheet(_NORMAL_QSS)

        self._label = QLabel(hint)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet('border: none; color: #a8b1b8; font-size: 14px;')

        lay = QVBoxLayout(self)
        lay.addWidget(self._label)

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls() and any(
            u.isLocalFile() for u in e.mimeData().urls()
        ):
            self.setStyleSheet(_HILITE_QSS)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e: QDragLeaveEvent) -> None:
        self.setStyleSheet(_NORMAL_QSS)
        e.accept()

    def dropEvent(self, e: QDropEvent) -> None:
        self.setStyleSheet(_NORMAL_QSS)
        paths = urls_to_paths(e.mimeData().urls())
        if paths:
            self.paths_dropped.emit(paths)
            e.acceptProposedAction()
        else:
            e.ignore()
