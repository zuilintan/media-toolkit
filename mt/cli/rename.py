"""
rename.py — rename 子命令：漫画文件 / 目录批量重命名

依赖: workflow.scanner / workflow.session / infra.console / cli.examples
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mt.infra.console import print_preview
from mt.workflow.scanner import scan_and_plan, apply_renames, run_drag_loop, confirm, move_author_dir
from mt.workflow.session import list_sessions, rollback
from mt.cli.examples import run_rename_examples


def cmd_rename(args: argparse.Namespace) -> int:
    """rename 子命令调度。"""
    if args.examples:
        return 0 if run_rename_examples() == 0 else 1
    if args.list_sessions:
        list_sessions()
        return 0
    if args.rollback:
        rollback(args.session)
        return 0
    if args.drag:
        run_drag_loop(args.move_to)
        return 0

    # --move-to 未配合 --drag 或 --apply 时给出提示
    if args.move_to and not args.apply:
        print('❌ --move-to 需配合 --drag 或 --apply 使用')
        return 2

    # 批量模式
    if not args.root:
        print('❌ 请指定 --root <目录> 或使用 --drag / --examples')
        return 2

    print(f'\n📂 扫描目录: {args.root}')
    plans = scan_and_plan(args.root)
    print_preview(plans)

    if args.apply and confirm():
        apply_renames(plans, dry_run=False)
        if args.move_to:
            for author_dir in sorted(Path(args.root).iterdir()):
                if author_dir.is_dir():
                    move_author_dir(author_dir, args.move_to)
    elif not args.apply:
        apply_renames(plans, dry_run=True)
    return 0


def add_rename_args(p: argparse.ArgumentParser) -> None:
    """挂载 rename 子命令的参数。"""
    p.add_argument('--root',          default='',
                   help='漫画根目录（批量模式）')
    p.add_argument('--move-to',       default='', dest='move_to',
                   metavar='DIR',
                   help='处理完成后将作者目录移动至此目录（需配合 --drag 或 --apply）')
    p.add_argument('--apply',         action='store_true',
                   help='执行重命名（批量模式）')
    p.add_argument('--drag',          action='store_true',
                   help='循环拖入模式')
    p.add_argument('--rollback',      action='store_true',
                   help='回退上次操作')
    p.add_argument('--session',       default=None,
                   help='指定回退的 session ID（配合 --rollback）')
    p.add_argument('--list-sessions', action='store_true',
                   dest='list_sessions',
                   help='列出所有可回退的操作记录')
    p.add_argument('--examples',      action='store_true',
                   help='运行内置解析示例（回归测试）')
