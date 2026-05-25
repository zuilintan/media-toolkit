"""
comicinfo.py — ComicInfo.xml 生成、读取与写入

将 MangaInfo 转换为 ComicInfo v2.1 XML 并写入 CBZ/ZIP 文件。

Number 字段规则（与 CH. 同级且互斥）:
  - chapter 不为 None  → 数字格式，如 "01-05+番外篇"
  - chapter 为 None，part_tag 是附录/结构类 → 分编词原文，如 "番外篇"/"后日谈"/"上篇"
  - 否则              → ''（留空，不显式指定）

Format 字段：part_tag 是合集类（总集篇等）时写入；否则空。

依赖: models / patterns / config / parser / console / presentation
"""

from __future__ import annotations
import os
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring, fromstring
from xml.dom import minidom

from mt.core.models import MangaInfo, fmt_num
from mt.core import patterns as P
from mt.core.config import (
    SCRIPT_NAME, SCRIPT_VERSION, COMICINFO_FILENAME, PAGE_EXTS, COMICINFO_TAGS,
)
from mt.infra.console import SEP, SEP2, error, debug, emit
from mt.presentation.view import print_comicinfo_fields

# ── 特殊字符（ComicInfo 文件名格式中使用）──────────────────────────────────────
WAVE        = '\uff5e'   # ～  全角波浪线（话标题定界符）
BAR         = '\u00a6'   # ¦   间断竖线  （译名定界符）
MIDDLE_DOT  = '\u30fb'   # ・  片假名中点（标题内空格替代符）
FCOLON      = '\uff1a'   # ：  全角冒号  （社团文件分隔符）


# ═══════════════════════════════════════════════════════════════════════════════
# 作者提取（从 CBZ 文件名中）
# ═══════════════════════════════════════════════════════════════════════════════

def extract_author(filename: str) -> str:
    """从 CBZ 文件名中提取作者名（第一个 [xxx] 括号）。"""
    m = re.match(r'^\[(.+?)\]', Path(filename).stem)
    return m.group(1).strip() if m else ''


# ═══════════════════════════════════════════════════════════════════════════════
# ComicInfo 字段构建
# ═══════════════════════════════════════════════════════════════════════════════

def _undot(s: str | None) -> str | None:
    """・ → 空格；None 透传。"""
    return s.replace(MIDDLE_DOT, ' ') if s else s


