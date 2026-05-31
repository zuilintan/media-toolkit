"""meta-kit 工作流层：:class:`~module.manga.core.models.MangaInfo`
→ ComicInfo v2.1 XML → 写入 CBZ。

``<Number>`` 字段规则（与 ``CH.`` 同级且互斥）:

- ``chapter`` 不为 ``None`` → 数字格式（如 ``01-05+番外篇``）
- ``chapter`` 为 ``None``，``part_tag`` 是附录 / 结构类 → 分编词原文（``番外篇`` / ``后日谈`` / ``上篇`` …）
- 否则 → ``''``（留空，不显式指定）

``<Format>`` 字段: ``part_tag`` 是合集类（``总集篇`` 等）时写入；否则空。
"""

from __future__ import annotations
import os
import re
import time
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring, fromstring
from xml.dom import minidom

from module.manga.core.models import MangaInfo, MetaKitPlan, fmt_num
from module.manga.core import patterns as P
from module.manga.core.config import (
    SCRIPT_NAME, SCRIPT_VERSION, COMICINFO_FILENAME, PAGE_EXTS, COMICINFO_TAGS,
)
from module.manga.naming.parser import parse_name
from base.console import (
    print_op_result, error, debug, info, warn, emit, )
from module.manga.infra.parallel import run_plans

# ── 特殊字符（ComicInfo 文件名格式中使用）──────────────────────────────────────
WAVE        = '\uff5e'   # ～  全角波浪线（话标题定界符）
BAR         = '\u00a6'   # ¦   间断竖线  （译名定界符）
MIDDLE_DOT  = '\u30fb'   # ・  片假名中点（标题内空格替代符）
FCOLON      = '\uff1a'   # ：  全角冒号  （社团文件分隔符）


# ═══════════════════════════════════════════════════════════════════════════════
# 作者提取（从 CBZ 文件名中）
# ═══════════════════════════════════════════════════════════════════════════════

def extract_author(filename: str) -> str:
    """从 CBZ 文件名第一个 ``[xxx]`` 括号提取作者名。"""
    m = re.match(r'^\[(.+?)\]', Path(filename).stem)
    return m.group(1).strip() if m else ''


# ═══════════════════════════════════════════════════════════════════════════════
# ComicInfo 字段构建
# ═══════════════════════════════════════════════════════════════════════════════

def _undot(s: str | None) -> str | None:
    """``・`` → 空格；``None`` 透传。"""
    return s.replace(MIDDLE_DOT, ' ') if s else s


