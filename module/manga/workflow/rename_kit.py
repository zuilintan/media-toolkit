"""rename-kit 工作流层：扫描作者目录下的 ``.zip`` / ``.cbz`` 源文件并重命名。"""

from __future__ import annotations
from pathlib import Path

from module.manga.core.models import RenameKitPlan
from module.manga.core.config import FILE_EXTS
from module.manga.naming.parser import parse_name
from module.manga.naming.builder import build_new_name
from base.fs import try_rename
from base.console import print_op_result, warn, error, info, emit
from module.manga.infra.parallel import run_plans


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描 & 计划
# ═══════════════════════════════════════════════════════════════════════════════

def _plan_one(item: tuple[str, str]) -> RenameKitPlan:
    """模块级 worker（picklable）：``(author, full_path_str)`` → :class:`~module.manga.core.models.RenameKitPlan`。

    DEBUG 由 :func:`~module.manga.presentation.view.print_rename_kit_preview`
    在渲染卡片时统一触发，本函数无副作用，安全用于子进程。
    """
    author, path_str = item
    file     = Path(path_str)
    mi       = parse_name(author, file.stem)
    suffix   = '.cbz' if file.suffix.lower() == '.zip' else file.suffix
    new_name = build_new_name(mi) + suffix
    return RenameKitPlan(
        author_dir = str(file.parent),
        author     = author,
        old_name   = file.name,
        new_name   = new_name,
        info       = mi,
    )


def _progress_line(idx: int, total: int, plan: RenameKitPlan) -> str:
    icon = ('!' if plan.needs_review
            else '*' if plan.changed
            else '-')
    return f'   {icon} [{idx}/{total}] {plan.old_name}'


def _iter_rename_kit_items(author_dirs: list[Path]) -> list[tuple[str, str]]:
    """作者目录列表展开为 ``(author, full_path)``，按 ``(作者, 文件名)`` 排序。"""
    items: list[tuple[str, str]] = []
    for author_dir in author_dirs:
        author = author_dir.name
        for f in sorted(author_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in FILE_EXTS:
                items.append((author, str(f)))
    return items



def preview_plans(
    root: str, jobs: int = 1, on_progress=None, cancel_token=None,
) -> list[RenameKitPlan]:
    """扫描根目录下所有作者目录，汇总重命名计划。

    plan 阶段是纯字符串处理（毫秒级），并行收益有限，主要作用是统一接口
    + 大规模目录下的进度反馈。

    :param jobs: 1=串行；>1=并行进程数；0=自动 ``min(cpu, 4)``。
        ≥ 4 个文件时才实际启用并行。
    :param on_progress: 每完成一项即回调 ``f(done, total)``。
    :param cancel_token: ``threading.Event``，已 set 时提前退出。
    """
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []
    author_dirs = [d for d in sorted(root_path.iterdir()) if d.is_dir()]
    items       = _iter_rename_kit_items(author_dirs)
    zip_n = sum(1 for _, p in items if p.lower().endswith('.zip'))
    cbz_n = len(items) - zip_n
    emit(f'  找到文件: {zip_n} 个 .zip，{cbz_n} 个 .cbz'
         f'（{len(author_dirs)} 个作者目录）')
    return run_plans(
        items, _plan_one, jobs=jobs, progress_line=_progress_line,
        on_progress=on_progress, cancel_token=cancel_token,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 执行重命名
# ═══════════════════════════════════════════════════════════════════════════════

def apply_plans(
    plans: list[RenameKitPlan], dry_run: bool = True, cancel_token=None,
) -> int:
    """执行重命名计划。

    :param dry_run: ``True`` 时仅预览，不实际执行。
    :param cancel_token: ``threading.Event``，已 set 时提前退出。
    :return: 失败数量（``dry_run`` 时为 0）。
    """
    if dry_run:
        info('\n🔍 预览模式 — 未做任何更改。使用 --apply 参数执行。')
        return 0

    def _cancelled() -> bool:
        return cancel_token is not None and cancel_token.is_set()

    ok_n = fail = skip = 0
    for p in plans:
        if _cancelled():
            emit('  ⏹️  已取消')
            break
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
                emit(f'   ✅ {p.old_name} — 已处理')
                ok_n += 1
        except Exception as e:
            error(f'{p.old_name} — {e}')
            fail += 1

    print_op_result(ok_n, fail, skip)
    return fail


