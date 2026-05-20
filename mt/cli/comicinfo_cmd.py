"""
cli/comicinfo_cmd.py — manga-comicinfo CLI 入口

用法:
  manga-comicinfo --root <dir>          # 预览（不修改文件）
  manga-comicinfo --root <dir> --apply  # 实际写入
  manga-comicinfo --examples            # 内置示例解析

文件数量 >= 100 时，每条目的详细日志自动写入同级目录的 .log 文件，
终端仅显示进度和汇总统计，避免输出溢出。
"""

from __future__ import annotations
import sys
import io
import contextlib
import argparse
from pathlib import Path
from datetime import datetime

from mt.console import setup_logging, SEP, SEP2
from mt.comicinfo import (
    _get_stem, _extract_publisher_name, extract_author,
    collect_fields, process_cbz,
)
from mt.parser import parse_name

# 超过此数量时将详细输出写入日志文件
_LARGE_THRESHOLD = 100

# ── 内置示例 ──────────────────────────────────────────────────────────────────

_EXAMPLES_PUBLISHER_FILE = '[社团]：青年晚报.txt'

_BUILTIN_EXAMPLES = [
    '[ゆ] 真夏 [zxx].zip',
    '[爱] 催眠 CH.01-04.5+番外篇 ～总集篇～ [zh][uncensored]',
    '[煌] JK VOL.04 CH.01-03+番外篇 ～アイデア落書き集～ (原神) ¦想法涂鸦集¦ [zh][uncensored].zip',
    '[mil] MyLittleLover (小林さんちのメイドラゴン) [zh].cbz',
    '[作者] タイトル 总集篇 VOL.03 [zh].cbz',
    '[作者] タイトル 番外篇 [zh].cbz',
    '[作者] タイトル 后日谈 ～素晴らしき日々～ [zh].cbz',
]


def run_examples() -> None:
    """解析内置示例并打印字段，Publisher 由常量模拟。"""
    sim_pub = _extract_publisher_name(_EXAMPLES_PUBLISHER_FILE)

    print(SEP2)
    print(f'  manga-comicinfo  —  内置示例解析（共 {len(_BUILTIN_EXAMPLES)} 条）')
    print(f'  模拟出版商文件: {_EXAMPLES_PUBLISHER_FILE}  →  Publisher: {sim_pub}')
    print(SEP2)

    from mt.console import print_comicinfo_fields
    ok_n = fail = 0
    for fname in _BUILTIN_EXAMPLES:
        stem   = _get_stem(fname)
        author = extract_author(fname)
        print(f'\n{SEP}')
        print(f'  📝  {stem}')
        print()
        if not author:
            print('  ❌  无法提取作者，跳过。')
            fail += 1
            continue
        mi     = parse_name(author, stem)
        fields = collect_fields(mi, sim_pub)
        print_comicinfo_fields(fields)
        ok_n += 1

    print(f'\n{SEP2}')
    print(f'  示例解析完成  ✅ {ok_n} 成功   ❌ {fail} 失败')
    print(SEP2)


# ═══════════════════════════════════════════════════════════════════════════════
# 大批量处理：捕获每条目输出写入日志
# ═══════════════════════════════════════════════════════════════════════════════

def _run_with_log(
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
    lines.append(f'manga-comicinfo 批量日志  {ts_header}')
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
        done = idx
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


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='manga-comicinfo',
        description='CBZ 漫画 ComicInfo.xml 批量生成/更新工具（ComicInfo v2.1）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-comicinfo --examples\n'
            '  manga-comicinfo --root ./manga\n'
            '  manga-comicinfo --root ./manga --apply\n'
        ),
    )
    parser.add_argument('--root',     metavar='DIR',
                        help='CBZ 文件根目录（递归处理所有子目录）')
    parser.add_argument('--apply',    action='store_true',
                        help='实际写入 ComicInfo.xml（不加此参数则仅预览）')
    parser.add_argument('--examples', action='store_true',
                        help='解析内置示例并展示结果，不处理任何文件')
    parser.add_argument('--debug',    action='store_true',
                        help='启用 debug 日志')
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.examples:
        run_examples()
        return

    if not args.root:
        parser.error('请指定 --root <目录> 或使用 --examples')

    root = Path(args.root).resolve()
    if not root.exists():
        print(f'❌ 目录不存在: {root}')
        sys.exit(1)
    if not root.is_dir():
        print(f'❌ 路径不是目录: {root}')
        sys.exit(1)

    cbz_files = sorted(root.rglob('*.cbz'))
    total     = len(cbz_files)
    use_log   = (total >= _LARGE_THRESHOLD)

    print(SEP2)
    print('  manga-comicinfo  —  CBZ ComicInfo.xml 批量工具')
    print(SEP2)
    print(f'  根目录:   {root}')
    print(f'  模式:     {"【写入模式】实际修改文件" if args.apply else "【预览模式】仅展示解析结果，不修改文件"}')
    print(f'  找到文件: {total} 个 .cbz（含子目录）')

    if not cbz_files:
        print('\n  没有需要处理的文件。')
        return

    counts: dict[str, int] = {'ok': 0, 'skip': 0, 'error': 0, 'warn': 0}

    if use_log:
        ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
        mode_tag = 'apply' if args.apply else 'preview'
        log_path = root.parent / f'comicinfo_{mode_tag}_{ts}.log'
        print(f'\n  文件数量 {total} ≥ {_LARGE_THRESHOLD}，详细结果将写入:\n  {log_path}\n')
        _run_with_log(cbz_files, args.apply, counts, log_path)
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
    if use_log:
        print(f'  📄 详细日志: {log_path}')
    if not args.apply and counts['ok'] > 0:
        print('  → 确认无误后，加上 --apply 参数重新运行以实际执行。')
    print(SEP2)


if __name__ == '__main__':
    main()
