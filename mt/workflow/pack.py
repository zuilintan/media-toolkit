"""
pack.py — 图片目录序号化重命名 + STORED zip 打包（pack 子命令工作流层）

把识别出的「打包单位」按 ``<Inc NrDir:0001>`` 规则改名为
``0001.<ext>``、``0002.<ext>`` …，再以 ``zipfile.ZIP_STORED`` 打包到同级
``<dir>.zip``；打包成功后整树 ``shutil.rmtree``。

`<Inc NrDir:0001>` 语义:
  - 每个目录独立计数（递归不跨目录），从 0001 起步
  - 4 位零填充；图片数 ≥ 10000 时扩位，确保字典序 = 数字序

打包单位识别（``_find_units``，递归自 root）:
  - ``'flat'``  直接含 ≥ ``MIN_IMAGES`` 张图、无子目录
  - ``'nested'`` 仅含子目录、每个子目录都是「image leaf」（≥1 图、无子目录；
                 不应用 MIN_IMAGES —— 章节合法可以很短）；zip 内保留子目录名
                 作为路径前缀，每子目录独立编号。
                 顶层允许伴随 ``cover.*`` / ``0000.*`` 元数据图与任意非图
                 （ComicInfo.xml 等），原名原样写入 zip 顶层。
  - ``MIXED``    图+目录同层且顶层图非 cover/0000 → 跳过该目录，不下钻
  - ``CONTAINER`` 仅子目录但不全是 image leaf → 下钻 children 继续找
  - ``EMPTY`` / ``TOO_FEW`` → 跳过

> NESTED 只允许 1 层子目录（子目录里再有子目录就退化为 CONTAINER），
> 故「漫画/卷/话/imgs」三层结构会自动停在卷级 —— 每卷独立一 zip，
> 与项目里「卷不可合一档」的约定一致。

apply 阶段:
  1. 以 ZIP_STORED 写入 ``<unit>.zip``（已存在覆盖）；
     源文件按原路径读、新名作 arcname 写 —— 不在盘上做改名
     （反正下一步整树要删）
  2. ``shutil.rmtree`` 删除整个单位目录（含非图 extras）
  3. 可选 ``move-to`` 将 zip 移到目标目录

依赖: models / config / utils / console / parallel / drag
"""

from __future__ import annotations
import os
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


# ── 常量 ─────────────────────────────────────────────────────────────────────
MIN_IMAGES: int = 3   # FLAT 单位的最少图片数；不足视为噪声跳过
MAX_DEPTH:  int = 8   # 递归扫描的最大层级（防符号链接 / 异常目录）

# NESTED 单位顶层允许保留的元数据图片 stem（小写）。
# 对齐 cover.py 的产物（cover.webp / 0000.webp）和常见命名约定；
# 这两个文件 + 任意非图片文件可与子目录共存，会原样写入 zip 顶层。
_NESTED_TOP_IMAGE_STEMS: frozenset[str] = frozenset({'cover', '0000'})

# OS / 文件管理器生成的元数据 / 缓存文件，绝不进 zip。case-insensitive。
# 单纯名字匹配在 _OS_JUNK_FILES；前缀匹配在 _is_os_junk 内单独处理。
_OS_JUNK_FILES: frozenset[str] = frozenset({
    'thumbs.db',     # Windows 缩略图缓存
    'desktop.ini',   # Windows 文件夹配置
    '.ds_store',     # macOS Finder
})


def _is_nested_top_image(p: Path) -> bool:
    """NESTED 单位顶层允许的元数据图片：``cover.*`` / ``0000.*``。"""
    return p.stem.lower() in _NESTED_TOP_IMAGE_STEMS


def _is_os_junk(name: str) -> bool:
    """OS / 文件管理器生成的元数据，绝不进 zip。

    包含: thumbs.db / desktop.ini / .DS_Store，以及 macOS AppleDouble
    资源派生文件（``._foo`` 形式）。
    """
    lower = name.lower()
    return lower in _OS_JUNK_FILES or lower.startswith('._')


# ═══════════════════════════════════════════════════════════════════════════════
# 通用工具
# ═══════════════════════════════════════════════════════════════════════════════

def _pad_width(n: int) -> int:
    """编号位数：默认 4 位；图片数 ≥ 10000 时扩展，确保字典序与数字序一致。"""
    return max(4, len(str(n)))


