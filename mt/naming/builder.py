"""
builder.py — 新文件名构建

核心入口: build_new_name(info: MangaInfo) → str

目标命名格式:
  [作者] 漫画标题( VOL.XX)?
  ( CH.XX(-YY)?(+番外篇)? | 番外篇 | 后日谈 | 上篇 | 中篇 | 下篇)?
  ( ～话标题～)?( (系列))? ( ¦译名¦)?
  ([总集篇])? ([zh])? ([uncensored])? ([colorized])? ([ongoing])?

规则:
  1. 标题/系列/译名中，空格以 ・ 替代
  2. 合集类（总集篇）作为 [总集篇] tag 输出，与 [zh] 同位（在语言标签前）
  3. 番外篇 / 后日谈 / 上篇 / 中篇 / 下篇 与 CH. 同级且互斥

依赖: models / patterns / naming.text
"""

from __future__ import annotations

from mt.core.models import MangaInfo
from mt.core import patterns as P
from mt.naming.text import dot, norm_punct


def build_new_name(info: MangaInfo) -> str:
    """根据 MangaInfo 拼合目标名称（不含文件后缀）。"""
    parts: list[str] = [f'[{info.author}]', dot(info.main_title)]

    if info.volume is not None:
        parts.append(str(info.volume))

    # CH. 话数 或 独立分编词（与 CH. 同级且互斥）；合集类走下方 tag 块
    if info.chapter is not None:
        parts.append(str(info.chapter))
    elif info.part_tag and info.part_tag not in P.COMPILATION_PARTS:
        parts.append(info.part_tag)

    if info.chapter_title:
        parts.append(f'～{dot(info.chapter_title)}～')

    if info.series:
        parts.append(f'({dot(info.series)})')

    if info.translation:
        parts.append(f'¦{info.translation}¦')

    tags = ''.join(filter(None, [
        f'[{info.part_tag}]'  if info.part_tag in P.COMPILATION_PARTS else '',
        f'[{info.language}]'  if info.language      else '',
        '[uncensored]'         if info.is_uncensored  else '',
        '[colorized]'          if info.is_colorized   else '',
        '[ongoing]'            if info.is_ongoing     else '',
    ]))
    if tags:
        parts.append(tags)

    return norm_punct(' '.join(parts))
