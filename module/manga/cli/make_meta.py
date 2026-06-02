"""向 CBZ 写入 ``ComicInfo.xml`` 元数据的子命令实现。

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批写入。结构与
:mod:`module.manga.cli.std_title` 对称。
"""

from __future__ import annotations

import argparse

from base.console import SEP2, emit, confirm, print_summary
from module.manga.presentation.view import print_make_meta_preview, print_run_banner
from module.manga.workflow.make_meta import preview_plans, apply_plans
from module.manga.cli import validate_root
from module.manga.extras.examples import run_make_meta_examples


def cmd_make_meta(args: argparse.Namespace) -> int:
    """元数据写入子命令调度。"""
    # ── 旁路子命令 ────────────────────────────────────────────────────────────
    if args.examples:
        return 0 if run_make_meta_examples() == 0 else 1

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = validate_root(args.root)
    if root is None:
        return 2

    print_run_banner(args.command, 'CBZ ComicInfo.xml 批量工具', root, args.apply)
    plans = preview_plans(str(root), jobs=args.jobs)

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_make_meta_preview(
        plans,
        sample_per_group=args.sample_per_group,
        rare_threshold=args.rare_threshold,
    )

    # ── 预览汇总 ──────────────────────────────────────────────────────────────
    n_changed   = sum(1 for p in plans if p.writable and p.changed)
    n_unchanged = sum(1 for p in plans if p.writable and not p.changed)
    n_conflict  = sum(1 for p in plans if not p.writable)
    n_warn      = sum(1 for p in plans if p.mi.warnings)
    emit(f'\n{SEP2}')
    print_summary(
        '解析完成',
        [
            ('✅', n_changed,   '待写入'),
            ('—',  n_unchanged, '已是最新'),
            ('⛔', n_conflict,  '出版商冲突'),
            ('🟡', n_warn,      '有警告'),
        ],
        note='' if args.apply else '（预览，未实际修改）',
    )

    if not args.apply:
        if n_changed:
            emit('  → 确认无误后，加上 --apply 参数重新运行以实际执行。')
        emit(SEP2)
        return 0

    # ── 写入分支 ──────────────────────────────────────────────────────────────
    if not n_changed:
        emit('  没有需要写入的文件（全部已是最新或全部冲突）。')
        emit(SEP2)
        return 0

    if not confirm(
        f'\n🟡 确认对 {n_changed} 个 CBZ 写入 ComicInfo.xml？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    apply_plans(plans, dry_run=False)
    emit(SEP2)
    return 0


def add_make_meta_args(p: argparse.ArgumentParser) -> None:
    """挂载元数据写入子命令的参数。"""
    p.add_argument('--root',    default='', metavar='DIR',
                   help='CBZ 文件根目录（递归处理所有子目录）')
    p.add_argument('--apply',   action='store_true',
                   help='实际写入 ComicInfo.xml（不加此参数则仅预览）')
    p.add_argument('--examples', action='store_true',
                   help='解析内置示例并展示结果，不处理任何文件')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；≥ 4 个文件时才真正启用并行）')
    p.add_argument('--sample-per-group', type=int, default=3, metavar='K',
                   help='预览阶段每类差异展示的样本卡数（默认 3；0=全量，不折叠）')
    p.add_argument('--rare-threshold', type=int, default=5, metavar='N',
                   help='出现 ≤ N 次的差异类视为稀有，强制全量渲染（默认 5）')
