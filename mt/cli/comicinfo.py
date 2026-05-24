"""
comicinfo.py — comicinfo 子命令：向 CBZ 写入 ComicInfo.xml

流程与 rename 对齐：全量预览 → 汇总 → 二次确认 → 批量写入。
文件数量较多时，详细日志写入 .log 文件，终端仅显示进度条与汇总。

依赖: workflow.comicinfo / infra.console / cli.examples
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from mt.infra.console import SEP2, emit, capture, confirm
from mt.workflow.comicinfo import (
    CbzPlan, plan_cbz, print_cbz_plan, apply_cbz_plan,
)
from mt.presentation.view import print_run_banner
from mt.cli.examples import run_comicinfo_examples

# 文件数量 ≥ 此阈值时，详细日志写入 .log 文件，终端仅显示进度条与汇总
_LARGE_THRESHOLD = 100


# ═══════════════════════════════════════════════════════════════════════════════
# 进度条
# ═══════════════════════════════════════════════════════════════════════════════

def _progress(done: int, total: int) -> None:
    bar_w  = 30
    filled = int(bar_w * done / total)
    bar    = '█' * filled + '░' * (bar_w - filled)
    pct    = done * 100 // total
    emit(f'\r  [{bar}] {pct:3d}%  {done}/{total}', end='', flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 预览阶段：全量 plan + 打印
# ═══════════════════════════════════════════════════════════════════════════════

def _preview_all(
    cbz_files: list[Path],
    plan_counts: dict[str, int],
    log_lines: list[str] | None,
) -> list[CbzPlan]:
    """逐文件 plan + print，按需把每条输出落到 log_lines（用于大批量模式）。"""
    plans: list[CbzPlan] = []
    total = len(cbz_files)
    for idx, fp in enumerate(cbz_files, 1):
        if log_lines is not None:
            with capture() as buf:
                plan, status = plan_cbz(str(fp))
                if plan:
                    print_cbz_plan(plan)
            log_lines.append(buf.getvalue().rstrip('\n'))
            _progress(idx, total)
        else:
            plan, status = plan_cbz(str(fp))
            if plan:
                print_cbz_plan(plan)
        plan_counts[status] += 1
        if plan:
            plans.append(plan)
    if log_lines is not None:
        emit()  # 进度条换行
    return plans


# ═══════════════════════════════════════════════════════════════════════════════
# 写入阶段
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_all(
    plans: list[CbzPlan],
    write_counts: dict[str, int],
    log_lines: list[str] | None,
) -> None:
    """对所有可写计划执行写入，按需把每条输出落到 log_lines。"""
    total = len(plans)
    for idx, plan in enumerate(plans, 1):
        if log_lines is not None:
            with capture() as buf:
                result = apply_cbz_plan(plan)
            log_lines.append(buf.getvalue().rstrip('\n'))
            _progress(idx, total)
        else:
            result = apply_cbz_plan(plan)
        write_counts[result] = write_counts.get(result, 0) + 1
    if log_lines is not None:
        emit()  # 进度条换行


# ═══════════════════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════════════════

def _print_preview_summary(plan_counts: dict[str, int], apply: bool) -> None:
    emit(f'\n{SEP2}')
    note  = '' if apply else '（预览，未实际修改）'
    parts = [f'✅ {plan_counts["ok"]} 可写']
    if plan_counts['warn']: parts.append(f'🟡 {plan_counts["warn"]} 需 review')
    if plan_counts['skip']: parts.append(f'— {plan_counts["skip"]} 跳过')
    emit(f'  解析完成{note}  {"   ".join(parts)}')


def _print_apply_summary(write_counts: dict[str, int]) -> None:
    parts = [f'✅ {write_counts.get("ok", 0)} 成功']
    if write_counts.get('error'): parts.append(f'❌ {write_counts["error"]} 失败')
    emit(f'  写入完成  {"   ".join(parts)}')


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_comicinfo(args: argparse.Namespace) -> int:
    """comicinfo 子命令调度。"""
    if args.examples:
        return 0 if run_comicinfo_examples() == 0 else 1

    if not args.root:
        emit('❌ 请指定 --root <目录> 或使用 --examples')
        return 2

    root = Path(args.root).resolve()
    if not root.exists():
        emit(f'❌ 目录不存在: {root}')
        return 1
    if not root.is_dir():
        emit(f'❌ 路径不是目录: {root}')
        return 1

    cbz_files = sorted(root.rglob('*.cbz'))
    total     = len(cbz_files)
    use_log   = (total >= _LARGE_THRESHOLD)

    print_run_banner('comicinfo', 'CBZ ComicInfo.xml 批量工具', root, args.apply)
    emit(f'  找到文件: {total} 个 .cbz（含子目录）')

    if not cbz_files:
        emit('\n  没有需要处理的文件。')
        return 0

    log_path:  Path | None       = None
    log_lines: list[str] | None  = None
    if use_log:
        ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
        mode_tag = 'apply' if args.apply else 'preview'
        log_path = root.parent / f'comicinfo_{mode_tag}_{ts}.log'
        emit(f'\n  文件数量 {total} ≥ {_LARGE_THRESHOLD}，详细结果将写入:\n  {log_path}\n')
        log_lines = [
            f'manga-toolkit-cli comicinfo 批量日志  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            f'模式: {"写入" if args.apply else "预览"}   总文件数: {total}',
            SEP2,
        ]

    # ── Phase 1: 预览 ──────────────────────────────────────────────────────────
    plan_counts: dict[str, int] = {'ok': 0, 'skip': 0, 'warn': 0}
    plans = _preview_all(cbz_files, plan_counts, log_lines)
    _print_preview_summary(plan_counts, args.apply)

    if not args.apply:
        if plan_counts['ok'] > 0:
            emit('  → 确认无误后，加上 --apply 参数重新运行以实际执行。')
        if log_path is not None:
            log_lines.append(SEP2)
            log_lines.append(f'解析完成   ok={plan_counts["ok"]}   warn={plan_counts["warn"]}   skip={plan_counts["skip"]}')
            log_path.write_text('\n'.join(log_lines) + '\n', encoding='utf-8')
            emit(f'  📄 详细日志: {log_path}')
        emit(SEP2)
        return 0

    # ── Phase 2: 确认 ──────────────────────────────────────────────────────────
    writable = [p for p in plans if p.writable]
    if not writable:
        emit('  没有可写入的文件。')
        emit(SEP2)
        return 0

    if not confirm(
        f'\n🟡 确认向 {len(writable)} 个 CBZ 写入 ComicInfo.xml？按 Enter 继续: '
    ):
        emit('  操作已取消。')
        return 0

    # ── Phase 3: 写入 ──────────────────────────────────────────────────────────
    write_counts: dict[str, int] = {'ok': 0, 'error': 0}
    if log_lines is not None:
        log_lines.append(SEP2)
        log_lines.append('── 写入阶段 ──')
    _apply_all(writable, write_counts, log_lines)
    _print_apply_summary(write_counts)

    if log_path is not None:
        log_lines.append(SEP2)
        log_lines.append(f'写入完成   ok={write_counts["ok"]}   error={write_counts["error"]}')
        log_path.write_text('\n'.join(log_lines) + '\n', encoding='utf-8')
        emit(f'  📄 详细日志: {log_path}')
    emit(SEP2)
    return 0


def add_comicinfo_args(p: argparse.ArgumentParser) -> None:
    """挂载 comicinfo 子命令的参数。"""
    p.add_argument('--root',     metavar='DIR',
                   help='CBZ 文件根目录（递归处理所有子目录）')
    p.add_argument('--apply',    action='store_true',
                   help='实际写入 ComicInfo.xml（不加此参数则仅预览）')
    p.add_argument('--examples', action='store_true',
                   help='解析内置示例并展示结果，不处理任何文件')
