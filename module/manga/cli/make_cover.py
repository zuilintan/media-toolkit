"""为 CBZ 写入 2:3 封面的子命令实现。

源图（``0001.*`` 或 ``cover.*``）→ ``0000.webp``；源为 ``cover.*`` 时写入后
同步从 ZIP 删除原 ``cover.*``。详见 :mod:`module.manga.workflow.make_cover`。

流程: scan → 全量 plan（含裁剪 + 编码）→ 预览 → 二次确认 → 整批写入。
"""

from __future__ import annotations

import argparse

from base.console import SEP2, emit, confirm, print_summary
from module.manga.presentation.view import print_make_cover_preview, print_run_banner
from module.manga.workflow.make_cover import preview_plans, apply_plans, DEFAULT_QUALITY
from module.manga.cli import validate_root


def cmd_make_cover(args: argparse.Namespace) -> int:
    """封面写入子命令调度。"""
    mode = 'smart' if args.smart else 'center'

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = validate_root(args.root)
    if root is None:
        return 2

    print_run_banner(args.command, f'CBZ 封面写入（mode={mode}）', root, args.apply)
    plans = preview_plans(str(root), mode=mode, quality=args.quality, jobs=args.jobs)

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_make_cover_preview(plans)

    # ── 预览汇总 ──────────────────────────────────────────────────────────────
    n_changed   = sum(1 for p in plans if p.writable and p.changed)
    n_replaced  = sum(1 for p in plans if p.writable and p.changed and p.replaced)
    n_unchanged = sum(1 for p in plans if p.writable and not p.changed)
    n_skipped   = sum(1 for p in plans if not p.writable)
    emit(f'\n{SEP2}')
    print_summary(
        '解析完成',
        [
            ('✅', n_changed,   '待写入'),
            ('🔁', n_replaced,  '替换现有'),
            ('—',  n_unchanged, '已是最新'),
            ('⛔', n_skipped,   '跳过'),
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
        emit('  没有需要写入的封面（全部已是最新或被跳过）。')
        emit(SEP2)
        return 0

    if not confirm(
        f'\n🟡 确认对 {n_changed} 个 CBZ 写入封面？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    apply_plans(plans, dry_run=False)
    emit(SEP2)
    return 0


def add_make_cover_args(p: argparse.ArgumentParser) -> None:
    """挂载封面写入子命令的参数。"""
    p.add_argument('--root',    default='', metavar='DIR',
                   help='CBZ 文件根目录（递归处理所有子目录）')
    p.add_argument('--apply',   action='store_true',
                   help='实际写入封面（不加此参数则仅预览）')
    p.add_argument('--smart',   action='store_true',
                   help='使用 smartcrop 显著性裁剪（默认居中裁剪）')
    p.add_argument('--quality', type=int, default=DEFAULT_QUALITY,
                   metavar='N',
                   help=f'WebP 质量（1-100，默认 {DEFAULT_QUALITY}）')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；≥ 4 个文件时才会真正启用并行）')
