"""终端输出 & 统一日志（纯基础设施，不耦合领域模型）。

输出约定：所有面向用户的文本一律经 :func:`emit` 写入当前 sink（默认 :data:`sys.stdout`），
:func:`info` / :func:`warn` / :func:`error` / :func:`ok` 亦基于 :func:`emit`。
GUI 可用 :func:`set_output` 接管。唯独 :func:`debug` 经 :mod:`logging` 写入 stderr，
其捕获由 logging handler 负责，与用户输出通道解耦。

sink 是**线程本地**的（:class:`threading.local`），多个后台 worker 线程并发跑长任务时
各自的 :func:`emit` 不会互相串扰；跨线程传递由 :class:`~base.gui.worker.Worker` 在
构造时捕获主线程 sink，再在 ``run()`` 内 :func:`set_output` 继承。

领域对象的渲染（StdTitlePlan / MakeMetaPlan 等）位于 presentation 层。
"""

from __future__ import annotations
import inspect
import logging
import sys
import threading
from itertools import zip_longest
from typing import TextIO

# ── ANSI 颜色 ─────────────────────────────────────────────────────────────────
RESET  = '\033[0m'
RED    = '\033[31m'
YELLOW = '\033[33m'
GREEN  = '\033[32m'
CYAN   = '\033[36m'

# ── 分隔线 ────────────────────────────────────────────────────────────────────
SEP  = '─' * 72
SEP2 = '═' * 72


# ═══════════════════════════════════════════════════════════════════════════════
# 输出通道（可注入 sink）
# ═══════════════════════════════════════════════════════════════════════════════

# 线程本地 sink；缺省（属性未设）等价于使用 :data:`sys.stdout`，
# 兼容终端重定向 / pytest 捕获，并避免多 worker 线程串扰。
_tls = threading.local()


def set_output(stream: TextIO | None) -> None:
    """设置**当前线程**的输出 sink（GUI 传入自定义可写对象；None 恢复为 sys.stdout）。

    线程本地存储意味着每个后台 worker 线程必须在线程内显式调用本函数，否则会
    回退到 sys.stdout。:class:`~base.gui.worker.Worker` 负责跨线程继承主线程
    sink；新增其他后台线程时应仿照其做法。
    """
    _tls.out = stream


def get_output() -> TextIO | None:
    """读取当前线程的输出 sink；``None`` 表示走默认 :data:`sys.stdout`。"""
    return getattr(_tls, 'out', None)


def _sink() -> TextIO:
    out = getattr(_tls, 'out', None)
    return sys.stdout if out is None else out


def emit(*args: object, sep: str = ' ', end: str = '\n', flush: bool = False) -> None:
    """面向用户输出的唯一出口：行为对齐 print，但写入可注入的 sink。"""
    s = _sink()
    s.write(sep.join(str(a) for a in args) + end)
    if flush:
        s.flush()


# ── 内部 logger ───────────────────────────────────────────────────────────────
_log = logging.getLogger('manga')


def setup_logging(debug: bool = False) -> None:
    """初始化日志，debug=True 时输出调试信息到 stderr。"""
    level = logging.DEBUG if debug else logging.WARNING
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('     DEBUG: %(message)s'))
    _log.setLevel(level)
    if not _log.handlers:
        _log.addHandler(handler)


# ── 日志便捷函数 ──────────────────────────────────────────────────────────────

def debug(msg: str, funcname: str | None = None) -> None:
    """调试日志（DEBUG 级别时输出）。

    :param msg:      日志正文。
    :param funcname: 显示的函数名标签；``None`` 时自动取调用栈的当前函数名。
                     调用方可显式覆盖以保持原始语义函数名（例如
                     :func:`~module.manga.presentation.view.print_std_title_preview`
                     想 emit ``[parse_name]`` 的 DEBUG）。
    """
    if funcname is None:
        frame    = inspect.currentframe().f_back
        funcname = frame.f_code.co_name
    _log.debug('[%s] → %s', funcname, msg)


def is_debug() -> bool:
    """是否处于 DEBUG 日志级别（供调用方决定要不要 emit 额外上下文行）。"""
    return _log.isEnabledFor(logging.DEBUG)


def info(msg: str)  -> None: emit(msg)
def warn(msg: str)  -> None: emit(f'🟡 {msg}')
def error(msg: str) -> None: emit(f'❌ {msg}')
def ok(msg: str)    -> None: emit(f'✅ {msg}')


def confirm(prompt: str) -> bool:
    """询问用户确认，按 Enter 视为同意；Ctrl-C 或非空输入视为取消。"""
    try:
        return input(prompt).strip() == ''
    except KeyboardInterrupt:
        emit('\n\n🛑 用户取消操作，程序已退出')
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 差异高亮
# ═══════════════════════════════════════════════════════════════════════════════

def highlight_diff(original: str, new: str, color: str = RED) -> str:
    """逐字符比较两个字符串，将不同位置以 color 高亮。"""
    return ''.join(
        f'{color}{n}{RESET}' if o != n else n
        for o, n in zip_longest(original, new, fillvalue='')
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 操作统计
# ═══════════════════════════════════════════════════════════════════════════════

def print_op_result(ok_n: int, fail: int, skip: int = 0, label: str = '完成') -> None:
    """统一格式输出操作统计行。"""
    parts = [f'成功 {ok_n}', f'失败 {fail}']
    if skip:
        parts.append(f'跳过 {skip}')
    emit(f'\n{label}: {" | ".join(parts)}')


def print_summary(
    label: str,
    counts: list[tuple[str, int, str]],
    *,
    note: str = '',
) -> None:
    """带 emoji 图标的汇总行（comicinfo / examples 风格）。

    ``counts`` 元素为 ``(icon, n, name)``；``n == 0`` 自动省略。输出形如::

        label[note]  ✅ 10 可写   🟡 2 需 review

    与 :func:`print_op_result` 各管一种语境：后者用于「成功/失败/跳过」纯计数，
    本函数适合多类别带语义的汇总。
    """
    parts = [f'{icon} {n} {name}' for icon, n, name in counts if n > 0]
    emit(f'  {label}{note}  {"   ".join(parts)}')
