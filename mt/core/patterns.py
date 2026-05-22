"""
patterns.py — 正则表达式常量与规则表

所有正则表达式集中在此，避免散落于各模块。
规则表（CHAPTER_PATTERNS / VOLUME_PATTERNS）顺序敏感，具体模式优先于模糊模式。

组织结构:
  1. 编译辅助           — _pat / _pats / _bracket
  2. 字符类与原子构件   — 数字 / CJK 字符类 / 常用前置断言
  3. 番外·分编词汇      — _BONUS_KW / _PART_UNIT / SUB_MAP / CN_NUM_MAP
  4. 标点规范化         — PUNCT_MAP
  5. 预处理管道         — wrap_bare_tags → promote_tags → normalize_chapter_tokens
                           → normalize_subtitle_delimiters → detect
  6. 结构提取模式       — 作者 / 系列 / 译名 / 话标题 / 番外整体剥除
  7. 话号提取回调       — _ch_* 函数
  8. 话号匹配规则表     — CHAPTER_PATTERNS
  9. 卷号匹配规则表     — VOLUME_PATTERNS

依赖: models（Chapter / Volume）
"""

from __future__ import annotations
import re
from collections.abc import Callable
from mt.core.models import Chapter, Volume, fmt_num


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 编译辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _pat(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern:
    return re.compile(pattern, flags)


def _pats(*patterns: str) -> list[re.Pattern]:
    return [_pat(p) for p in patterns]


def _bracket(inner: str) -> str:
    """生成匹配半角/全角方括号的片段：[...] 或 [...]。"""
    return rf'[\[［]{inner}[\]］]'


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 字符类与原子构件
# ═══════════════════════════════════════════════════════════════════════════════

# ── 数字 ───────────────────────────────────────────────────────────────────────
_NUM   = r'\d+(?:\.\d+)?'                       # 数字（含小数）
_RANGE = rf'{_NUM}\s*[-~～]\s*{_NUM}'            # 连续范围 N-M

# ── 字符类（character classes） ────────────────────────────────────────────────
_CHAP_SUFFIX_CC   = r'[編编篇話话章節节巻卷]'    # 话/章/节 后缀字符
_VOL_SUFFIX_CC    = r'[巻卷]'                    # 卷字
_TALE_CC          = r'[話话]'                    # 话字
_RIGHT_OPEN_CC    = r'[\[¦～(「]'                # 话号右侧合法开界字符
_NOT_FIELD_SEP_CC = r'[^\s・]'                   # 非空白且非「・」（字段分隔符）

# ── 前置断言（lookbehind/word boundary） ──────────────────────────────────────
_WORD_BOUNDARY_LB = r'(?:(?<=\s)|(?<=\D))'       # 前置：空白或非数字
_NOT_FIELD_SEP_LB = r'(?<![\d.・])'              # 前置：非数字、非「.」「・」
_CJK_KANA_NEG_LB  = (                             # 前置：非 CJK 汉字 / 平假 / 片假
    r'(?<![\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])'
)

# ── 字段前缀 ───────────────────────────────────────────────────────────────────
_DAI_PREFIX = r'第\s*'                           # 「第N…」
_CH_PREFIX  = r'C[hH]\.?\s*'                     # 「CH.N」/「Ch.N」/「ChN」


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 番外·分编词汇
# ═══════════════════════════════════════════════════════════════════════════════

# ── 番外关键字 ─────────────────────────────────────────────────────────────────
_BONUS_KW     = r'(?:おまけ|特典|番外)'           # 非捕获，用于剥除/检测
_BONUS_KW_CAP = r'((?:おまけ|特典|番外)[編篇]?)'   # 捕获版，用于提取实际词汇

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


# ── 中文数字映射（仅限序数话数） ───────────────────────────────────────────────
CN_NUM_MAP: dict[str, int] = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '壹': 1, '貳': 2, '贰': 2, '參': 3, '参': 3, '叁': 3,
    '肆': 4, '伍': 5, '陸': 6, '陆': 6, '柒': 7,
    '捌': 8, '玖': 9, '拾': 10, '什': 10,
}
_CN_NUM_CC = '[' + ''.join(CN_NUM_MAP.keys()) + ']'


