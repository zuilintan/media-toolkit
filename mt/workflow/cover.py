"""
cover.py — CBZ 封面生成（cover 子命令工作流层）

目的: grimmory 在生成 cover 时若第一张图超过 2000 万像素会触发
``Rejected image: dimensions ... — possible decompression bomb`` 报错。
本工作流在 CBZ 内追加一张 ``0000.webp``（字典序排在最前），grimmory
即可直接采用，且尺寸/比例与其内部 cover (2:3, 1000×1500) 对齐。

流程:
  1. 在 CBZ 根目录依次寻找 ``cover.*`` / ``0001.*`` 作为源图
  2. 居中裁剪到 2:3（默认）或 smartcrop 显著性裁剪
  3. 缩放至 ≤ 1000×1500（保持比例）
  4. 编码为 WebP
  5. ZIP 追加写入 ``0000.webp``（参考 ComicInfo.xml 的追加替换方式，
     不重建整个压缩包）

依赖: Pillow / smartcrop（可选） / models / config / console / drag
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
from mt.infra.console import (
    SEP, emit, error, debug, info, warn, confirm, print_op_result,
)
from mt.infra.parallel import run_plans
from mt.workflow.drag import move_dir


# ── 常量 ─────────────────────────────────────────────────────────────────────
COVER_FILENAME: str            = '0000.webp'
TARGET_RATIO:   float          = 2 / 3            # W / H (竖图 2:3)
MAX_SIZE:       tuple[int, int] = (1000, 1500)    # 与 grimmory cover 对齐
DEFAULT_QUALITY: int           = 85
SOURCE_PRIORITY: tuple[str, ...] = ('cover', '0001')


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

def _cover_zinfo(inherited_attr: int) -> zipfile.ZipInfo:
    t  = time.localtime()
    zi = zipfile.ZipInfo(
        COVER_FILENAME,
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


def write_cover(cbz_path: str, webp_bytes: bytes) -> bool:
    """以追加模式写入 0000.webp，旧条目从内存目录摘除（死空间 < 1 个图像）。

    与 ``workflow.metadata.write_comicinfo`` 同构。

    Returns:
        True 表示替换了旧版，False 表示首次写入。
    """
    with zipfile.ZipFile(cbz_path, 'a') as zf:
        attr = _inherit_attr(
            [i for i in zf.infolist()
             if i.filename.lower() != COVER_FILENAME.lower()]
        )
        replaced = False
        for key in list(zf.NameToInfo.keys()):
            if key.lower() == COVER_FILENAME.lower():
                zf.filelist.remove(zf.NameToInfo.pop(key))
                replaced = True
                break
        zf.writestr(_cover_zinfo(attr), webp_bytes)
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
            # 读取现有 0000.webp 字节（如果有），用于 changed 判定
            for zi in zf.infolist():
                if zi.filename.lower() == COVER_FILENAME.lower():
                    existing = zf.read(zi.filename)
                    break
            src_name  = find_source_image(zf)
            if src_name is None:
                return CoverPlan(
                    cbz_path=cbz_path, src_name=None, src_size=None,
                    dst_size=None, mode=mode, webp_bytes=None,
                    existing_bytes=existing, error='未找到 cover.* / 0001.* 源图',
                )
            src_bytes = zf.read(src_name)
    except Exception as e:
        return CoverPlan(
            cbz_path=cbz_path, src_name=None, src_size=None, dst_size=None,
            mode=mode, webp_bytes=None, existing_bytes=None,
            error=f'打开 CBZ 失败: {e}',
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
            mode=mode, webp_bytes=None, existing_bytes=existing,
            error=f'图像处理失败 ({src_name}): {e}',
        )

    return CoverPlan(
        cbz_path=cbz_path, src_name=src_name, src_size=src_size,
        dst_size=fitted.size, mode=mode, webp_bytes=webp,
        existing_bytes=existing, error='',
    )


def apply_cover_plan(plan: CoverPlan) -> str:
    """写入单个 CBZ 的 0000.webp。

    Returns:
        'ok' / 'error'（无源图等情况由调用方过滤，此处不再判定）。
    """
    filename = plan.filename
    try:
        assert plan.webp_bytes is not None   # writable 已保证
        replaced = write_cover(plan.cbz_path, plan.webp_bytes)
        verb     = '已更新' if replaced else '已写入'
        sz       = f'{plan.dst_size[0]}×{plan.dst_size[1]}'
        emit(f'   ✅ {filename} — {COVER_FILENAME} {verb} ({sz})')
        return 'ok'
    except Exception as e:
        error(f'{filename} — {e}')
        return 'error'


# ═══════════════════════════════════════════════════════════════════════════════
# 批量 plan / apply
# ═══════════════════════════════════════════════════════════════════════════════

def _progress_line(idx: int, total: int, plan: CoverPlan) -> str:
    icon = ('✅' if plan.writable and plan.changed
            else '➡️ ' if plan.writable
            else '⛔')
    return f'   {icon} [{idx}/{total}] {plan.filename}'


def plan_covers(
    root:    str,
    mode:    str = 'center',
    quality: int = DEFAULT_QUALITY,
    jobs:    int = 1,
) -> list[CoverPlan]:
    """递归扫描 root 下所有 .cbz，返回 plan 列表。

    Args:
        jobs: 1=串行；>1=ProcessPoolExecutor 并行；0=自动选 min(cpu,4)。
              ≥ 4 个文件时才启用并行（避免 spawn 启动成本超过收益）。

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
    )


def apply_cover_plans(plans: list[CoverPlan], dry_run: bool = True) -> int:
    """整批写入封面。

    Args:
        plans:   预览阶段产出的 CoverPlan 列表。
        dry_run: True 时仅提示。

    Returns:
        失败数量（dry_run 时 0）。
    """
    if dry_run:
        info('\n🔍 预览模式 — 未做任何更改。使用 --apply 参数执行。')
        return 0

    ok_n = fail = skip = 0
    for plan in plans:
        if not plan.writable:
            warn(f'跳过 ({plan.error or "无源图"}): {plan.filename}')
            skip += 1
            continue
        if not plan.changed:
            skip += 1   # 现有 0000.webp 与目标字节完全一致，幂等跳过
            continue
        if apply_cover_plan(plan) == 'ok':
            ok_n += 1
        else:
            fail += 1

    print_op_result(ok_n, fail, skip)
    return fail


# ═══════════════════════════════════════════════════════════════════════════════
# 单目录处理（drag 模式回调）
# ═══════════════════════════════════════════════════════════════════════════════

def make_process_cover_dir(mode: str, quality: int, jobs: int = 1):
    """构造一个绑定 mode/quality/jobs 的 process_cover_dir 函数（供 drag 注入）。"""
    from mt.presentation.view import print_cover_preview   # 延迟导入避免循环

    def process_cover_dir(target_dir: Path, move_to: str) -> None:
        emit(f'\n{SEP}')
        emit(f'📂 目录: {target_dir}')
        plans = plan_covers(str(target_dir), mode=mode, quality=quality, jobs=jobs)
        print_cover_preview(plans)
        if not any(p.writable and p.changed for p in plans):
            return
        if not confirm('\n🟡 确认写入 0000.webp 封面？按 Enter 继续: '):
            return
        fail = apply_cover_plans(plans, dry_run=False)
        if fail == 0 and move_to:
            move_dir(target_dir, move_to)
        elif fail > 0:
            warn(f'{fail} 个写入失败，目录未移动，请修复后重试。')

    return process_cover_dir
