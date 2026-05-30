"""
text.py — 命名层字符串工具

包含:
  - 繁简转换 (trad_to_simp)
  - 字符串归一化 / 相似度 (normalize, similar)
  - 命名片段格式化 (dot, norm_punct)
  - flag 抽取 / 数字符号转换 (extract_flag, to_circle, conv_roman_suffix)

依赖: zhconv / mt.core.patterns
"""

from __future__ import annotations
import re
import unicodedata

import zhconv

from mt.core import patterns as P


# ═══════════════════════════════════════════════════════════════════════════════
# 繁简转换
# ═══════════════════════════════════════════════════════════════════════════════

def trad_to_simp(text: str) -> str:
    """繁体中文转简体。"""
    return re.sub(r'姊', '姐', zhconv.convert(text, 'zh-hans'))


# ═══════════════════════════════════════════════════════════════════════════════
# 字符串工具
# ═══════════════════════════════════════════════════════════════════════════════

def normalize(s: str) -> str:
    """NFKC 归一化并压缩空白，用于相似度比较。"""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', s)).lower()


def similar(a: str, b: str) -> bool:
    """检查两个字符串是否相似（归一化后相等或包含）。"""
    na, nb = normalize(a), normalize(b)
    return na == nb or na in nb or nb in na


def dot(s: str) -> str:
    """将字段内空格替换为 ・（片假名中点）。"""
    return s.strip().replace(' ', '・')


def norm_punct(s: str) -> str:
    """统一全角标点（〜→～、...→…、数字间逗号→，等）。"""
    s = s.translate(P.PUNCT_MAP).replace('...', '…')
    return re.sub(r'(?<=\d),(?=\d)', '，', s)


def extract_flag(stem: str, pattern: re.Pattern) -> tuple[str, bool]:
    """若匹配 pattern，移除并返回 (新stem, True)；否则返回 (stem, False)。"""
    if pattern.search(stem):
        return pattern.sub('', stem), True
    return stem, False


def to_circle(n: int) -> str:
    """整数 0–20 → 带圈数字 ⓪–⑳；超出范围原样返回。

    ⓪ = U+24EA（与 ①–⑳ 的 U+2460–U+2473 不连续，单独处理）
    """
    if n == 0:
        return '\u24ea'          # ⓪
    if 1 <= n <= 20:
        return chr(0x2460 + n - 1)   # ①–⑳
    return str(n)


def conv_roman_suffix(s: str) -> str:
    """将字符串末尾的罗马数字（I–XII）转换为带圈数字。"""
    m = P.ROMAN_SUFFIX_RE.search(s)
    if m and m.group() in P.ROMAN_MAP:
        return s[:m.start()] + P.ROMAN_MAP[m.group()]
    return s
