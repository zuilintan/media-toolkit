"""
drag_loop.py — CLI 拖入循环工具

通用形态:
  - 持续等待用户在终端拖入路径（可同时多个）
  - 解析后逐个调用 ``process_one(path)``
  - Ctrl+C / EOF 退出

设计要点
--------
- ``process_one`` 形参收窄为 ``Callable[[Path], None]``；调用方有额外状态
  （目标目录、配置等）一律通过闭包绑定，避免本工具与业务参数耦合。
- 进度/警告通过可选 ``reporter`` 回调输出，缺省走 stdout/stderr；
  GUI 路由由调用方注入。
- 启动 banner 由 ``title`` 参数控制：传入显示名（如 ``'classify'``）即自动
  打印统一格式 4 行 banner；不传则不打印（脚本化 / 嵌入场景）。

依赖: 仅标准库
"""

from __future__ import annotations
import shlex
from collections.abc import Callable
from pathlib import Path

from base.fs import Reporter, _default_reporter

_BANNER_SEP = '═' * 72


def _parse_drag_paths(raw: str) -> tuple[list[Path], list[str]]:
    """解析拖入字符串，支持引号包裹的含空格路径。"""
    raw = raw.strip()
    if not raw:
        return [], []
    try:
        tokens = shlex.split(raw, posix=False)
    except ValueError:
        tokens = [raw]
    valid:   list[Path] = []
    invalid: list[str]  = []
    for token in tokens:
        p = Path(token.strip('"').strip("'"))
        if p.is_dir():
            valid.append(p)
        else:
            invalid.append(str(p))
    return valid, invalid


def run_drag_loop(
    *,
    process_one: Callable[[Path], None],
    title:       str | None = None,
    prompt:      str = '📂 拖入目录，Enter 处理: ',
    reporter:    Reporter = _default_reporter,
) -> None:
    """循环拖入模式：持续读 stdin，解析路径，逐个调 process_one。

    Args:
        title: 非 None 时打印统一启动 banner（"🔁  {title} 循环拖入模式…"）。

    Ctrl+C / EOF 退出。
    """
    if title is not None:
        reporter('info', f'\n{_BANNER_SEP}')
        reporter('info', f'🔁  {title} 循环拖入模式（支持同时拖入多个目录）')
        reporter('info', '    Ctrl+C 退出')
        reporter('info', _BANNER_SEP)
    while True:
        reporter('info', '')
        try:
            raw = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            reporter('info', '\n\n👋 已退出循环模式')
            return
        if not raw:
            continue
        dirs, bad = _parse_drag_paths(raw)
        for p in bad:
            reporter('error', f'不是有效目录，已跳过: {p}')
        if not dirs:
            continue
        if len(dirs) > 1:
            reporter('info', f'📦 本次共 {len(dirs)} 个目录，逐一处理')
        try:
            for d in dirs:
                process_one(d)
        except KeyboardInterrupt:
            reporter('info', '\n\n👋 已退出循环模式')
            return
