"""
log_view.py — 接收 QtSink 文本流的只读日志框

职责
----
- 接收 QtSink.text_written 信号，剥掉 ANSI 颜色转义，追加显示
- 等宽字体；保留 emit 的换行
- 上限块数防止超长任务把内存吃光（QPlainTextEdit.maximumBlockCount）

依赖: 仅 PySide6
"""

from __future__ import annotations
import re

from PySide6.QtCore import Slot
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


# ANSI CSI（颜色 / 光标等）转义序列；mt 项目目前只用颜色，剥掉即可
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


class LogView(QPlainTextEdit):
    """只读日志显示框。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(10000)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont('Consolas')
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        self.setFont(font)

    @Slot(str)
    def append_text(self, s: str) -> None:
        """槽：QtSink → 这里。逐次 write 的字符串可能不以换行结尾，
        直接 insertPlainText 而不要用 appendPlainText（后者会自加换行）。
        """
        clean = _ANSI_RE.sub('', s)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(clean)
        # 跟随到末尾，但不抢用户的滚动焦点：始终滚到底，符合日志框惯例
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    @Slot()
    def clear_log(self) -> None:
        self.clear()
