"""
parser.py — 文件名解析

核心入口: parse_name(author, name) → MangaInfo

依赖: models / patterns / utils / console
"""

from __future__ import annotations
import re
from collections.abc import Callable
from typing import TypeVar

from mt.core.models import Chapter, Volume, MangaInfo
from mt.core import patterns as P
from mt.infra.utils import (
    norm_punct, trad_to_simp,
    extract_flag, to_circle, conv_roman_suffix,
    similar,
)
from mt.infra.console import debug, CYAN, RESET


# ═══════════════════════════════════════════════════════════════════════════════
# 通用模式匹配
# ═══════════════════════════════════════════════════════════════════════════════

_T = TypeVar('_T')


def _match_first(
    pattern_list: list[tuple[re.Pattern, Callable[..., _T]]],
    text: str,
    whitelist_check: bool = False,
) -> _T | None:
    """遍历规则表，返回第一个匹配结果，支持白名单过滤。"""
    for pat, extractor in pattern_list:
        m = pat.search(text)
        if not m:
            continue
        if whitelist_check and not _is_unambiguous(m) and _is_whitelisted(text, m):
            continue
        return extractor(m)
    return None


def _is_unambiguous(m: re.Match) -> bool:
    tok = m.group(0)
    return bool(P.UNAMBIGUOUS_RE.search(tok) or P.BONUS_WORD_RE.search(tok))


def _is_whitelisted(text: str, m: re.Match) -> bool:
    return bool(P.WHITELIST_RE.search(text[: m.end()]))


# ═══════════════════════════════════════════════════════════════════════════════
# 话/卷检测
# ═══════════════════════════════════════════════════════════════════════════════

def _preclean(text: str) -> str:
    """移除出版括号、方括号标签并遮盖话标题块，供检测函数使用。"""
    text = P.PUBLICATION_PAREN_RE.sub('', text)
    text = P.BRACKET_TAG_RE.sub('', text)
    return P.SUB_PROTECT_RE.sub('', text)


def detect_chapter(text: str) -> Chapter | None:
    return _match_first(P.CHAPTER_PATTERNS, _preclean(text), whitelist_check=True)


def detect_volume(text: str) -> Volume | None:
    return _match_first(P.VOLUME_PATTERNS, _preclean(text))


# ═══════════════════════════════════════════════════════════════════════════════
# 标签剥除
# ═══════════════════════════════════════════════════════════════════════════════

def _protect_part_plus(text: str) -> str:
    """将分编词汇间的 + 替换为占位符，防止被当作噪音去除。"""
    prev = None
    while prev != text:
        prev  = text
        text  = P.PART_PAIR_RE.sub(rf'\1{P.PART_PAIR_PH}\2', text)
    return text


def _restore_part_plus(text: str) -> str:
    text = re.sub(r'(?<!\d)\s*\+\s*(?!\d)', ' ', text)
    return text.replace(P.PART_PAIR_PH, '+')


def _chapter_replace_cb(m: re.Match, cached: str) -> str:
    if not _is_unambiguous(m) and _is_whitelisted(cached, m):
        return m.group(0)
    # 返回空格而非空串，避免「主标题名6過去編」剥离话号后粘连
    return ' '


def strip_tags(text: str) -> str:
    """去除噪音标签、卷/话数表达式及多余符号，保留干净标题。

    话标题 ～xxx～ 在此过程中保留，最终由 extract_subtitle() 提取。
    """
    # 1. 去除杂志来源括号
    text = P.PUBLICATION_PAREN_RE.sub('', text)

    # 2. 剥除噪音标签 + 版本标记，再兜底去除所有方括号标签
    text = P.NOISE_TAG_RE.sub('', text)
    text = P.VERSION_RE.sub('', text)
    text = P.BRACKET_TAG_RE.sub('', text).rstrip()

    # 3. 去除系列名括号（依赖 norm_punct 已将全角括号转半角）
    text = re.sub(r'(?:^|(?<=\s))\([^)]*\)', '', text)

    # 4. 处理番外关键词
    text = P.BONUS_RANGE_RE.sub('', text)
    text = re.sub(r'\s+(?:おまけ|特典|番外)[編篇]?(?=\s|$|～|\[)', '', text,
                  flags=re.IGNORECASE)

    # 5. 保护分编词汇组合中的 + 号
    text = _protect_part_plus(text)
    text = _restore_part_plus(text)

    # 6. 剥除卷数表达式
    for pat, _ in P.VOLUME_PATTERNS:
        text = pat.sub('', text)

    # 7. 剥除话数表达式（保护已存在的 ～...～ 内容）
    _store: dict[str, str] = {}

    def _stash(m: re.Match) -> str:
        key = f'\ufffe{len(_store)}\ufffe'
        _store[key] = m.group(1)
        return f'～{key}～'

    text = P.SUB_PROTECT_RE.sub(_stash, text)
    for pat, _ in P.CHAPTER_PATTERNS:
        cached = text
        text = pat.sub(lambda m, s=cached: _chapter_replace_cb(m, s), text)
    for key, val in _store.items():
        text = text.replace(key, val)

    return re.sub(r'\s+', ' ', text).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 话标题提取
