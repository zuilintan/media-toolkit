"""
log_view.py — 接收 QtSink 文本流的只读日志框

职责
----
- 接收 QtSink.text_written 信号，**解析** ANSI SGR 颜色转义，按色片段渲染
- 上限块数防止超长任务把内存吃光（QPlainTextEdit.maximumBlockCount）

依赖: 仅 PySide6
"""

from __future__ import annotations
import os
import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontDatabase, QMouseEvent,
    QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import QApplication, QMenu, QPlainTextEdit

# 中西等宽融合字体优先列表（CJK 字形宽 = ASCII 字形宽 × 2，表格对齐稳定）。
# 找不到任何一款时回落 Consolas（纯 ASCII 等宽，CJK 靠系统回落字体，可能对齐略差）。
_CJK_MONO_CANDIDATES = [
    'JetBrains Maple Mono',   # Fusion-JetBrainsMapleMono（用户已安装）
    'Maple Mono NF CN',
    'Maple Mono CN',
    'Sarasa Mono SC',
    'Sarasa Fixed SC',
    'Source Han Mono SC',
]


def _pick_log_font(size: int = 10) -> QFont:
    installed = set(QFontDatabase.families())
    for name in _CJK_MONO_CANDIDATES:
        if name in installed:
            font = QFont(name)
            font.setPointSize(size)
            return font
    font = QFont('Consolas')
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(size)
    return font


# ── ANSI SGR ───────────────────────────────────────────────────────────────────
# 项目只用 SGR（结尾 m）；其它 CSI 序列（光标移动等）一律丢弃。
_SGR_RE = re.compile(r'\x1b\[([\d;]*)m')
# 兜底丢弃其他 CSI 序列
_OTHER_CSI_RE = re.compile(r'\x1b\[[\d;]*[A-Za-ln-~]')

# 文件路径匹配：Windows 绝对路径 或 Unix 绝对路径
_PATH_RE = re.compile(
    r'(?:[A-Za-z]:[/\\]|/)'
    r'(?:[^\s<>:"|?*\x1b]| (?=[^/\\]*(?:[/\\]|\.\w{2,5}\b)))+'
    r'\.(?:cbz|zip|xml|txt|webp|png|jpg|jpeg|gif|bmp)\b',
)

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
        self.setFont(_pick_log_font())
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

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

    # ── 路径交互 ───────────────────────────────────────────────────────
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        cursor = self.cursorForPosition(event.pos())
        block = cursor.block()
        line_text = block.text()
        paths = _PATH_RE.findall(line_text)
        if paths:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(paths[0]))
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = self.createStandardContextMenu(event.pos())
        cursor = self.cursorForPosition(event.pos())
        block = cursor.block()
        line_text = block.text()
        paths = _PATH_RE.findall(line_text)
        if paths:
            path = paths[0]
            copy_path_action = QAction('复制路径')
            copy_path_action.triggered.connect(
                lambda: QApplication.clipboard().setText(path)
            )
            menu.addSeparator()
            menu.addAction(copy_path_action)
        menu.exec(event.globalPos())

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
