"""通用 plan 调度：进度反馈 + 可选 ``ProcessPoolExecutor``。

四个 *-kit 的 plan 阶段都符合「列出 items → 对每项 ``worker(item)`` → 收集结果」
骨架，统一抽到 :func:`run_plans`。

设计要点
--------
- 串行（``jobs=1``，默认）保序、零启动成本、debug 友好；
- 并行（``jobs>1`` / ``jobs=0`` 自动）用 ``ProcessPoolExecutor``，``as_completed``
  顺序非确定，通过**索引回填**保证最终结果按 ``items`` 原序；
- :data:`DEFAULT_PARALLEL_THRESHOLD` 阈值：少量任务下 Windows ``spawn`` 启动成本
  （≈ 0.3s/进程）大于并行收益，强制走串行；
- ``worker`` 必须 picklable（顶层 / 模块级函数）；内部应捕获异常以
  「错误 plan」形式返回，避免未捕获异常透传到主进程。
"""

from __future__ import annotations
import os
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TypeVar

from base.console import emit

T = TypeVar('T')   # 输入项
R = TypeVar('R')   # plan 结果


# 默认值与封面写入工作流初版语义对齐
DEFAULT_JOBS_CAP:           int = 4
DEFAULT_PARALLEL_THRESHOLD: int = 4


def resolve_jobs(jobs: int, *, cap: int = DEFAULT_JOBS_CAP) -> int:
    """``jobs=0`` → 自动 ``min(cpu, cap)``；其余按用户指定，至少 1。

    ``cap`` 默认 4 是经验值：CPU 密集场景下 4 进程能拿到大部分加速，再多增益递减；
    同时 IPC 序列化开始与启动成本抵消收益。
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
    parallel_banner:    str = '⚙️ 并行处理',
    on_progress:        Callable[[int, int], None] | None = None,
    cancel_token:       threading.Event | None = None,
) -> list[R]:
    """通用 plan 调度。

    :param items:              待处理项；空列表直接返回 ``[]``。
    :param worker:             ``f(item) -> result``，必须 picklable（顶层 / 模块级函数）。
    :param jobs:               1 串行；>1 并行进程数；0 自动 ``min(cpu, cap)``。
    :param parallel_threshold: items 数 ≥ 此值才启用并行；否则强制串行
        （避免 spawn 启动成本 > 收益）。
    :param progress_line:      ``f(idx_done, total, result) -> str``；
        ``None`` 表示不打进度。
    :param parallel_banner:    并行启动时打印的提示前缀。
    :param on_progress:        每完成一项即回调 ``f(done, total)``；始终在主进程调用。
    :param cancel_token:       已 set 时提前退出，返回当前已处理的结果。
    :return: 与 ``items`` 等长、顺序一致的 ``[R]``（即使并行也按原序）；
        取消时未处理项位置上为 ``None``。
    """
    total = len(items)
    if total == 0:
        return []

    n_jobs = resolve_jobs(jobs)
    results: list[R] = [None] * total  # type: ignore[list-item]

    def _cancelled() -> bool:
        return cancel_token is not None and cancel_token.is_set()

    if n_jobs > 1 and total >= parallel_threshold:
        emit(f'  {parallel_banner}（{n_jobs} 进程）...')
        with ProcessPoolExecutor(max_workers=n_jobs) as ex:
            futures = {
                ex.submit(worker, item): idx
                for idx, item in enumerate(items)
            }
            for done_n, fut in enumerate(as_completed(futures), 1):
                if _cancelled():
                    emit('  ⏹️  已取消')
                    # 先 snapshot 再 shutdown（shutdown 异步清理 _processes）
                    procs = list(getattr(ex, '_processes', {}).values())
                    ex.shutdown(wait=False, cancel_futures=True)
                    for p in procs:
                        try:
                            p.kill()
                        except Exception:
                            pass
                    break
                idx          = futures[fut]
                result       = fut.result()   # worker 内部应已吸收业务异常
                results[idx] = result
                if progress_line:
                    emit(progress_line(done_n, total, result), flush=True)
                if on_progress:
                    on_progress(done_n, total)
    else:
        for idx, item in enumerate(items):
            if _cancelled():
                emit('  ⏹️  已取消')
                break
            result       = worker(item)
            results[idx] = result
            if progress_line:
                emit(progress_line(idx + 1, total, result), flush=True)
            if on_progress:
                on_progress(idx + 1, total)

    return results
