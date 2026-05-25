"""
view.py — 领域对象的终端渲染

提供:
  - print_run_banner()          — 命令运行 banner（sourcefile / metadata 共用）
  - print_sourcefile_preview()  — 源文件重命名计划预览（按作者分组的卡片表）
  - print_metadata_preview()    — ComicInfo 写入计划预览（结构对齐 sourcefile）
  - print_metadata_fields()     — ComicInfo 字段块（被 preview 卡片体复用）

依赖: core.models / core.config / infra.console / naming.parser
"""

from __future__ import annotations
import os
from collections.abc import Iterable, Iterator

from mt.core.models import MangaInfo, MetadataPlan, SourcefilePlan
from mt.core.config import COMICINFO_TAGS
from mt.infra.console import SEP, SEP2, RED, highlight_diff, emit
from mt.naming.parser import emit_parse_debug


# ═══════════════════════════════════════════════════════════════════════════════
# 运行 banner（sourcefile / metadata 共用）
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
# 卡片骨架（sourcefile / metadata 共用）
# ═══════════════════════════════════════════════════════════════════════════════

def _print_preview_header(title: str) -> None:
    emit(f'\n{SEP2}')
    emit(f'📁 {title}')
    emit(SEP2)


def _print_preview_footer(total: int, parts: list[tuple[str, int]]) -> None:
    emit(SEP)
    pieces = [f'合计: {total} 项']
    pieces += [f'{label}: {n}' for label, n in parts if n]
    emit(' | '.join(pieces))
    emit(SEP)


def _iter_authored_cards(items: Iterable[object]) -> Iterator[tuple[int, object, bool]]:
    """逐项 yield (idx_from_1, item, is_new_author)。author 切换时返回 True。"""
    last = None
    for idx, item in enumerate(items, 1):
        author    = getattr(item, 'author', '')
        is_new    = (author != last)
        last      = author
        yield idx, item, is_new


# ═══════════════════════════════════════════════════════════════════════════════
# 源文件重命名预览
# ═══════════════════════════════════════════════════════════════════════════════

def print_sourcefile_preview(plans: list[SourcefilePlan]) -> None:
    """以可读格式打印源文件重命名计划。"""
    changed   = [p for p in plans if p.changed]
    unchanged = [p for p in plans if not p.changed]
    reviews   = [p for p in plans if p.needs_review]
    warns     = [p for p in plans if p.info and p.info.warnings]

    _print_preview_header('漫画重命名预览')

    if changed:
        emit(f'\n✅ 将重命名 ({len(changed)} 个):\n')
        for idx, p, is_new in _iter_authored_cards(changed):
            if is_new:
                emit(f'  📂 {p.author}')
            note = ' 🟡 需审核' if p.needs_review else ''
            emit(f'     📄 [{idx:>3}]')
            if p.info is not None:
                emit_parse_debug(p.info)
            emit(f'       旧: {p.old_name}')
            emit(f'       新: {highlight_diff(p.old_name, p.new_name, RED)}{note}')
            if p.info:
                for w in p.info.warnings:
                    emit(f'       🟡 {w}')
                emit(f'       Path:\n       {p.author_dir}\\{p.old_name}\n')
            emit()
    else:
        emit('\n没有需要改名的项目。')

    if unchanged: emit(f'➡️   无需修改: {len(unchanged)} 个')
    if reviews:   emit(f'🟡  需人工审核: {len(reviews)} 个')
    if warns:     emit(f'🟡  有警告:    {len(warns)} 个')

    _print_preview_footer(
        len(plans),
        [('需改名', len(changed)), ('需审核', len(reviews)), ('警告', len(warns))],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Metadata 预览（结构与 sourcefile 对齐）
# ═══════════════════════════════════════════════════════════════════════════════

def print_metadata_preview(plans: list[MetadataPlan]) -> None:
    """打印 ComicInfo 写入计划，按作者分组、逐卡片渲染。

    结构对齐 print_sourcefile_preview：相同的 header / 作者分组 / 卡片
    布局 / footer，仅卡片体换成 ComicInfo 字段块。

    每张卡片头部标注本次状态：
      - 出版商冲突
      - 已是最新（existing == new，幂等跳过）
      - 待写入
    """
    changed   = [p for p in plans if p.writable and p.changed]
    unchanged = [p for p in plans if p.writable and not p.changed]
    conflict  = [p for p in plans if not p.writable]
    warns     = [p for p in plans if p.mi.warnings]

    _print_preview_header('ComicInfo 写入预览')

    if plans:
        emit(f'\n✅ 写入计划 ({len(plans)} 项):\n')
        for idx, p, is_new in _iter_authored_cards(plans):
            if is_new:
                emit(f'  📂 {p.author}')
            if not p.writable:
                note = ' 🟡 出版商冲突'
            elif not p.changed:
                note = ' — 已是最新'
            else:
                note = ''
            emit(f'     📄 [{idx:>3}] {p.filename}{note}')
            emit_parse_debug(p.mi)
            # ComicInfo 字段比 Path 多一级缩进，区分"数据块" vs "元信息行"
            print_metadata_fields(p.fields, p.pub_conflict, indent='         ')
            for w in p.mi.warnings:
                emit(f'       🟡 {w}')
            cur_enc = p.existing_encoding or '—'
            new_enc = p.new_encoding
            enc_line = (f'{cur_enc} → {new_enc}' if cur_enc != new_enc
                        else cur_enc)
            emit(f'       Encoding: {enc_line}')
            emit(f'       Path:\n       {p.cbz_path}\n')
            emit()
    else:
        emit('\n没有需要处理的 CBZ 文件。')

    if unchanged: emit(f'➡️   已是最新: {len(unchanged)} 个')
    if conflict:  emit(f'⛔  出版商冲突: {len(conflict)} 个')
    if warns:     emit(f'🟡  有警告:    {len(warns)} 个')

    _print_preview_footer(
        len(plans),
        [('待写入', len(changed)), ('已是最新', len(unchanged)),
         ('冲突',   len(conflict)), ('警告',     len(warns))],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Metadata 字段块（ComicInfo 字段名为 spec 名，不做改动）
# ═══════════════════════════════════════════════════════════════════════════════

def print_metadata_fields(
    fields:       dict[str, str],
    pub_conflict: list[str] | None = None,
    *,
    indent:       str = '     ',
) -> None:
    """以 'TagName: value' 格式打印 ComicInfo 字段（标签与 DEBUG 同栏对齐）。"""
    col_w = max(len(t) for t in COMICINFO_TAGS) + 2     # 'Tag: ' 列宽（含冒号 + 空格）
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
