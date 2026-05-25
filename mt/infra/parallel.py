"""
parallel.py — 通用 plan 调度：进度反馈 + 可选 ProcessPoolExecutor

三个子命令（sourcefile / metadata / cover）的 plan 阶段都符合
「列出 items → 对每项调用 worker → 收集结果」骨架。本模块抽公共
执行器，让各子命令只关心 items / worker / 进度行格式。

设计要点
--------
- 串行模式（``jobs=1``，默认）：保证顺序、零启动成本、debug 友好；
- 并行模式（``jobs>1`` 或 ``jobs=0`` 自动）：使用 ``ProcessPoolExecutor``，
  ``as_completed`` 顺序非确定，通过 **索引回填** 让最终结果按 items 原顺序，
  避免调用方再做一次排序；
- 启用阈值（``parallel_threshold``）：items 少于阈值时即使指定 ``jobs>1``
  也走串行 —— Windows ``spawn`` 启动成本 ≈ 0.3s/进程，少量任务上并行反而更慢；
- worker 必须 picklable（顶层 / 模块级函数）；worker 内部应捕获异常并以
  「错误 plan」形式返回，避免子进程未捕获异常通过 ``fut.result()`` 透传到
  主进程；
- ``progress_line(idx, total, result) -> str``：每完成一个调用一次。
  ``None`` 表示不打进度。

依赖: 仅标准库 + infra.console
"""

from __future__ import annotations
import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TypeVar

from mt.infra.console import emit

T = TypeVar('T')   # 输入项
R = TypeVar('R')   # plan 结果


# ── 默认值（与 cover 子命令初版语义对齐）─────────────────────────────────────
DEFAULT_JOBS_CAP:           int = 4
DEFAULT_PARALLEL_THRESHOLD: int = 4


def resolve_jobs(jobs: int, *, cap: int = DEFAULT_JOBS_CAP) -> int:
    """``jobs=0`` → 自动 ``min(cpu, cap)``；其余按用户指定，至少 1。

    上限 ``cap`` 默认 4 是经验值：CPU 密集场景下 4 进程能拿到大部分加速，
    再多增益递减；同时 IPC（大对象序列化）开始与启动成本抵消收益。
    """
    if jobs == 0:
        return max(1, min(os.cpu_count() or 1, cap))
    return max(1, jobs)


def run_plans(
    items:              list[T],
    worker:             Callable[[T], R],
    *,
    jobs:               int = 1,
    parallel_threshold: int = DEFAULT_PARALLEL_THRESHOLD,
    progress_line:      Callable[[int, int, R], str] | None = None,
    parallel_banner:    str = '⚙️  并行处理',
) -> list[R]:
    """通用 plan 调度。

    Args:
        items:              待处理项；空列表直接返回 []。
        worker:             ``f(item) -> result``，必须 picklable
                            （顶层函数 / 模块级函数）。
        jobs:               1 串行；>1 并行进程数；0 自动 ``min(cpu, cap)``。
        parallel_threshold: items 数 ≥ 此值才启用并行；否则强制串行
                            （避免 spawn 启动成本 > 收益）。
        progress_line:      ``f(idx_done, total, result) -> str``；
                            ``None`` 表示不打进度。
        parallel_banner:    并行启动时打印的提示前缀。

    Returns:
        与 ``items`` 等长、顺序一致的 ``[R]``（即使并行也按原序）。
    """
    total = len(items)
    if total == 0:
        return []

    n_jobs = resolve_jobs(jobs)
    results: list[R] = [None] * total  # type: ignore[list-item]

    if n_jobs > 1 and total >= parallel_threshold:
        emit(f'  {parallel_banner}（{n_jobs} 进程）...')
        with ProcessPoolExecutor(max_workers=n_jobs) as ex:
            futures = {
                ex.submit(worker, item): idx
                for idx, item in enumerate(items)
            }
            for done_n, fut in enumerate(as_completed(futures), 1):
                idx          = futures[fut]
                result       = fut.result()   # worker 内部应已吸收业务异常
                results[idx] = result
                if progress_line:
                    emit(progress_line(done_n, total, result), flush=True)
    else:
        for idx, item in enumerate(items):
            result       = worker(item)
            results[idx] = result
            if progress_line:
                emit(progress_line(idx + 1, total, result), flush=True)

    return results
