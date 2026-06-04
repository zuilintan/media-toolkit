"""图片目录序号化重命名 + STORED zip 打包的子命令实现。

两种输入(可组合,至少指定一项):

- ``--root <dir>``  根目录(可重复):递归识别其下打包单位
- ``--unit <dir>``  打包单位(可重复):直接指定一个打包单位目录(image leaf
  或 wrapper);workflow 层会按 FLAT / NESTED 自动识别。
"""

from __future__ import annotations

import argparse

from base.console import SEP2, emit, confirm, error, print_summary
from module.manga.presentation.view import print_pack_pic_preview, print_run_banner
from module.manga.workflow.pack_pic import apply_plans, preview_plans_for_targets
from module.manga.cli import validate_dirs


def cmd_pack_pic(args: argparse.Namespace) -> int:
    """图片打包子命令调度。"""
    if not args.root and not args.unit:
        error('请指定 --root <dir> 或 --unit <dir>(可重复,可组合)')
        return 2

    roots = validate_dirs(args.root)
    units = validate_dirs(args.unit)
    if roots is None or units is None:
        return 2

    banner_target = f'根 {len(roots)} / 单位 {len(units)}'
    print_run_banner(args.command, '图片目录序号化重命名 + STORED zip 打包',
                     banner_target, args.apply)
    plans = preview_plans_for_targets(roots, units, jobs=args.jobs)

    if not plans:
        emit('\n  没有识别出可打包的单位。')
        emit(SEP2)
        return 0

    print_pack_pic_preview(plans)

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
    p.add_argument('--root',    action='append', default=[], metavar='DIR',
                   help='待处理根目录（可重复指定）；递归识别其下图片目录单位')
    p.add_argument('--unit',    action='append', default=[], metavar='DIR',
                   help='直接指定单个打包单位目录（可重复指定）；'
                        'workflow 层按 FLAT / NESTED 自动识别')
    p.add_argument('--apply',   action='store_true',
                   help='实际执行重命名 + 打包（不加此参数则仅预览）')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；≥ 4 个目录时才真正启用并行）')
