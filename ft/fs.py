"""
fs.py — 文件/路径安全操作原语

包含:
  - guard_path / strict_exists  — 路径校验
  - is_smb_path                 — SMB 路径识别（Windows 专有）
  - execute_rename / try_rename — 安全重命名（含 SMB 大小写两步法）
  - safe_unlink / safe_rmdir    — 带深度守卫的删除

设计原则:
  - 仅依赖标准库，不引入任何业务模块
  - 调试日志走标准 logging（logger 名 ``ft.fs``）
"""

from __future__ import annotations
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 路径安全操作
# ═══════════════════════════════════════════════════════════════════════════════

_MIN_DEPTH = 2   # 路径的最少层数（去根锚点后），防止误操作根目录


def guard_path(p: Path, min_depth: int = _MIN_DEPTH) -> None:
    """断言路径深度 >= min_depth。"""
    resolved = p.resolve()
    depth = len(resolved.parts) - 1
    if depth < min_depth:
        raise ValueError(
            f"拒绝操作路径（深度 {depth} < {min_depth}，疑似根目录）: {resolved!r}"
        )


def strict_exists(path: Path) -> bool:
    """严格大小写判断文件是否存在（修正大小写不敏感文件系统的误判）。"""
    if not path.exists():
        return False
    try:
        return path.resolve().name == path.name
    except Exception as e:
        logger.debug('strict_exists 失败（按不存在处理）: %s — %s', path, e)
        return False


def is_smb_path(path: str) -> bool:
    """判断路径是否位于 SMB/网络驱动器（仅 Windows 有效）。"""
    import sys
    if sys.platform != 'win32':
        return False
    import ctypes
    abs_path = os.path.abspath(path)
    if abs_path.startswith(r'\\'):
        return True
    drive = os.path.splitdrive(abs_path)[0] + '\\'
    return bool(drive and ctypes.windll.kernel32.GetDriveTypeW(drive) == 4)


def execute_rename(old: Path, new: Path) -> None:
    """执行重命名；SMB 环境下大小写变更使用两步法。"""
    guard_path(old)
    guard_path(new)
    if (is_smb_path(str(new))
            and old.name.lower() == new.name.lower()
            and old.name != new.name):
        tmp = old.with_name(old.stem + '_tmp_rename' + old.suffix)
        old.rename(tmp)
        tmp.rename(new)
    else:
        old.rename(new)


def try_rename(src: Path, dst: Path) -> str:
    """尝试重命名，返回状态:
    - ``"same"``   — 完全相同，无需操作
    - ``"exists"`` — 目标已存在（且不同于源）
    - ``"ok"``     — 重命名成功
    异常由调用方处理。
    """
    if str(src) == str(dst):
        return 'same'
    if strict_exists(dst):
        return 'exists'
    if str(src).lower() == str(dst).lower():
        tmp = dst.with_name(dst.stem + '_tmp_rename' + dst.suffix)
        execute_rename(src, tmp)
        execute_rename(tmp, dst)
        return 'ok'
    execute_rename(src, dst)
    return 'ok'


def safe_unlink(p: Path) -> None:
    guard_path(p)
    p.unlink()


def safe_rmdir(p: Path) -> None:
    guard_path(p)
    p.rmdir()
