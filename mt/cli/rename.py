"""
rename.py — rename 子命令：漫画文件 / 目录批量重命名

依赖: workflow.scanner / workflow.session / infra.console / presentation / cli.examples
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mt.infra.console import emit, confirm
from mt.presentation.view import print_preview, print_run_banner
from mt.workflow.scanner import plan_renames, apply_rename_plans, run_drag_loop, move_author_dir
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
        emit('❌ --move-to 需配合 --drag 或 --apply 使用')
        return 2

    # 批量模式
    if not args.root:
        emit('❌ 请指定 --root <目录> 或使用 --drag / --examples')
        return 2

    print_run_banner('rename', '漫画文件 / 目录批量重命名', args.root, args.apply)
    plans = plan_renames(args.root)
    emit(f'  找到条目: {len(plans)} 项')
    print_preview(plans)

    if args.apply:
        if not any(p.changed for p in plans):
            return 0
        if confirm('\n🟡 确认执行重命名？按 Enter 继续: '):
            apply_rename_plans(plans, dry_run=False)
            if args.move_to:
                for author_dir in sorted(Path(args.root).iterdir()):
                    if author_dir.is_dir():
                        move_author_dir(author_dir, args.move_to)
    else:
        apply_rename_plans(plans, dry_run=True)
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
