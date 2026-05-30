"""
path.py — 拖入路径 → 作者名解析

规则（来自 ps1 Get-AuthorNameFromPath）:
  - 拖入文件夹 → 文件夹名即作者名
  - 拖入文件   → 父目录名即作者名

例:
  D:\\Downloads\\AuthorA               → 'AuthorA'
  D:\\Downloads\\AuthorA\\video.mp4    → 'AuthorA'
"""

from __future__ import annotations
from pathlib import Path


def path_to_author_name(p: Path) -> str:
    """从拖入路径推断作者名。文件 → 父目录名；目录 → 自身名。"""
    if p.is_dir():
        return p.name
    return p.parent.name
