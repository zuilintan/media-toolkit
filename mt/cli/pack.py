"""
pack.py — pack 子命令：图片目录序号化重命名 + STORED zip 打包

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批执行 → 可选移动 zip。
与 cli/sourcefile.py 结构对称。

依赖: workflow.pack / workflow.drag / infra.console / presentation
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mt.infra.console import SEP2, emit, confirm, print_summary
from mt.presentation.view import print_pack_preview, print_run_banner
from mt.workflow.pack import (
    plan_packs, apply_pack_plans, process_pack_dir, move_zip,
)
from mt.workflow.drag import run_drag_loop
from mt.cli import validate_root


def cmd_pack(args: argparse.Namespace) -> int:
    """pack 子命令调度。"""
    # ── 旁路: drag ───────────────────────────────────────────────────────────
    if args.drag:
        run_drag_loop(
            title='pack 循环拖入模式',
            target=args.move_to,
            process_one=process_pack_dir,
        )
        return 0

    if args.move_to and not args.apply:
        emit('❌ --move-to 需配合 --drag 或 --apply 使用')
        return 2

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = validate_root(args.root)
    if root is None:
        return 2

    print_run_banner('pack', '图片目录序号化重命名 + STORED zip 打包',
                     root, args.apply)
    plans = plan_packs(str(root), jobs=args.jobs)

    if not plans:
        emit('\n  没有需要处理的目录。')
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
        emit('  没有可执行的目录。')
        emit(SEP2)
        return 0

    if not confirm(
        f'\n🟡 确认对 {n_writable} 个目录执行重命名并打包？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    fail = apply_pack_plans(plans, dry_run=False)
    if args.move_to and fail == 0:
        for p in plans:
            if p.writable:
                move_zip(Path(p.zip_path), args.move_to)
    elif args.move_to and fail > 0:
        emit(f'  🟡 {fail} 个失败，跳过移动。')
    emit(SEP2)
    return 0


def add_pack_args(p: argparse.ArgumentParser) -> None:
    """挂载 pack 子命令的参数。"""
    p.add_argument('--root',    default='', metavar='DIR',
                   help='待处理根目录（其下每个直接子目录为一本相册/漫画）')
    p.add_argument('--move-to', default='', dest='move_to',
                   metavar='DIR',
                   help='处理完成后将生成的 zip 移动到此目录'
                        '（需配合 --drag 或 --apply）')
    p.add_argument('--apply',   action='store_true',
                   help='实际执行重命名 + 打包（不加此参数则仅预览）')
    p.add_argument('--drag',    action='store_true',
                   help='循环拖入模式')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；≥ 4 个目录时才真正启用并行）')
