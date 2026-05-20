"""
cli/rename_cmd.py — manga-rename CLI 入口

用法:
  manga-rename                  # 批量预览（需 --root）
  manga-rename --drag           # 循环拖入模式（推荐）
  manga-rename --apply          # 批量执行
  manga-rename --examples       # 内置解析示例
  manga-rename --rollback       # 回退上次操作
  manga-rename --list-sessions  # 列出所有操作记录
"""

from __future__ import annotations
import argparse

from mt.console import (
    setup_logging, highlight_diff, print_preview, SEP2, RED, GREEN,
)
from mt.parser import parse_name
from mt.builder import build_new_name
from mt.scanner import scan_and_plan, apply_renames, run_drag_loop, confirm
from mt.session import list_sessions, rollback


# ═══════════════════════════════════════════════════════════════════════════════
# 内置解析示例（用于 --examples，同时作为回归测试）
# ═══════════════════════════════════════════════════════════════════════════════

EXAMPLES: list[tuple[str, str, str]] = [
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


# ═══════════════════════════════════════════════════════════════════════════════
# --examples 模式
# ═══════════════════════════════════════════════════════════════════════════════

def run_examples() -> None:
    """运行内建示例测试，逐条验证解析结果。"""
    print(f'\n{SEP2}')
    print('🧪 解析示例')
    print(SEP2)
    fail = 0
    for author, name, expected in EXAMPLES:
        info = parse_name(author, name)
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


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(
        prog='manga-rename',
        description='漫画重命名工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '常用模式:\n'
            '  manga-rename --root <dir>         # 批量预览\n'
            '  manga-rename --root <dir> --apply # 批量执行\n'
            '  manga-rename --drag               # 循环拖入模式（推荐）\n'
            '  manga-rename --examples           # 内置解析示例\n'
        ),
    )
    ap.add_argument('--root',          default='',
                    help='漫画根目录（批量模式）')
    ap.add_argument('--target',        default='',
                    help='拖入模式：处理后将作者目录移动到此目录')
    ap.add_argument('--apply',         action='store_true',
                    help='执行重命名（批量模式）')
    ap.add_argument('--drag',          action='store_true',
                    help='循环拖入模式')
    ap.add_argument('--rollback',      action='store_true',
                    help='回退上次操作')
    ap.add_argument('--session',       default=None,
                    help='指定回退的 session ID（配合 --rollback）')
    ap.add_argument('--list-sessions', action='store_true',
                    help='列出所有可回退的操作记录')
    ap.add_argument('--examples',      action='store_true',
                    help='运行内置解析示例（回归测试）')
    ap.add_argument('--debug',         action='store_true',
                    help='启用 debug 日志')
    args = ap.parse_args()

    setup_logging(args.debug)

    if args.examples:
        run_examples()
        return
    if args.list_sessions:
        list_sessions()
        return
    if args.rollback:
        rollback(args.session)
        return
    if args.drag:
        run_drag_loop(args.target)
        return

    # 批量模式
    if not args.root:
        ap.error('请指定 --root <目录> 或使用 --drag / --examples')

    print(f'\n📂 扫描目录: {args.root}')
    plans = scan_and_plan(args.root)
    print_preview(plans)

    if args.apply and confirm():
        apply_renames(plans, dry_run=False)
    elif not args.apply:
        apply_renames(plans, dry_run=True)


if __name__ == '__main__':
    main()
