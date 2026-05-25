"""
metadata.py — metadata 子命令：向 CBZ 写入 ComicInfo.xml 元数据

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批写入 → 可选移动。
与 cli/sourcefile.py 结构对称。

依赖: workflow.metadata / workflow.drag / infra.console / presentation
      / cli.examples
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mt.infra.console import SEP2, emit, confirm, print_summary
from mt.presentation.view import print_metadata_preview, print_run_banner
from mt.workflow.metadata import (
    plan_metadatas, apply_metadata_plans, process_metadata_dir,
)
from mt.workflow.drag import run_drag_loop, move_dir
from mt.cli.examples import run_metadata_examples


def _validate_root(root_arg: str) -> Path | None:
    """统一的 --root 校验（与 cli/sourcefile 对齐）。返回 None 表示已报错。"""
    if not root_arg:
        emit('❌ 请指定 --root <目录>'); return None
    root = Path(root_arg).resolve()
    if not root.exists():
        emit(f'❌ 目录不存在: {root}'); return None
    if not root.is_dir():
        emit(f'❌ 路径不是目录: {root}'); return None
    return root


def cmd_metadata(args: argparse.Namespace) -> int:
    """metadata 子命令调度。"""
    # ── 旁路子命令 ────────────────────────────────────────────────────────────
    if args.examples:
        return 0 if run_metadata_examples() == 0 else 1
    if args.drag:
        run_drag_loop(
            title='metadata 循环拖入模式',
            target=args.move_to,
            process_one=process_metadata_dir,
        )
        return 0

    if args.move_to and not args.apply:
        emit('❌ --move-to 需配合 --drag 或 --apply 使用')
        return 2

    # ── 批量模式 ──────────────────────────────────────────────────────────────
    root = _validate_root(args.root)
    if root is None:
        return 2

    print_run_banner('metadata', 'CBZ ComicInfo.xml 批量工具', root, args.apply)
    plans = plan_metadatas(str(root))
    emit(f'  找到文件: {len(plans)} 个 .cbz（含子目录）')

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_metadata_preview(plans)

    # ── 预览汇总 ──────────────────────────────────────────────────────────────
    n_writable = sum(1 for p in plans if p.writable)
    n_conflict = sum(1 for p in plans if not p.writable)
    n_warn     = sum(1 for p in plans if p.mi.warnings)
    emit(f'\n{SEP2}')
    print_summary(
        '解析完成',
        [
            ('✅', n_writable, '可写'),
            ('⛔', n_conflict, '出版商冲突'),
            ('🟡', n_warn,     '有警告'),
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
        emit('  没有可写入的文件。')
        emit(SEP2)
        return 0

    if not confirm(
        f'\n🟡 确认对 {n_writable} 个 CBZ 写入 ComicInfo.xml？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    apply_metadata_plans(plans, dry_run=False)
    if args.move_to:
        for sub in sorted(root.iterdir()):
            if sub.is_dir():
                move_dir(sub, args.move_to)
    emit(SEP2)
    return 0


def add_metadata_args(p: argparse.ArgumentParser) -> None:
    """挂载 metadata 子命令的参数。"""
    p.add_argument('--root',    default='', metavar='DIR',
                   help='CBZ 文件根目录（递归处理所有子目录）')
    p.add_argument('--move-to', default='', dest='move_to',
                   metavar='DIR',
                   help='处理完成后将根目录下的子目录移动至此目录（需配合 --drag 或 --apply）')
    p.add_argument('--apply',   action='store_true',
                   help='实际写入 ComicInfo.xml（不加此参数则仅预览）')
    p.add_argument('--drag',    action='store_true',
                   help='循环拖入模式')
    p.add_argument('--examples', action='store_true',
                   help='解析内置示例并展示结果，不处理任何文件')
