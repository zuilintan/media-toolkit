"""
console.py — 终端输出 & 统一日志（纯基础设施，不耦合领域模型）

提供:
  - ANSI 颜色常量
  - emit()             — 面向用户输出的唯一出口（可注入 sink）
  - set_output()       — GUI 接管输出通道
  - debug() / info() / warn() / error() / ok() 日志函数
  - setup_logging()    — CLI 调用，设定日志级别
  - highlight_diff()   — 差异高亮
  - print_op_result()  — 通用操作统计行（`完成: 成功 N | 失败 N` 风格）
  - print_summary()    — 带 emoji 图标的汇总行（`label  ✅ N name   🟡 N name`）
  - SEP / SEP2         — 分隔线常量

输出约定: 所有面向用户的文本一律经 emit() 写入当前 sink（默认 sys.stdout，
info/warn/error/ok 亦基于 emit）。GUI 可用 set_output() 接管。唯独 debug()
经 logging 写入 stderr，其捕获由 logging handler 负责，与用户输出通道解耦。
领域对象的渲染（SourcefilePlan / ComicInfo 字段）位于 presentation 层。

依赖: 仅标准库
"""

from __future__ import annotations
import inspect
import logging
import sys
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

# 当前输出 sink；None 表示动态使用 sys.stdout（兼容终端重定向 / pytest 捕获）。
_out: TextIO | None = None


def set_output(stream: TextIO | None) -> None:
    """设置全局输出 sink（GUI 传入自定义可写对象；None 恢复为 sys.stdout）。"""
    global _out
    _out = stream


def _sink() -> TextIO:
    return sys.stdout if _out is None else _out


def emit(*args: object, sep: str = ' ', end: str = '\n', flush: bool = False) -> None:
    """面向用户输出的唯一出口：行为对齐 print，但写入可注入的 sink。"""
    s = _sink()
    s.write(sep.join(str(a) for a in args) + end)
    if flush:
        s.flush()


# ── 内部 logger ───────────────────────────────────────────────────────────────
_log = logging.getLogger('mt')


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

    Args:
        msg:      日志正文。
        funcname: 显示的函数名标签；None 时自动取调用栈的当前函数名，
                  调用方可显式覆盖以保持原始语义函数名
                  （例如 view.print_preview 想 emit `[parse_name]` 的 DEBUG）。
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
    """统一格式输出操作统计行（rename apply / session rollback 风格）。"""
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

    counts 元素 ``(icon, n, name)``；``n == 0`` 自动省略。
    输出形如::

        label[note]  ✅ 10 可写   🟡 2 需 review

    与 :func:`print_op_result` 各管一种语境：
    后者用于「成功/失败/跳过」纯计数；本函数适合多类别带语义的汇总。
    """
    parts = [f'{icon} {n} {name}' for icon, n, name in counts if n > 0]
    emit(f'  {label}{note}  {"   ".join(parts)}')
