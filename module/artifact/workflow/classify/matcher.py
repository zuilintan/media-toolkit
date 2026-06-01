"""作者名 → 候选目标作者目录（精确路径 + 别名映射）。

匹配规则（ps1 ``Get-TargetAuthorFolder`` 等价）：

1. 精确：每个 WorkDir 检查 ``WorkDir / 作者名`` 是否为已存在目录
2. 别名：``alias_map`` 中 ``作者名`` 命中则加入对应作者目录
3. 候选去重，保留发现顺序
"""

from __future__ import annotations
from pathlib import Path


def find_candidates(
    author_name: str,
    workdirs: list[Path],
    alias_map: dict[str, Path],
) -> list[Path]:
    """返回候选作者目录列表（按 WorkDir 顺序 + 别名映射，去重）。"""
    if not author_name:
        return []

    seen: set[str] = set()
    out: list[Path] = []

    for wd in workdirs:
        cand = wd / author_name
        if cand.is_dir():
            key = str(cand.resolve()).lower()
            if key not in seen:
                seen.add(key)
                out.append(cand)

    if author_name in alias_map:
        cand = alias_map[author_name]
        key = str(cand.resolve()).lower()
        if key not in seen:
            seen.add(key)
            out.append(cand)

    return out
