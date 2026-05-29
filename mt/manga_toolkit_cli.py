"""
manga_toolkit_cli.py — manga-toolkit 统一命令行入口

整合三个子命令:
  - sourcefile → 源文件（.zip / .cbz）批量重命名（原 rename）
  - metadata   → 向 CBZ 写入 ComicInfo.xml 元数据（原 comicinfo）
  - cover      → 为 CBZ 写入 2:3 封面（绕开 grimmory 像素上限）

模块名遵循 PEP 8（下划线），对外暴露的 console 命令则使用连字符
``manga-toolkit-cli``（CLI 惯例）。两者解耦，互不影响。

子命令实现位于 mt.cli 包；本模块仅负责参数解析与调度。

用法示例:
  manga-toolkit-cli sourcefile --drag                          # 循环拖入模式（推荐）
  manga-toolkit-cli sourcefile --drag --move-to /sorted        # 拖入后移动到指定目录
  manga-toolkit-cli sourcefile --root /path/to/manga           # 批量预览
  manga-toolkit-cli sourcefile --root /path/to/manga --apply   # 批量执行
  manga-toolkit-cli sourcefile --rollback                      # 回退上次操作
  manga-toolkit-cli sourcefile --list-sessions                 # 列出所有操作记录
  manga-toolkit-cli sourcefile --examples                      # 内置解析示例

  manga-toolkit-cli metadata --root /path/to/cbz               # 预览
  manga-toolkit-cli metadata --root /path/to/cbz --apply       # 写入 ComicInfo.xml
  manga-toolkit-cli metadata --examples                        # 内置示例

  manga-toolkit-cli cover --root /path/to/cbz                  # 预览
  manga-toolkit-cli cover --root /path/to/cbz --apply          # 写入封面 webp
  manga-toolkit-cli cover --root /path/to/cbz --apply --smart  # smartcrop 模式

兼容性: 也可使用 `python -m mt <subcommand> ...`。
"""

from __future__ import annotations

import argparse
import sys

from mt.infra.console import setup_logging
from mt.cli.sourcefile import cmd_sourcefile, add_sourcefile_args
from mt.cli.metadata   import cmd_metadata,   add_metadata_args
from mt.cli.cover      import cmd_cover,      add_cover_args
from mt.cli.pack       import cmd_pack,       add_pack_args
from mt.cli.doctor     import cmd_doctor,     add_doctor_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='manga-toolkit-cli',
        description='manga-toolkit 统一命令行工具（sourcefile + metadata）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  manga-toolkit-cli sourcefile --drag\n'
            '  manga-toolkit-cli sourcefile --drag --move-to /sorted\n'
            '  manga-toolkit-cli sourcefile --root /path/to/manga --apply\n'
            '  manga-toolkit-cli sourcefile --rollback\n'
            '  manga-toolkit-cli sourcefile --examples\n'
            '  manga-toolkit-cli metadata --root /path/to/cbz\n'
            '  manga-toolkit-cli metadata --root /path/to/cbz --apply\n'
            '  manga-toolkit-cli metadata --examples\n'
            '  manga-toolkit-cli cover --root /path/to/cbz --apply\n'
            '  manga-toolkit-cli cover --root /path/to/cbz --apply --smart\n'
        ),
    )
    parser.add_argument('--debug', action='store_true',
                        help='启用 debug 日志')

    sub = parser.add_subparsers(
        dest='command', metavar='<command>', required=True,
        help='可用子命令'
    )

    # sourcefile（原 rename）
    p_sourcefile = sub.add_parser(
        'sourcefile',
        help='源文件（.zip / .cbz）批量重命名',
        description='源文件批量重命名工具（处理 .zip / .cbz）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '常用模式:\n'
            '  manga-toolkit-cli sourcefile --root <dir>         # 批量预览\n'
            '  manga-toolkit-cli sourcefile --root <dir> --apply # 批量执行\n'
            '  manga-toolkit-cli sourcefile --drag               # 循环拖入模式（推荐）\n'
            '  manga-toolkit-cli sourcefile --drag --move-to <dir> # 拖入后移动至目录\n'
            '  manga-toolkit-cli sourcefile --examples           # 内置解析示例\n'
        ),
    )
    add_sourcefile_args(p_sourcefile)
    p_sourcefile.set_defaults(func=cmd_sourcefile)

    # metadata（原 comicinfo）
    p_metadata = sub.add_parser(
        'metadata',
        help='向 CBZ 写入 ComicInfo.xml 元数据',
        description='CBZ 漫画 ComicInfo.xml 批量生成/更新工具（ComicInfo v2.1）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-toolkit-cli metadata --examples\n'
            '  manga-toolkit-cli metadata --root ./manga\n'
            '  manga-toolkit-cli metadata --root ./manga --apply\n'
        ),
    )
    add_metadata_args(p_metadata)
    p_metadata.set_defaults(func=cmd_metadata)

    # cover
    p_cover = sub.add_parser(
        'cover',
        help='为 CBZ 写入 2:3 封面（绕开 grimmory 像素上限）',
        description='CBZ 封面写入工具（生成 2:3 / ≤ 1000×1500 的 WebP；'
                    '源 0001.* → 0000.webp，源 cover.* → cover.webp）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '裁剪模式:\n'
            '  默认  居中裁剪到 2:3（最简单、可预测；横图可能丢主体）\n'
            '  --smart  smartcrop 显著性裁剪（横图更稳，依赖 smartcrop 库）\n\n'
            '示例:\n'
            '  manga-toolkit-cli cover --root ./manga\n'
            '  manga-toolkit-cli cover --root ./manga --apply\n'
            '  manga-toolkit-cli cover --root ./manga --apply --smart\n'
            '  manga-toolkit-cli cover --drag --move-to /sorted\n'
        ),
    )
    add_cover_args(p_cover)
    p_cover.set_defaults(func=cmd_cover)

    # pack
    p_pack = sub.add_parser(
        'pack',
        help='图片目录序号化重命名 + STORED zip 打包',
        description='把目录内的图片按 <Inc NrDir:0001> 规则重命名为 '
                    '0001.ext / 0002.ext …，再以 zip 存储模式（不压缩）'
                    '打包到同级 <dir>.zip',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-toolkit-cli pack --drag\n'
            '  manga-toolkit-cli pack --drag --move-to /sorted\n'
            '  manga-toolkit-cli pack --root ./albums\n'
            '  manga-toolkit-cli pack --root ./albums --apply\n'
            '  manga-toolkit-cli pack --root ./albums --apply --move-to /sorted\n'
        ),
    )
    add_pack_args(p_pack)
    p_pack.set_defaults(func=cmd_pack)

    # doctor
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
    args   = parser.parse_args(argv)
    setup_logging(args.debug)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
