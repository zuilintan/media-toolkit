"""
comicinfo.py — comicinfo 子命令：向 CBZ 写入 ComicInfo.xml

文件数量较多时，详细日志写入 .log 文件，终端仅显示进度条与汇总。

依赖: workflow.comicinfo / infra.console / cli.examples
"""

from __future__ import annotations

import argparse
import contextlib
import io
from datetime import datetime
from pathlib import Path

from mt.infra.console import SEP2
from mt.workflow.comicinfo import process_cbz
from mt.cli.examples import run_comicinfo_examples

# 文件数量 ≥ 此阈值时，详细日志写入 .log 文件，终端仅显示进度条与汇总
_LARGE_THRESHOLD = 100


def _run_comicinfo_with_log(
    cbz_files: list[Path],
    apply: bool,
    counts: dict[str, int],
    log_path: Path,
) -> None:
    """处理所有文件，将每条目详细输出重定向到 log_path（UTF-8）。

    终端仅显示实时进度条，完成后写入日志。
    """
    total  = len(cbz_files)
    lines: list[str] = []

    ts_header = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines.append(f'manga-toolkit-cli comicinfo 批量日志  {ts_header}')
    lines.append(f'模式: {"写入" if apply else "预览"}   总文件数: {total}')
    lines.append(SEP2)

    for idx, fp in enumerate(cbz_files, 1):
        # 捕获 process_cbz 的所有 print 输出
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = process_cbz(str(fp), apply=apply)
        counts[result] += 1
        lines.append(buf.getvalue().rstrip('\n'))

        # 终端进度（覆盖同一行）
        done   = idx
        bar_w  = 30
        filled = int(bar_w * done / total)
        bar    = '█' * filled + '░' * (bar_w - filled)
        pct    = done * 100 // total
        print(
            f'\r  [{bar}] {pct:3d}%  {done}/{total}',
            end='', flush=True,
        )

    print()  # 换行，清除进度条

    # 追加汇总行
    lines.append(SEP2)
    ok_n = counts['ok']; warn = counts['warn']
    skip = counts['skip']; err = counts['error']
    lines.append(
        f'完成  ✅ {ok_n} 成功'
        + (f'  ⚠️  {warn} 需 review' if warn else '')
        + (f'  — {skip} 跳过'        if skip else '')
        + (f'  ❌ {err} 失败'         if err  else '')
    )

    log_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def cmd_comicinfo(args: argparse.Namespace) -> int:
    """comicinfo 子命令调度。"""
    if args.examples:
        run_comicinfo_examples()
        return 0

    if not args.root:
        print('❌ 请指定 --root <目录> 或使用 --examples')
        return 2

    root = Path(args.root).resolve()
    if not root.exists():
        print(f'❌ 目录不存在: {root}')
        return 1
    if not root.is_dir():
        print(f'❌ 路径不是目录: {root}')
        return 1

    cbz_files = sorted(root.rglob('*.cbz'))
    total     = len(cbz_files)
    use_log   = (total >= _LARGE_THRESHOLD)

    print(SEP2)
    print('  manga-toolkit-cli  —  comicinfo (CBZ ComicInfo.xml 批量工具)')
    print(SEP2)
    print(f'  根目录:   {root}')
    print(f'  模式:     {"【写入模式】实际修改文件" if args.apply else "【预览模式】仅展示解析结果，不修改文件"}')
    print(f'  找到文件: {total} 个 .cbz（含子目录）')

    if not cbz_files:
        print('\n  没有需要处理的文件。')
        return 0

    counts: dict[str, int] = {'ok': 0, 'skip': 0, 'error': 0, 'warn': 0}
    log_path: Path | None  = None

    if use_log:
        ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
        mode_tag = 'apply' if args.apply else 'preview'
        log_path = root.parent / f'comicinfo_{mode_tag}_{ts}.log'
        print(f'\n  文件数量 {total} ≥ {_LARGE_THRESHOLD}，详细结果将写入:\n  {log_path}\n')
        _run_comicinfo_with_log(cbz_files, args.apply, counts, log_path)
    else:
        for fp in cbz_files:
            counts[process_cbz(str(fp), apply=args.apply)] += 1

    # ── 终端汇总 ────────────────────────────────────────────────────────────
    print(f'\n{SEP2}')
    note  = '' if args.apply else '（预览，未实际修改）'
    parts = [f'✅ {counts["ok"]} 成功']
    if counts['warn']:  parts.append(f'⚠️  {counts["warn"]} 需 review')
    if counts['skip']:  parts.append(f'— {counts["skip"]} 跳过')
    if counts['error']: parts.append(f'❌ {counts["error"]} 失败')
    print(f'  完成{note}  {"   ".join(parts)}')
    if use_log and log_path is not None:
        print(f'  📄 详细日志: {log_path}')
    if not args.apply and counts['ok'] > 0:
        print('  → 确认无误后，加上 --apply 参数重新运行以实际执行。')
    print(SEP2)
    return 0


def add_comicinfo_args(p: argparse.ArgumentParser) -> None:
    """挂载 comicinfo 子命令的参数。"""
    p.add_argument('--root',     metavar='DIR',
                   help='CBZ 文件根目录（递归处理所有子目录）')
    p.add_argument('--apply',    action='store_true',
                   help='实际写入 ComicInfo.xml（不加此参数则仅预览）')
    p.add_argument('--examples', action='store_true',
                   help='解析内置示例并展示结果，不处理任何文件')
