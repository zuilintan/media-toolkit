"""
view.py — 领域对象的终端渲染

提供:
  - print_preview()          — 重命名计划预览
  - print_comicinfo_fields() — ComicInfo 字段展示

依赖: core.models（RenamePlan）/ core.config（COMICINFO_TAGS）/ infra.console（颜色、分隔线、高亮）
"""

from __future__ import annotations
import os

from mt.core.models import RenamePlan
from mt.core.config import COMICINFO_TAGS
from mt.infra.console import SEP, SEP2, RED, highlight_diff, emit


# ═══════════════════════════════════════════════════════════════════════════════
# 重命名预览
# ═══════════════════════════════════════════════════════════════════════════════

def print_preview(plans: list[RenamePlan]) -> None:
    """以可读格式打印重命名计划。"""
    changed   = [p for p in plans if p.changed]
    unchanged = [p for p in plans if not p.changed]
    reviews   = [p for p in plans if p.needs_review]

    emit(f'\n{SEP2}')
    emit('📁 漫画重命名预览')
    emit(SEP2)

    if changed:
        emit(f'\n✅ 将重命名 ({len(changed)} 个):\n')
        last_author = None
        for idx, p in enumerate(changed, 1):
            if p.author != last_author:
                emit(f'  📂 {p.author}')
                last_author = p.author
            icon = '📄' if p.is_file else '🗂 '
            note = ' ⚠️  需审核' if p.needs_review else ''
            emit(f'    {icon} [{idx:>3}]')
            emit(f'       旧: {p.old_name}')
            emit(f'       新: {highlight_diff(p.old_name, p.new_name, RED)}{note}')
            if p.info:
                i = p.info
                flags: list[str] = []
                if i.language:      flags.append(i.language)
                if i.is_uncensored: flags.append('uncensored')
                if i.is_colorized:  flags.append('colorized')
                if i.is_ongoing:    flags.append('ongoing')
                if i.series:        flags.append(f'系列:{i.series}')
                if i.translation:   flags.append(f'译名:{i.translation}')
                if i.volume:        flags.append(str(i.volume))
                if i.chapter:       flags.append(str(i.chapter))
                if i.appendix:      flags.append(f'附录:{i.appendix}')
                if flags:
                    emit(f'       Flag: {" | ".join(flags)}')
                emit(f'       Path:\n       {p.author_dir}\\{p.old_name}\n')
            emit()
    else:
        emit('\n没有需要改名的项目。')

    if unchanged:
        emit(f'➡️   无需修改: {len(unchanged)} 个')
    if reviews:
        emit(f'⚠️   需人工审核: {len(reviews)} 个')
    emit(SEP)
    emit(f'合计: {len(plans)} 项 | 需改名: {len(changed)} | 需审核: {len(reviews)}')
    emit(SEP)


# ═══════════════════════════════════════════════════════════════════════════════
# ComicInfo 字段打印
# ═══════════════════════════════════════════════════════════════════════════════

def print_comicinfo_fields(fields: dict[str, str],
                           pub_conflict: list[str] | None = None) -> None:
    """以 'TagName: value' 格式打印 ComicInfo 字段。"""
    for tag in COMICINFO_TAGS:
        if tag == 'Publisher' and pub_conflict:
            emit(f'  {tag}: ⚠️  多个社团文件，请手动确认！')
            for p in pub_conflict:
                emit(f'           • {os.path.basename(p)}')
        elif tag == 'Tags':
            val = fields.get(tag, '')
            suffix = '  (保留)' if val else ''
            emit(f'  {tag}: {val}{suffix}')
        else:
            val = fields.get(tag, '')
            emit(f'  {tag}: {val}' if val else f'  {tag}:')
