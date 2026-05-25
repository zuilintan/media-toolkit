"""
scanner.py — 目录扫描与重命名计划执行（rename 子命令的工作流层）

依赖: models / config / parser / builder / utils / console / presentation / drag
"""

from __future__ import annotations
from pathlib import Path

from mt.core.models import MangaInfo, RenamePlan
from mt.core.config import FILE_EXTS
from mt.naming.parser import parse_name
from mt.naming.builder import build_new_name
from mt.infra.utils import try_rename
from mt.infra.console import print_op_result, SEP, warn, error, info, emit, confirm
from mt.presentation.view import print_rename_preview
from mt.workflow.drag import move_dir


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描 & 计划
# ═══════════════════════════════════════════════════════════════════════════════

def scan_author_dir(author_dir: Path) -> list[RenamePlan]:
    """扫描单个作者目录，仅处理 .zip / .cbz 文件。

    DEBUG 由 print_rename_preview 在渲染卡片时统一触发，使每条 DEBUG
    紧贴对应卡片。
    """
    author = author_dir.name
    plans: list[RenamePlan] = []
    for item in sorted(author_dir.iterdir()):
        if not item.is_file() or item.suffix.lower() not in FILE_EXTS:
            continue
        mi       = parse_name(author, item.stem)
        new_name = build_new_name(mi) + item.suffix
        plans.append(RenamePlan(
            author_dir = str(author_dir),
            author     = author,
            old_name   = item.name,
            new_name   = new_name,
            info       = mi,
        ))
    return plans


def plan_renames(root: str) -> list[RenamePlan]:
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

def apply_rename_plans(plans: list[RenamePlan], dry_run: bool = True) -> int:
    """执行重命名计划。

    Args:
        plans:   重命名计划列表。
        dry_run: True 时仅预览，不实际执行。

    Returns:
        失败数量（dry_run 时返回 0）。
    """
    if dry_run:
        info('\n🔍 预览模式 — 未做任何更改。使用 --apply 参数执行。')
        return 0

    ok_n = fail = skip = 0
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
                emit(f'   ✅ 旧: {p.old_name}')
                emit(f'     新: {p.new_name}')
                ok_n += 1
        except Exception as e:
            error(f'{p.old_name} — {e}')
            fail += 1

    print_op_result(ok_n, fail, skip)
    return fail


# ═══════════════════════════════════════════════════════════════════════════════
# 单作者目录处理（drag 模式回调）
# ═══════════════════════════════════════════════════════════════════════════════

def process_author_dir(author_dir: Path, target: str) -> None:
    """drag 模式下处理单个作者目录：plan → preview → confirm → apply → 可选移动。"""
    emit(f'\n{SEP}')
    emit(f'📂 作者目录: {author_dir}')
    plans = scan_author_dir(author_dir)
    print_rename_preview(plans)
    if not confirm('\n🟡 确认执行重命名？按 Enter 继续: '):
        return
    fail = apply_rename_plans(plans, dry_run=False)
    if fail == 0 and target:
        move_dir(author_dir, target)
    elif fail > 0:
        warn(f'{fail} 个重命名失败，目录未移动，请修复后重试。')
