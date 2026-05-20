"""
manga_toolkit_cli.py — manga-toolkit 统一命令行入口

整合了原先两个独立工具：
  - 子命令 rename     → 漫画文件 / 目录批量重命名（原 manga-rename）
  - 子命令 comicinfo  → 向 CBZ 写入 ComicInfo.xml（原 manga-comicinfo）

模块名遵循 PEP 8（下划线），对外暴露的 console 命令则使用连字符
``manga-toolkit-cli``（CLI 惯例）。两者解耦，互不影响。

子命令实现位于 mt.cli 包；本模块仅负责参数解析与调度。

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
import sys

from mt.infra.console import setup_logging
from mt.cli.rename import cmd_rename, add_rename_args
from mt.cli.comicinfo import cmd_comicinfo, add_comicinfo_args


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
            '  manga-toolkit-cli rename --drag --move-to <dir># 拖入后移动至目录\n'
            '  manga-toolkit-cli rename --examples           # 内置解析示例\n'
        ),
    )
    add_rename_args(p_rename)
    p_rename.set_defaults(func=cmd_rename)

    # comicinfo
    p_comicinfo = sub.add_parser(
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
    add_comicinfo_args(p_comicinfo)
    p_comicinfo.set_defaults(func=cmd_comicinfo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)
    setup_logging(args.debug)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
