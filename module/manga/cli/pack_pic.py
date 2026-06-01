"""图片目录序号化重命名 + STORED zip 打包的子命令实现。

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批执行。
详见 :mod:`module.manga.workflow.pack_pic`。
"""

from __future__ import annotations

import argparse

from base.console import SEP2, emit, confirm, print_summary
from module.manga.presentation.view import print_pack_preview, print_run_banner
from module.manga.workflow.pack_pic import preview_plans, apply_plans
from module.manga.cli import validate_root


def cmd_pack_pic(args: argparse.Namespace) -> int:
    """图片打包子命令调度。"""
    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = validate_root(args.root)
    if root is None:
        return 2

    print_run_banner(args.command, '图片目录序号化重命名 + STORED zip 打包',
                     root, args.apply)
    plans = preview_plans(str(root), jobs=args.jobs)

    if not plans:
        emit('\n  没有识别出可打包的单位。')
        emit(SEP2)
        return 0

    print_pack_preview(plans)

    # ── 预览汇总 ──────────────────────────────────────────────────────────────
    n_writable = sum(1 for p in plans if p.writable)
    n_replaced = sum(1 for p in plans if p.writable and p.zip_exists)
    n_skipped  = sum(1 for p in plans if not p.writable)
    emit(f'\n{SEP2}')
    print_summary(
        '解析完成',
        [
            ('✅', n_writable, '待处理'),
            ('🔁', n_replaced, '覆盖现有 zip'),
            ('⛔', n_skipped,  '跳过'),
        ],
        note='' if args.apply else '（预览，未实际修改）',
    )

    if not args.apply:
        if n_writable:
            emit('  → 确认无误后，加上 --apply 参数重新运行以实际执行。')
        emit(SEP2)
        return 0

    # ── 写入分支 ──────────────────────────────────────────────────────────────
    if not n_writable:
        emit('  没有可执行的单位。')
        emit(SEP2)
        return 0

    if not confirm(
        f'\n🟡 确认对 {n_writable} 个单位执行打包并删除源目录？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    apply_plans(plans, dry_run=False)
    emit(SEP2)
    return 0


def add_pack_pic_args(p: argparse.ArgumentParser) -> None:
    """挂载图片打包子命令的参数。"""
    p.add_argument('--root',    default='', metavar='DIR',
                   help='待处理根目录（递归识别图片目录单位：「仅图片」'
                        '或「仅含图片子目录」即视为一本漫画）')
    p.add_argument('--apply',   action='store_true',
                   help='实际执行重命名 + 打包（不加此参数则仅预览）')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；≥ 4 个目录时才真正启用并行）')
