"""
meta_kit.py — meta-kit 子命令：向 CBZ 写入 ComicInfo.xml 元数据

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批写入。
与 cli/rename_kit.py 结构对称。

依赖: workflow.meta_kit / infra.console / presentation / cli.examples
"""

from __future__ import annotations

import argparse

from base.console import SEP2, emit, confirm, print_summary
from module.manga.presentation.view import print_meta_kit_preview, print_run_banner
from module.manga.workflow.meta_kit import preview_plans, apply_plans
from module.manga.cli import validate_root
from module.manga.cli.examples import run_meta_kit_examples


def cmd_meta(args: argparse.Namespace) -> int:
    """meta-kit 子命令调度。"""
    # ── 旁路子命令 ────────────────────────────────────────────────────────────
    if args.examples:
        return 0 if run_meta_kit_examples() == 0 else 1

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = validate_root(args.root)
    if root is None:
        return 2

    print_run_banner('meta-kit', 'CBZ ComicInfo.xml 批量工具', root, args.apply)
    plans = preview_plans(str(root), jobs=args.jobs)

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_meta_kit_preview(plans)

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


def add_meta_kit_args(p: argparse.ArgumentParser) -> None:
    """挂载 meta-kit 子命令的参数。"""
    p.add_argument('--root',    default='', metavar='DIR',
                   help='CBZ 文件根目录（递归处理所有子目录）')
    p.add_argument('--apply',   action='store_true',
                   help='实际写入 ComicInfo.xml（不加此参数则仅预览）')
    p.add_argument('--examples', action='store_true',
                   help='解析内置示例并展示结果，不处理任何文件')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；≥ 4 个文件时才真正启用并行）')
