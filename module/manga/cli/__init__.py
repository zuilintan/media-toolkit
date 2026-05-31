"""
manga.cli — manga-toolkit 命令行入口与子命令实现

包入口 ``main()`` 对应 pyproject scripts 的 ``manga-cli``；子命令拆分为独立
模块（rename-kit/meta-kit/cover-kit/pack-kit/doctor），由本模块的 build_parser 组装：

    rename_kit.py       — 源文件批量重命名（.zip / .cbz）
    meta_kit.py       — 向 CBZ 写入 ComicInfo.xml
    cover_kit.py      — 为 CBZ 写入 2:3 封面
    pack_kit.py       — 图片目录序号化重命名 + STORED zip 打包
    doctor.py     — 环境体检
    examples.py   — 内置示例数据（rename-kit / meta-kit 共用）

本模块同时提供包级共用工具:
    validate_root() — --root 参数三件套校验（非空 / 存在 / 是目录）

兼容性: 也可使用 ``python -m manga <subcommand> ...``。
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
    """统一的 --root 校验。rename-kit / meta-kit 等子命令共用。

    Returns:
        通过校验的绝对路径；任一校验失败时返回 None 并已 emit 错误提示。
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
    # 延迟 import 子命令避免循环（manga.cli.rename_kit 反向 import 本模块的 validate_root）
    from module.manga.cli.cover_kit import cmd_cover,  add_cover_kit_args
    from module.manga.cli.doctor import cmd_doctor, add_doctor_args
    from module.manga.cli.meta_kit import cmd_meta,   add_meta_kit_args
    from module.manga.cli.pack_kit import cmd_pack,   add_pack_kit_args
    from module.manga.cli.rename_kit import cmd_rename,   add_rename_kit_args

    parser = argparse.ArgumentParser(
        prog='manga-cli',
        description='manga-toolkit 统一命令行工具（name + meta）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  manga-cli rename-kit --root /path/to/manga --apply\n'
            '  manga-cli rename-kit --examples\n'
            '  manga-cli meta-kit --root /path/to/cbz\n'
            '  manga-cli meta-kit --root /path/to/cbz --apply\n'
            '  manga-cli meta-kit --examples\n'
            '  manga-cli cover-kit --root /path/to/cbz --apply\n'
            '  manga-cli cover-kit --root /path/to/cbz --apply --smart\n'
        ),
    )
    parser.add_argument('--debug', action='store_true', help='启用 debug 日志')

    sub = parser.add_subparsers(
        dest='command', metavar='<command>', required=True, help='可用子命令',
    )

    p_rename_kit = sub.add_parser(
        'rename-kit',
        help='源文件（.zip / .cbz）批量重命名',
        description='源文件批量重命名工具（处理 .zip / .cbz）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '常用模式:\n'
            '  manga-cli rename-kit --root <dir>         # 批量预览\n'
            '  manga-cli rename-kit --root <dir> --apply # 批量执行\n'
            '  manga-cli rename-kit --examples           # 内置解析示例\n'
        ),
    )
    add_rename_kit_args(p_rename_kit)
    p_rename_kit.set_defaults(func=cmd_rename)

    p_meta_kit = sub.add_parser(
        'meta-kit',
        help='向 CBZ 写入 ComicInfo.xml 元数据',
        description='CBZ 漫画 ComicInfo.xml 批量生成/更新工具（ComicInfo v2.1）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-cli meta-kit --examples\n'
            '  manga-cli meta-kit --root ./manga\n'
            '  manga-cli meta-kit --root ./manga --apply\n'
        ),
    )
    add_meta_kit_args(p_meta_kit)
    p_meta_kit.set_defaults(func=cmd_meta)

    p_cover_kit = sub.add_parser(
        'cover-kit',
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
            '  manga-cli cover-kit --root ./manga\n'
            '  manga-cli cover-kit --root ./manga --apply\n'
            '  manga-cli cover-kit --root ./manga --apply --smart\n'
        ),
    )
    add_cover_kit_args(p_cover_kit)
    p_cover_kit.set_defaults(func=cmd_cover)

    p_pack_kit = sub.add_parser(
        'pack-kit',
        help='图片目录序号化重命名 + STORED zip 打包',
        description='把目录内的图片按 <Inc NrDir:0001> 规则重命名为 '
                    '0001.ext / 0002.ext …，再以 zip 存储模式（不压缩）'
                    '打包到同级 <dir>.zip',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认为预览模式（不修改文件），确认无误后加 --apply 实际执行。\n\n'
            '示例:\n'
            '  manga-cli pack-kit --root ./albums\n'
            '  manga-cli pack-kit --root ./albums --apply\n'
        ),
    )
    add_pack_kit_args(p_pack_kit)
    p_pack_kit.set_defaults(func=cmd_pack)

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
    setup_logging(args.debug)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
