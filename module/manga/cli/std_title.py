"""源文件（``.zip`` / ``.cbz``）批量标题标准化子命令实现。

两种模式（互斥）:

- ``--root <dir>``  批量模式：扫描 ``{root}/{author}/`` 结构（原行为）
- ``--file <path>`` 单文件 / 混合模式（可重复）：每个文件单独推导作者，
  ``[社团 (作者)]`` 自动抽取社团并生成 ``[社团]：XX.txt`` 标识；
  冲突 / 缺失时在 tty 下 prompt，non-tty 下报错退出

可选 ``--library-root`` 指向漫画库根目录：``--file`` 模式下推导出的作者会
先经 :mod:`~module.manga.workflow.author_library` 简繁归一对齐到库里既有
主名 / 别名（``[别名]：XX.txt``），命中即替换为库主名，避免一作者出现
"作者甲（繁）" 与 "作者甲（简）" 两份目录。

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
from module.manga.workflow.author_library import load_or_scan, scan_library
from module.manga.workflow.std_title import (
    AuthorDerivation, StdTitleAbort,
    apply_plans, derive_inputs,
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


def _cli_resolve(path: Path, deriv: AuthorDerivation) -> tuple[str, str] | None:
    """``derive_inputs`` 的 CLI 回调：tty → prompt；non-tty → 报错 + 抛中止。

    返回 ``None`` 表示用户跳过该文件 → 整批取消（CLI 语义：任一文件未确定即停）。
    """
    if not sys.stdin.isatty():
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
        raise StdTitleAbort
    author, publisher = _prompt_author(path, deriv)
    if not author:
        emit('  已跳过 → 操作取消。')
        raise StdTitleAbort
    return author, publisher


def _resolve_file_paths(files: list[str]) -> list[Path] | None:
    """``--file`` 列表合法性校验，返回 :class:`Path` 列表；任一非法即 ``None``。"""
    paths: list[Path] = []
    for f in files:
        path = Path(f).resolve()
        if not path.is_file():
            error(f'不是文件: {f}')
            return None
        if path.suffix.lower() not in FILE_EXTS:
            error(f'文件类型不支持（仅 .zip / .cbz）: {f}')
            return None
        paths.append(path)
    return paths


def _build_normalizer(library_root: str, force_rescan: bool):
    """根据 ``--library-root`` 构造 :func:`derive_inputs` 的 ``normalize_author``
    钩子；未指定库根时返回 ``None``（不做规范化）。
    """
    if not library_root:
        return None
    root = Path(library_root).resolve()
    if not root.is_dir():
        error(f'漫画库根目录不存在: {library_root}（已忽略，跳过规范化）')
        return None
    lib = load_or_scan(root, force_rescan=force_rescan)
    emit(f'  📚 已加载库索引: {len(lib)} 个作者')
    return lib.resolve


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
        paths = _resolve_file_paths(args.file)
        if paths is None:
            emit(SEP2)
            return 2
        normalize_author = _build_normalizer(args.library_root,
                                             args.rebuild_author_index)
        try:
            inputs = derive_inputs(paths, resolve_fn=_cli_resolve,
                                   normalize_author=normalize_author)
        except StdTitleAbort:
            emit(SEP2)
            return 2
        plans = preview_plans_for_inputs(inputs, jobs=args.jobs)
    else:
        root = validate_root(args.root)
        if root is None:
            return 2
        print_run_banner(args.command, '源文件批量重命名', root, args.apply)
        # --root 模式下父目录即作者，不需要二次规范化；但若用户指定了
        # --rebuild-author-index，顺手把这次扫到的库快照存一下，方便后续
        # --file 模式复用
        if args.rebuild_author_index:
            scan_library(root)
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
    p.add_argument('--library-root',  default='', metavar='DIR',
                   help='漫画库根目录（按 {root}/{author}/ 组织）；--file 模式下'
                        '指定后推导作者会先在库里查简繁归一一致的主名 / 别名 '
                        '([别名]：xxx.txt)，命中即对齐，避免一作者出现简繁两份'
                        '目录。--root 模式父目录即作者，无需指定本选项')
    p.add_argument('--rebuild-author-index', action='store_true',
                   help='强制重建漫画库作者索引（默认懒加载已落盘的 cache）')
