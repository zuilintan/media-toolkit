"""
qt_sink.py — 把 base.console.emit 的输出引流到 Qt 信号

base.console.set_output(stream) 接受任何带 write/flush 的对象。
QtSink 实现这两个方法，并把每次写入通过 Qt 信号转交到 GUI 线程的
日志框；后台 worker 线程里的 emit() 调用因此线程安全地到达 GUI。

设计要点
--------
- write() 可能被任何线程调用（plan/apply 走 QThread；并行模式 run_plans
  在主进程 ``as_completed`` 循环里 emit）。信号默认 QueuedConnection
  跨线程传递，Qt 会自动安全派发到接收端线程。
- flush() 在 GUI 场景下是空操作（追加文本立刻可见）。
- ANSI 转义序列保留原样，由 LogView 端剥离（关注点分离）。
- 每行自动添加 [HH:MM:SS] 时间戳前缀。
"""

from __future__ import annotations
from datetime import datetime

from PySide6.QtCore import QObject, Signal


class QtSink(QObject):
    """文件对象语义 + Qt 信号；可直接作为 set_output 的参数。"""

    text_written = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._buf = ''

    def write(self, s: str) -> int:
        self._buf += s
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            if line.strip():
                ts = datetime.now().strftime('[%H:%M:%S] ')
                self.text_written.emit(ts + line + '\n')
            else:
                self.text_written.emit(line + '\n')
        return len(s)

    def flush(self) -> None:
        if self._buf.strip():
            ts = datetime.now().strftime('[%H:%M:%S] ')
            self.text_written.emit(ts + self._buf)
        elif self._buf:
            self.text_written.emit(self._buf)
        self._buf = ''
