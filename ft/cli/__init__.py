"""
ft.cli — file-toolkit 命令行入口与子命令实现

包入口 ``main()`` 对应 pyproject scripts 的 ``ft-cli``；子命令拆分为独立
模块（当前仅 classify，未来按需扩展）。

模块名遵循 PEP 8（下划线），对外暴露的 console 命令则使用连字符
``ft-cli``（CLI 惯例），两者解耦互不影响。

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


def build_parser() -> argparse.ArgumentParser:
    # 延迟 import 子命令模块（保持 ft.cli 包基本 import 轻量）
    from ft.cli.classify import cmd_classify, add_classify_args

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
        dest='command', metavar='<command>', required=True, help='可用子命令',
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
