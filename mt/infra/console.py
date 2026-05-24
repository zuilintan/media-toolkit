"""
console.py — 终端输出 & 统一日志（纯基础设施，不耦合领域模型）

提供:
  - ANSI 颜色常量
  - emit()             — 面向用户输出的唯一出口（可注入 sink）
  - set_output() / capture() — 重定向输出（GUI 接管 / 测试与日志捕获）
  - debug() / info() / warn() / error() / ok() 日志函数
  - setup_logging()    — CLI 调用，设定日志级别
  - highlight_diff()   — 差异高亮
  - print_op_result()  — 通用操作统计行
  - SEP / SEP2         — 分隔线常量

输出约定: 所有面向用户的文本一律经 emit() 写入当前 sink（默认 sys.stdout，
info/warn/error/ok 亦基于 emit）。GUI 可用 set_output() 接管，批量日志/测试
可用 capture() 临时重定向到内存缓冲。唯独 debug() 经 logging 写入 stderr，
其捕获由 logging handler 负责，与用户输出通道解耦。
领域对象的渲染（RenamePlan / ComicInfo 字段）位于 presentation 层。

依赖: 仅标准库
"""

from __future__ import annotations
import inspect
import io
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
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


@contextmanager
def capture() -> Iterator[io.StringIO]:
    """临时把 emit() 输出重定向到内存缓冲，退出时恢复原 sink。"""
    global _out
    buf = io.StringIO()
    prev = _out
    _out = buf
    try:
        yield buf
    finally:
        _out = prev


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

def debug(msg: str) -> None:
    """带调用函数名的调试日志（DEBUG 级别时输出）。"""
    frame = inspect.currentframe().f_back
    func  = frame.f_code.co_name
    _log.debug('[%s] → %s', func, msg)


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
