"""
scanner.py — 目录扫描、重命名计划执行与拖入模式

依赖: models / config / parser / builder / utils / console / session
"""

from __future__ import annotations
import shlex
import shutil
from pathlib import Path

from mt.core.models import MangaInfo, RenamePlan
from mt.core.config import FILE_EXTS
from mt.naming.parser import parse_name
from mt.naming.builder import build_new_name
from mt.infra.utils import try_rename, safe_unlink, safe_rmdir
from mt.infra.console import (
    print_preview, print_op_result, SEP, warn, error, ok, info,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描 & 计划
# ═══════════════════════════════════════════════════════════════════════════════

def scan_author_dir(author_dir: Path) -> list[RenamePlan]:
    """扫描单个作者目录，返回所有条目的重命名计划。"""
    author = author_dir.name
    plans: list[RenamePlan] = []
    for item in sorted(author_dir.iterdir()):
        if not (item.is_dir() or item.suffix.lower() in FILE_EXTS):
            continue
        is_file  = item.is_file()
        suffix   = item.suffix if is_file else ''
        old_stem = item.stem if is_file else item.name
        mi       = parse_name(author, old_stem)
        new_name = build_new_name(mi) + suffix
        plans.append(RenamePlan(
            author_dir = str(author_dir),
            author     = author,
            old_name   = item.name,
            new_name   = new_name,
            info       = mi,
            is_file    = is_file,
            suffix     = suffix,
        ))
    return plans


def scan_and_plan(root: str) -> list[RenamePlan]:
    """扫描根目录下所有作者目录，汇总重命名计划。"""
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []
    plans: list[RenamePlan] = []
    for author_dir in sorted(root_path.iterdir()):
        if author_dir.is_dir():
            plans.extend(scan_author_dir(author_dir))
    return plans


# ═══════════════════════════════════════════════════════════════════════════════
# 执行重命名
# ═══════════════════════════════════════════════════════════════════════════════

def apply_renames(plans: list[RenamePlan], dry_run: bool = True) -> int:
    """执行重命名计划。

    Args:
        plans:   重命名计划列表。
        dry_run: True 时仅预览，不实际执行。

    Returns:
        失败数量（dry_run 时返回 0）。成功执行后自动记录 session。
    """
    if dry_run:
        info('\n🔍 预览模式 — 未做任何更改。使用 --apply 参数执行。')
        return 0

    # 延迟导入，避免循环（session 反向依赖 RenamePlan）
    from mt.workflow.session import append_session

    ok_n = fail = skip = 0
    renamed: list[RenamePlan] = []

    for p in plans:
        if not p.changed:
            continue
        if p.needs_review:
            warn(f'跳过（需审核）: {p.old_name}')
            skip += 1
            continue
        old_path = Path(p.author_dir) / p.old_name
        new_path = Path(p.author_dir) / p.new_name
        try:
            result = try_rename(old_path, new_path)
            if result == 'exists':
                warn(f'跳过（目标已存在）: {p.new_name}')
                skip += 1
            else:
                print(f'  ✅ 旧: {p.old_name}')
                print(f'     新: {p.new_name}')
                ok_n += 1
                renamed.append(p)
        except Exception as e:
            error(f'{p.old_name} — {e}')
            fail += 1

    print_op_result(ok_n, fail, skip)
    if renamed:
        append_session(renamed)
    return fail


# ═══════════════════════════════════════════════════════════════════════════════
# 作者目录移动
# ═══════════════════════════════════════════════════════════════════════════════

def move_author_dir(author_dir: Path, target: str) -> bool:
    """将作者目录移动至目标位置，若已存在同名目录则逐文件合并。

    Returns:
        移动成功返回 True。
    """
    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)
    dest = target_path / author_dir.name

    if not dest.exists():
        shutil.move(str(author_dir), str(dest))
        print(f'📦 已移动: {author_dir.name}\n   → {dest}')
        return True

    warn(f'目标目录已存在，逐项移动并覆盖同名文件: {dest}')
    ok_n = fail = 0
    for item in sorted(author_dir.iterdir()):
        item_dest = dest / item.name
        try:
            if item_dest.exists():
                safe_unlink(item_dest)
                print(f'  🗑  删除已存在文件: {item_dest.name}')
            shutil.move(str(item), str(item_dest))
            ok_n += 1
            print(f'  ✅ 移动: {item.name}')
        except Exception as e:
            error(f'{item.name} — {e}')
            fail += 1

    remaining = list(author_dir.iterdir())
    if not remaining:
        safe_rmdir(author_dir)
        print(f'  🗑  源目录已清空并删除: {author_dir}')
    else:
        warn(f'{len(remaining)} 个文件未能移动，源目录保留: {author_dir}')
    print(f'  合并完成: 成功 {ok_n} | 失败 {fail}')
    return fail == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 交互辅助
# ═══════════════════════════════════════════════════════════════════════════════

def confirm(prompt: str = '\n⚠️  确认执行重命名？按 Enter 继续: ') -> bool:
    """询问用户确认，Ctrl-C 视为取消。"""
    try:
        return input(prompt).strip() == ''
    except KeyboardInterrupt:
        print('\n\n🛑 用户取消操作，程序已退出')
        return False


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
        (valid if p.is_dir() else invalid).append(p if p.is_dir() else str(p))
    return valid, invalid


def _process_author_dir(author_dir: Path, target: str) -> None:
    print(f'\n{SEP}')
    print(f'📂 作者目录: {author_dir}')
    plans = scan_author_dir(author_dir)
    print_preview(plans)
    if not confirm():
        return
    fail = apply_renames(plans, dry_run=False)
    if fail == 0 and target:
        move_author_dir(author_dir, target)
    elif fail > 0:
        warn(f'{fail} 个重命名失败，目录未移动，请修复后重试。')


# ═══════════════════════════════════════════════════════════════════════════════
# 循环拖入模式
# ═══════════════════════════════════════════════════════════════════════════════

def run_drag_loop(target: str) -> None:
    """循环拖入模式：持续等待拖入目录并处理，Ctrl+C 退出。"""
    from mt.infra.console import SEP2
    print(f'\n{SEP2}')
    print('🔁  循环拖入模式（支持同时拖入多个目录）')
    if target:
        print(f'    处理完成后将移动到: {target}')
    else:
        print('    处理完成后不移动（未指定 --move-to）')
    print('    Ctrl+C 退出')
    print(SEP2)

    while True:
        print()
        try:
            raw = input('📂 拖入作者目录，Enter 处理: ').strip()
        except (KeyboardInterrupt, EOFError):
            print('\n\n👋 已退出循环模式')
            break
        if not raw:
            continue
        dirs, bad = _parse_drag_paths(raw)
        for p in bad:
            error(f'不是有效目录，已跳过: {p}')
        if not dirs:
            continue
        if len(dirs) > 1:
            print(f'📦 本次共 {len(dirs)} 个目录，逐一处理')
        try:
            for author_dir in dirs:
                _process_author_dir(author_dir, target)
        except KeyboardInterrupt:
            print('\n\n👋 已退出循环模式')
            break
