"""
plan_worker.py — 把任意阻塞函数包成 QThread 友好的 worker

只用一个通用 Worker 类：构造时传入 (fn, *args, **kwargs)，moveToThread
后调 run() 即可。完成时 emit ``finished(result)``，异常时 emit ``failed(str)``。

设计权衡
--------
- 不继承 QThread，沿用 worker-on-thread 模式：worker 是 QObject，
  线程是 QThread，二者解耦，便于一个线程跑多个任务（虽然这里没用上）。
- ``finished`` 携带 ``object``（plans 列表或 int 失败数），由 Tab 端解释。
- cancel_token 注入到 kwargs，由 plan/apply 函数在各循环迭代间检查；
  并行模式下已提交的 future 会跑完，但不等待新 future。

依赖: 仅 PySide6 + threading
"""

from __future__ import annotations
import threading
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot


class Worker(QObject):
    """通用阻塞任务的 worker（QThread 配套）。"""

    finished = Signal(object)   # 任务正常返回值
    failed   = Signal(str)      # 任务异常时的错误描述
    progress = Signal(int, int) # 进度：done, total

    def __init__(self, fn: Callable[..., Any], *args, **kwargs) -> None:
        super().__init__()
        self._fn     = fn
        self._args   = args
        self._cancel = threading.Event()
        # 注入回调 → 信号（始终在主/工作线程调用，安全）
        kwargs['on_progress'] = lambda c, t: self.progress.emit(c, t)
        kwargs['cancel_token'] = self._cancel
        self._kwargs = kwargs

    def cancel(self) -> None:
        """请求取消：设置 cancel_token，任务在下次检查点退出。"""
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # noqa: BLE001 — worker 必须吸收一切异常
            self.failed.emit(f'{e}\n\n{traceback.format_exc()}')
            return
        self.finished.emit(result)
