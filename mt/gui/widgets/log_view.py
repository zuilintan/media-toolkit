"""
log_view.py — 接收 QtSink 文本流的只读日志框

职责
----
- 接收 QtSink.text_written 信号，**解析** ANSI SGR 颜色转义，按色片段渲染
- 上限块数防止超长任务把内存吃光（QPlainTextEdit.maximumBlockCount）

依赖: 仅 PySide6
"""

from __future__ import annotations
import re

from PySide6.QtCore import Slot
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


# ── ANSI SGR ───────────────────────────────────────────────────────────────────
# 项目只用 SGR（结尾 m）；其它 CSI 序列（光标移动等）一律丢弃。
_SGR_RE = re.compile(r'\x1b\[([\d;]*)m')
# 兜底丢弃其他 CSI 序列
_OTHER_CSI_RE = re.compile(r'\x1b\[[\d;]*[A-Za-ln-~]')

# SGR 30–37 → 前景色（深色背景下醒目的中间饱和度，不刺眼）
_SGR_FG: dict[int, QColor] = {
    31: QColor('#e06c75'),   # red    — 差异字符
    32: QColor('#98c379'),   # green
    33: QColor('#e5c07b'),   # yellow — 行尾 * / 警告
    36: QColor('#56b6c2'),   # cyan
}


class LogView(QPlainTextEdit):
    """只读日志显示框：ANSI SGR 着色。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(10000)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont('Consolas')
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        self.setFont(font)

        # 当前段前景色；None = 用调色板默认色
        self._fg: QColor | None = None

    # ── 接收文本 ───────────────────────────────────────────────────────
    @Slot(str)
    def append_text(self, s: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        # 按 SGR 分段：转义之间的纯文本用当前 _fg 插入，遇 SGR 切换 _fg
        pos = 0
        for m in _SGR_RE.finditer(s):
            if m.start() > pos:
                self._insert(cursor, s[pos:m.start()])
            self._apply_sgr(m.group(1))
            pos = m.end()
        if pos < len(s):
            self._insert(cursor, s[pos:])

        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    @Slot()
    def clear_log(self) -> None:
        self.clear()
        self._fg = None

    # ── 内部 ───────────────────────────────────────────────────────────
    def _insert(self, cursor: QTextCursor, text: str) -> None:
        """插入一段文本：每段都重建 QTextCharFormat 并**显式** setForeground，
        以避免 cursor.insertText 的 merge 语义把上一段残留色继承下来。
        """
        if not text:
            return
        fmt = QTextCharFormat()
        fmt.setForeground(self._fg if self._fg else self.palette().text())
        cursor.insertText(_OTHER_CSI_RE.sub('', text), fmt)

    def _apply_sgr(self, params: str) -> None:
        """按 SGR 参数列表更新当前前景色。空串或 0 都视作 reset。"""
        if not params:
            self._fg = None
            return
        for tok in params.split(';'):
            try:
                n = int(tok)
            except ValueError:
                continue
            if n == 0:
                self._fg = None
            elif n in _SGR_FG:
                self._fg = _SGR_FG[n]
