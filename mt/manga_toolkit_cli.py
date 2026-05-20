"""
manga_toolkit_cli.py — manga-toolkit 统一命令行入口

整合了原先两个独立工具：
  - 子命令 rename     → 漫画文件 / 目录批量重命名（原 manga-rename）
  - 子命令 comicinfo  → 向 CBZ 写入 ComicInfo.xml（原 manga-comicinfo）

模块名遵循 PEP 8（下划线），对外暴露的 console 命令则使用连字符
``manga-toolkit-cli``（CLI 惯例）。两者解耦，互不影响。

用法示例:
  manga-toolkit-cli rename --drag                          # 循环拖入模式（推荐）
  manga-toolkit-cli rename --drag --target /sorted         # 拖入后移动到指定目录
  manga-toolkit-cli rename --root /path/to/manga           # 批量预览
  manga-toolkit-cli rename --root /path/to/manga --apply   # 批量执行
  manga-toolkit-cli rename --rollback                      # 回退上次操作
  manga-toolkit-cli rename --list-sessions                 # 列出所有操作记录
  manga-toolkit-cli rename --examples                      # 内置解析示例

  manga-toolkit-cli comicinfo --root /path/to/cbz          # 预览
  manga-toolkit-cli comicinfo --root /path/to/cbz --apply  # 写入 ComicInfo.xml
  manga-toolkit-cli comicinfo --examples                   # 内置示例

兼容性: 也可使用 `python -m mt <subcommand> ...`。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from datetime import datetime
from pathlib import Path

from mt.infra.console import (
    setup_logging, highlight_diff, print_preview, print_comicinfo_fields,
    SEP, SEP2, RED, GREEN,
)
from mt.naming.parser import parse_name
from mt.naming.builder import build_new_name
from mt.workflow.scanner import (
    scan_and_plan, apply_renames, run_drag_loop, confirm,
)
from mt.workflow.session import list_sessions, rollback
from mt.workflow.comicinfo import (
    _get_stem, _extract_publisher_name, extract_author,
    collect_fields, process_cbz,
)


# ═══════════════════════════════════════════════════════════════════════════════
#                          ── rename 子命令 ──
# ═══════════════════════════════════════════════════════════════════════════════

# 内置解析示例（同时作为回归测试）
RENAME_EXAMPLES: list[tuple[str, str, str]] = [
    # (author, input, expected_output)
    ## 命名稳定性
    ("动", "[动] ニャーニャーワンワン VOL.01 CH.01-09 ～大危機～ (动物世界) [zh][uncensored]",
           "[动] ニャーニャーワンワン VOL.01 CH.01-09 ～大危機～ (动物世界) [zh][uncensored]"),
    ("ね", "[ね] 管理人 CH.01-02+番外篇 [zh]",
           "[ね] 管理人 CH.01-02+番外篇 [zh]"),
    ("无", "[无] 真夏 [zxx]",          "[无] 真夏 [zxx]"),
    ("花", "[花] オハ [colorized]",     "[花] オハ [colorized]"),
    ("花", "[花] オハ [ongoing]",       "[花] オハ [ongoing]"),
    ("鳳", "[鳳] 姉妹After CH.02 ～幼馴染～ [zh]",
           "[鳳] 姉妹After CH.02 ～幼馴染～ [zh]"),
    ("鳳", "[鳳] 姉妹 总集篇 ～全員～ [zh]",
           "[鳳] 姉妹 总集篇 ～全員～ [zh]"),
    ## 总集篇
    ("鳳", "[鳳] 姉妹 総集編 [zh]",    "[鳳] 姉妹 总集篇 [zh]"),
    ("鳳", "[鳳] 姉妹 ～総集編～ [zh]", "[鳳] 姉妹 总集篇 [zh]"),
    ("鳳", "[鳳] 姉妹 总集篇 上篇 [zh]","[鳳] 姉妹 总集篇 上篇 [zh]"),
    ## 番外篇 / 后日谈
    ("鳳", "[鳳] 姉妹 后日谈 [zh]",    "[鳳] 姉妹 后日谈 [zh]"),
    ("鳳", "[鳳] 姉妹 ～After～ [zh]", "[鳳] 姉妹 后日谈 [zh]"),
    ("鳳", "[鳳] 姉妹 After ～素晴话～ [zh]",
           "[鳳] 姉妹 后日谈 ～素晴话～ [zh]"),
    ("天", "[天] 時 番外 [zh]",         "[天] 時 番外篇 [zh]"),
    ("天", "[天] 時番外編 [zh]",        "[天] 時 番外篇 [zh]"),
    ("天", "[天] 時! 番外編～今日～ [zh]","[天] 時！ 番外篇 ～今日～ [zh]"),
    ("煌", "[煌] JK VOL.04 CH.00 ～ヤマ編～ [zh]",
           "[煌] JK VOL.04 番外篇 ～ヤマ編～ [zh]"),
    ## 卷数
    ("煌", "[煌] JK Season2 [zh]",      "[煌] JK VOL.02 [zh]"),
    ("煌", "[煌] JK Season2 CH.02 [zh]","[煌] JK VOL.02 CH.02 [zh]"),
    ("煌", "[煌] JK VOL.01 02 [zh]",    "[煌] JK VOL.01 CH.02 [zh]"),
    ("煌", "[煌] JK Season4.5 CH.06.2 ～水道編～ [zh]",
           "[煌] JK VOL.04.5 CH.06.2 ～水道編～ [zh]"),
    ## 话数
    ("多", "[多] 破手2.5 [zh]",         "[多] 破手 CH.02.5 [zh]"),
    ("多", "[多] 破手2.5〜無限〜（GT）[zh]",
           "[多] 破手 CH.02.5 ～無限～ (GT) [zh]"),
    ("水", "[水] 夫 [zh]",              "[水] 夫 [zh]"),
    ("水", "[水] 夫1 [zh]",             "[水] 夫 CH.01 [zh]"),
    ("水", "[水] 夫 1-3 [zh]",          "[水] 夫 CH.01-03 [zh]"),
    ("水", "[水] 夫 1-3+番外 [zh]",     "[水] 夫 CH.01-03+番外篇 [zh]"),
    ("水", "[水] 夫 4-5+番外 [zh]",     "[水] 夫 CH.04-05+番外篇 [zh]"),
    ("天", "[天] 時 1+2+2.5 [zh]",      "[天] 時 CH.01-02.5 [zh]"),
    ("笑", "[笑] 会長!2 (校园) [zh]",   "[笑] 会長！ CH.02 (校园) [zh]"),
    ("pz", "[pz] JKお嬢2 挑戦編 [zh]",  "[pz] JKお嬢 CH.02 ～挑戦編～ [zh]"),
    ("真", "[真] 蛇神 貳 [中国語]",      "[真] 蛇神 CH.02 [zh]"),
    ("真", "[真] 蛇神 参 [中国語]",      "[真] 蛇神 CH.03 [zh]"),
    ## 话标题
    ("冬", "[冬] 学生2 ~憑依~ [zh]",    "[冬] 学生 CH.02 ～憑依～ [zh]"),
    ("冬", "[冬] 学生2 ～憑依～ [zh]",  "[冬] 学生 CH.02 ～憑依～ [zh]"),
    ("冬", "[冬] 学生2～憑依 [zh]",     "[冬] 学生 CH.02 ～憑依～ [zh]"),
    ("冬", "[冬] 学生2 〜憑依〜 [zh]",  "[冬] 学生 CH.02 ～憑依～ [zh]"),
    ("は", "[は] 高慢-チャ- [zh]",      "[は] 高慢 ～チャ～ [zh]"),
    ("は", "[は] 高慢 CH.03 -ENDLESS HAREM- [zh]",
           "[は] 高慢 CH.03 ～ENDLESS・HAREM～ [zh]"),
    ## 分编复合词
    ("田", "[田] 幼 前編+中編+後編+After [zh]",
           "[田] 幼 上篇+中篇+下篇+后日谈 [zh]"),
    ("田", "[田] 幼 前編+後編 [zh]",    "[田] 幼 上篇+下篇 [zh]"),
    ("田", "[田] 幼【前編】 [zh]",      "[田] 幼 上篇 [zh]"),
    ("田", "[田] 幼【後編】 [zh]",      "[田] 幼 下篇 [zh]"),
    ("田", "[田] 幼 上編+下編 [zh]",    "[田] 幼 上篇+下篇 [zh]"),
    ("田", "[田] 幼 ～后編～ [zh]",     "[田] 幼 下篇 [zh]"),
    ## 「」替换
    ("人", "[人] 幼 2「绝伦」前編 [zh]","[人] 幼 CH.02 ～绝伦・上篇～ [zh]"),
    ("人", "[人] 幼 CH.00 ～本1～ [zh]","[人] 幼 番外篇 ～本①～ [zh]"),
    ("人", "[人] 幼6「夢幻」過去編I [zh]",
           "[人] 幼 CH.06 ～夢幻・過去編①～ [zh]"),
    ## 系列
    ("冲", "[70年 (冲)] 少女 (Fate Grand Order) [zh]",
           "[冲] 少女 (Fate・Grand・Order) [zh]"),
    ("冲", "[冲] 少女【後編】(ぼっち・ざ・ろっく!) [zh]",
           "[冲] 少女 下篇 (ぼっち・ざ・ろっく！) [zh]"),
    ("千", "(秋) [Re (千)] 蝶屋 (鬼滅の刃) [zh]",
           "[千] 蝶屋 (鬼滅の刃) [zh]"),
    ("春", "(新)[春] 真子[zh]",         "[春] 真子 [zh]"),
    ## 译名
    ("Cr", "[Cr] ヤリ～異世～｜完美 ～異世～ [zh]",
           "[Cr] ヤリ ～異世～ ¦完美 ～异世～¦ [zh]"),
    ("鳳", "[鳳] 姉妹｜精靈姊妹為找老公而來 [zh]",
           "[鳳] 姉妹 ¦精灵姐妹为找老公而来¦ [zh]"),
    ("Cr", "[Cr] ゆれ ¦ 摇曳 [zh]",     "[Cr] ゆれ ¦摇曳¦ [zh]"),
    ("合", "[合] SPOHAME 1,2,3！  ¦愛上運動 1,2,3！ [zh]",
           "[合] SPOHAME・1,2,3！ ¦爱上运动 1,2,3！¦ [zh]"),
    ## 彩色
    ("花", "[花] オハ 【フルカラー版】",  "[花] オハ [colorized]"),
    ## 噪音标签
    ("煌", "[煌] (COMIC アン 2014年06月号 Vol.49) Wi Be We [不咕鸟x这很汉化组]",
           "[煌] Wi・Be・We [zh]"),
    ("煌", "[煌] [14-08-07] ドロ [黑暗掃圖]",
           "[煌] ドロ [zh]"),
    ("煌", "[煌] [20-03-07] 千年～マイ、 スター～ 第1-5話 [鬼畜王汉化组]",
           "[煌] 千年 CH.01-05 ～マイ、・スター～ [zh]"),
    ("八", "[八] 天国 [中国翻訳] [無修正] v2",
           "[八] 天国 [zh][uncensored]"),
    ("和", "[和] 彼 [含着个人汉化 5+7个人去码] [無修正]",
           "[和] 彼 [zh][uncensored]"),
    ("和", "[和] 彼2023 [zh]",          "[和] 彼2023 [zh]"),
    ## 特殊
    ("LS", "[LS] 番外 LOL ～腕豪～",    "[LS] 番外・LOL ～腕豪～"),
    ("LS", "[LS] 在哪以后... [zh]",     "[LS] 在哪以后… [zh]"),
]


def run_rename_examples() -> None:
    """运行内建示例测试，逐条验证解析结果。"""
    print(f'\n{SEP2}')
    print('🧪 解析示例')
    print(SEP2)
    fail = 0
    for author, name, expected in RENAME_EXAMPLES:
        info   = parse_name(author, name)
        result = build_new_name(info)
        passed = result == expected
        if not passed:
            fail += 1
        mark = '✅' if passed else '❌'
        print(f'  {mark} 旧: {name}')
        print(f'     新: {highlight_diff(name, result, RED)}')
        if not passed:
            print(f'   预期: {highlight_diff(result, expected, GREEN)}')
        print()
    print(f'{"  全部通过 ✅" if not fail else f"  {fail} 个失败 ❌"}')
    print()


def cmd_rename(args: argparse.Namespace) -> int:
    """rename 子命令调度。"""
    if args.examples:
        run_rename_examples()
        return 0
    if args.list_sessions:
        list_sessions()
        return 0
    if args.rollback:
        rollback(args.session)
        return 0
    if args.drag:
        run_drag_loop(args.target)
        return 0

    # 批量模式
    if not args.root:
        print('❌ 请指定 --root <目录> 或使用 --drag / --examples')
        return 2

    print(f'\n📂 扫描目录: {args.root}')
    plans = scan_and_plan(args.root)
    print_preview(plans)

    if args.apply and confirm():
        apply_renames(plans, dry_run=False)
    elif not args.apply:
        apply_renames(plans, dry_run=True)
    return 0


def add_rename_args(p: argparse.ArgumentParser) -> None:
    """挂载 rename 子命令的参数。"""
    p.add_argument('--root',          default='',
                   help='漫画根目录（批量模式）')
    p.add_argument('--target',        default='',
                   help='拖入模式：处理后将作者目录移动到此目录（未指定则不移动）')
    p.add_argument('--apply',         action='store_true',
                   help='执行重命名（批量模式）')
    p.add_argument('--drag',          action='store_true',
                   help='循环拖入模式')
    p.add_argument('--rollback',      action='store_true',
                   help='回退上次操作')
    p.add_argument('--session',       default=None,
                   help='指定回退的 session ID（配合 --rollback）')
    p.add_argument('--list-sessions', action='store_true',
                   dest='list_sessions',
                   help='列出所有可回退的操作记录')
    p.add_argument('--examples',      action='store_true',
                   help='运行内置解析示例（回归测试）')


# ═══════════════════════════════════════════════════════════════════════════════
#                          ── comicinfo 子命令 ──
# ═══════════════════════════════════════════════════════════════════════════════

# 文件数量 ≥ 此阈值时，详细日志写入 .log 文件，终端仅显示进度条与汇总
_LARGE_THRESHOLD = 100

# 内置示例用的模拟出版商文件名
_EXAMPLES_PUBLISHER_FILE = '[社团]：青年晚报.txt'

_COMICINFO_BUILTIN_EXAMPLES = [
    '[ゆ] 真夏 [zxx].zip',
    '[爱] 催眠 CH.01-04.5+番外篇 ～总集篇～ [zh][uncensored]',
    '[煌] JK VOL.04 CH.01-03+番外篇 ～アイデア落書き集～ (原神) ¦想法涂鸦集¦ [zh][uncensored].zip',
    '[mil] MyLittleLover (小林さんちのメイドラゴン) [zh].cbz',
    '[作者] タイトル 总集篇 VOL.03 [zh].cbz',
    '[作者] タイトル 番外篇 [zh].cbz',
    '[作者] タイトル 后日谈 ～素晴らしき日々～ [zh].cbz',
]


def run_comicinfo_examples() -> None:
    """解析内置示例并打印字段，Publisher 由常量模拟，PageCount 留空。"""
    sim_pub = _extract_publisher_name(_EXAMPLES_PUBLISHER_FILE)

    print(SEP2)
    print(f'  comicinfo  —  内置示例解析（共 {len(_COMICINFO_BUILTIN_EXAMPLES)} 条）')
    print(f'  模拟出版商文件: {_EXAMPLES_PUBLISHER_FILE}  →  Publisher: {sim_pub}')
    print(SEP2)

    ok_n = fail = 0
    for fname in _COMICINFO_BUILTIN_EXAMPLES:
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


# ═══════════════════════════════════════════════════════════════════════════════
#                          ── 主入口 ──
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='manga-toolkit-cli',
        description='manga-toolkit 统一命令行工具（rename + comicinfo）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  manga-toolkit-cli rename --drag\n'
            '  manga-toolkit-cli rename --drag --target /sorted\n'
            '  manga-toolkit-cli rename --root /path/to/manga --apply\n'
            '  manga-toolkit-cli rename --rollback\n'
            '  manga-toolkit-cli rename --examples\n'
            '  manga-toolkit-cli comicinfo --root /path/to/cbz\n'
            '  manga-toolkit-cli comicinfo --root /path/to/cbz --apply\n'
            '  manga-toolkit-cli comicinfo --examples\n'
        ),
    )
    parser.add_argument('--debug', action='store_true',
                        help='启用 debug 日志')

    sub = parser.add_subparsers(
        dest='command', metavar='<command>', required=True,
        help='可用子命令'
    )

    # rename
    p_rename = sub.add_parser(
        'rename',
        help='漫画文件 / 目录批量重命名',
        description='漫画文件 / 目录批量重命名工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '常用模式:\n'
            '  manga-toolkit-cli rename --root <dir>         # 批量预览\n'
            '  manga-toolkit-cli rename --root <dir> --apply # 批量执行\n'
            '  manga-toolkit-cli rename --drag               # 循环拖入模式（推荐）\n'
            '  manga-toolkit-cli rename --drag --target <dir># 拖入后移动至目录\n'
            '  manga-toolkit-cli rename --examples           # 内置解析示例\n'
        ),
    )
    add_rename_args(p_rename)
    p_rename.set_defaults(func=cmd_rename)

    # comicinfo
    p_ci = sub.add_parser(
        'comicinfo',
        help='向 CBZ 写入 ComicInfo.xml',
        description='CBZ 漫画 ComicInfo.xml 批量生成/更新工具（ComicInfo v2.1）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-toolkit-cli comicinfo --examples\n'
            '  manga-toolkit-cli comicinfo --root ./manga\n'
            '  manga-toolkit-cli comicinfo --root ./manga --apply\n'
        ),
    )
    add_comicinfo_args(p_ci)
    p_ci.set_defaults(func=cmd_comicinfo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)
    setup_logging(args.debug)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
