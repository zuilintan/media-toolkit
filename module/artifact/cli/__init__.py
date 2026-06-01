"""file-toolkit 命令行入口与子命令实现。

包入口 :func:`main` 对应 pyproject scripts 的 ``artifact-cli``；子命令拆分为独立
模块（当前仅 :mod:`~module.artifact.cli.classify` + :mod:`~module.artifact.cli.doctor`）。
模块名遵循 PEP 8（下划线），对外暴露的 console 命令使用连字符（CLI 惯例）。

用法示例::

    artifact-cli classify --drag                       # 循环拖入模式（推荐）
    artifact-cli classify ./AuthorA                    # 单次处理
    artifact-cli classify ./a ./b ./c                  # 多个一起
    artifact-cli classify ./a --target M:/MK/作者/A    # 指定目标跳过候选交互
    artifact-cli classify --drag --no-open             # 完成后不开资源管理器
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    # 延迟 import 子命令模块（保持 artifact.cli 包基本 import 轻量）
    from module.artifact.cli.classify import cmd_classify, add_classify_args
    from module.artifact.cli.doctor import cmd_doctor,   add_doctor_args

    parser = argparse.ArgumentParser(
        prog='artifact-cli',
        description='file-toolkit 统一命令行工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  artifact-cli classify --drag\n'
            '  artifact-cli classify ./AuthorA\n'
            '  artifact-cli classify ./a --target M:/MK/作者/A\n'
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
            '  artifact-cli classify --drag                     # 循环拖入模式\n'
            '  artifact-cli classify ./AuthorA                  # 单次处理\n'
            '  artifact-cli classify ./a --target M:/.../A      # 指定目标\n'
        ),
    )
    add_classify_args(p_classify)
    p_classify.set_defaults(func=cmd_classify)

    p_doctor = sub.add_parser(
        'doctor',
        help='环境体检（Python 版本 + 各依赖安装状态）',
        description='打印当前环境的 Python 版本与依赖安装状态，'
                    '便于发 issue 前自查。',
    )
    add_doctor_args(p_doctor)
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