def build_title(info: MangaInfo) -> str:
    """<Title>：移除 [...] 和 (...) 块，保留其余所有内容。"""
    s = info.original
    s = re.sub(r'\[.+?\]', '', s)
    s = re.sub(r'\(.+?\)', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def build_number(info: MangaInfo) -> str:
    """<Number>：话号或独立分编词（附录/结构类），与 CH. 同级且互斥。

    - chapter 不为 None → 数字格式（不含 'CH.' 前缀），如 "01-05+番外篇"
    - chapter 为 None，part_tag 是附录/结构类 → 分编词原文
    - 否则 → ''（留空，不显式指定；合集类走 build_format）
    """
    if info.chapter is not None:
        return info.chapter.number_str()
    if info.part_tag and info.part_tag not in P.COMPILATION_PARTS:
        # 番外篇 / 后日谈 / 上篇 / 中篇 / 下篇 均在此
        return info.part_tag
    return ''


def build_format(info: MangaInfo) -> str:
    """<Format>：合集类分编词（总集篇等）的归宿；否则空。"""
    return info.part_tag if info.part_tag in P.COMPILATION_PARTS else ''


def build_volume(info: MangaInfo) -> str:
    """<Volume>：两位补零卷号字符串，无卷时为空。"""
    if info.volume is None:
        return ''
    return fmt_num(info.volume.start)


def build_genre(info: MangaInfo) -> str:
    """<Genre>：内容标签（uncensored / colorized / ongoing），逗号分隔。"""
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
    """按 COMICINFO_TAGS 顺序返回 {tag: value_str}。"""
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


# ═══════════════════════════════════════════════════════════════════════════════
# XML 生成
# ═══════════════════════════════════════════════════════════════════════════════

def build_comicinfo_xml(
    info: MangaInfo,
    publisher: str | None = None,
    existing_tags: str = '',
    page_count: int = 0,
) -> bytes:
    """生成 ComicInfo v2.1 XML，返回 UTF-8 bytes。"""
    root = Element('ComicInfo')
    root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    root.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')
    fields = collect_fields(info, publisher, existing_tags, page_count)
    for tag in COMICINFO_TAGS:
        SubElement(root, tag).text = fields[tag]
    raw    = tostring(root, encoding='unicode')
    pretty = minidom.parseString(raw).toprettyxml(indent='  ', encoding='utf-8')
    return pretty


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
    """在 cbz 所在目录中搜索 [社团]：XX.txt。

    Returns:
        (name, None)        — 找到唯一社团文件
        (None, None)        — 未找到
        (None, [paths…])    — 多文件冲突
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
# CBZ 元信息（单次打开：页数 + 现有 Tags）
# ═══════════════════════════════════════════════════════════════════════════════

def read_cbz_meta(cbz_path: str) -> tuple[int, str]:
    """单次打开 CBZ，返回 (图片页数, 现有 Tags)。

    - 页数：按 PAGE_EXTS 过滤，目录条目与 ComicInfo.xml 不计入。
    - Tags：读取根级 ComicInfo.xml 的 <Tags>（外部程序维护，本工具只读不改）；
            无则空串。内嵌 XML 损坏时只丢 Tags，不影响页数。
    - 整包打不开时按 (0, '') 处理并记 debug。
    """
    comicinfo_lc = COMICINFO_FILENAME.lower()
    page_count   = 0
    tags         = ''
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
                    root = fromstring(zf.read(root_comicinfo))
                    el   = root.find('Tags')
                    tags = (el.text or '').strip() if el is not None else ''
                except Exception as e:
                    debug(f'解析内嵌 ComicInfo.xml 失败（按无 Tags 处理）: {cbz_path} — {e}')
    except Exception as e:
        debug(f'read_cbz_meta 失败（按 0 页 / 无 Tags 处理）: {cbz_path} — {e}')
        return 0, ''
    return page_count, tags


# ═══════════════════════════════════════════════════════════════════════════════
# ZIP/CBZ 写入
# ═══════════════════════════════════════════════════════════════════════════════

def _comicinfo_zinfo(inherited_attr: int) -> zipfile.ZipInfo:
    """构建 ComicInfo.xml 的 ZipInfo：ZIP_STORED + 当前时间 + 继承属性。"""
    t = time.localtime()
    zi = zipfile.ZipInfo(
        COMICINFO_FILENAME,
        date_time=(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec),
    )
    zi.compress_type  = zipfile.ZIP_STORED
    zi.external_attr  = inherited_attr
    return zi


def _inherit_attr(infos: list[zipfile.ZipInfo]) -> int:
    for info in infos:
        if info.external_attr:
            return info.external_attr
    return 0x20  # DOS Archive 默认


def write_comicinfo(cbz_path: str, xml_bytes: bytes) -> bool:
    """写入 ComicInfo.xml（追加模式，不重建整个压缩包）。

    替换旧条目时只从内存目录中摘除，旧本地数据成为死空间（< 1 KB，可忽略）。

    Returns:
        True 表示替换了旧版，False 表示首次写入。
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
    return replaced


# ═══════════════════════════════════════════════════════════════════════════════
# 单文件处理（两阶段：plan → apply，与 rename 的 plan_renames / apply_rename_plans 对称）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CbzPlan:
    """单个 CBZ 的 ComicInfo 写入计划（解析阶段产出，写入阶段消费）。"""
    cbz_path:     str
    mi:           MangaInfo
    publisher:    str | None
    pub_conflict: list[str] | None
    page_count:   int
    tags_val:     str
    fields:       dict[str, str]

    @property
    def writable(self) -> bool:
        """是否可写入：无出版商冲突即可。"""
        return not self.pub_conflict


def plan_cbz(cbz_path: str) -> tuple[CbzPlan | None, str]:
    """构建单个 CBZ 的写入计划，并在解析前先输出卡片 banner。

    banner（SEP + 📦 文件名）有意提前到 parse_name 之前输出，
    使 ``--debug`` 模式下 ``parse_name`` 的 DEBUG 行落在当前卡片内，
    而不是漏到上一张卡片的 SEP 之外。

    Returns:
        (plan, status):
            status='skip' (无作者)        → plan=None（不输出 banner）
            status='warn' (出版商冲突)    → plan 返回（用于显示，但不可写）
            status='ok'                    → plan 可写
    """
    from mt.naming.parser import parse_name, emit_parse_debug  # 在此导入，避免顶层循环

    filename = os.path.basename(cbz_path)
    author   = extract_author(filename)
    if not author:
        return None, 'skip'

    # banner 提前到 parse_name 之前 → DEBUG 输出在卡片内
    emit(f'\n{SEP}')
    emit(f'  📦  {filename}')

    mi                      = parse_name(author, Path(filename).stem)
    emit_parse_debug(mi)
    publisher, pub_conflict = find_publisher(cbz_path)
    page_count, tags_val    = read_cbz_meta(cbz_path)
    fields                  = collect_fields(mi, publisher, tags_val, page_count)
    plan = CbzPlan(cbz_path, mi, publisher, pub_conflict, page_count, tags_val, fields)
    return plan, ('warn' if pub_conflict else 'ok')


def print_cbz_plan(plan: CbzPlan) -> None:
    """打印单个 CBZ 计划的字段、警告与冲突提示（banner 已由 plan_cbz 输出）。"""
    emit()
    print_comicinfo_fields(plan.fields, plan.pub_conflict)
    for w in plan.mi.warnings:
        emit(f'     🟡 {w}')
    if plan.pub_conflict:
        emit(f'\n  ⛔  出版商冲突，跳过本文件，请先解决上述异常。')


def apply_cbz_plan(plan: CbzPlan) -> str:
    """执行单个 CBZ 的 ComicInfo.xml 写入。

    Returns:
        ``'ok'`` / ``'error'``（不可写计划由调用方过滤，此处不再判定）
    """
    filename = os.path.basename(plan.cbz_path)
    try:
        xml_bytes = build_comicinfo_xml(
            plan.mi, plan.publisher, plan.tags_val, plan.page_count,
        )
        replaced  = write_comicinfo(plan.cbz_path, xml_bytes)
        emit(f'   ✅ {filename} — ComicInfo.xml {"已更新" if replaced else "已写入"}')
        return 'ok'
    except Exception as e:
        error(f'{filename} — {e}')
        return 'error'
