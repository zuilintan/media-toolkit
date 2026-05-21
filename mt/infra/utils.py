"""
utils.py — 纯工具函数（无 I/O、无副作用）

包含:
  - 字符串规范化
  - 繁简转换
  - 路径安全操作
  - 重命名执行

依赖: patterns（PUNCT_MAP）
"""

from __future__ import annotations
import os
import re
import unicodedata
from pathlib import Path

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


def any_match(text: str, patterns: list[re.Pattern]) -> bool:
    """任意一个正则匹配即返回 True。"""
    return any(p.search(text) for p in patterns)


def dot(s: str) -> str:
    """将字段内空格替换为 ・（片假名中点）。"""
    return s.strip().replace(' ', '・')


def norm_punct(s: str) -> str:
    """统一全角标点（〜→～、...→…等）。"""
    return s.translate(P.PUNCT_MAP).replace('...', '…')


def extract_flag(stem: str, pattern: re.Pattern) -> tuple[str, bool]:
    """若匹配 pattern，移除并返回 (新stem, True)；否则返回 (stem, False)。"""
    if pattern.search(stem):
        return pattern.sub('', stem), True
    return stem, False


def extract_flag_from_list(stem: str, patterns: list[re.Pattern]) -> tuple[str, bool]:
    """尝试列表各模式，移除第一个命中，全不命中返回 (stem, False)。"""
    for pat in patterns:
        stem, hit = extract_flag(stem, pat)
        if hit:
            return stem, True
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


# ═══════════════════════════════════════════════════════════════════════════════
# 路径安全操作
# ═══════════════════════════════════════════════════════════════════════════════

_MIN_DEPTH = 2   # 路径的最少层数（去根锚点后），防止误操作根目录


def guard_path(p: Path, min_depth: int = _MIN_DEPTH) -> None:
    """断言路径深度 >= min_depth。"""
    resolved = p.resolve()
    depth = len(resolved.parts) - 1
    if depth < min_depth:
        raise ValueError(
            f"拒绝操作路径（深度 {depth} < {min_depth}，疑似根目录）: {resolved!r}"
        )


def strict_exists(path: Path) -> bool:
    """严格大小写判断文件是否存在（修正大小写不敏感文件系统的误判）。"""
    if not path.exists():
        return False
    try:
        return path.resolve().name == path.name
    except Exception:
        return False


def is_smb_path(path: str) -> bool:
    """判断路径是否位于 SMB/网络驱动器（仅 Windows 有效）。"""
    import sys
    if sys.platform != 'win32':
        return False
    import ctypes
    abs_path = os.path.abspath(path)
    if abs_path.startswith(r'\\'):
        return True
    drive = os.path.splitdrive(abs_path)[0] + '\\'
    return bool(drive and ctypes.windll.kernel32.GetDriveTypeW(drive) == 4)


def execute_rename(old: Path, new: Path) -> None:
    """执行重命名；SMB 环境下大小写变更使用两步法。"""
    guard_path(old)
    guard_path(new)
    if (is_smb_path(str(new))
            and old.name.lower() == new.name.lower()
            and old.name != new.name):
        tmp = old.with_name(old.stem + '_tmp_rename' + old.suffix)
        old.rename(tmp)
        tmp.rename(new)
    else:
        old.rename(new)


def try_rename(src: Path, dst: Path) -> str:
    """尝试重命名，返回状态:
    - ``"same"``   — 完全相同，无需操作
    - ``"exists"`` — 目标已存在（且不同于源）
    - ``"ok"``     — 重命名成功
    异常由调用方处理。
    """
    if str(src) == str(dst):
        return 'same'
    if strict_exists(dst):
        return 'exists'
    if str(src).lower() == str(dst).lower():
        tmp = dst.with_name(dst.stem + '_tmp_rename' + dst.suffix)
        execute_rename(src, tmp)
        execute_rename(tmp, dst)
        return 'ok'
    execute_rename(src, dst)
    return 'ok'


def safe_unlink(p: Path) -> None:
    guard_path(p)
    p.unlink()


def safe_rmdir(p: Path) -> None:
    guard_path(p)
    p.rmdir()