# ═══════════════════════════════════════════════════════════════════════════════

def extract_subtitle(title: str) -> tuple[str, str]:
    """从标题中分离话标题，返回 (主标题, 话标题)。

    话标题不含外围定界符。合集词（如总集篇）直接归入 part_tag，不视为话标题。

    优先级:
      1. ～xxx～ / ―xxx― / —xxx—
      2. 「xxx」（可带后缀词）
      3. 【前編/後編…】
      4. 末尾分编词汇循环剥离
      5. 兜底：末尾含「編/篇」的词汇
    """
    # 1. 波浪线（其它定界符已由 normalize_subtitle_delimiters 预规范化）
    m = P.SUBTITLE_RE.search(title)
    if m:
        sub = m.group(1)
        if P.is_compilation(sub):
            return title[:m.start()].strip(), P.normalize_part(sub)
        return title[:m.start()].strip(), sub.strip()

    # 2. 「」+ 后缀词
    m = P.KAGI_PART_RE.search(title)
    if m:
        suffix   = P.normalize_part(conv_roman_suffix(m.group(2)))
        combined = f"{m.group(1)}・{suffix}"
        if P.is_compilation(combined):
            return title[:m.start()].strip(), P.normalize_part(combined)
        return title[:m.start()].strip(), combined

    # 3. 「」单独
    m = P.KAGI_SUB_RE.search(title)
    if m:
        sub = m.group(1).strip()
        if P.is_compilation(sub):
            return title[:m.start()].strip(), P.normalize_part(sub)
        return title[:m.start()].strip(), sub

    # 4. 【部分词汇】
    m = P.KAKKO_PART_RE.search(title)
    if m:
        part = P.normalize_part(m.group(1).strip())
        return title[:m.start()].strip(), part

    # 5. 末尾分编词汇循环剥离（合集类排前，其它排后）
    compilation_parts: list[str] = []
    chapter_parts:     list[str] = []
    working = title
    while True:
        found = False
        for pat in (P.PART_COMPOUND_RE, P.PART_SUFFIX_RE):
            m = pat.search(working)
            if m and m.start() > 0:
                part = P.normalize_part(m.group(1).strip())
                if P.is_compilation(part):
                    compilation_parts.insert(0, part)
                else:
                    chapter_parts.insert(0, part)
                working = working[:m.start()].strip()
                found   = True
                break
        if not found:
            break
    if compilation_parts or chapter_parts:
        ch = '・'.join(compilation_parts + chapter_parts)
        return working.strip(), ch

    # 6. 兜底：末尾任意「XX編/篇」，可带罗马数字尾缀
    m = re.search(
        r'\s+(\S+[编編篇](?:I{1,3}|IV|VI{0,3}|IX|XI{0,3}|XII)?)\s*$', working
    )
    if m and m.start() > 0:
        raw = m.group(1).strip()
        return working[:m.start()].strip(), conv_roman_suffix(P.normalize_part(raw))

    return title, ''


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助提取函数
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_series(bare: str) -> tuple[str, str]:
    bare_clean = P.BRACKET_TAG_RE.sub('', bare)
    m = P.SERIES_PAREN_RE.search(bare_clean)
    if not m:
        return bare, ''
    series  = m.group(1).strip()
    escaped = re.escape(series)
    bare    = re.sub(rf'\(\s*{escaped}\s*\)', '', bare)
    return bare, series


def _extract_translation(bare: str) -> tuple[str, str]:
    """提取 ¦译名¦。译名内只做多空格合并，不做其它形态规范化。

    译名常不严格遵循原名格式（可能只翻译一部分，或自带「主标题 ～话标题～」
    结构），因此不再把空格转为 ・，也不再识别尾部分编词。
    单侧 ¦ 形态已由 normalize_translation_delim() 在管道阶段补全。
    """
    m = P.TRANS_INLINE_RE.search(bare)
    translation = m.group(1).strip() if m else ''
    # 多空格 → 单空格
    translation = re.sub(r'\s+', ' ', translation)
    bare        = P.TRANS_INLINE_RE.sub('', bare).strip()
    translation = trad_to_simp(translation)
    return bare, translation


