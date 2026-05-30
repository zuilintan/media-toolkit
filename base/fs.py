"""
fs.py — 文件/路径安全操作原语

包含:
  - guard_path / strict_exists  — 路径校验
  - is_smb_path                 — SMB 路径识别（Windows 专有）
  - execute_rename / try_rename — 安全重命名（含 SMB 大小写两步法）
  - safe_unlink / safe_rmdir    — 带深度守卫的删除
  - move_dir                    — 目录搬移（同名目标存在则逐项合并覆盖）

设计原则:
  - 仅依赖标准库，不引入任何业务模块
  - 调试日志走标准 logging（logger 名 ``base.fs``）
  - 面向用户的状态信息通过可选 ``reporter`` 回调输出，默认走 print；
    宿主应用（mt/ft）可注入自身的 emit / warn / error 实现 GUI 日志路由
"""

from __future__ import annotations
import logging
import os
import shutil
from collections.abc import Callable
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


# ═══════════════════════════════════════════════════════════════════════════════
# 目录搬移
# ═══════════════════════════════════════════════════════════════════════════════

# reporter 协议：(level, message) → None；level ∈ {'info', 'warn', 'error'}
Reporter = Callable[[str, str], None]


def _default_reporter(level: str, msg: str) -> None:
    """缺省 reporter：info → stdout，warn/error → stderr。"""
    import sys
    (sys.stdout if level == 'info' else sys.stderr).write(msg + '\n')


def move_dir(
    src: Path,
    target: str,
    *,
    reporter: Reporter = _default_reporter,
) -> bool:
    """将目录 src 移动到 target，已存在同名目录则逐项合并并覆盖。

    Args:
        src:      源目录。
        target:   目标父目录路径；不存在会自动创建。
        reporter: 进度/警告输出回调。默认走 stdout/stderr；GUI 场景
                  可注入 ``lambda lvl, msg: emit(msg)`` 类闭包路由到日志框。

    Returns:
        移动/合并成功（无失败）返回 True。
    """
    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)
    dest = target_path / src.name

    if not dest.exists():
        shutil.move(str(src), str(dest))
        reporter('info', f'📦 已移动: {src.name}\n   → {dest}')
        return True

    reporter('warn', f'目标目录已存在，逐项移动并覆盖同名文件: {dest}')
    ok_n = fail = 0
    for item in sorted(src.iterdir()):
        item_dest = dest / item.name
        try:
            if item_dest.exists():
                safe_unlink(item_dest)
                reporter('info', f'  🗑  删除已存在文件: {item_dest.name}')
            shutil.move(str(item), str(item_dest))
            ok_n += 1
            reporter('info', f'  ✅ 移动: {item.name}')
        except Exception as e:
            reporter('error', f'{item.name} — {e}')
            fail += 1

    remaining = list(src.iterdir())
    if not remaining:
        safe_rmdir(src)
        reporter('info', f'  🗑  源目录已清空并删除: {src}')
    else:
        reporter('warn',
                 f'{len(remaining)} 个文件未能移动，源目录保留: {src}')
    reporter('info', f'  合并完成: 成功 {ok_n} | 失败 {fail}')
    return fail == 0
