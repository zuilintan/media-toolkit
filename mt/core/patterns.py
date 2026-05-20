"""
patterns.py — 正则表达式常量与规则表

所有正则表达式集中在此，避免散落于各模块。
规则表（CHAPTER_PATTERNS / VOLUME_PATTERNS）顺序敏感，具体模式优先于模糊模式。

依赖: models（Chapter / Volume）
"""

from __future__ import annotations
import re
from collections.abc import Callable
from mt.core.models import Chapter, Volume, fmt_num


# ═══════════════════════════════════════════════════════════════════════════════
# 编译辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _pat(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern:
    return re.compile(pattern, flags)


def _pats(*patterns: str) -> list[re.Pattern]:
    return [_pat(p) for p in patterns]


def _bracket(inner: str) -> str:
    """生成匹配半角/全角方括号的片段：[...] 或 [...]。"""
    return rf'[\[［]{inner}[\]］]'


# ═══════════════════════════════════════════════════════════════════════════════
# 原子构件
# ═══════════════════════════════════════════════════════════════════════════════

_BONUS_KW     = r'(?:おまけ|特典|番外)'                # 非捕获，用于剥除/检测
_BONUS_KW_CAP = r'((?:おまけ|特典|番外)[編篇]?)'        # 捕获版，用于提取实际词汇
_NUM          = r'\d+(?:\.\d+)?'                        # 数字（含小数）
_RANGE        = rf'{_NUM}\s*[-~～]\s*{_NUM}'            # 连续范围

# 番外词汇规范化映射（扩展时在此添加即可）
BONUS_NORM: dict[str, str] = {
    'おまけ':   '番外篇',
    'おまけ篇': '番外篇',
    '特典':     '番外篇',
    '特典篇':   '番外篇',
    '番外':     '番外篇',
    '番外篇':   '番外篇',
    '番外編':   '番外篇',
}


def norm_bonus(raw: str) -> str:
    """将原始番外关键词规范化为标准形式；未知词汇原样返回（允许未来扩展）。"""
    return BONUS_NORM.get(raw, raw)

# 中文数字映射（仅限序数话数）
CN_NUM_MAP: dict[str, int] = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '壹': 1, '貳': 2, '贰': 2, '參': 3, '参': 3, '叁': 3,
    '肆': 4, '伍': 5, '陸': 6, '陆': 6, '柒': 7,
    '捌': 8, '玖': 9, '拾': 10, '什': 10,
}

# 分编词汇单元（用于话标题识别）
_PART_UNIT = (
    r'(?:前|後|前|后|上|中|下|総集|总集|完結|完结)[编編篇]'
    r'|後日談|后日谈|After'
)
_PART_COMPOUND = rf'(?:{_PART_UNIT})(?:\+(?:{_PART_UNIT}))*'

# 附录性质词汇（不视为话标题，附加在主标题末尾）
_APPENDIX_RAW: frozenset[str] = frozenset({'总集篇'})

# 与 CH. 同级且互斥的独立附录词（单独出现时提升为 appendix 字段）
STANDALONE_APPENDIX: frozenset[str] = frozenset({
    '上篇', '中篇', '下篇', '番外篇', '后日谈', '总集篇'
})

# 在 VOL. 之前输出的附录词汇
PRE_VOL_APPENDIX: frozenset[str] = frozenset({'总集篇'})

# 直接附在标题末尾的番外标记，如「時番外編」
BONUS_SUFFIX_RE = re.compile(r'(?:おまけ|特典|番外)[編篇]?\s*$')

# 分编词汇规范化映射
SUB_MAP: list[tuple[str, str | Callable]] = [
    (r'前([编編篇])',      '上篇'),
    (r'[後后]([编編篇])',  '下篇'),
    (r'[総总]集[编編篇]',  '总集篇'),
    (r'([上中下])[编編]',  lambda m: m.group(1) + '篇'),
    (r'[後后]日[談谈]',    '后日谈'),
    (r'After',             '后日谈'),
]

def norm_part_subtitle(s: str) -> str:
    """将分编词汇统一为简体规范形式。"""
    for pat, repl in SUB_MAP:
        s = re.sub(pat, repl, s)
    return s

def is_appendix(part: str) -> bool:
    """判断规范化后的词汇是否为附录词汇。"""
    return norm_part_subtitle(part.strip()) in _APPENDIX_RAW


