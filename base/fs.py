"""文件/路径安全操作原语（深度守卫 + SMB 大小写两步法 + 可注入 reporter）。

调试日志走标准 :mod:`logging`（logger 名 ``base.fs``）；面向用户的状态信息通过
可选 ``reporter`` 回调输出（默认走 stdout/stderr），GUI 宿主可注入自身的
emit / warn / error 实现日志路由。
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
    """尝试重命名；异常由调用方处理。

    :return:
        - ``"same"``   — 完全相同，无需操作
        - ``"exists"`` — 目标已存在（且不同于源）
        - ``"ok"``     — 重命名成功
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


def safe_rmtree(p: Path) -> None:
    """带深度守卫的递归删除（含非空目录与全部子内容）。"""
    guard_path(p)
    shutil.rmtree(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 目录搬移
# ═══════════════════════════════════════════════════════════════════════════════

# reporter 协议：(level, message) → None；level ∈ {'info', 'warn', 'error'}
Reporter = Callable[[str, str], None]


def _default_reporter(level: str, msg: str) -> None:
    """缺省 reporter：info → stdout，warn/error → stderr。"""
    import sys
    (sys.stdout if level == 'info' else sys.stderr).write(msg + '\n')


def merge_into(
    src: Path,
    dst: Path,
    *,
    reporter: Reporter = _default_reporter,
) -> dict:
    """把 src 内的所有内容递归 move 到 dst 内（不嵌套 ``src.name``）。

    冲突策略：文件冲突 → :func:`safe_unlink` + ``shutil.move``；子目录冲突 → 递归合并。

    源目录是否清空由调用方决定（本函数只做合并，不删 src 本身），可据返回值
    ``moved == src.iterdir() count`` 推断。

    :param src:      源目录。
    :param dst:      目标目录；不存在会自动创建。
    :param reporter: 进度/警告输出回调。
    :return: ``{'moved': N, 'overwritten': M, 'failed': K}``。
    """
    dst.mkdir(parents=True, exist_ok=True)
    moved = overwritten = failed = 0
    for item in sorted(src.iterdir()):
        target = dst / item.name
        try:
            if item.is_dir() and target.exists() and target.is_dir():
                # 子目录冲突 → 递归合并；合并完成后若 item 已空则删之
                stats = merge_into(item, target, reporter=reporter)
                moved       += stats['moved']
                overwritten += stats['overwritten']
                failed      += stats['failed']
                if not any(item.iterdir()):
                    safe_rmdir(item)
            elif target.exists():
                safe_unlink(target)
                shutil.move(str(item), str(target))
                overwritten += 1
            else:
                shutil.move(str(item), str(target))
                moved += 1
        except Exception as e:
            reporter('error', f'{item.name} — {e}')
            failed += 1
    return {'moved': moved, 'overwritten': overwritten, 'failed': failed}
