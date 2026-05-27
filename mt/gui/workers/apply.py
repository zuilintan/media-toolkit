"""
apply.py — 三个子命令共用的「apply + 可选移动」流程

每个 Tab 写入完成后的「移动 root 下顶层子目录到 move_to」逻辑完全一致
（sourcefile 的「作者目录」也是 root 的顶层子目录），抽到这里复用。

依赖: 仅标准库 + mt.workflow.drag
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from mt.workflow.drag import move_dir

P = TypeVar('P')


def apply_and_move(
    apply_fn: Callable[[list[P], bool], int],
    plans:    list[P],
    root:     str,
    move_to:  str,
    **_: object,
) -> int:
    """整批写入 + 失败为 0 时移动 root 下顶层子目录到 move_to。

    Args:
        apply_fn: ``apply_sourcefile_plans`` / ``apply_metadata_plans`` /
                  ``apply_cover_plans`` 之一；签名 ``(plans, dry_run) -> fail``。
        plans:    plan 列表。
        root:     原扫描根目录。
        move_to:  目标目录；空串表示不移动。

    Returns:
        apply_fn 的失败计数。
    """
    fail = apply_fn(plans, False)
    if fail == 0 and move_to:
        for sub in sorted(Path(root).iterdir()):
            if sub.is_dir():
                move_dir(sub, move_to)
    return fail