def _normalize_chapter_title(s: str) -> str:
    """将话标题中的 本1/本2 转为带圈数字 本①/本②。"""
    return re.sub(r'本(\d{1,2})', lambda m: '本' + to_circle(int(m.group(1))), s)


# ═══════════════════════════════════════════════════════════════════════════════
# 特殊标志提取
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_special_flags(stem: str) -> tuple[str, str, str, bool, bool]:
    """提取并剥离独立 tag，返回 (stem, language, pre_part_tag, is_colorized, is_ongoing)。

    pre_part_tag：显式 [总集篇] tag 命中则为 '总集篇'，否则空串；
                  作为 _resolve_part_tag 的最高优先来源（裸词位置启发式保留向后兼容）。
    """
    stem, is_zxx       = extract_flag(stem, P.TEXTLESS_TAG_RE)
    language           = 'zxx' if is_zxx else ''
    stem, is_colorized = extract_flag(stem, P.COLORIZED_TAG_RE)
    stem, is_ongoing   = extract_flag(stem, P.ONGOING_TAG_RE)
    stem, has_compilation = extract_flag(stem, P.COMPILATION_TAG_RE)
    pre_part_tag       = '总集篇' if has_compilation else ''
    return stem, language, pre_part_tag, is_colorized, is_ongoing


def _detect_language_uncensored(bare: str, language: str) -> tuple[str, bool]:
    """检测语言与无修正标志。

    promote_tags 已把所有变体收敛到 [zh]/[ja]/.../[uncensored]，
    故只需在 bare 中扫一次标准形态即可（原始 name 无需重复扫描）。
    """
    if language != 'zxx':
        for lang, pat in P.LANG_TAGS.items():
            if pat.search(bare):
                language = lang
                break
    return language, bool(P.UNCENSORED_RE.search(bare))


def _detect_volume_chapter(bare: str) -> tuple[Volume | None, Chapter | None, bool]:
    """检测卷/话数，返回 (volume, chapter, is_bonus)。

    is_bonus=True 表示话数是纯番外标记（CH.00），应提升为 part_tag 字段。
    """
    bare_pub  = P.PUBLICATION_PAREN_RE.sub('', bare)
    volume    = detect_volume(bare_pub)
    bare_novol = bare_pub
    for pat, _ in P.VOLUME_PATTERNS:
        bare_novol = pat.sub('', bare_novol)
    chapter = detect_chapter(bare_novol)
    is_bonus = (
        chapter is not None
        and chapter.start == 0.0
        and chapter.end is None
        and not chapter.bonus
    )
    if is_bonus:
        chapter = None
    return volume, chapter, is_bonus


# ═══════════════════════════════════════════════════════════════════════════════
# part_tag 字段推导
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_part_tag(
    main_title: str, ch_title: str, is_bonus: bool, pre_part_tag: str = ''
) -> tuple[str, str, str]:
    """从标题部件和番外标志推导 part_tag 字段，返回 (main_title, ch_title, part_tag)。

    优先级: pre_part_tag（显式 [总集篇] tag）> is_bonus > 末尾裸词启发式。
    """
    part_tag = pre_part_tag

    if part_tag:
        pass
    elif is_bonus:
        part_tag = '番外篇'
    else:
        m = P.BONUS_SUFFIX_RE.search(main_title)
        if m:
            main_title = main_title[: m.start()].strip()
            part_tag   = '番外篇'

    if not part_tag:
        for word in sorted(P.STANDALONE_PARTS, key=len, reverse=True):
            if main_title.endswith(' ' + word):
                main_title = main_title[: -len(word) - 1].strip()
                part_tag   = word
                break
        else:
            parts = main_title.rsplit(' ', 1)
            if len(parts) == 2:
                normed = P.normalize_part(parts[1])
                if normed in P.STANDALONE_PARTS:
                    main_title = parts[0].strip()
                    part_tag   = normed

    if not part_tag:
        if ch_title in P.STANDALONE_PARTS:
            part_tag  = ch_title
            ch_title  = ''
        elif '+' in ch_title and all(
            p in P.STANDALONE_PARTS for p in ch_title.split('+')
        ):
            part_tag  = ch_title
            ch_title  = ''
        elif '・' in ch_title:
            parts = ch_title.split('・')
            if all(p in P.STANDALONE_PARTS for p in parts):
                part_tag = ' '.join(parts)
                ch_title = ''

    return main_title, ch_title, part_tag


