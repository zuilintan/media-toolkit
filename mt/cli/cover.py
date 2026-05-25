"""
cover.py — cover 子命令：为 CBZ 追加 0000.webp 封面

解决 grimmory 在生成 cover 时遇到「decompression bomb」（源图超过 2000 万
像素）的问题。通过在 CBZ 内追加一张 2:3 / ≤ 1000×1500 的 WebP（字典序排
在最前），grimmory 即可直接用之，不再读取超大原图。

流程: scan → 全量 plan（含裁剪+编码）→ 预览 → 二次确认 → 整批写入 → 可选移动。
与 cli/metadata.py 结构对称。

依赖: workflow.cover / workflow.drag / infra.console / presentation
"""

from __future__ import annotations

import argparse

from mt.infra.console import SEP2, emit, confirm, print_summary
from mt.presentation.view import print_cover_preview, print_run_banner
from mt.workflow.cover import (
    plan_covers, apply_cover_plans, make_process_cover_dir,
    DEFAULT_QUALITY,
)
from mt.workflow.drag import run_drag_loop, move_dir
from mt.cli import validate_root


def cmd_cover(args: argparse.Namespace) -> int:
    """cover 子命令调度。"""
    mode = 'smart' if args.smart else 'center'

    # ── 旁路: drag ───────────────────────────────────────────────────────────
    if args.drag:
        run_drag_loop(
            title='cover 循环拖入模式',
            target=args.move_to,
            process_one=make_process_cover_dir(mode, args.quality),
        )
        return 0

    if args.move_to and not args.apply:
        emit('❌ --move-to 需配合 --drag 或 --apply 使用')
        return 2

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = validate_root(args.root)
    if root is None:
        return 2

    print_run_banner('cover', f'CBZ 封面追加写入（mode={mode}）', root, args.apply)
    plans = plan_covers(str(root), mode=mode, quality=args.quality)
    emit(f'  找到文件: {len(plans)} 个 .cbz（含子目录）')

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_cover_preview(plans)

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
        f'\n🟡 确认对 {n_changed} 个 CBZ 写入 0000.webp？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    apply_cover_plans(plans, dry_run=False)
    if args.move_to:
        for sub in sorted(root.iterdir()):
            if sub.is_dir():
                move_dir(sub, args.move_to)
    emit(SEP2)
    return 0


def add_cover_args(p: argparse.ArgumentParser) -> None:
    """挂载 cover 子命令的参数。"""
    p.add_argument('--root',    default='', metavar='DIR',
                   help='CBZ 文件根目录（递归处理所有子目录）')
    p.add_argument('--move-to', default='', dest='move_to',
                   metavar='DIR',
                   help='处理完成后将根目录下的子目录移动至此目录'
                        '（需配合 --drag 或 --apply）')
    p.add_argument('--apply',   action='store_true',
                   help='实际写入 0000.webp（不加此参数则仅预览）')
    p.add_argument('--drag',    action='store_true',
                   help='循环拖入模式')
    p.add_argument('--smart',   action='store_true',
                   help='使用 smartcrop 显著性裁剪（默认居中裁剪）')
    p.add_argument('--quality', type=int, default=DEFAULT_QUALITY,
                   metavar='N',
                   help=f'WebP 质量（1-100，默认 {DEFAULT_QUALITY}）')
