"""
pack.py — 图片目录序号化重命名 + STORED zip 打包（pack 子命令工作流层）

每个目录视为一本「漫画/相册」，将其内的图片文件按字典序重命名为
``0001.<ext>``、``0002.<ext>`` …（对齐 ReNamer 的 ``<Inc NrDir:0001>``
规则），并以 ``zipfile.ZIP_STORED``（不压缩）打包到同级 ``<dir>.zip``。

`<Inc NrDir:0001>` 语义:
  - 每个目录独立计数（递归不跨目录），从 0001 起步
  - 4 位零填充；图片数超过 9999 时自动扩展位数（保证字典序与编号一致）

流程:
  1. 列出目录内的图片文件（PAGE_EXTS），按字典序定序
  2. 计算目标名 ``{i:0Wd}{ext}``（ext 转小写，保留原后缀；含 .jpeg 等）
  3. apply: 两阶段重命名（→ 临时名 → 目标名）以规避名称碰撞
  4. apply: 以 ZIP_STORED 写入 ``<dir>.zip``（已存在则覆盖）
  5. 可选 ``move-to``：将生成的 zip 移动至目标目录

依赖: models / config / utils / console / parallel / drag
"""

from __future__ import annotations
import os
import secrets
import shutil
import time
import zipfile
from pathlib import Path

from mt.core.models import PackPlan
from mt.core.config import PAGE_EXTS
from mt.infra.console import (
    SEP, emit, error, info, warn, confirm, print_op_result,
)
from mt.infra.parallel import run_plans
from mt.infra.utils import guard_path


# ═══════════════════════════════════════════════════════════════════════════════
# 单目录 plan
# ═══════════════════════════════════════════════════════════════════════════════

def _pad_width(n: int) -> int:
    """编号位数：默认 4 位；图片数 ≥ 10000 时扩展，确保字典序与数字序一致。"""
    return max(4, len(str(n)))