# ── 分编词汇单元（用于话标题/附录链识别） ──────────────────────────────────────
_PART_UNIT = (
    r'(?:前|後|前|后|上|中|下|総集|总集|完結|完结)[编編篇]'   # XX编/編/篇
    r'|番外[編篇]?'                                            # 番外/番外編/番外篇
    r'|後日談|后日谈|After'                                    # 后日谈类
)
_PART_COMPOUND = rf'(?:{_PART_UNIT})(?:\+(?:{_PART_UNIT}))*'

# 话号尾链：紧跟在「+番外」之后的 +part/+bonus 链
_BONUS_TAIL = rf'(?:\+(?:{_PART_UNIT}|{_BONUS_KW}[編篇]?))*'

# ── 附录判定 ───────────────────────────────────────────────────────────────────
_APPENDIX_RAW: frozenset[str] = frozenset({'总集篇'})   # 在话标题位置时仍视为附录

# 与 CH. 同级且互斥的独立附录词（单独出现时提升为 appendix 字段）
STANDALONE_APPENDIX: frozenset[str] = frozenset({
    '上篇', '中篇', '下篇', '番外篇', '后日谈', '总集篇'
})

# 在 VOL. 之前输出的附录词汇
PRE_VOL_APPENDIX: frozenset[str] = frozenset({'总集篇'})

# 直接附在标题末尾的番外标记，如「時番外編」
BONUS_SUFFIX_RE = re.compile(r'(?:おまけ|特典|番外)[編篇]?\s*$')