# ═══════════════════════════════════════════════════════════════════════════════
# 标点规范化
# ═══════════════════════════════════════════════════════════════════════════════

PUNCT_MAP = str.maketrans({
    '!': '！', '?': '？', '~': '～', '〜': '～',
    '·': '・', '｜': '¦', '︱': '¦',
})


# ═══════════════════════════════════════════════════════════════════════════════
# 标签检测模式
# ═══════════════════════════════════════════════════════════════════════════════

ZH_PATTERNS = _pats(
    _bracket(r'中[国國]翻[译訳]'),  _bracket(r'中文翻[译訳]'),
    _bracket(r'[^\]]*[汉漢]化[^\]]*'), _bracket(r'[^\]]*[扫掃][圖图][^\]]*'),
    _bracket(r'[^\]]*嵌字[^\]]*'),  _bracket(r'[^\]]*重嵌[^\]]*'),
    _bracket(r'[^\]]*日语社[^\]]*'), _bracket(r'[^\]]*考生[組组][^\]]*'),
    _bracket(r'[风風]的工房'),       _bracket(r'如月工房'),
    _bracket(r'淫书馆'),             _bracket(r'洨五[組组]'),
    _bracket(r'中[国國][语語]'),     _bracket(r'中文'),
    _bracket(r'Chinese'),            _bracket(r'zh'),
    _bracket(r'简中'),  _bracket(r'简体中文'),
    _bracket(r'繁中'),  _bracket(r'繁体中文'),
    _bracket(r'官中'),  _bracket(r'官方中文'),
    _bracket(r'官中无修'),           _bracket(r'AI貓貓翻譯'),
    r'中文版', r'[机機]翻', r'個人翻譯',
)

JA_PATTERNS = _pats(
    _bracket(r'ja'), _bracket(r'Japanese'),
    _bracket(r'日语'), _bracket(r'日文'),
)

KO_PATTERNS = _pats(
    _bracket(r'ko'), _bracket(r'Korean'),
    _bracket(r'韩语'), _bracket(r'韩文'),
)

EN_PATTERNS = _pats(
    _bracket(r'en'), _bracket(r'English'),
    _bracket(r'英语'), _bracket(r'英文'),
)

UNCENSORED_PATTERNS = _pats(
    _bracket(r'[无無]修正?'), _bracket(r'官[方中][无無]修?'),
    _bracket(r'Uncensored'),  _bracket(r'Decensored'),
    _bracket(r'无修'),
    r'\bUncensored\b', r'\bDecensored\b',
)

CENSORED_PATTERNS = _pats(
    _bracket(r'有修正'), _bracket(r'修正あり'), r'\bCensored\b',
)

TEXTLESS_TAG_RE    = _pat(_bracket(r'zxx'))
ONGOING_TAG_RE     = _pat(_bracket(r'ongoing'))
COLORIZED_TAG_PATTERNS = [
    _pat(_bracket(r'colorized')),
    _pat(r'【\s*フルカラー(?:版)?\s*】'),
    _pat(r'【\s*カラー(?:版)?\s*】'),
    _pat(r'【\s*全彩(?:色)?\s*】'),
    _pat(r'【\s*彩色(?:版)?\s*】'),
    _pat(r'[\[［]\s*フルカラー(?:版)?\s*[\]］]'),
    _pat(r'\s*カラー化\s*'),
    _pat(r'\s*フルカラー\s*'),
]

# 纯噪音方括号标签（直接丢弃）
NOISE_TAG_RE = _pat(
    _bracket(
        r'(?:'
        r'Digital|DL[版板]'
        r'|tankoubon|単行本|雑誌'
        r'|COMICIMHO'
        r'|\d{4}-\d{2}-\d{2}'
        r'|\d{2}-\d{2}-\d{2}'
        r'|注[：:][^\]]*'
        r'|restday\d+[^\]]*'
        r'|開坑[^\]]*'
        r'|台[灣湾]老頭[^\]]*'
        r')'
    )
)

# 版本标记（v2 / v1.5 等），在话数提取前清除
VERSION_RE = _pat(r'\s*\bv\d+(?:\.\d+)?\b', flags=0)

# 聚合：需依次剥除的标签列表
STRIP_PATTERNS: list[re.Pattern] = (
    ZH_PATTERNS + UNCENSORED_PATTERNS + CENSORED_PATTERNS
    + [NOISE_TAG_RE, VERSION_RE]
)


