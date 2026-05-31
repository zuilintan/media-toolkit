"""
cover.py — CBZ 封面生成（cover 子命令工作流层）

目的: grimmory 在生成 cover 时若第一张图超过 2000 万像素会触发
``Rejected image: dimensions ... — possible decompression bomb`` 报错。
本工作流在 CBZ 内写入一张 2:3 / ≤ 1000×1500 的 WebP，grimmory 即可直接采用。

目标文件名取决于源图：
  - 源 ``0001.*`` → 写入 ``0000.webp``（字典序在最前，作为新增封面）
  - 源 ``cover.*`` → 写入 ``0000.webp``，并从 ZIP 中删除原 ``cover.*``

流程:
  1. 在 CBZ 根目录依次寻找 ``cover.*`` / ``0001.*`` 作为源图
  2. 居中裁剪到 2:3（默认）或 smartcrop 显著性裁剪
  3. 缩放至 ≤ 1000×1500（保持比例）
  4. 编码为 WebP
  5. ZIP 追加写入 ``0000.webp``；写入前清理同 stem 旧条目；源为
     ``cover.*`` 时额外删除所有 ``cover.*`` 条目（参考 ComicInfo.xml
     的追加替换方式，不重建整个压缩包）

依赖: Pillow / smartcrop（可选） / models / config / console
"""

from __future__ import annotations
import os
import time
import zipfile
from functools import partial
from io import BytesIO
from pathlib import Path

from PIL import Image

from mt.core.models import CoverPlan
from mt.core.config import PAGE_EXTS
from base.console import (
    SEP, emit, error, debug, info, warn, confirm, print_op_result,
)
from mt.infra.parallel import run_plans


# ── 常量 ─────────────────────────────────────────────────────────────────────
TARGET_RATIO:   float          = 2 / 3            # W / H (竖图 2:3)
MAX_SIZE:       tuple[int, int] = (1000, 1500)    # 与 grimmory cover 对齐
DEFAULT_QUALITY: int           = 85
SOURCE_PRIORITY: tuple[str, ...] = ('cover', '0001')
# 源 stem → 目标文件名
DST_FOR: dict[str, str] = {
    'cover': '0000.webp',      # 生成 0000.webp 并删除原 cover.*
    '0001':  '0000.webp',      # 追加新封面，排在 0001 之前
}


# ═══════════════════════════════════════════════════════════════════════════════
# 源图查找（仅 ZIP 根目录）
# ═══════════════════════════════════════════════════════════════════════════════

def find_source_image(zf: zipfile.ZipFile) -> str | None:
    """在 zf 根目录按优先级查找源图：cover.* → 0001.*。

    仅扫根目录；同优先级若有多个扩展名，取字典序最小者（确定性）。
    扩展名以 PAGE_EXTS 为准（与 PageCount 一致）。
    """
    buckets: dict[str, list[str]] = {k: [] for k in SOURCE_PRIORITY}
    for name in zf.namelist():
        if name.endswith('/') or '/' in name:
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() not in PAGE_EXTS:
            continue
        key = stem.lower()
        if key in buckets:
            buckets[key].append(name)
    for key in SOURCE_PRIORITY:
        if buckets[key]:
            return sorted(buckets[key])[0]
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 裁剪 & 缩放
# ═══════════════════════════════════════════════════════════════════════════════

def crop_center(img: Image.Image, ratio: float = TARGET_RATIO) -> Image.Image:
    """居中裁剪到指定 W/H 比例；保持比例，超出部分舍弃。"""
    W, H = img.size
    if W / H > ratio:           # 太宽 → 裁宽
        new_W = int(round(H * ratio))
        left  = (W - new_W) // 2
        return img.crop((left, 0, left + new_W, H))
    if W / H < ratio:           # 太高 → 裁高
        new_H = int(round(W / ratio))
        top   = (H - new_H) // 2
        return img.crop((0, top, W, top + new_H))
    return img


def crop_smart(img: Image.Image, ratio: float = TARGET_RATIO) -> Image.Image:
    """smartcrop 显著性裁剪到指定 W/H 比例。

    smartcrop 库基于边缘 / 饱和度 / 肤色综合打分挑选最佳子矩形；
    在横向跨页 / 主体偏置的封面上比 center 裁剪更可能保留主体。
    依赖未安装时回退到 :func:`crop_center` 并记 debug。
    """
    try:
        import smartcrop          # noqa: WPS433 — 懒加载，依赖可选
    except ImportError:
        debug('smartcrop 未安装，回退至 center 裁剪')
        return crop_center(img, ratio)

    # smartcrop 期望 RGB；GIF/PSD/调色板模式需要转换
    src = img.convert('RGB') if img.mode not in ('RGB', 'RGBA') else img
    sc  = smartcrop.SmartCrop()
    # crop_width/height 只需提供比例值（库内部按短边等比缩放定位）
    result = sc.crop(src, 100, int(round(100 / ratio)))
    box    = result['top_crop']
    return img.crop((
        box['x'], box['y'],
        box['x'] + box['width'], box['y'] + box['height'],
    ))