def plan_pack(src_dir_path: str) -> PackPlan:
    """构建单个目录的打包计划（picklable，可用于并行）。

    错误（路径不存在 / 无图片）被吸收进 plan.error，调用方据此过滤；不抛。
    """
    src_dir  = Path(src_dir_path)
    zip_path = str(src_dir.parent / f'{src_dir.name}.zip')
    if not src_dir.is_dir():
        return PackPlan(
            src_dir=src_dir_path, zip_path=zip_path,
            renames=[], extras=[], zip_exists=False,
            error='目录不存在',
        )

    images: list[Path] = []
    extras: list[str]  = []
    for f in sorted(src_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() in PAGE_EXTS:
            images.append(f)
        else:
            extras.append(f.name)

    if not images:
        return PackPlan(
            src_dir=src_dir_path, zip_path=zip_path,
            renames=[], extras=extras, zip_exists=Path(zip_path).exists(),
            error='未找到图片文件',
        )

    pad = _pad_width(len(images))
    renames = [
        (img.name, f'{i:0{pad}d}{img.suffix.lower()}')
        for i, img in enumerate(images, 1)
    ]
    return PackPlan(
        src_dir=src_dir_path, zip_path=zip_path,
        renames=renames, extras=extras,
        zip_exists=Path(zip_path).exists(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 单目录 apply
# ═══════════════════════════════════════════════════════════════════════════════

def _rename_pass(src_dir: Path, renames: list[tuple[str, str]]) -> list[str]:
    """两阶段重命名：原名 → ``__pack_<nonce>_<seq>`` → 目标名。

    用随机 nonce + 顺序号作为临时名，规避任意源/目标名碰撞；
    返回最终落盘的文件名列表（按 renames 顺序，含未改名的）。
    """
    nonce       = secrets.token_hex(4)
    tmp_pairs:    list[tuple[str, str]] = []   # (tmp_name, final_name)
    final_names:  list[str]             = []

    # phase 1: 仅对真正需要改名的项移到临时名
    for idx, (old, new) in enumerate(renames):
        final_names.append(new)
        if old == new:
            continue
        tmp = f'__pack_{nonce}_{idx:06d}{Path(old).suffix}'
        (src_dir / old).rename(src_dir / tmp)
        tmp_pairs.append((tmp, new))

    # phase 2: 临时名 → 目标名
    for tmp, final in tmp_pairs:
        (src_dir / tmp).rename(src_dir / final)

    return final_names


def _stored_zinfo(arcname: str, src_path: Path) -> zipfile.ZipInfo:
    """构造一个「DOS 属性」风格的 ZipInfo（与 cover.py / Bandizip 输出对齐）。

    用源文件 mtime 作为条目时间；``external_attr`` 仅置 Archive bit (0x20)，
    高 16 位的 Unix mode 留空，避免在查看器中显示出 ``-rw-rw-rw-``。
    """
    t = time.localtime(src_path.stat().st_mtime)
    zi = zipfile.ZipInfo(
        arcname,
        date_time=(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec),
    )
    zi.compress_type = zipfile.ZIP_STORED
    zi.external_attr = 0x20         # DOS Archive
    zi.create_system = 0            # FAT/DOS
    return zi


def _write_stored_zip(zip_path: Path, src_dir: Path, names: list[str]) -> None:
    """以 ``ZIP_STORED`` 模式打包 names 中的文件到 zip_path（覆盖已存在）。

    手动构造 ZipInfo + ``writestr`` 而非 ``zf.write(path)``，目的是
    清除默认 ``ZipInfo.from_file`` 写入的 Unix mode 高位，让条目显示为
    纯 DOS 属性。
    """
    guard_path(zip_path)
    with zipfile.ZipFile(
        zip_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True,
    ) as zf:
        for name in names:
            src = src_dir / name
            with open(src, 'rb') as fp:
                zf.writestr(_stored_zinfo(name, src), fp.read())


def apply_pack_plan(plan: PackPlan) -> str:
    """执行单个 plan：两阶段改名 + STORED 打包。

    Returns:
        'ok' / 'error'。失败会 ``error()`` 提示，由调用方计入失败数。
    """
    src_dir  = Path(plan.src_dir)
    zip_path = Path(plan.zip_path)
    try:
        final_names = _rename_pass(src_dir, plan.renames)
        _write_stored_zip(zip_path, src_dir, final_names)
        emit(f'   ✅ {plan.name} — 已处理（{len(final_names)} 张 → {zip_path.name}）')
        return 'ok'
    except Exception as e:
        error(f'{plan.name} — {e}')
        return 'error'


# ═══════════════════════════════════════════════════════════════════════════════
# 批量 plan / apply
# ═══════════════════════════════════════════════════════════════════════════════

def _progress_line(idx: int, total: int, plan: PackPlan) -> str:
    icon = ('*' if plan.writable
            else '!')
    return f'   {icon} [{idx}/{total}] {plan.name}'


def plan_packs(
    root: str, jobs: int = 1, on_progress=None, cancel_token=None,
) -> list[PackPlan]:
    """扫描 root 下的直接子目录，每个子目录产出一个 PackPlan。

    与 sourcefile 单层扫描语义一致：不递归更深。

    Args:
        jobs: 1=串行；>1=并行；0=自动 ``min(cpu,4)``；< 4 个目录强制串行。
        on_progress: 每完成一项即回调 ``f(done, total)``。
        cancel_token: threading.Event，已 set 时提前退出。
    """
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []
    target_dirs = [str(d) for d in sorted(root_path.iterdir()) if d.is_dir()]
    emit(f'  找到目录: {len(target_dirs)} 个')
    return run_plans(
        target_dirs, plan_pack, jobs=jobs, progress_line=_progress_line,
        on_progress=on_progress, cancel_token=cancel_token,
    )


def apply_pack_plans(
    plans: list[PackPlan], dry_run: bool = True, cancel_token=None,
) -> int:
    """整批执行打包计划。

    Returns:
        失败数（dry_run 时 0）。
    """
    if dry_run:
        info('\n🔍 预览模式 — 未做任何更改。使用 --apply 参数执行。')
        return 0

    def _cancelled() -> bool:
        return cancel_token is not None and cancel_token.is_set()

    ok_n = fail = skip = 0
    for plan in plans:
        if _cancelled():
            emit('  ⏹️  已取消')
            break
        if not plan.writable:
            warn(f'跳过 ({plan.error or "无图片"}): {plan.name}')
            skip += 1
            continue
        if apply_pack_plan(plan) == 'ok':
            ok_n += 1
        else:
            fail += 1

    print_op_result(ok_n, fail, skip)
    return fail


# ═══════════════════════════════════════════════════════════════════════════════
# move-to：移动产物 zip（与 sourcefile/cover 移动目录的语义不同）
# ═══════════════════════════════════════════════════════════════════════════════

def move_zip(zip_path: Path, target: str) -> bool:
    """将打包产物 zip 移动到 target 目录；同名已存在则覆盖。"""
    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)
    dest = target_path / zip_path.name
    if dest.exists():
        warn(f'目标 zip 已存在，将覆盖: {dest}')
        try:
            dest.unlink()
        except Exception as e:
            error(f'删除已存在 zip 失败: {dest} — {e}')
            return False
    try:
        shutil.move(str(zip_path), str(dest))
        emit(f'📦 已移动: {zip_path.name}\n   → {dest}')
        return True
    except Exception as e:
        error(f'移动失败: {zip_path.name} — {e}')
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 单目录处理（drag 模式回调）
# ═══════════════════════════════════════════════════════════════════════════════

def process_pack_dir(src_dir: Path, target: str) -> None:
    """drag 模式入口：plan → preview → confirm → apply → 可选移动 zip。"""
    from mt.presentation.view import print_pack_preview   # 延迟导入避免循环
    emit(f'\n{SEP}')
    emit(f'📂 目录: {src_dir}')
    plans = [plan_pack(str(src_dir))]
    print_pack_preview(plans)
    if not any(p.writable for p in plans):
        return
    if not confirm('\n🟡 确认重命名并打包？按 Enter 继续: '):
        return
    fail = apply_pack_plans(plans, dry_run=False)
    if fail == 0 and target:
        for p in plans:
            if p.writable:
                move_zip(Path(p.zip_path), target)
    elif fail > 0:
        warn(f'{fail} 个目录处理失败，zip 未移动，请修复后重试。')