# ═══════════════════════════════════════════════════════════════════════════════
# 结构提取模式
# ═══════════════════════════════════════════════════════════════════════════════

AUTHOR_TAG_RE       = _pat(_bracket(r'([^\]］]+)'), 0)   # 第一个 [xxx] → 作者
BRACKET_TAG_RE      = _pat(_bracket(r'[^\]］]*'), 0)      # 所有方括号标签
SERIES_PAREN_RE     = _pat(                               # 系列名 (xxx) / （xxx）
    r'(?:^|(?<=[\s～】」\]）]))[\(（]([^\)）]+)[\)）]', 0)
TRANS_INLINE_RE     = _pat(r'¦([^¦]+)¦', 0)              # 内嵌译名 ¦译名¦
PUBLICATION_PAREN_RE= _pat(                               # 杂志来源括号
    r'[\(（][^\)）]*(?:COMIC|別冊|よろず|雑誌|月号|週刊|Vol\.|C\d{2,})[^\)）]*[\)）]')
LEADING_PREFIX_RE   = _pat(                               # 开头噪音前缀
    r'^\s*(?:[\(（][^\)）]{1,10}[\)）]\s*)+', 0)

# 话标题分隔符（支持单侧波浪线）
SUBTITLE_RE = _pat(
    r'\s*(?:～([^～]+)～?|―([^―]+)―?|—([^—]+)—?|-([^-]*(?:[^\x00-\x7f]|\s)[^-]*)-?)\s*$', 0
)

_PART_COMPOUND_RE = _pat(rf'\s+({_PART_COMPOUND})$', 0)
_KAGI_SUB_RE      = _pat(r'\s*「([^」]+)」\s*$', 0)       # 日语书名号话标题
_KAGI_PART_RE     = _pat(r'\s*「([^」]+)」\s*(\S+)\s*$', 0)
_KAKKO_PART_RE    = _pat(rf'【\s*({_PART_COMPOUND})\s*】', 0)
_PART_SUFFIX_RE   = _pat(rf'\s+(\S*(?:{_PART_UNIT}))\s*$', 0)

# 公开给 parser.py 使用
PART_COMPOUND_RE  = _PART_COMPOUND_RE
KAGI_SUB_RE       = _KAGI_SUB_RE
KAGI_PART_RE      = _KAGI_PART_RE
KAKKO_PART_RE     = _KAKKO_PART_RE
PART_SUFFIX_RE    = _PART_SUFFIX_RE

# 保护 ～...～ 内容（strip_tags 内部用）
SUB_PROTECT_RE = re.compile(r'～([^～]+)～')

# 番外整体剥除
BONUS_RANGE_RE = _pat(
    rf'(?:(?:C[hH]\.?\s*)?{_RANGE}\s*\+\s*{_BONUS_KW}[編篇]?'
    rf'|{_BONUS_KW}[編篇]?\s*\+\s*{_RANGE})'
)
BONUS_WORD_RE = _pat(r'(?<![～~])' + _BONUS_KW + r'[編篇]?(?![～~])')

# 白名单 & 明确话数前缀
WHITELIST_RE   = _pat(r'(?<![a-zA-Z0-9])Season\s*\d')
UNAMBIGUOUS_RE = _pat(r'CH\.|第')

# 分编词汇 + 号保护（占位符）
PART_PAIR_PH = '\uffff'
PART_PAIR_RE = re.compile(rf'({_PART_UNIT})\s*\+\s*({_PART_UNIT})')

