"""源文件（``.zip`` / ``.cbz``）批量标题标准化子命令实现。

两种模式（互斥）:

- ``--root <dir>``  批量模式：扫描 ``{root}/{author}/`` 结构（原行为）
- ``--file <path>`` 单文件 / 混合模式（可重复）：每个文件单独推导作者，
  ``[社团 (作者)]`` 自动抽取社团并生成 ``[社团]：XX.txt`` 标识；
  冲突 / 缺失时在 tty 下 prompt，non-tty 下报错退出

流程: scan → 全量 plan → 预览 → 预览汇总 → 二次确认 → 整批写入。结构与
:mod:`module.manga.cli.make_meta` 对称。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from base.console import SEP2, emit, confirm, error, print_summary
from module.manga.core.config import FILE_EXTS
from module.manga.presentation.view import print_std_title_preview, print_run_banner
from module.manga.workflow.std_title import (
    AuthorDerivation, StdTitleInput,
    apply_plans, build_input, derive_author,
    preview_plans, preview_plans_for_inputs,
)
from module.manga.cli import validate_root
from module.manga.extras.examples import run_std_title_examples


# ═══════════════════════════════════════════════════════════════════════════════
# 单文件作者解析（tty 交互 / non-tty 报错）
# ═══════════════════════════════════════════════════════════════════════════════

def _prompt_author(path: Path, deriv: AuthorDerivation) -> tuple[str, str]:
    """tty 下交互选作者，返回 ``(author, publisher)``；用户取消时返回 ``('', '')``。"""
    emit(f'\n📄 {path.name}')
    options: list[tuple[str, str, str]] = []   # (label, author, publisher)
    if deriv.parent_author:
        options.append(
            (f'父目录: {deriv.parent_author}', deriv.parent_author, '')
        )
    if deriv.bracket_author:
        pub   = deriv.bracket_publisher
        label = (f'[]:    {deriv.bracket_author}'
                 + (f'  (社团: {pub})' if pub else ''))
        options.append((label, deriv.bracket_author, pub))

    if options:
        emit('  请选择作者来源:')
        for i, (label, _, _) in enumerate(options, 1):
            emit(f'    {i}. {label}')
        emit(f'    {len(options) + 1}. 手动输入')
        emit( '    0. 跳过')
        while True:
            choice = input('  输入序号: ').strip()
            if choice == '0':
                return '', ''
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(options):
                    _, a, pub = options[idx - 1]
                    return a, pub
                if idx == len(options) + 1:
                    break
            emit('  无效输入，请重试')

    author = input('  请输入作者: ').strip()
    return (author, '') if author else ('', '')


def _resolve_file_inputs(files: list[str]) -> list[StdTitleInput] | None:
    """解析 ``--file`` 列表为 :class:`StdTitleInput` 列表。

    任一文件作者无法确定（non-tty 推导失败 / tty 用户跳过）即返回 ``None``。
    """
    is_tty = sys.stdin.isatty()
    inputs: list[StdTitleInput] = []
    for f in files:
        path = Path(f).resolve()
        if not path.is_file():
            error(f'不是文件: {f}')
            return None
        if path.suffix.lower() not in FILE_EXTS:
            error(f'文件类型不支持（仅 .zip / .cbz）: {f}')
            return None

        deriv     = derive_author(str(path))
        author    = deriv.auto_author
        publisher = (deriv.bracket_publisher
                     if author and author == deriv.bracket_author else '')

        if not author:
            if not is_tty:
                if deriv.conflict:
                    error(
                        f'作者推导冲突: {path.name}\n'
                        f'  父目录: {deriv.parent_author}\n'
                        f'  []:     {deriv.bracket_author}\n'
                        f'  → 请整理后重试（交互式终端下可 prompt 选择）'
                    )
                else:
                    error(
                        f'无法推导作者: {path.name}'
                        f'（父目录 / [] 均未命中）'
                    )
                return None
            author, publisher = _prompt_author(path, deriv)
            if not author:
                emit('  已跳过 → 操作取消。')
                return None

        inputs.append(build_input(str(path), author, publisher))
    return inputs


# ═══════════════════════════════════════════════════════════════════════════════
# 命令调度
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_std_title(args: argparse.Namespace) -> int:
    """标题标准化子命令调度。"""
    # ── 旁路子命令 ────────────────────────────────────────────────────────────
    if args.examples:
        return 0 if run_std_title_examples() == 0 else 1

    if args.file and args.root:
        error('--file 与 --root 互斥')
        return 2
    if not args.file and not args.root:
        error('请指定 --root <dir> 或 --file <path>（可重复）')
        return 2

    # ── 模式分派：单文件 / 批量 ──────────────────────────────────────────────
    if args.file:
        banner_target = f'单文件模式（{len(args.file)} 个文件）'
        print_run_banner(args.command, '源文件批量重命名',
                         banner_target, args.apply)
        inputs = _resolve_file_inputs(args.file)
        if inputs is None:
            emit(SEP2)
            return 2
        plans = preview_plans_for_inputs(inputs, jobs=args.jobs)
    else:
        root = validate_root(args.root)
        if root is None:
            return 2
        print_run_banner(args.command, '源文件批量重命名', root, args.apply)
        plans = preview_plans(str(root), jobs=args.jobs)

    if not plans:
        emit('\n  没有需要处理的文件。')
        emit(SEP2)
        return 0

    print_std_title_preview(plans)

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

    apply_plans(plans, dry_run=False)
    emit(SEP2)
    return 0


def add_std_title_args(p: argparse.ArgumentParser) -> None:
    """挂载标题标准化子命令的参数。"""
    p.add_argument('--root',          default='',
                   help='漫画根目录（批量模式，目录下按作者目录组织）')
    p.add_argument('--file',          action='append', default=[], metavar='PATH',
                   help='单个源文件路径（可重复指定）；与 --root 互斥。'
                        '作者从父目录 / [社团 (作者)] 自动推导，'
                        '冲突 / 缺失时 tty 下交互选择')
    p.add_argument('--apply',         action='store_true',
                   help='执行重命名')
    p.add_argument('--examples',      action='store_true',
                   help='运行内置解析示例（回归测试）')
    p.add_argument('--jobs', '-j', type=int, default=1, metavar='N',
                   help='plan 阶段并行进程数（1=串行，默认；'
                        '0=自动 min(cpu, 4)；plan 阶段是纯字符串处理'
                        '故并行收益有限）')
