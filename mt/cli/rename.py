"""
rename.py — rename 子命令：漫画文件（.zip / .cbz）批量重命名

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批写入 → 可选移动。
与 cli/comicinfo.py 结构对称。

依赖: workflow.scanner / workflow.drag / workflow.session / infra.console
      / presentation / cli.examples
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mt.infra.console import SEP2, emit, confirm, print_summary
from mt.presentation.view import print_rename_preview, print_run_banner
from mt.workflow.scanner import plan_renames, apply_rename_plans, process_author_dir
from mt.workflow.drag import run_drag_loop, move_dir
from mt.workflow.session import list_sessions, rollback
from mt.cli.examples import run_rename_examples


def _validate_root(root_arg: str) -> Path | None:
    """统一的 --root 校验（与 cli/comicinfo 对齐）。返回 None 表示已报错。"""
    if not root_arg:
        emit('❌ 请指定 --root <目录>'); return None
    root = Path(root_arg).resolve()
    if not root.exists():
        emit(f'❌ 目录不存在: {root}'); return None
    if not root.is_dir():
        emit(f'❌ 路径不是目录: {root}'); return None
    return root


def cmd_rename(args: argparse.Namespace) -> int:
    """rename 子命令调度。"""
    # ── 旁路子命令 ────────────────────────────────────────────────────────────
    if args.examples:
        return 0 if run_rename_examples() == 0 else 1
    if args.list_sessions:
        list_sessions()
        return 0
    if args.rollback:
        rollback(args.session)
        return 0
    if args.drag:
        run_drag_loop(
            title='rename 循环拖入模式',
            target=args.move_to,
            process_one=process_author_dir,
        )
        return 0

    if args.move_to and not args.apply:
        emit('❌ --move-to 需配合 --drag 或 --apply 使用')
        return 2

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = _validate_root(args.root)
    if root is None:
        return 2

    print_run_banner('rename', '漫画文件批量重命名', root, args.apply)
    plans = plan_renames(str(root))
    emit(f'  找到条目: {len(plans)} 项')

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_rename_preview(plans)

    # ── 预览汇总（采用 print_summary 风格，与 comicinfo 一致） ───────────────
    n_changed   = sum(1 for p in plans if p.changed)
    n_review    = sum(1 for p in plans if p.needs_review)
    n_unchanged = sum(1 for p in plans if not p.changed)
    emit(f'\n{SEP2}')
    print_summary(
        '解析完成',
        [
            ('✅', n_changed,   '待重命名'),
            ('🟡', n_review,    '需审核'),
            ('—',  n_unchanged, '无需修改'),
        ],
        note='' if args.apply else '（预览，未实际修改）',
    )

    if not args.apply:
        if n_changed:
            emit('  → 确认无误后，加上 --apply 参数重新运行以实际执行。')
        emit(SEP2)
        return 0

    # ── 写入分支 ──────────────────────────────────────────────────────────────
    actionable = [p for p in plans if p.changed and not p.needs_review]
    if not actionable:
        emit('  没有可执行的重命名。')
        emit(SEP2)
        return 0

    if not confirm(
        f'\n🟡 确认对 {len(actionable)} 个文件执行重命名？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    apply_rename_plans(plans, dry_run=False)
    if args.move_to:
        for author_dir in sorted(root.iterdir()):
            if author_dir.is_dir():
                move_dir(author_dir, args.move_to)
    emit(SEP2)
    return 0


def add_rename_args(p: argparse.ArgumentParser) -> None:
    """挂载 rename 子命令的参数。"""
    p.add_argument('--root',          default='',
                   help='漫画根目录（批量模式，目录下按作者目录组织）')
    p.add_argument('--move-to',       default='', dest='move_to',
                   metavar='DIR',
                   help='处理完成后将作者目录移动至此目录（需配合 --drag 或 --apply）')
    p.add_argument('--apply',         action='store_true',
                   help='执行重命名（批量模式）')
    p.add_argument('--drag',          action='store_true',
                   help='循环拖入模式')
    p.add_argument('--rollback',      action='store_true',
                   help='回退已有的 session 记录')
    p.add_argument('--session',       default=None,
                   help='指定回退的 session ID（配合 --rollback）')
    p.add_argument('--list-sessions', action='store_true',
                   dest='list_sessions',
                   help='列出所有可回退的操作记录')
    p.add_argument('--examples',      action='store_true',
                   help='运行内置解析示例（回归测试）')
