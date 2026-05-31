"""
name.py — name 子命令：源文件（.zip / .cbz）批量重命名

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批写入。
与 cli/meta.py 结构对称。

依赖: workflow.sourcefile / infra.console / presentation / cli.examples
"""

from __future__ import annotations

import argparse

from base.console import SEP2, emit, confirm, print_summary
from module.manga.presentation.view import print_sourcefile_preview, print_run_banner
from module.manga.workflow.sourcefile import plan_sourcefiles, apply_sourcefile_plans
from module.manga.cli import validate_root
from module.manga.cli.examples import run_sourcefile_examples


def cmd_name(args: argparse.Namespace) -> int:
    """name 子命令调度。"""
    # ── 旁路子命令 ────────────────────────────────────────────────────────────
    if args.examples:
        return 0 if run_sourcefile_examples() == 0 else 1

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = validate_root(args.root)
    if root is None:
        return 2

    print_run_banner('name', '源文件批量重命名', root, args.apply)
    plans = plan_sourcefiles(str(root), jobs=args.jobs)

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_sourcefile_preview(plans)

    # ── 预览汇总 ──────────────────────────────────────────────────────────────
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

    apply_sourcefile_plans(plans, dry_run=False)
    emit(SEP2)
    return 0


def add_name_args(p: argparse.ArgumentParser) -> None:
    """挂载 name 子命令的参数。"""
    p.add_argument('--root',          default='',
                   help='漫画根目录（批量模式，目录下按作者目录组织）')
    p.add_argument('--apply',         action='store_true',
                   help='执行重命名（批量模式）')
    p.add_argument('--examples',      action='store_true',
                   help='运行内置解析示例（回归测试）')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；plan 阶段是纯字符串处理'
                        '故并行收益有限）')
