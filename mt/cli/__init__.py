"""
mt.cli — 命令行子命令实现

各子命令拆分为独立模块，由 mt.manga_toolkit_cli 组装为统一 CLI:
    examples.py   — 内置示例数据加载与展示（sourcefile / metadata 共用一份数据）
    sourcefile.py — sourcefile 子命令（源文件批量重命名）
    metadata.py   — metadata 子命令（向 CBZ 写入 ComicInfo.xml）

并提供本包级共用工具:
    validate_root() — --root 参数三件套校验（非空 / 存在 / 是目录）
"""

from __future__ import annotations
from pathlib import Path

from mt.infra.console import emit


def validate_root(root_arg: str) -> Path | None:
    """统一的 --root 校验。sourcefile / metadata 共用。

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
