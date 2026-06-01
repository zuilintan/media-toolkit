"""``manga-cli`` 入口与子命令实现。

本包只放业务子命令；旁路子命令（``doctor`` / ``--examples`` 演示运行器）位于
:mod:`module.manga.extras`，由 :func:`build_parser` 一并组装到顶层 subparsers。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from base.console import emit, setup_logging


# ═══════════════════════════════════════════════════════════════════════════════
# 公共工具
# ═══════════════════════════════════════════════════════════════════════════════

def validate_root(root_arg: str) -> Path | None:
    """``--root`` 三件套校验（非空 / 存在 / 是目录），各子命令共用。

    :return: 通过校验的绝对路径；任一校验失败时返回 ``None`` 并已 emit 错误提示。
    """
    if not root_arg:
        emit('❌ 请指定 --root <目录>'); return None
    root = Path(root_arg).resolve()
    if not root.exists():
        emit(f'❌ 目录不存在: {root}'); return None
    if not root.is_dir():
        emit(f'❌ 路径不是目录: {root}'); return None
    return root


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 主入口（pyproject scripts: manga-cli = "module.manga.cli:main"）
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    # 延迟 import 子命令避免循环（cli.std_title 等反向 import 本模块的 validate_root）
    from module.manga.cli.make_cover import cmd_make_cover, add_make_cover_args
    from module.manga.extras.doctor   import cmd_doctor,     add_doctor_args
    from module.manga.cli.make_meta  import cmd_make_meta,   add_make_meta_args
    from module.manga.cli.pack_pic   import cmd_pack_pic,    add_pack_pic_args
    from module.manga.cli.std_title  import cmd_std_title,   add_std_title_args

    parser = argparse.ArgumentParser(
        prog='manga-cli',
        description='manga-toolkit 统一命令行工具（std-title + make-meta + make-cover + pack-pic）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  manga-cli std-title --root /path/to/manga --apply\n'
            '  manga-cli std-title --examples\n'
            '  manga-cli make-meta --root /path/to/cbz\n'
            '  manga-cli make-meta --root /path/to/cbz --apply\n'
            '  manga-cli make-meta --examples\n'
            '  manga-cli make-cover --root /path/to/cbz --apply\n'
            '  manga-cli make-cover --root /path/to/cbz --apply --smart\n'
        ),
    )
    parser.add_argument('--debug', action='store_true', help='启用 debug 日志')

    sub = parser.add_subparsers(
        dest='command', metavar='<command>', required=True, help='可用子命令',
    )

    p_std_title = sub.add_parser(
        'std-title',
        help='源文件（.zip / .cbz）批量重命名（标题标准化）',
        description='源文件批量重命名工具（处理 .zip / .cbz）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '常用模式:\n'
            '  manga-cli std-title --root <dir>         # 批量预览\n'
            '  manga-cli std-title --root <dir> --apply # 批量执行\n'
            '  manga-cli std-title --examples           # 内置解析示例\n'
        ),
    )
    add_std_title_args(p_std_title)
    p_std_title.set_defaults(func=cmd_std_title)

    p_make_meta = sub.add_parser(
        'make-meta',
        help='向 CBZ 写入 ComicInfo.xml 元数据',
        description='CBZ 漫画 ComicInfo.xml 批量生成/更新工具（ComicInfo v2.1）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-cli make-meta --examples\n'
            '  manga-cli make-meta --root ./manga\n'
            '  manga-cli make-meta --root ./manga --apply\n'
        ),
    )
    add_make_meta_args(p_make_meta)
    p_make_meta.set_defaults(func=cmd_make_meta)

    p_make_cover = sub.add_parser(
        'make-cover',
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
            '  manga-cli make-cover --root ./manga\n'
            '  manga-cli make-cover --root ./manga --apply\n'
            '  manga-cli make-cover --root ./manga --apply --smart\n'
        ),
    )
    add_make_cover_args(p_make_cover)
    p_make_cover.set_defaults(func=cmd_make_cover)

    p_pack_pic = sub.add_parser(
        'pack-pic',
        help='图片目录序号化重命名 + STORED zip 打包',
        description='把目录内的图片按 <Inc NrDir:0001> 规则重命名为 '
                    '0001.ext / 0002.ext …，再以 zip 存储模式（不压缩）'
                    '打包到同级 <dir>.zip',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-cli pack-pic --root ./albums\n'
            '  manga-cli pack-pic --root ./albums --apply\n'
        ),
    )
    add_pack_pic_args(p_pack_pic)
    p_pack_pic.set_defaults(func=cmd_pack_pic)

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
    from module.manga.core.runtime_config import get_manga_config

    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.debug)
    # 启动期确保 manga.json 已落盘
    get_manga_config()
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