def _split_dir_content(d: Path) -> tuple[list[Path], list[str]]:
    """目录的直接内容拆分为 ``(images, extras_filenames)``；不递归、忽略子目录。

    images 按字典序排好，可直接喂给 ``<Inc NrDir>`` 编号；extras 是相对
    该目录的文件名（无路径前缀）。OS 垃圾（``thumbs.db`` / ``._*`` 等）
    归入 extras，不参与编号。
    """
    images: list[Path] = []
    extras: list[str]  = []
    for e in sorted(d.iterdir()):
        if not e.is_file():
            continue
        if e.suffix.lower() in PAGE_EXTS and not _is_os_junk(e.name):
            images.append(e)
        else:
            extras.append(e.name)
    return images, extras


# ═══════════════════════════════════════════════════════════════════════════════
# 打包单位识别
# ═══════════════════════════════════════════════════════════════════════════════

def _is_image_leaf(d: Path) -> bool:
    """``d`` 的直接内容是「≥ 1 张图 + 无子目录」？

    用于 NESTED 子目录的合格判定 —— **不**应用 MIN_IMAGES 阈值，因为
    章节合法可以很短（番外、小尾声、预览等）；MIN_IMAGES 仅在顶层
    FLAT 判定中作噪声过滤。非图片文件不影响判定（会作为 extras 处理）。
    """
    has_image = False
    for e in d.iterdir():
        if e.is_dir():
            return False
        if (e.is_file() and e.suffix.lower() in PAGE_EXTS
                and not _is_os_junk(e.name)):
            has_image = True
    return has_image


def _find_units_in_root(root: Path) -> list[tuple[Path, str]]:
    """批量模式入口：``--root`` 已被用户声明为「容器」，**不**把 root 自身
    当作 NESTED 单位。

    规则:
      - root 只有图、无子目录 → 把 root 当 FLAT（少见但合理）
      - 否则遍历直接子目录，逐个走 ``_find_units`` 递归

    这样可避免「root 下若干个 FLAT 子目录」被误识别为
    「root 是 NESTED 包含若干子目录」，导致全部塞进 root.zip。
    """
    images:  list[Path] = []
    subdirs: list[Path] = []
    for e in sorted(root.iterdir()):
        if e.is_dir():
            subdirs.append(e)
        elif (e.is_file() and e.suffix.lower() in PAGE_EXTS
              and not _is_os_junk(e.name)):
            images.append(e)

    # root 自身是 FLAT
    if images and not subdirs:
        if len(images) >= MIN_IMAGES:
            return [(root, 'flat')]
        info(f'  ⏭️  跳过（仅 {len(images)} 张图 < {MIN_IMAGES}）: {root}')
        return []

    if images and subdirs:
        info(f'  ⏭️  根目录图片与子目录混合，仅扫子目录: {root}')

    # 容器：递归每个子目录（注意是 _find_units，子目录可以是 NESTED）
    result: list[tuple[Path, str]] = []
    for d in subdirs:
        result.extend(_find_units(d))
    return result


def _find_units(dir_path: Path, _depth: int = 0) -> list[tuple[Path, str]]:
    """从 ``dir_path`` 递归识别打包单位，返回 ``[(unit_dir, kind)]``。

    kind ∈ ``{'flat', 'nested'}``。跳过的目录（含混合 / 图不足 / 空 /
    超深）会经 ``info()`` 打印一条提示，便于用户排查。

    drag 模式入口；batch 模式请改用 ``_find_units_in_root`` 以避免把 root
    自身当 NESTED。
    """
    if _depth > MAX_DEPTH:
        info(f'  ⏭️  跳过（嵌套层级 > {MAX_DEPTH}）: {dir_path}')
        return []

    images:  list[Path] = []
    subdirs: list[Path] = []
    for e in sorted(dir_path.iterdir()):
        if e.is_dir():
            subdirs.append(e)
        elif e.is_file() and e.suffix.lower() in PAGE_EXTS:
            # OS 垃圾即使戴着图片后缀（``._cover.webp`` 这类 AppleDouble
            # 资源派生文件）也不算图，跳过以免触发 MIXED 误判
            if _is_os_junk(e.name):
                continue
            images.append(e)

    # FLAT: 仅图片
    if images and not subdirs:
        if len(images) >= MIN_IMAGES:
            return [(dir_path, 'flat')]
        info(f'  ⏭️  跳过（仅 {len(images)} 张图 < {MIN_IMAGES}）: {dir_path}')
        return []

    # 图 + 目录同层：默认 MIXED 跳过；但若顶层图都是元数据图（cover/0000）
    # 且所有子目录都是 FLAT，则视为 NESTED —— 处理「漫画/cover.webp +
    # ComicInfo.xml + 第N话/imgs」这种 metadata 子命令产物 + 分话的常见结构。
    if images and subdirs:
        if (all(_is_nested_top_image(img) for img in images)
                and all(_is_image_leaf(d) for d in subdirs)):
            return [(dir_path, 'nested')]
        info(f'  ⏭️  跳过（图片与子目录混合）: {dir_path}')
        return []

    # 仅子目录
    if subdirs:
        if all(_is_image_leaf(d) for d in subdirs):
            return [(dir_path, 'nested')]
        # CONTAINER: 下钻
        result: list[tuple[Path, str]] = []
        for d in subdirs:
            result.extend(_find_units(d, _depth + 1))
        return result

    # EMPTY
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# 单 unit 的 plan
# ═══════════════════════════════════════════════════════════════════════════════