# ── 分编词汇规范化映射 ────────────────────────────────────────────────────────
SUB_MAP: list[tuple[str, str | Callable]] = [
    (r'番外[编編]',        '番外篇'),
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
# 4. 标点规范化
# ═══════════════════════════════════════════════════════════════════════════════

PUNCT_MAP = str.maketrans({
    '!': '！', '?': '？',
    '~': '～', '〜': '～', '〰': '～',
    '·': '・', '｜': '¦', '︱': '¦',
    '（': '(', '）': ')',                       # 全角括号 → 半角，简化下游正则
    '　': ' ',                                  # 全角空格 → 半角
    '\u200b': '', '\u200c': '',                # 零宽字符直接清除
    '\u200d': '', '\ufeff': '',
})


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 预处理管道（normalize → detect）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 多段式管道，把各字段的所有变体收敛到唯一标准形态，下游只需处理一种形态：
#
#   原始
#    │ wrap_bare_tags          裸词 → [裸词]
#    │ promote_tags            [任意容器+关键字] → [标准tag]
#    │ normalize_chapter_tokens  第N話/第N-M話 → CH.N / CH.N-M
#    ▼ normalize_subtitle_delimiters  -t-/―t―/—t— → ～t～（在 strip_tags 之后调用）
#   检测（标签 / 话号 / 话标题 各自只需匹配唯一标准形态）
#
# 标准 tag：[zh] [ja] [ko] [en] [zxx] [uncensored] [colorized] [ongoing]
# 标准话号：CH.N / CH.N-M
# 标准话标题：～title～
#
# 扩展指南：
#   - 新增「裸词 → 标签」：往 _BARE_TAG_KEYWORDS 加一个 alternation
#   - 新增「容器+关键字 → 标准tag」：往 TAG_PROMOTE_RULES 加一行
#   - 新增「最终形态检测」：往 XX_PATTERNS 加一条（一般只匹配 [tag]）

# ── 5a. 裸词包裹 ───────────────────────────────────────────────────────────────
# 把"无容器的已知关键字"包裹为 [keyword]，让 promote_tags 后续接管。
# 顺序敏感：长 alternation 优先，避免「フルカラー化」被切碎。

_BARE_TAG_KEYWORDS = (
    # colorized 类
    r'フルカラー版?'
    r'|カラー化|カラー版'
    # zh 类（裸词形式的"中文版/机翻/個人翻譯"）
    r'|中文版|機翻|机翻|個人翻譯'
    # uncensored 类
    r'|Uncensored|Decensored'
    # censored 类
    r'|Censored'
)
_BARE_TAG_RE = _pat(
    rf'(?<![\[\(［【\w])({_BARE_TAG_KEYWORDS})(?![\]\)］】\w])'
)


def wrap_bare_tags(s: str) -> str:
    """把孤立（无容器）的已知标签关键字包裹为 [keyword]，供 promote_tags 处理。"""
    return _BARE_TAG_RE.sub(r'[\1]', s)


# ── 5b. 标签提升 ───────────────────────────────────────────────────────────────
# 把"任意容器（[]/()/【】/［］）+ 已知关键字"统一规范化为标准 [tag] 形式。
# 仅对"内容是已知关键字"的容器做提升，避免误改 (系列名) / 【前編】 等。

_TAG_OPEN  = r'[\[\(［【]'
_TAG_CLOSE = r'[\]\)］】]'


def _tag(inner: str) -> str:
    """生成「任意容器 + 内容」的匹配片段。"""
    return rf'{_TAG_OPEN}\s*(?:{inner})\s*{_TAG_CLOSE}'


# 注意顺序：复合标签（如「官中无修」同时是 zh + uncensored）需在单标签前处理
TAG_PROMOTE_RULES: list[tuple[re.Pattern, str]] = [
    # 双重标签：官中无修 → [zh][uncensored]
    (_pat(_tag(r'官中无修')), '[zh][uncensored]'),

    # ── colorized ──────────────────────────────────────────────────────────────
    (_pat(_tag(r'(?:フルカラー|カラー化|カラー|全彩色?|彩色)版?')), '[colorized]'),

    # ── uncensored ─────────────────────────────────────────────────────────────
    (_pat(_tag(
        r'[无無]修(?:正)?|官[方中][无無]修?|无修|Uncensored|Decensored'
    )), '[uncensored]'),

    # ── censored ───────────────────────────────────────────────────────────────
    (_pat(_tag(r'有修正|修正あり|Censored')), '[censored]'),

    # ── zh ─────────────────────────────────────────────────────────────────────
    # 整段含「汉化/掃图/嵌字/重嵌/日语社/考生組」的方括号 → [zh]（吞掉社团名）
    (_pat(_bracket(
        r'[^\]]*(?:[汉漢]化|[扫掃][圖图]|嵌字|重嵌|日语社|考生[組组])[^\]]*'
    )), '[zh]'),
    # 已知社团/工坊
    (_pat(_tag(
        r'[风風]的工房|如月工房|淫书馆|洨五[組组]|AI貓貓翻譯'
    )), '[zh]'),
    # 中文相关关键字
    (_pat(_tag(
        r'中[国國]翻[译訳]|中文翻[译訳]'
        r'|中[国國][语語]|中文'
        r'|Chinese|zh'
        r'|简中|简体中文|繁中|繁体中文'
        r'|官中|官方中文'
        r'|中文版|機翻|机翻|個人翻譯'
    )), '[zh]'),

    # ── ja / ko / en ───────────────────────────────────────────────────────────
    (_pat(_tag(r'ja|Japanese|日语|日文')),  '[ja]'),
    (_pat(_tag(r'ko|Korean|韩语|韩文')),    '[ko]'),
    (_pat(_tag(r'en|English|英语|英文')),   '[en]'),

    # ── 其它原子标签（形态本身已规范，只做容器统一） ─────────────────────────
    (_pat(_tag(r'zxx')),       '[zxx]'),
    (_pat(_tag(r'ongoing')),   '[ongoing]'),
]


def promote_tags(s: str) -> str:
    """把任意容器内的已知标签关键字规范化为 [tag] 形式。"""
    for pat, std in TAG_PROMOTE_RULES:
        s = pat.sub(std, s)
    return s


# ── 5c. 话号标识规范化 ─────────────────────────────────────────────────────────
# 把 '第N-M話' / '第N話' 规范化为 'CH.N-M' / 'CH.N'，
# 后续 CHAPTER_PATTERNS 只需保留 CH. 前缀规则，无需再设 第…話 分支。

_DAI_TALE_RANGE_RE = _pat(rf'{_DAI_PREFIX}({_NUM})\s*[-~～]\s*({_NUM})\s*{_TALE_CC}')
_DAI_TALE_SINGLE_RE = _pat(rf'{_DAI_PREFIX}({_NUM})\s*{_TALE_CC}')


def normalize_chapter_tokens(s: str) -> str:
    """将 '第N-M話' / '第N話' 规范化为 'CH.N-M' / 'CH.N'。"""
    s = _DAI_TALE_RANGE_RE.sub(lambda m: f'CH.{m.group(1)}-{m.group(2)}', s)
    s = _DAI_TALE_SINGLE_RE.sub(lambda m: f'CH.{m.group(1)}', s)
    return s


# ── 5d. 话标题定界符规范化 ─────────────────────────────────────────────────────
# 把 '-title-' / '―title―' / '—title—' 统一规范化为 '～title～'。
# 须在 strip_tags 之后、extract_subtitle 之前调用（此时 [...] 标签已移除，
# $-锚点可以正确命中句尾）。

_SUBTITLE_ALT_RE = re.compile(
    r'\s*(?:―([^―]+)―?|—([^—]+)—?|-([^-]*(?:[^\x00-\x7f]|\s)[^-]*)-?)\s*$', 0
)


def normalize_subtitle_delimiters(s: str) -> str:
    """将话标题非标准定界符 (-/―/—) 规范化为 ～～。"""
    def _repl(m: re.Match) -> str:
        content = next(g for g in m.groups() if g is not None)
        return f' ～{content.strip()}～'
    return _SUBTITLE_ALT_RE.sub(_repl, s)


# ── 5e. 最终形态检测（管道后只需检测唯一标准形态） ───────────────────────────
ZH_PATTERNS         = _pats(_bracket(r'zh'))
JA_PATTERNS         = _pats(_bracket(r'ja'))
KO_PATTERNS         = _pats(_bracket(r'ko'))
EN_PATTERNS         = _pats(_bracket(r'en'))
UNCENSORED_PATTERNS = _pats(_bracket(r'uncensored'))
CENSORED_PATTERNS   = _pats(_bracket(r'censored'))
COLORIZED_TAG_PATTERNS = [_pat(_bracket(r'colorized'))]
TEXTLESS_TAG_RE     = _pat(_bracket(r'zxx'))
ONGOING_TAG_RE      = _pat(_bracket(r'ongoing'))

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

# 聚合：strip_tags 中的额外剥除规则
# 标准方括号标签（[zh]/[uncensored]/…）已由 BRACKET_TAG_RE 兜底剥除，
# 此处只需处理「不在方括号内」的噪音（NOISE_TAG_RE 自带方括号，VERSION_RE 是裸词）
STRIP_PATTERNS: list[re.Pattern] = [NOISE_TAG_RE, VERSION_RE]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 结构提取模式
# ═══════════════════════════════════════════════════════════════════════════════

AUTHOR_TAG_RE       = _pat(_bracket(r'([^\]］]+)'), 0)   # 第一个 [xxx] → 作者
BRACKET_TAG_RE      = _pat(_bracket(r'[^\]］]*'), 0)      # 所有方括号标签
SERIES_PAREN_RE     = _pat(                               # 系列名 (xxx)
    r'(?:^|(?<=[\s～】」\])]))\(([^)]+)\)', 0)
TRANS_INLINE_RE     = _pat(r'¦([^¦]+)¦', 0)              # 内嵌译名 ¦译名¦
PUBLICATION_PAREN_RE= _pat(                               # 杂志来源括号
    r'\([^)]*(?:COMIC|別冊|よろず|雑誌|月号|週刊|Vol\.|C\d{2,})[^)]*\)')
LEADING_PREFIX_RE   = _pat(                               # 开头噪音前缀
    r'^\s*(?:\([^)]{1,10}\)\s*)+', 0)

# 话标题分隔符（定界符已由 normalize_subtitle_delimiters 预规范化为 ～～）
SUBTITLE_RE = _pat(r'\s*～([^～]+)～?\s*$', 0)

# 分编词汇 / 「」/【】 话标题
PART_COMPOUND_RE = _pat(rf'\s+({_PART_COMPOUND})$', 0)
KAGI_SUB_RE      = _pat(r'\s*「([^」]+)」\s*$', 0)            # 「xxx」单独
KAGI_PART_RE     = _pat(r'\s*「([^」]+)」\s*(\S+)\s*$', 0)    # 「xxx」+ 后缀词
KAKKO_PART_RE    = _pat(rf'【\s*({_PART_COMPOUND})\s*】', 0)
PART_SUFFIX_RE   = _pat(rf'\s+(\S*(?:{_PART_UNIT}))\s*$', 0)

# 保护 ～...～ 内容（strip_tags 内部用）
SUB_PROTECT_RE = re.compile(r'～([^～]+)～')

# 番外整体剥除（支持尾随的 +分编词链）
BONUS_RANGE_RE = _pat(
    rf'(?:(?:{_CH_PREFIX})?{_RANGE}\s*\+\s*{_BONUS_KW}[編篇]?{_BONUS_TAIL}'
    rf'|{_BONUS_KW}[編篇]?\s*\+\s*{_RANGE})'
)
BONUS_WORD_RE = _pat(rf'(?<![～~]){_BONUS_KW}[編篇]?(?![～~])')

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
# 7. 话号提取回调
# ═══════════════════════════════════════════════════════════════════════════════

def _ch_single(m: re.Match) -> Chapter:
    return Chapter(float(m.group(1)))


def _ch_range(m: re.Match) -> Chapter:
    return Chapter(float(m.group(1)), float(m.group(2)))


def _ch_range_bonus(m: re.Match) -> Chapter:
    """range + bonus（后置，可带 +part 尾链）。
    group(1)=start, group(2)=end, group(3)=bonus词汇, group(4)=尾链(可空)。
    """
    head = norm_bonus(m.group(3))
    tail = m.group(4) or ''
    if tail:
        segs = [s for s in tail.split('+') if s]
        head = '+'.join([head, *(norm_part_subtitle(s) for s in segs)])
    return Chapter(float(m.group(1)), float(m.group(2)), bonus=head)


def _ch_bonus_range(m: re.Match) -> Chapter:
    """bonus + range（前置，少见）：group(1)=bonus词汇, group(2)=start, group(3)=end。"""
    return Chapter(float(m.group(2)), float(m.group(3)), bonus=norm_bonus(m.group(1)))


def _ch_range_plus_zero(m: re.Match) -> Chapter:
    """CH.X-Y+0 旧格式 → 降级为 bonus='番外篇'。"""
    return Chapter(float(m.group(1)), float(m.group(2)), bonus='番外篇')


def _ch_bonus(_: re.Match) -> Chapter:
    return Chapter(0.0)


def _ch_cnnum(m: re.Match) -> Chapter:
    return Chapter(float(CN_NUM_MAP[m.group(1)]))


def _ch_plus_range(m: re.Match) -> Chapter:
    nums = [float(x) for x in re.findall(_NUM, m.group(0))]
    return Chapter(min(nums), max(nums)) if nums else Chapter(0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 话号匹配规则表（顺序敏感：具体优先于模糊）
# ═══════════════════════════════════════════════════════════════════════════════

CHAPTER_PATTERNS: list[tuple[re.Pattern, Callable[[re.Match], Chapter]]] = [
    # 范围 + 番外（后置）+ 可选 +part/+bonus 尾链
    # 例：「01-09+番外篇+后日谈」→ Chapter(1, 9, bonus='番外篇+后日谈')
    (_pat(rf'({_NUM})\s*[-~～]\s*({_NUM})\s*\+\s*{_BONUS_KW_CAP}({_BONUS_TAIL})'),
     _ch_range_bonus),

    # 番外 + 范围（前置，少见）
    (_pat(rf'{_BONUS_KW_CAP}\s*\+\s*({_NUM})\s*[-~～]\s*({_NUM})'),
     _ch_bonus_range),

    # 纯番外（standalone，无话号），生成 Chapter(0)，后续提升为 appendix
    (_pat(rf'(?<=[\s+]){_BONUS_KW}[編篇]?(?=\s|\[|$|～)'),
     _ch_bonus),

    # CH. 前缀（含 +0 旧格式 → bonus='番外篇'；第N話 已由 normalize_chapter_tokens 预规范化为 CH.N）
    (_pat(rf'{_CH_PREFIX}({_NUM})\s*[-~～]\s*({_NUM})\s*\+\s*0+(?!\d)'),
     _ch_range_plus_zero),
    (_pat(rf'{_CH_PREFIX}({_NUM})\s*[-~～]\s*({_NUM})'), _ch_range),
    (_pat(rf'{_CH_PREFIX}({_NUM})'),                    _ch_single),

    # 加号连接（多话合集，如「1+2+2.5」→ CH.01-02.5）
    (_pat(rf'(?<!\d)({_NUM}\s*\+\s*)+{_NUM}(?!\d)', 0), _ch_plus_range),

    # 裸数字范围（「4-5」）
    (_pat(rf'({_NUM})\s*[-~～]\s*({_NUM})', 0), _ch_range),

    # 数字 + 章节后缀（紧贴）：与「編/篇/话」之间最多 3 个非空白非「・」字符；
    # 前置不可为「.」「・」。例「主标题名6過去編」匹配；「no.10・自編」不匹配。
    (_pat(
        rf'{_NOT_FIELD_SEP_LB}(?<=\S)({_NUM})'
        rf'(?={_NOT_FIELD_SEP_CC}{{0,3}}{_CHAP_SUFFIX_CC})'
    ), _ch_single),

    # 数字 + 章节后缀（空白分隔）：如「2 挑戦編」
    # 前置不可为「.」「・」（避免「no.10 ～咕咕嘎嘎編」等字段链误判）
    (_pat(rf'{_NOT_FIELD_SEP_LB}{_WORD_BOUNDARY_LB}({_NUM})'
          rf'(?=\s+\S*{_CHAP_SUFFIX_CC})'),
     _ch_single),

    # 单个中文数字（前置非 CJK/假名，右侧为空白/EOL/标签开界）
    (_pat(
        rf'{_WORD_BOUNDARY_LB}{_CJK_KANA_NEG_LB}'
        rf'({_CN_NUM_CC})(?=\s|$|[\[(～])',
        0,
    ), _ch_cnnum),

    # 裸单数字（1-3 位 + 可选小数），右侧为标签/译名/括号/话标题/EOL，
    # 前置不可为「.」「・」（避免「no.10 ～…」等字段链误判），防止年号误判
    (_pat(
        rf'{_NOT_FIELD_SEP_LB}{_WORD_BOUNDARY_LB}'
        rf'(\d{{1,3}}(?:\.\d+)?)(?=\s*(?:{_RIGHT_OPEN_CC}|$))',
        0,
    ), _ch_single),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 9. 卷号匹配规则表
# ═══════════════════════════════════════════════════════════════════════════════

def _vol_single(m: re.Match) -> Volume:
    return Volume(float(m.group(1)))


VOLUME_PATTERNS: list[tuple[re.Pattern, Callable[[re.Match], Volume]]] = [
    (_pat(rf'\b[Vv][Oo][Ll]\.?\s*({_NUM})\b'),                              _vol_single),
    (_pat(rf'{_DAI_PREFIX}({_NUM})\s*{_VOL_SUFFIX_CC}(?!{_TALE_CC})'),      _vol_single),
    (_pat(rf'{_VOL_SUFFIX_CC}\s*({_NUM})'),                                 _vol_single),
    (_pat(rf'\bSeason\s*({_NUM})\b'),                                       _vol_single),
]