def resize_to_target(img: Image.Image, target: tuple[int, int] = MAX_SIZE) -> Image.Image:
    """缩到精确 target 尺寸；源小于 target 则保持原尺寸不放大。

    前提：调用方已通过 :func:`crop_center` 校正过比例，img 比例与 target 几乎
    一致。smartcrop 的整数步长可能引入亚像素级偏差（如源 2666×3999 vs target
    1000×1500 = 0.03% 形变），直接 resize 到 target 比输出 999×1500 在视觉上
    更整齐，肉眼无法察觉形变。
    """
    W, H        = img.size
    tW, tH      = target
    if W <= tW and H <= tH:
        return img                            # 源更小：保持原尺寸（不放大）
    return img.resize((tW, tH), Image.LANCZOS)


# ═══════════════════════════════════════════════════════════════════════════════
# WebP 编码
# ═══════════════════════════════════════════════════════════════════════════════

def encode_webp(img: Image.Image, quality: int = DEFAULT_QUALITY) -> bytes:
    """编码为 WebP；alpha 通道保留，无 alpha 走 RGB。"""
    mode = 'RGBA' if img.mode in ('RGBA', 'LA', 'PA') else 'RGB'
    if img.mode != mode:
        img = img.convert(mode)
    buf = BytesIO()
    img.save(buf, format='WEBP', quality=quality, method=6)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# CBZ 追加写入（参考 workflow.metadata.write_comicinfo）
# ═══════════════════════════════════════════════════════════════════════════════

def _cover_zinfo(filename: str, inherited_attr: int) -> zipfile.ZipInfo:
    t  = time.localtime()
    zi = zipfile.ZipInfo(
        filename,
        date_time=(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec),
    )
    zi.compress_type = zipfile.ZIP_STORED      # WebP 已压缩
    zi.external_attr = inherited_attr
    return zi


def _inherit_attr(infos: list[zipfile.ZipInfo]) -> int:
    for ifo in infos:
        if ifo.external_attr:
            return ifo.external_attr
    return 0x20  # DOS Archive 默认


def write_cover(
    cbz_path: str,
    dst_name: str,
    webp_bytes: bytes,
    also_delete_stem: str | None = None,
) -> bool:
    """以追加模式写入 ``dst_name``，根目录下同 stem 的旧条目（任何扩展名）
    从内存目录摘除（死空间 < 1 个图像）。

    ``also_delete_stem`` 不为 None 时，同样摘除根目录下该 stem 的所有条目
    （用于 cover.* → 0000.webp 时删除原 cover.*）。

    与 ``workflow.metadata.write_comicinfo`` 同构。

    Returns:
        True 表示替换了旧版（dst_name 本身已存在），False 表示首次写入。
    """
    dst_stem = os.path.splitext(dst_name)[0].lower()
    with zipfile.ZipFile(cbz_path, 'a') as zf:
        attr = _inherit_attr(
            [i for i in zf.infolist()
             if '/' in i.filename
             or os.path.splitext(i.filename)[0].lower() != dst_stem]
        )
        replaced = False
        for key in list(zf.NameToInfo.keys()):
            if '/' in key:
                continue
            key_stem = os.path.splitext(key)[0].lower()
            if key_stem == dst_stem:
                if key.lower() == dst_name.lower():
                    replaced = True
                zf.filelist.remove(zf.NameToInfo.pop(key))
            elif also_delete_stem and key_stem == also_delete_stem:
                zf.filelist.remove(zf.NameToInfo.pop(key))
        zf.writestr(_cover_zinfo(dst_name, attr), webp_bytes)
        zf.NameToInfo[dst_name].flag_bits |= 0x800
    return replaced


# ═══════════════════════════════════════════════════════════════════════════════
# 单文件 plan / apply
# ═══════════════════════════════════════════════════════════════════════════════

