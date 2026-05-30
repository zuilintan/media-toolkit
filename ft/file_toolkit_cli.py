"""
file_toolkit_cli.py — file-toolkit 统一命令行入口

子命令：
  - classify  按作者名归类文件/文件夹（从 ps1 移植）

模块名遵循 PEP 8（下划线），对外暴露的 console 命令则使用连字符 ``ft-cli``
（CLI 惯例）。两者解耦，互不影响。

子命令实现位于 ``ft.cli`` 包；本模块仅负责参数解析与调度。

用法示例:
  ft-cli classify --drag                       # 循环拖入模式（推荐）
  ft-cli classify ./AuthorA                    # 单次处理
  ft-cli classify ./a ./b ./c                  # 多个一起
  ft-cli classify ./a --target M:/MK/作者/A    # 指定目标跳过候选交互
  ft-cli classify --drag --no-open             # 完成后不开资源管理器
"""

from __future__ import annotations

import argparse
import sys

from ft.cli.classify import cmd_classify, add_classify_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ft-cli',
        description='file-toolkit 统一命令行工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  ft-cli classify --drag\n'
            '  ft-cli classify ./AuthorA\n'
            '  ft-cli classify ./a --target M:/MK/作者/A\n'
        ),
    )

    sub = parser.add_subparsers(
        dest='command', metavar='<command>', required=True,
        help='可用子命令',
    )

    p_classify = sub.add_parser(
        'classify',
        help='按作者名归类文件/文件夹（移动到对应作者目录）',
        description='按拖入路径自动推断作者名，在所有 WorkDir 内查找'
                    '同名/别名候选目录，0/1/N 候选交互式选择后剪切搬移。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  ft-cli classify --drag                     # 循环拖入模式\n'
            '  ft-cli classify ./AuthorA                  # 单次处理\n'
            '  ft-cli classify ./a --target M:/.../A      # 指定目标\n'
        ),
    )
    add_classify_args(p_classify)
    p_classify.set_defaults(func=cmd_classify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
