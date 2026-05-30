"""
drag.py — 通用拖入循环 + 目录搬移工具

rename / comicinfo 共用：
  - run_drag_loop(): 监听用户拖入目录，逐个交给 process_one 处理
  - move_dir():      把已处理目录移到 target，同名存在则逐项合并并覆盖

依赖: infra.utils / infra.console
"""

from __future__ import annotations
import shlex
import shutil
from collections.abc import Callable
from pathlib import Path

from ft.fs import safe_unlink, safe_rmdir
from mt.infra.console import SEP2, emit, warn, error


# ═══════════════════════════════════════════════════════════════════════════════
# 目录搬移
# ═══════════════════════════════════════════════════════════════════════════════

def move_dir(src: Path, target: str) -> bool:
    """将目录 src 移动到 target，已存在同名目录则逐项合并并覆盖。

    Returns:
        移动/合并成功（无失败）返回 True。
    """
    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)
    dest = target_path / src.name

    if not dest.exists():
        shutil.move(str(src), str(dest))
        emit(f'📦 已移动: {src.name}\n   → {dest}')
        return True

    warn(f'目标目录已存在，逐项移动并覆盖同名文件: {dest}')
    ok_n = fail = 0
    for item in sorted(src.iterdir()):
        item_dest = dest / item.name
        try:
            if item_dest.exists():
                safe_unlink(item_dest)
                emit(f'  🗑  删除已存在文件: {item_dest.name}')
            shutil.move(str(item), str(item_dest))
            ok_n += 1
            emit(f'  ✅ 移动: {item.name}')
        except Exception as e:
            error(f'{item.name} — {e}')
            fail += 1

    remaining = list(src.iterdir())
    if not remaining:
        safe_rmdir(src)
        emit(f'  🗑  源目录已清空并删除: {src}')
    else:
        warn(f'{len(remaining)} 个文件未能移动，源目录保留: {src}')
    emit(f'  合并完成: 成功 {ok_n} | 失败 {fail}')
    return fail == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 拖入路径解析
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_drag_paths(raw: str) -> tuple[list[Path], list[str]]:
    """解析拖入字符串，支持引号包裹的含空格路径。"""
    raw = raw.strip()
    if not raw:
        return [], []
    try:
        tokens = shlex.split(raw, posix=False)
    except ValueError:
        tokens = [raw]
    valid:   list[Path] = []
    invalid: list[str]  = []
    for token in tokens:
        p = Path(token.strip('"').strip("'"))
        if p.is_dir():
            valid.append(p)
        else:
            invalid.append(str(p))
    return valid, invalid


# ═══════════════════════════════════════════════════════════════════════════════
# 拖入循环
# ═══════════════════════════════════════════════════════════════════════════════

def run_drag_loop(
    *,
    title:       str,
    target:      str,
    process_one: Callable[[Path, str], None],
) -> None:
    """循环拖入模式：持续等待用户拖入目录，对每个目录调用 process_one(dir, target)。

    Ctrl+C / EOF 退出。
    """
    emit(f'\n{SEP2}')
    emit(f'🔁  {title}（支持同时拖入多个目录）')
    if target:
        emit(f'    处理完成后将移动到: {target}')
    else:
        emit('    处理完成后不移动（未指定 --move-to）')
    emit('    Ctrl+C 退出')
    emit(SEP2)

    while True:
        emit()
        try:
            raw = input('📂 拖入目录，Enter 处理: ').strip()
        except (KeyboardInterrupt, EOFError):
            emit('\n\n👋 已退出循环模式')
            return
        if not raw:
            continue
        dirs, bad = _parse_drag_paths(raw)
        for p in bad:
            error(f'不是有效目录，已跳过: {p}')
        if not dirs:
            continue
        if len(dirs) > 1:
            emit(f'📦 本次共 {len(dirs)} 个目录，逐一处理')
        try:
            for d in dirs:
                process_one(d, target)
        except KeyboardInterrupt:
            emit('\n\n👋 已退出循环模式')
            return