def plan_cover(
    cbz_path: str,
    mode:     str = 'center',
    quality:  int = DEFAULT_QUALITY,
) -> CoverPlan:
    """构建单个 CBZ 的封面写入计划（plan 阶段即完成裁剪 + 编码）。

    任何步骤异常都被吸收进 plan.error，调用方据此过滤；不会抛出。
    """
    existing: bytes | None = None
    try:
        with zipfile.ZipFile(cbz_path, 'r') as zf:
            src_name  = find_source_image(zf)
            if src_name is None:
                return CoverPlan(
                    cbz_path=cbz_path, src_name=None, src_size=None,
                    dst_size=None, mode=mode, dst_name=None, webp_bytes=None,
                    existing_bytes=None, error='未找到 cover.* / 0001.* 源图',
                )
            src_stem = os.path.splitext(src_name)[0].lower()
            dst_name = DST_FOR[src_stem]
            # 读取现有目标文件字节（若有），用于 changed 判定
            for zi in zf.infolist():
                if zi.filename.lower() == dst_name.lower():
                    existing = zf.read(zi.filename)
                    break
            src_bytes = zf.read(src_name)
    except Exception as e:
        return CoverPlan(
            cbz_path=cbz_path, src_name=None, src_size=None, dst_size=None,
            mode=mode, dst_name=None, webp_bytes=None, existing_bytes=None,
            error=f'打开 CBZ 失败: {e}',
        )

    # 源即目标 → 上一次已处理过；再次裁剪/编码必然产生新字节（smartcrop
    # 步长取整会切几像素，center 模式也会因 WebP 重编码而字节不一致），
    # 导致每跑一次都"变小一圈"。这里直接标记为已是最新，跳过处理。
    if src_name.lower() == dst_name.lower():
        return CoverPlan(
            cbz_path=cbz_path, src_name=src_name, src_size=None,
            dst_size=None, mode=mode, dst_name=dst_name,
            webp_bytes=src_bytes, existing_bytes=src_bytes, error='',
        )

    try:
        # 解码源图：开启炸弹豁免（我们自己控制下游尺寸）
        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(BytesIO(src_bytes))
        img.load()
        src_size = img.size

        if mode == 'smart':
            cropped = crop_smart(img, TARGET_RATIO)
            # smartcrop 内部步长取整可能给出近似比例（如 999×1495）；
            # 再过一遍 center 校正，确保严格 2:3。
            cropped = crop_center(cropped, TARGET_RATIO)
        else:
            cropped = crop_center(img, TARGET_RATIO)
        fitted  = resize_to_target(cropped, MAX_SIZE)
        webp    = encode_webp(fitted, quality=quality)
    except Exception as e:
        return CoverPlan(
            cbz_path=cbz_path, src_name=src_name, src_size=None, dst_size=None,
            mode=mode, dst_name=dst_name, webp_bytes=None,
            existing_bytes=existing,
            error=f'图像处理失败 ({src_name}): {e}',
        )

    return CoverPlan(
        cbz_path=cbz_path, src_name=src_name, src_size=src_size,
        dst_size=fitted.size, mode=mode, dst_name=dst_name, webp_bytes=webp,
        existing_bytes=existing, error='',
    )


def apply_cover_plan(plan: CoverPlan) -> str:
    """写入单个 CBZ 的目标封面（plan.dst_name）。

    源为 cover.* 时，写入后同步从 ZIP 删除所有 cover.* 条目（自身）。

    Returns:
        'ok' / 'error'（无源图等情况由调用方过滤，此处不再判定）。
    """
    filename = plan.filename
    try:
        assert plan.webp_bytes is not None and plan.dst_name is not None
        src_stem = os.path.splitext(plan.src_name)[0].lower() if plan.src_name else None
        also_delete = src_stem if src_stem == 'cover' else None
        write_cover(plan.cbz_path, plan.dst_name, plan.webp_bytes, also_delete_stem=also_delete)
        emit(f'   ✅ {filename} — 已处理')
        return 'ok'
    except Exception as e:
        error(f'{filename} — {e}')
        return 'error'


# ═══════════════════════════════════════════════════════════════════════════════
# 批量 plan / apply
# ═══════════════════════════════════════════════════════════════════════════════

def _progress_line(idx: int, total: int, plan: CoverPlan) -> str:
    icon = ('*' if plan.writable and plan.changed
            else '-' if plan.writable
            else '!')
    return f'   {icon} [{idx}/{total}] {plan.filename}'


def plan_covers(
    root:    str,
    mode:    str = 'center',
    quality: int = DEFAULT_QUALITY,
    jobs:    int = 1,
    on_progress=None,
    cancel_token=None,
) -> list[CoverPlan]:
    """递归扫描 root 下所有 .cbz，返回 plan 列表。

    Args:
        jobs: 1=串行；>1=ProcessPoolExecutor 并行；0=自动选 min(cpu,4)。
              ≥ 4 个文件时才启用并行（避免 spawn 启动成本超过收益）。
        on_progress: 每完成一项即回调 ``f(done, total)``。
        cancel_token: threading.Event，已 set 时提前退出。

    每完成一个文件即打印进度行，便于大批量任务跟踪。
    """
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []
    files = [str(fp) for fp in sorted(root_path.rglob('*.cbz'))]
    emit(f'  找到文件: {len(files)} 个 .cbz（含子目录）')
    return run_plans(
        files,
        partial(plan_cover, mode=mode, quality=quality),
        jobs=jobs,
        progress_line=_progress_line,
        on_progress=on_progress,
        cancel_token=cancel_token,
    )


def apply_cover_plans(
    plans: list[CoverPlan], dry_run: bool = True, cancel_token=None,
) -> int:
    """整批写入封面。

    Args:
        plans:   预览阶段产出的 CoverPlan 列表。
        dry_run: True 时仅提示。
        cancel_token: threading.Event，已 set 时提前退出。

    Returns:
        失败数量（dry_run 时 0）。
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
            warn(f'跳过 ({plan.error or "无源图"}): {plan.filename}')
            skip += 1
            continue
        if not plan.changed:
            skip += 1   # 现有封面与目标字节完全一致，幂等跳过
            continue
        if apply_cover_plan(plan) == 'ok':
            ok_n += 1
        else:
            fail += 1

    print_op_result(ok_n, fail, skip)
    return fail

