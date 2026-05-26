"""
plan_worker.py — 把任意阻塞函数包成 QThread 友好的 worker

只用一个通用 Worker 类：构造时传入 (fn, *args, **kwargs)，moveToThread
后调 run() 即可。完成时 emit ``finished(result)``，异常时 emit ``failed(str)``。

设计权衡
--------
- 不继承 QThread，沿用 worker-on-thread 模式：worker 是 QObject，
  线程是 QThread，二者解耦，便于一个线程跑多个任务（虽然这里没用上）。
- ``finished`` 携带 ``object``（plans 列表或 int 失败数），由 Tab 端解释。
- 不实现「取消」：plan_* / apply_* 都是同步阻塞函数，没有 cooperative
  cancel 点；硬终止 QThread 不安全。改善路径是后续给 run_plans 加 token。

依赖: 仅 PySide6
"""

from __future__ import annotations
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot


class Worker(QObject):
    """通用阻塞任务的 worker（QThread 配套）。"""

    finished = Signal(object)   # 任务正常返回值
    failed   = Signal(str)      # 任务异常时的错误描述

    def __init__(self, fn: Callable[..., Any], *args, **kwargs) -> None:
        super().__init__()
        self._fn     = fn
        self._args   = args
        self._kwargs = kwargs

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # noqa: BLE001 — worker 必须吸收一切异常
            self.failed.emit(f'{e}\n\n{traceback.format_exc()}')
            return
        self.finished.emit(result)