# 带圈数字
ROMAN_MAP = {
    'I': '①', 'II': '②', 'III': '③', 'IV': '④', 'V': '⑤',
    'VI': '⑥', 'VII': '⑦', 'VIII': '⑧', 'IX': '⑨', 'X': '⑩',
    'XI': '⑪', 'XII': '⑫',
}
ROMAN_SUFFIX_RE = _pat(r'(?<![A-Za-z])(I{1,3}|IV|VI{0,3}|IX|XI{0,3}|XII)$', 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 话号提取回调
# ═══════════════════════════════════════════════════════════════════════════════

def _ch_single(m: re.Match)      -> Chapter: return Chapter(float(m.group(1)))
def _ch_range(m: re.Match)       -> Chapter: return Chapter(float(m.group(1)), float(m.group(2)))
def _ch_range_bonus(m: re.Match) -> Chapter:
    """range + bonus（后置）：group(1)=start, group(2)=end, group(3)=bonus词汇。"""
    return Chapter(float(m.group(1)), float(m.group(2)), bonus=norm_bonus(m.group(3)))
def _ch_bonus_range(m: re.Match) -> Chapter:
    """bonus + range（前置，少见）：group(1)=bonus词汇, group(2)=start, group(3)=end。"""
    return Chapter(float(m.group(2)), float(m.group(3)), bonus=norm_bonus(m.group(1)))
def _ch_bonus(_: re.Match)       -> Chapter: return Chapter(0.0)
def _ch_cnnum(m: re.Match)       -> Chapter: return Chapter(float(CN_NUM_MAP[m.group(1)]))

def _ch_plus_range(m: re.Match)  -> Chapter:
    nums = [float(x) for x in re.findall(_NUM, m.group(0))]
    return Chapter(min(nums), max(nums)) if nums else Chapter(0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 话号匹配规则表（顺序敏感）
# ═══════════════════════════════════════════════════════════════════════════════

CHAPTER_PATTERNS: list[tuple[re.Pattern, Callable[[re.Match], Chapter]]] = [
    # 范围 + 番外（后置）：group(1)=start, group(2)=end, group(3)=bonus词汇
    (_pat(rf'({_NUM})\s*[-~～]\s*({_NUM})\s*\+\s*{_BONUS_KW_CAP}'), _ch_range_bonus),
    # 番外 + 范围（前置，少见）：group(1)=bonus词汇, group(2)=start, group(3)=end
    (_pat(rf'{_BONUS_KW_CAP}\s*\+\s*({_NUM})\s*[-~～]\s*({_NUM})'), _ch_bonus_range),
    # 纯番外（standalone，无话号）
    (_pat(rf'(?<=[\s+]){_BONUS_KW}[編篇]?(?=\s|\[|$|～)'), _ch_bonus),
    # 带"第"前缀
    (_pat(rf'第\s*({_NUM})\s*[-~～]\s*({_NUM})\s*[話话]'), _ch_range),
    (_pat(rf'第\s*({_NUM})\s*[話话]'), _ch_single),
    # CH. 前缀（含 +0 旧格式，降级为 bonus='番外篇'）
    (_pat(rf'C[hH]\.?\s*({_NUM})\s*[-~～]\s*({_NUM})\s*\+\s*0+(?!\d)'),
     lambda m: Chapter(float(m.group(1)), float(m.group(2)), bonus='番外篇')),
    (_pat(rf'C[hH]\.?\s*({_NUM})\s*[-~～]\s*({_NUM})'), _ch_range),
    (_pat(rf'C[hH]\.?\s*({_NUM})'), _ch_single),
    # 加号连接（多话合集）
    (_pat(rf'(?<!\d)({_NUM}\s*\+\s*)+{_NUM}(?!\d)', 0), _ch_plus_range),
    # 裸数字范围
    (_pat(rf'({_NUM})\s*[-~～]\s*({_NUM})', 0), _ch_range),
    # 数字 + 编/篇/话等
    (_pat(rf'(?:(?<=\s)|(?<=\D))({_NUM})(?=\s+\S*[編编篇話话章節节巻卷])', re.IGNORECASE), _ch_single),
    # 单个中文数字
    (_pat(
        rf'(?:(?<=\s)|(?<=\D))(?<![\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])'
        rf'([{"".join(CN_NUM_MAP.keys())}])(?=\s|$|[\[（(～])',
        0), _ch_cnnum),
    # 裸单数字（1-3 位，防止年号误判）
    (_pat(r'(?:(?<=\s)|(?<=\D))(\d{1,3}(?:\.\d+)?)(?=\s*(?:\[|¦|～|\(|（|「|$))', 0), _ch_single),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 卷号匹配规则表
# ═══════════════════════════════════════════════════════════════════════════════

def _vol_single(m: re.Match) -> Volume:
    return Volume(float(m.group(1)))

VOLUME_PATTERNS: list[tuple[re.Pattern, Callable[[re.Match], Volume]]] = [
    (_pat(rf'\b[Vv][Oo][Ll]\.?\s*({_NUM})\b'),          _vol_single),
    (_pat(rf'第\s*({_NUM})\s*[巻卷](?![話话])'),          _vol_single),
    (_pat(rf'[巻卷]\s*({_NUM})'),                         _vol_single),
    (_pat(rf'\bSeason\s*({_NUM})\b'),                     _vol_single),
]
