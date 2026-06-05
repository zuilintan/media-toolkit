"""命名层字符串工具：繁简转换、归一化、相似度、命名片段格式化、flag 抽取。"""

from __future__ import annotations
import re
import unicodedata

import zhconv

from module.manga.core import patterns as P


# ═══════════════════════════════════════════════════════════════════════════════
# 繁简转换
# ═══════════════════════════════════════════════════════════════════════════════

def trad_to_simp(text: str) -> str:
    """繁体中文 → 简体（``姊`` → ``姐`` 手工修补）。"""
    return re.sub(r'姊', '姐', zhconv.convert(text, 'zh-hans'))


# ═══════════════════════════════════════════════════════════════════════════════
# 字符串工具
# ═══════════════════════════════════════════════════════════════════════════════

def normalize(s: str) -> str:
    """NFKC 归一化并去掉空白，用于相似度比较。"""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', s)).lower()


def similar(a: str, b: str) -> bool:
    """归一化后相等或一方包含另一方。"""
    na, nb = normalize(a), normalize(b)
    return na == nb or na in nb or nb in na


def dot(s: str) -> str:
    """字段内空格替换为 ``・``（片假名中点）。"""
    return s.strip().replace(' ', '・')


def norm_punct(s: str) -> str:
    """统一全角标点（``〜`` → ``～``、``...`` → ``…``、数字间 ``,`` → ``，``）。"""
    s = s.translate(P.PUNCT_MAP).replace('...', '…')
    return re.sub(r'(?<=\d),(?=\d)', '，', s)


def strip_leading_prefix(stem: str) -> str:
    """剥离 ``(同人CG集)`` / ``(成年コミック)`` 这类文件名首部噪音括号前缀。

    :func:`~module.manga.naming.parser.parse_name` 的预处理首步与
    :func:`~module.manga.workflow.std_title.derive_author` 共用，确保两处对
    "首个 ``[xxx]``" 的认定一致。
    """
    return P.LEADING_PREFIX_RE.sub('', stem)


def extract_flag(stem: str, pattern: re.Pattern) -> tuple[str, bool]:
    """匹配 ``pattern`` 时移除并返回 ``(new_stem, True)``，否则 ``(stem, False)``。"""
    if pattern.search(stem):
        return pattern.sub('', stem), True
    return stem, False


def to_circle(n: int) -> str:
    """整数 0–20 → 带圈数字 ``⓪`` – ``⑳``；超出范围原样返回。

    ``⓪`` = U+24EA（与 ``①`` – ``⑳`` U+2460–U+2473 不连续，单独处理）。
    """
    if n == 0:
        return '\u24ea'
    if 1 <= n <= 20:
        return chr(0x2460 + n - 1)
    return str(n)


def conv_roman_suffix(s: str) -> str:
    """字符串末尾的罗马数字（I–XII）转为带圈数字。"""
    m = P.ROMAN_SUFFIX_RE.search(s)
    if m and m.group() in P.ROMAN_MAP:
        return s[:m.start()] + P.ROMAN_MAP[m.group()]
    return s