def _plan_flat(unit_dir: Path) -> tuple[list[tuple[str, str]], list[str]]:
    images, extras = _split_dir_content(unit_dir)
    pad = _pad_width(len(images))
    renames = [
        (img.name, f'{i:0{pad}d}{img.suffix.lower()}')
        for i, img in enumerate(images, 1)
    ]
    return renames, extras


def _plan_nested(unit_dir: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """NESTED unit：

    - 顶层文件（cover.* / 0000.* / ComicInfo.xml / 等）**原名原样**写入 zip，
      作为 identity 改名（``(name, name)``）；不计入 n_renamed。
    - 每个直接子目录独立编号，arcname 加子目录名前缀。
    - 子目录内的非图片文件归入 ``extras``（不进 zip，随 rmtree 删除）。
    """
    renames: list[tuple[str, str]] = []
    extras:  list[str]             = []
    # 顶层：文件直通进 zip（含元数据图与非图）；_find_units 已保证图都是
    # cover/0000 类。OS 垃圾（thumbs.db 等）转入 extras 并随 rmtree 删除，
    # 绝不进 zip。
    for e in sorted(unit_dir.iterdir()):
        if not e.is_file():
            continue
        if _is_os_junk(e.name):
            extras.append(e.name)
            continue
        renames.append((e.name, e.name))
    # 每子目录独立编号
    for sub in sorted(unit_dir.iterdir()):
        if not sub.is_dir():
            continue
        sub_images, sub_extras = _split_dir_content(sub)
        pad = _pad_width(len(sub_images))
        for i, img in enumerate(sub_images, 1):
            renames.append((
                f'{sub.name}/{img.name}',
                f'{sub.name}/{i:0{pad}d}{img.suffix.lower()}',
            ))
        for ex in sub_extras:
            extras.append(f'{sub.name}/{ex}')
    return renames, extras


def plan_unit(unit_dir_str: str, kind: str) -> PackPlan:
    """构建单个打包单位的 PackPlan（picklable worker，可走并行）。"""
    unit_dir = Path(unit_dir_str)
    zip_path = str(unit_dir.parent / f'{unit_dir.name}.zip')

    if not unit_dir.is_dir():
        return PackPlan(
            src_dir=unit_dir_str, zip_path=zip_path,
            renames=[], extras=[], zip_exists=False, kind=kind,
            error='目录不存在',
        )

    if kind == 'flat':
        renames, extras = _plan_flat(unit_dir)
    else:
        renames, extras = _plan_nested(unit_dir)

    if not renames:
        return PackPlan(
            src_dir=unit_dir_str, zip_path=zip_path,
            renames=[], extras=extras, zip_exists=Path(zip_path).exists(),
            kind=kind, error='未找到图片文件',
        )

    return PackPlan(
        src_dir=unit_dir_str, zip_path=zip_path,
        renames=renames, extras=extras,
        zip_exists=Path(zip_path).exists(), kind=kind,
    )


def _plan_unit_item(item: tuple[str, str]) -> PackPlan:
    """run_plans worker：解包 (unit_dir_str, kind) 元组。"""
    return plan_unit(item[0], item[1])


# ═══════════════════════════════════════════════════════════════════════════════
# 单 unit 的 apply
# ═══════════════════════════════════════════════════════════════════════════════

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


def _write_stored_zip(
    zip_path: Path, src_dir: Path, renames: list[tuple[str, str]],
) -> None:
    """以 ``ZIP_STORED`` 模式打包到 zip_path（覆盖已存在）。

    源文件按原路径读取，以新 arcname 写入 —— 不在盘上做改名，因为
    打包成功后整个 unit 目录就会被 rmtree。

    手动构造 ZipInfo + ``writestr`` 而非 ``zf.write(path)``，目的是
    清除默认 ``ZipInfo.from_file`` 写入的 Unix mode 高位，让条目显示为
    纯 DOS 属性（与 Bandizip 对齐）。

    nested 模式下 renames 的字符串带子目录前缀（``Ch01/x.jpg`` →
    ``Ch01/0001.jpg``）；Path 在 Windows 上能正确解析正斜杠，zip arcname
    本身也用正斜杠，二者天然兼容。
    """
    guard_path(zip_path)
    with zipfile.ZipFile(
        zip_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True,
    ) as zf:
        for old, new in renames:
            src = src_dir / old
            with open(src, 'rb') as fp:
                zf.writestr(_stored_zinfo(new, src), fp.read())


def apply_pack_plan(plan: PackPlan) -> str:
    """执行单个 plan：写 STORED zip → 删除整个 unit 目录树。

    源目录删除失败不视为整体失败：zip 已落盘，仅警告并 ``ok`` 返回，
    用户可自行清理（典型原因：杀软/索引器/网盘客户端临时占用句柄）。

    Returns:
        'ok' / 'error'。'error' 表示 zip 未生成。
    """
    src_dir  = Path(plan.src_dir)
    zip_path = Path(plan.zip_path)
    try:
        _write_stored_zip(zip_path, src_dir, plan.renames)
    except Exception as e:
        error(f'{plan.name} — 打包失败: {e}')
        return 'error'

    suffix = f'（{len(plan.renames)} 张 → {zip_path.name}）'
    try:
        guard_path(src_dir)
        shutil.rmtree(src_dir)
        emit(f'   ✅ {plan.name} — 已打包并删除源目录{suffix}')
    except Exception as e:
        warn(f'{plan.name} — zip 已生成，但源目录删除失败: {e}')
        emit(f'   ✅ {plan.name} — 已打包{suffix}')
    return 'ok'


# ═══════════════════════════════════════════════════════════════════════════════
# 批量 plan / apply
# ═══════════════════════════════════════════════════════════════════════════════

def _progress_line(idx: int, total: int, plan: PackPlan) -> str:
    icon = ('*' if plan.writable else '!')
    return f'   {icon} [{idx}/{total}] {plan.name}'


def plan_packs(
    root: str, jobs: int = 1, on_progress=None, cancel_token=None,
) -> list[PackPlan]:
    """从 root 递归识别打包单位，每单位产出一个 PackPlan。

    与 sourcefile 的「root 是高层容器」语义对齐，但走的是结构化递归：
    遇到 FLAT / NESTED 立即视作一个单位（不再下钻），其它情况继续递归。

    Args:
        jobs: 1=串行；>1=并行 plan_unit；0=自动 ``min(cpu,4)``。
              识别本身（_find_units）始终在主进程串行执行，并行的只是
              已识别单位的 PackPlan 构建 —— 通常是字符串处理，并行收益
              有限，主要作用是统一接口。
        on_progress: 每完成一项即回调 ``f(done, total)``。
        cancel_token: threading.Event，已 set 时提前退出。
    """
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []

    units = _find_units_in_root(root_path)
    if not units:
        emit('  未识别出任何打包单位')
        return []

    flat_n   = sum(1 for _, k in units if k == 'flat')
    nested_n = sum(1 for _, k in units if k == 'nested')
    emit(f'  识别打包单位: {len(units)} 个（单层 {flat_n}，嵌套 {nested_n}）')

    items: list[tuple[str, str]] = [(str(d), k) for d, k in units]
    return run_plans(
        items, _plan_unit_item, jobs=jobs, progress_line=_progress_line,
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
    """drag 模式入口：在拖入的目录下识别单位 → preview → confirm → apply →
    可选移动 zip。

    与批量模式共用 _find_units：拖入的目录本身可能是 FLAT/NESTED 单位
    （单本/分话漫画），也可能是包含多本的容器，统一处理。
    """
    from mt.presentation.view import print_pack_preview   # 延迟导入避免循环
    emit(f'\n{SEP}')
    emit(f'📂 目录: {src_dir}')
    units = _find_units(src_dir)
    if not units:
        emit('  未识别出任何打包单位')
        return
    plans = [plan_unit(str(d), k) for d, k in units]
    print_pack_preview(plans)
    if not any(p.writable for p in plans):
        return
    if not confirm('\n🟡 确认打包并删除源目录？按 Enter 继续: '):
        return
    fail = apply_pack_plans(plans, dry_run=False)
    if fail == 0 and target:
        for p in plans:
            if p.writable:
                move_zip(Path(p.zip_path), target)
    elif fail > 0:
        warn(f'{fail} 个单位处理失败，zip 未移动，请修复后重试。')