# ═══════════════════════════════════════════════════════════════════════════════
# 核心解析入口
# ═══════════════════════════════════════════════════════════════════════════════

_BONUS_TITLE_PAT = re.compile(
    r'^\s*(' + r'(?:おまけ|特典|番外)' + r')\s+(\S+)\s+(.+)$'
)


def parse_name(author: str, name: str) -> MangaInfo:
    """将文件夹或文件名解析为结构化的 MangaInfo。

    Args:
        author: 作者目录名（或文件名中的作者标识）。
        name:   待解析的原始名称（不含后缀）。

    Returns:
        填充完毕的 MangaInfo。
    """
    # 0. 预处理管道（详见 patterns.py §5）
    stem = norm_punct(name)
    stem = P.wrap_bare_tags(stem)
    stem = P.promote_tags(stem)
    stem = P.normalize_chapter_tokens(stem)
    stem = P.normalize_translation_delim(stem)
    stem, language, pre_part_tag, is_colorized, is_ongoing = _extract_special_flags(stem)

    # 1. 去除开头噪音前缀 & 匹配作者名的首个方括号标签
    stem = P.LEADING_PREFIX_RE.sub('', stem)
    m = P.AUTHOR_TAG_RE.search(stem)
    if m and similar(m.group(1), author):
        stem = stem[m.end():].strip()

    # 2. 初步去除噪音标签 & 版本标记
    bare = P.NOISE_TAG_RE.sub('', stem).strip()
    bare = P.VERSION_RE.sub('', bare).strip()

    # 3. 提取内嵌译名
    bare, translation = _extract_translation(bare)

    # 4. 检测语言、无修正、卷数、话数
    language, is_uncensored = _detect_language_uncensored(bare, language)
    volume, chapter, is_bonus = _detect_volume_chapter(bare)

    # 5. 提取系列名
    bare = P.PUBLICATION_PAREN_RE.sub('', bare).strip()
    bare, series = _extract_series(bare)

    # 6. 清理干净标题
    clean_title = strip_tags(bare)
    if volume is None:
        m_bonus = _BONUS_TITLE_PAT.match(clean_title)
        if m_bonus and '～' not in clean_title:
            clean_title = (
                f"{m_bonus.group(1)}・{m_bonus.group(2)} ～{m_bonus.group(3)}～"
            )

    # 7. 提取话标题 & part_tag
    clean_title = P.normalize_subtitle_delimiters(clean_title)
    main_title, ch_title = extract_subtitle(clean_title)
    if ch_title:
        ch_title = _normalize_chapter_title(ch_title)
        ch_title = P.normalize_part(ch_title)
    main_title, ch_title, part_tag = _resolve_part_tag(
        main_title, ch_title, is_bonus, pre_part_tag
    )

    return MangaInfo(
        author        = author,
        main_title    = main_title,
        volume        = volume,
        chapter       = chapter,
        chapter_title = ch_title,
        series        = series,
        translation   = translation,
        language      = language,
        is_uncensored = is_uncensored,
        is_colorized  = is_colorized,
        is_ongoing    = is_ongoing,
        part_tag      = part_tag,
        original      = name,
    )


def emit_parse_debug(mi: MangaInfo) -> None:
    """Emit ``parse_name`` 的 DEBUG 摘要行（DEBUG 级别下生效）。

    parse_name 本身只做解析、不输出 DEBUG，由调用方在最合适的时机触发：
      - print_sourcefile_preview / print_metadata_preview：渲染卡片时；
      - examples：每条示例渲染时。

    funcname 锁定为 ``parse_name``，与原先 parse_name 内部 debug() 的输出一致。
    """
    debug(
        f"main='{CYAN}{mi.main_title}{RESET}' "
        f"vol='{CYAN}{mi.volume}{RESET}' "
        f"ch='{CYAN}{mi.chapter}{RESET}' "
        f"ch_title='{CYAN}{mi.chapter_title}{RESET}' "
        f"part_tag='{CYAN}{mi.part_tag}{RESET}' "
        f"series='{CYAN}{mi.series}{RESET}' "
        f"lang='{CYAN}{mi.language}{RESET}'",
        funcname='parse_name',
    )