def build_title(info: MangaInfo) -> str:
    """``<Title>``：移除 ``[...]`` / ``(...)`` 块，保留其余内容。"""
    s = info.original
    s = re.sub(r'\[.+?\]', '', s)
    s = re.sub(r'\(.+?\)', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def build_number(info: MangaInfo) -> str:
    """``<Number>``：话号或独立分编词（附录 / 结构类），与 ``CH.`` 同级且互斥。

    合集类（``总集篇`` 等）走 :func:`build_format`。
    """
    if info.chapter is not None:
        return info.chapter.number_str()
    if info.part_tag and info.part_tag not in P.COMPILATION_PARTS:
        # 番外篇 / 后日谈 / 上篇 / 中篇 / 下篇 均在此
        return info.part_tag
    return ''


def build_format(info: MangaInfo) -> str:
    """``<Format>``：合集类分编词（``总集篇`` 等）的归宿；否则空。"""
    return info.part_tag if info.part_tag in P.COMPILATION_PARTS else ''


def build_volume(info: MangaInfo) -> str:
    """``<Volume>``：两位补零卷号字符串，无卷时为空。"""
    if info.volume is None:
        return ''
    return fmt_num(info.volume.start)


def build_genre(info: MangaInfo) -> str:
    """``<Genre>``：内容标签（``uncensored`` / ``colorized`` / ``ongoing``），逗号分隔。"""
    parts = []
    if info.is_uncensored: parts.append('uncensored')
    if info.is_colorized:  parts.append('colorized')
    if info.is_ongoing:    parts.append('ongoing')
    return ', '.join(parts)


def collect_fields(
    info: MangaInfo,
    publisher: str | None = None,
    existing_tags: str = '',
    page_count: int = 0,
) -> dict[str, str]:
    """按 :data:`~module.manga.core.config.COMICINFO_TAGS` 顺序返回 ``{tag: value}``。"""
    return {
        'Publisher':   publisher or '',
        'Writer':      _undot(info.author) or '',
        'Title':       build_title(info),
        'Volume':      build_volume(info),
        'Number':      build_number(info),
        'Series':      _undot(info.series) or '',
        'Format':      build_format(info),
        'LanguageISO': info.language or '',
        'Genre':       build_genre(info),
        'PageCount':   str(page_count) if page_count else '',
        'Tags':        existing_tags or '',
        'Notes':       f'"metadata creator": "{SCRIPT_NAME} {SCRIPT_VERSION}"',
    }


#: ``"metadata creator"`` Notes 形态，识别仅本工具自动产出的版本号差异
_METADATA_CREATOR_RE = re.compile(
    rf'^"metadata creator":\s*"{re.escape(SCRIPT_NAME)}\s+\S+"$'
)


def _only_creator_version_differs(
    existing: dict[str, str], new: dict[str, str],
) -> bool:
    """旧 / 新字段除 ``Notes`` 外完全相同，且双方 ``Notes`` 都是 metadata creator 形态。

    用于避免本工具版本升级导致仅 ``Notes`` 中 :data:`~module.manga.core.config.SCRIPT_VERSION`
    变动的无意义改写。
    """
    for tag in COMICINFO_TAGS:
        if tag == 'Notes':
            continue
        if existing.get(tag, '') != new.get(tag, ''):
            return False
    en, nn = existing.get('Notes', ''), new.get('Notes', '')
    if en == nn:
        return False
    return bool(_METADATA_CREATOR_RE.match(en) and _METADATA_CREATOR_RE.match(nn))


# ═══════════════════════════════════════════════════════════════════════════════
# XML 生成
# ═══════════════════════════════════════════════════════════════════════════════

def _serialize_xml(fields: dict[str, str]) -> bytes:
    """按 :data:`~module.manga.core.config.COMICINFO_TAGS` 顺序序列化为 ComicInfo v2.1 UTF-8 XML。"""
    root = Element('ComicInfo')
    root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    root.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')
    for tag in COMICINFO_TAGS:
        SubElement(root, tag).text = fields[tag]
    raw    = tostring(root, encoding='unicode')
    pretty = minidom.parseString(raw).toprettyxml(indent='  ', encoding='utf-8')
    return pretty


def build_comicinfo_xml(
    info: MangaInfo,
    publisher: str | None = None,
    existing_tags: str = '',
    page_count: int = 0,
) -> bytes:
    """生成 ComicInfo v2.1 XML，返回 UTF-8 ``bytes``。"""
    return _serialize_xml(collect_fields(info, publisher, existing_tags, page_count))


# ═══════════════════════════════════════════════════════════════════════════════
# Publisher 查找
# ═══════════════════════════════════════════════════════════════════════════════

_PUBLISHER_RE = re.compile(
    rf'^[\[［]社团[\]］][{FCOLON}:]\s*(?P<name>.+)\.txt$',
    re.IGNORECASE,
)


def _extract_publisher_name(filename: str) -> str | None:
    m = _PUBLISHER_RE.match(os.path.basename(filename))
    return m.group('name').strip() if m else None


def find_publisher(cbz_path: str) -> tuple[str | None, list[str] | None]:
    """在 CBZ 所在目录搜索 ``[社团]：XX.txt``。

    :return:

        - ``(name, None)``     — 找到唯一社团文件
        - ``(None, None)``     — 未找到
        - ``(None, [paths…])`` — 多文件冲突
    """
    hits: list[tuple[str, str]] = []
    for f in Path(cbz_path).parent.iterdir():
        if not f.is_file():
            continue
        name = _extract_publisher_name(f.name)
        if name:
            hits.append((name, str(f)))
    if len(hits) == 0: return None, None
    if len(hits) == 1: return hits[0][0], None
    return None, [h[1] for h in hits]


# ═══════════════════════════════════════════════════════════════════════════════
# CBZ 元信息（单次打开：页数 + 现有 Tags + 现有 ComicInfo.xml 原始 bytes）
# ═══════════════════════════════════════════════════════════════════════════════

def read_cbz_meta(cbz_path: str) -> tuple[int, str, bytes | None]:
    """单次打开 CBZ，返回 ``(图片页数, 现有 Tags, 现有 ComicInfo.xml 原始 bytes)``。

    - 页数: 按 :data:`~module.manga.core.config.PAGE_EXTS` 过滤，目录条目与
      ``ComicInfo.xml`` 不计入。
    - Tags: 读取根级 ``ComicInfo.xml`` 的 ``<Tags>``（外部程序维护，本工具只读不改）。
      内嵌 XML 损坏时只丢 Tags，不影响页数。
    - bytes: 根级 ``ComicInfo.xml`` 原始字节，供 plan 阶段 diff 判定。
      无内嵌或整包损坏时为 ``None``。
    - 整包打不开时按 ``(0, '', None)`` 处理并记 DEBUG。
    """
    comicinfo_lc = COMICINFO_FILENAME.lower()
    page_count   = 0
    tags         = ''
    existing     : bytes | None = None
    try:
        with zipfile.ZipFile(cbz_path, 'r') as zf:
            root_comicinfo: str | None = None   # 根级 ComicInfo.xml 原始名
            for zi in zf.infolist():
                name = zi.filename
                if name.endswith('/'):
                    continue
                if name.lower() == comicinfo_lc:
                    root_comicinfo = name
                base = os.path.basename(name)
                if base.lower() == comicinfo_lc:
                    continue
                ext = os.path.splitext(base)[1].lower()
                if ext in PAGE_EXTS:
                    page_count += 1
            if root_comicinfo is not None:
                try:
                    existing = zf.read(root_comicinfo)
                    root     = fromstring(existing)
                    el       = root.find('Tags')
                    tags     = (el.text or '').strip() if el is not None else ''
                except Exception as e:
                    debug(f'解析内嵌 ComicInfo.xml 失败（按无 Tags 处理）: {cbz_path} — {e}')
    except Exception as e:
        debug(f'read_cbz_meta 失败（按 0 页 / 无 Tags 处理）: {cbz_path} — {e}')
        return 0, '', None
    return page_count, tags, existing


# ═══════════════════════════════════════════════════════════════════════════════
# ZIP/CBZ 写入
# ═══════════════════════════════════════════════════════════════════════════════

def _comicinfo_zinfo(inherited_attr: int) -> zipfile.ZipInfo:
    """构建 ``ComicInfo.xml`` 的 ``ZipInfo``：``ZIP_STORED`` + 当前时间 + 继承属性。"""
    t = time.localtime()
    zi = zipfile.ZipInfo(
        COMICINFO_FILENAME,
        date_time=(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec),
    )
    zi.compress_type  = zipfile.ZIP_STORED
    zi.external_attr  = inherited_attr
    return zi


def _inherit_attr(infos: list[zipfile.ZipInfo]) -> int:
    for ifo in infos:
        if ifo.external_attr:
            return ifo.external_attr
    return 0x20  # DOS Archive 默认


def write_comicinfo(cbz_path: str, xml_bytes: bytes) -> bool:
    """以追加模式写入 ``ComicInfo.xml``（不重建整个压缩包）。

    替换旧条目时只从内存目录中摘除，旧本地数据成为死空间（< 1 KB，可忽略）。

    :return: ``True`` 表示替换了旧版，``False`` 表示首次写入。
    """
    with zipfile.ZipFile(cbz_path, 'a') as zf:
        attr = _inherit_attr(
            [i for i in zf.infolist()
             if i.filename.lower() != COMICINFO_FILENAME.lower()]
        )
        replaced = False
        for key in list(zf.NameToInfo.keys()):
            if key.lower() == COMICINFO_FILENAME.lower():
                zf.filelist.remove(zf.NameToInfo.pop(key))
                replaced = True
                break
        zf.writestr(_comicinfo_zinfo(attr), xml_bytes)
        zf.NameToInfo[COMICINFO_FILENAME].flag_bits |= 0x800
    return replaced


# ═══════════════════════════════════════════════════════════════════════════════
# 单文件 plan / apply（纯函数；批量入口见下）
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_existing_fields(xml_bytes: bytes | None) -> dict[str, str]:
    """从现有 ``ComicInfo.xml`` 提取 ``{tag: value}``；缺失或解析失败按空串。

    返回值始终包含 :data:`~module.manga.core.config.COMICINFO_TAGS` 全部 key，
    便于 diff 表格直接对位渲染。
    """
    out: dict[str, str] = {tag: '' for tag in COMICINFO_TAGS}
    if not xml_bytes:
        return out
    try:
        root = fromstring(xml_bytes)
        for tag in COMICINFO_TAGS:
            el = root.find(tag)
            if el is not None and el.text:
                out[tag] = el.text.strip()
    except Exception as e:
        debug(f'_parse_existing_fields 失败（按全空处理）: {e}')
    return out


def preview_plan(cbz_path: str) -> MetaKitPlan | None:
    """构建单个 CBZ 的 ComicInfo 写入计划（纯函数，无输出副作用）。

    :return: ``None`` 表示文件名无法提取作者（跳过）；否则返回
        :class:`~module.manga.core.models.MetaKitPlan`，由
        :attr:`~module.manga.core.models.MetaKitPlan.writable` /
        :attr:`~module.manga.core.models.MetaKitPlan.changed` 标识是否可写 / 需写。
    """
    filename = os.path.basename(cbz_path)
    author   = extract_author(filename)
    if not author:
        return None

    mi                          = parse_name(author, Path(filename).stem)
    publisher, pub_conflict     = find_publisher(cbz_path)
    page_count, tags_val, existing_xml = read_cbz_meta(cbz_path)
    fields                      = collect_fields(mi, publisher, tags_val, page_count)
    existing_fields             = _parse_existing_fields(existing_xml)

    # 仅 Notes 中 SCRIPT_VERSION 变动时保留旧 Notes，使 new_xml == existing_xml
    # → plan.changed 为 False，整批写入幂等跳过此文件
    if existing_xml is not None and _only_creator_version_differs(existing_fields, fields):
        fields['Notes'] = existing_fields['Notes']

    new_xml = _serialize_xml(fields)
    return MetaKitPlan(
        cbz_path        = cbz_path,
        mi              = mi,
        publisher       = publisher,
        pub_conflict    = pub_conflict,
        page_count      = page_count,
        tags_val        = tags_val,
        fields          = fields,
        existing_fields = existing_fields,
        existing_xml    = existing_xml,
        new_xml         = new_xml,
    )


def apply_plan(plan: MetaKitPlan) -> str:
    """执行单个 CBZ 的写入（:attr:`~module.manga.core.models.MetaKitPlan.new_xml` 已在 plan 阶段构建）。

    :return: ``'ok'`` / ``'error'``。不可写 / 无变化由调用方过滤，此处不再判定。
    """
    filename = os.path.basename(plan.cbz_path)
    try:
        write_comicinfo(plan.cbz_path, plan.new_xml)
        emit(f'   ✅ {filename} — 已处理')
        return 'ok'
    except Exception as e:
        error(f'{filename} — {e}')
        return 'error'


# ═══════════════════════════════════════════════════════════════════════════════
# 批量 plan / apply（对齐 rename_kit.preview_plan / apply_plan）
# ═══════════════════════════════════════════════════════════════════════════════

def _progress_line(idx: int, total: int, plan: MetaKitPlan | None) -> str:
    if plan is None:
        return f'   ! [{idx}/{total}] (无作者，已跳过)'
    icon = ('*' if plan.writable and plan.changed
            else '-' if plan.writable
            else '!')
    return f'   {icon} [{idx}/{total}] {plan.filename}'


def preview_plans(
    root: str, jobs: int = 1, on_progress=None, cancel_token=None,
) -> list[MetaKitPlan]:
    """递归扫描 ``root`` 下所有 ``.cbz``，返回 plan 列表。

    无作者的文件（:func:`preview_plan` 返回 ``None``）静默丢弃。

    :param jobs: 1=串行；>1=并行进程数；0=自动 ``min(cpu, 4)``。≥ 4 个文件才启用并行。
    :param on_progress: 每完成一项即回调 ``f(done, total)``。
    :param cancel_token: ``threading.Event``，已 set 时提前退出。
    """
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []
    files = [str(fp) for fp in sorted(root_path.rglob('*.cbz'))]
    emit(f'  找到文件: {len(files)} 个 .cbz（含子目录）')
    raw = run_plans(
        files, preview_plan, jobs=jobs, progress_line=_progress_line,
        on_progress=on_progress, cancel_token=cancel_token,
    )
    return [p for p in raw if p is not None]


def apply_plans(
    plans: list[MetaKitPlan], dry_run: bool = True, cancel_token=None,
) -> int:
    """整批写入 ``ComicInfo.xml``。

    :param plans:   预览阶段产出的 plan 列表（含 writable / 不可写两类）。
    :param dry_run: ``True`` 时仅预览提示，不实际写入。
    :param cancel_token: ``threading.Event``，已 set 时提前退出。
    :return: 失败数量（``dry_run`` 时为 0）。
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
            warn(f'跳过（出版商冲突）: {os.path.basename(plan.cbz_path)}')
            skip += 1
            continue
        if not plan.changed:
            skip += 1   # ComicInfo.xml 已存在且与目标完全一致：幂等跳过
            continue
        result = apply_plan(plan)
        if result == 'ok':
            ok_n += 1
        else:
            fail += 1

    print_op_result(ok_n, fail, skip)
    return fail


