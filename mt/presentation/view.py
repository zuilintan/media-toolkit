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
from mt.naming.parser import emit_parse_debug


# ═══════════════════════════════════════════════════════════════════════════════
# 运行 banner（rename / comicinfo 共用）
# ═══════════════════════════════════════════════════════════════════════════════

def print_run_banner(cmd: str, subtitle: str, root: object, mode_apply: bool) -> None:
    """统一的命令运行 banner：═══ + 命令标题 + 根目录 + 模式。

    具体「找到 N 项」一行因不同子命令的扫描成本和 DEBUG 时序而异，
    由调用方在 banner 之后自行追加。
    """
    emit(SEP2)
    emit(f'  manga-toolkit-cli  —  {cmd} ({subtitle})')
    emit(SEP2)
    emit(f'  根目录:   {root}')
    emit(f'  模式:     '
         f'{"【写入模式】实际修改文件" if mode_apply else "【预览模式】仅展示解析结果，不修改文件"}')


# ═══════════════════════════════════════════════════════════════════════════════
# 重命名预览
# ═══════════════════════════════════════════════════════════════════════════════

def print_preview(plans: list[RenamePlan]) -> None:
    """以可读格式打印重命名计划。"""
    changed   = [p for p in plans if p.changed]
    unchanged = [p for p in plans if not p.changed]
    reviews   = [p for p in plans if p.needs_review]
    warns     = [p for p in plans if p.info and p.info.warnings]

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
            note = ' 🟡 需审核' if p.needs_review else ''
            emit(f'     {icon} [{idx:>3}]')
            if p.info is not None:
                emit_parse_debug(p.info)
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
                if i.part_tag:      flags.append(f'分编:{i.part_tag}')
                if flags:
                    emit(f'       Flag: {" | ".join(flags)}')
                for w in i.warnings:
                    emit(f'       🟡 {w}')
                emit(f'       Path:\n       {p.author_dir}\\{p.old_name}\n')
            emit()
    else:
        emit('\n没有需要改名的项目。')

    if unchanged:
        emit(f'➡️   无需修改: {len(unchanged)} 个')
    if reviews:
        emit(f'🟡  需人工审核: {len(reviews)} 个')
    if warns:
        emit(f'🟡  有警告:    {len(warns)} 个')
    emit(SEP)
    parts = [
        f'合计: {len(plans)} 项',
        f'需改名: {len(changed)}',
        f'需审核: {len(reviews)}',
    ]
    if warns:
        parts.append(f'警告: {len(warns)}')
    emit(' | '.join(parts))
    emit(SEP)


# ═══════════════════════════════════════════════════════════════════════════════
# ComicInfo 字段打印
# ═══════════════════════════════════════════════════════════════════════════════

def print_comicinfo_fields(fields: dict[str, str],
                           pub_conflict: list[str] | None = None) -> None:
    """以 'TagName: value' 格式打印 ComicInfo 字段（标签与 DEBUG 同栏对齐）。"""
    indent  = '     '                                     # 与 console.debug 同
    col_w   = max(len(t) for t in COMICINFO_TAGS) + 2     # 'Tag: ' 列宽（含冒号 + 空格）
    for tag in COMICINFO_TAGS:
        label = f'{indent}{(tag + ":"):<{col_w}}'
        if tag == 'Publisher' and pub_conflict:
            emit(f'{label}🟡 多个社团文件，请手动确认！')
            for p in pub_conflict:
                emit(f'{" " * len(label)}• {os.path.basename(p)}')
        elif tag == 'Tags':
            val = fields.get(tag, '')
            suffix = '  (保留)' if val else ''
            emit(f'{label}{val}{suffix}'.rstrip())
        else:
            val = fields.get(tag, '')
            emit(f'{label}{val}'.rstrip())
