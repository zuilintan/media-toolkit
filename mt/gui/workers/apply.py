"""
apply.py — 各子命令共用的「apply + 可选移动」流程

apply_fn 的语义统一（``(plans, dry_run, **kw) -> fail``），写入后的「移动」
策略各 Tab 不同：
  - sourcefile / cover / metadata: 把 root 下顶层子目录移到 move_to
  - pack: 源目录已被删除，移动的是 plan.zip_path 指向的产物 zip

通过 ``mover`` 钩子注入策略，默认走「移动 root 下顶层子目录」（向后兼容）。

依赖: 仅标准库 + mt.workflow.drag
"""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from mt.workflow.drag import move_dir

P = TypeVar('P')

# 「移动 plans, root, move_to」回调；apply 成功（fail==0 且 move_to 非空）后调用
Mover = Callable[[list, str, str], None]


def _move_root_subdirs(plans: list, root: str, move_to: str) -> None:
    """默认 mover：移动 root 下所有顶层子目录到 move_to。

    sourcefile/metadata/cover 共用此策略：写入后源目录依旧存在，
    把它们成批搬到归档目录。
    """
    for sub in sorted(Path(root).iterdir()):
        if sub.is_dir():
            move_dir(sub, move_to)


def apply_and_move(
    apply_fn: Callable[..., int],
    plans:    list[P],
    root:     str,
    move_to:  str,
    *,
    mover:    Mover = _move_root_subdirs,
    **kwargs: object,
) -> int:
    """整批写入 + 失败为 0 时执行 mover。

    Args:
        apply_fn: ``apply_sourcefile_plans`` / ``apply_metadata_plans`` /
                  ``apply_cover_plans`` / ``apply_pack_plans`` 之一。
        plans:    plan 列表。
        root:     原扫描根目录。
        move_to:  目标目录；空串表示不移动。
        mover:    移动策略；默认搬移 root 下顶层子目录。
        kwargs:   透传至 apply_fn（cancel_token 等）。

    Returns:
        apply_fn 的失败计数。
    """
    kwargs.pop('on_progress', None)  # Worker 内部回调，apply 函数不需要
    fail = apply_fn(plans, False, **kwargs)
    if fail == 0 and move_to:
        mover(plans, root, move_to)
    return fail
