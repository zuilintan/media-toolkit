"""
sourcefile.py — 源文件扫描与重命名（sourcefile 子命令的工作流层）

只处理 .zip / .cbz 源文件；按作者目录组织。

依赖: models / config / parser / builder / utils / console / presentation / drag
"""

from __future__ import annotations
from pathlib import Path

from mt.core.models import SourcefilePlan
from mt.core.config import FILE_EXTS
from mt.naming.parser import parse_name
from mt.naming.builder import build_new_name
from mt.infra.utils import try_rename
from mt.infra.console import print_op_result, SEP, warn, error, info, emit, confirm
from mt.infra.parallel import run_plans
from mt.presentation.view import print_sourcefile_preview
from mt.workflow.drag import move_dir


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描 & 计划
# ═══════════════════════════════════════════════════════════════════════════════

def _plan_one(item: tuple[str, str]) -> SourcefilePlan:
    """模块级 worker（picklable）：``(author, full_path_str)`` → SourcefilePlan。

    DEBUG 由 print_sourcefile_preview 在渲染卡片时统一触发，本函数无副作用，
    安全用于子进程。
    """
    author, path_str = item
    file     = Path(path_str)
    mi       = parse_name(author, file.stem)
    new_name = build_new_name(mi) + file.suffix
    return SourcefilePlan(
        author_dir = str(file.parent),
        author     = author,
        old_name   = file.name,
        new_name   = new_name,
        info       = mi,
    )


def _progress_line(idx: int, total: int, plan: SourcefilePlan) -> str:
    icon = ('🟡' if plan.needs_review
            else '✅' if plan.changed
            else '—')
    return f'   {icon} [{idx}/{total}] {plan.old_name}'


def _iter_sourcefile_items(author_dirs: list[Path]) -> list[tuple[str, str]]:
    """从作者目录列表展开为 ``(author, full_path)`` 列表（按 (作者, 文件名) 排序）。"""
    items: list[tuple[str, str]] = []
    for author_dir in author_dirs:
        author = author_dir.name
        for f in sorted(author_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in FILE_EXTS:
                items.append((author, str(f)))
    return items


def scan_author_dir(author_dir: Path) -> list[SourcefilePlan]:
    """扫描单个作者目录，仅处理 .zip / .cbz 文件（drag 模式入口；不打进度）。"""
    items = _iter_sourcefile_items([author_dir])
    return [_plan_one(it) for it in items]


def plan_sourcefiles(
    root: str, jobs: int = 1, on_progress=None,
) -> list[SourcefilePlan]:
    """扫描根目录下所有作者目录，汇总重命名计划。

    Args:
        jobs: 1=串行；>1=ProcessPoolExecutor 并行；0=自动 min(cpu,4)。
              ≥ 4 个文件时才启用并行。
        on_progress: 每完成一项即回调 ``f(done, total)``。

    每完成一个文件即打印进度行。注意 plan 阶段是纯字符串处理（毫秒级），
    并行收益有限，主要作用是统一接口 + 大规模目录下的进度反馈。
    """
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []
    author_dirs = [d for d in sorted(root_path.iterdir()) if d.is_dir()]
    items       = _iter_sourcefile_items(author_dirs)
    emit(f'  找到条目: {len(items)} 项（{len(author_dirs)} 个作者目录）')
    return run_plans(
        items, _plan_one, jobs=jobs, progress_line=_progress_line,
        on_progress=on_progress,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 执行重命名
# ═══════════════════════════════════════════════════════════════════════════════

def apply_sourcefile_plans(plans: list[SourcefilePlan], dry_run: bool = True) -> int:
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

def process_sourcefile_dir(author_dir: Path, target: str) -> None:
    """drag 模式下处理单个作者目录：plan → preview → confirm → apply → 可选移动。"""
    emit(f'\n{SEP}')
    emit(f'📂 作者目录: {author_dir}')
    plans = scan_author_dir(author_dir)
    print_sourcefile_preview(plans)
    if not confirm('\n🟡 确认执行重命名？按 Enter 继续: '):
        return
    fail = apply_sourcefile_plans(plans, dry_run=False)
    if fail == 0 and target:
        move_dir(author_dir, target)
    elif fail > 0:
        warn(f'{fail} 个重命名失败，目录未移动，请修复后重试。')
