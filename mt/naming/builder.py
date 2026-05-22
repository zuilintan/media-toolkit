"""
builder.py — 新文件名构建

核心入口: build_new_name(info: MangaInfo) → str

目标命名格式:
  [作者] 漫画标题( 总集篇)?( VOL.XX)?
  ( CH.XX(-YY)?(+番外篇)? | 番外篇 | 后日谈 | 上篇 | 中篇 | 下篇)?
  ( ～话标题～)?( (系列))? ( ¦译名¦)?
  ([zh])? ([uncensored])? ([colorized])? ([ongoing])?

规则:
  1. 标题/系列/译名中，空格以 ・ 替代
  2. 总集篇 在 VOL. 之前；其余附录词与 CH. 同级（VOL. 之后）
  3. 后日谈 / 番外篇 / 上篇 / 中篇 / 下篇 与 CH. 互斥

依赖: models / patterns / utils
"""

from __future__ import annotations

from mt.core.models import MangaInfo
from mt.core import patterns as P
from mt.infra.utils import dot, norm_punct


def build_new_name(info: MangaInfo) -> str:
    """根据 MangaInfo 拼合目标名称（不含文件后缀）。"""
    parts: list[str] = [f'[{info.author}]', dot(info.main_title)]

    # 总集篇 在 VOL. 之前
    if info.appendix in P.PRE_VOL_APPENDIX:
        parts.append(info.appendix)

    if info.volume is not None:
        parts.append(str(info.volume))

    # CH. 话数 或 独立附录词（与 CH. 同级且互斥，在 VOL. 之后）
    if info.chapter is not None:
        parts.append(str(info.chapter))
    elif info.appendix and info.appendix not in P.PRE_VOL_APPENDIX:
        parts.append(info.appendix)

    if info.chapter_title:
        parts.append(f'～{dot(info.chapter_title)}～')

    if info.series:
        parts.append(f'({dot(info.series)})')

    if info.translation:
        parts.append(f'¦{info.translation}¦')

    tags = ''.join(filter(None, [
        f'[{info.language}]'  if info.language      else '',
        '[uncensored]'         if info.is_uncensored  else '',
        '[colorized]'          if info.is_colorized   else '',
        '[ongoing]'            if info.is_ongoing     else '',
    ]))
    if tags:
        parts.append(tags)

    return norm_punct(' '.join(parts))
