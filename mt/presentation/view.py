"""
view.py — 领域对象的终端渲染

提供:
  - print_run_banner()          — 命令运行 banner（sourcefile / metadata 共用）
  - print_sourcefile_preview()  — 源文件重命名计划预览（按作者分组的卡片表）
  - print_metadata_preview()    — ComicInfo 写入计划预览（结构对齐 sourcefile）
  - print_metadata_diff_table() — ComicInfo 字段「旧/新」两列 diff 表格
                                  （metadata 预览 & examples 共用）

依赖: core.models / core.config / infra.console / naming.parser
"""

from __future__ import annotations
import os
import unicodedata

from mt.core.models import CoverPlan, MangaInfo, MetadataPlan, SourcefilePlan
from mt.core.config import COMICINFO_TAGS
from mt.infra.console import SEP, SEP2, RED, YELLOW, RESET, highlight_diff, emit
from mt.naming.parser import emit_parse_debug


# ── 显示宽度工具（中文 / 全角字符占 2 列）─────────────────────────────────────
def _vis_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


def _pad(s: str, w: int) -> str:
    """按显示宽度右侧补空格。"""
    return s + ' ' * max(0, w - _vis_width(s))


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


# ═══════════════════════════════════════════════════════════════════════════════
# 源文件重命名预览
# ═══════════════════════════════════════════════════════════════════════════════

def print_sourcefile_preview(plans: list[SourcefilePlan]) -> None:
    """以可读格式打印源文件重命名计划。

    卡片骨架与 run_sourcefile_examples 对齐：
      ``   📄 [N]{note}``   (3 空格)
      ``     DEBUG: …``     (5 空格，与 emit_parse_debug formatter 一致)
      ``     旧: …``        (5 空格)
      ``     新: …``        (5 空格)
    """
    changed   = [p for p in plans if p.changed]
    unchanged = [p for p in plans if not p.changed]
    reviews   = [p for p in plans if p.needs_review]
    warns     = [p for p in plans if p.info and p.info.warnings]

    _print_preview_header('漫画重命名预览')

    if changed:
        emit(f'\n计划处理: {len(changed)} 个\n')
        for idx, p in enumerate(changed, 1):
            note = ' 🟡 需审核' if p.needs_review else ''
            emit(f'   📄 [{idx}]{note}')
            if p.info is not None:
                emit_parse_debug(p.info)
            emit(f'     旧: {p.old_name}')
            emit(f'     新: {highlight_diff(p.old_name, p.new_name, RED)}')
            if p.info:
                for w in p.info.warnings:
                    emit(f'     🟡 {w}')
            emit()
    else:
        emit('\n没有需要改名的项目。')

    if unchanged: emit(f'无需处理: {len(unchanged)} 个')
    if reviews:   emit(f'🟡  需人工审核: {len(reviews)} 个')
    if warns:     emit(f'🟡  有警告:    {len(warns)} 个')

    _print_preview_footer(
        len(plans),
        [('计划处理', len(changed)), ('需审核', len(reviews)), ('警告', len(warns))],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Metadata 预览（结构与 sourcefile 对齐）
# ═══════════════════════════════════════════════════════════════════════════════

def print_metadata_preview(plans: list[MetadataPlan]) -> None:
    """打印 ComicInfo 写入计划，逐卡片渲染。

    卡片骨架与 print_sourcefile_preview / run_*_examples 对齐：
      ``   📄 [N] {filename}``   (3 空格)
      ``     DEBUG: …``          (5 空格)
      ``     {diff_table}``      (5 空格)
      ``     Encoding: …``       (5 空格)

    只渲染 ``writable && changed`` 的卡片；其余（已是最新 / 出版商冲突
    / 有警告）仅作计数提示。
    """
    changed   = [p for p in plans if p.writable and p.changed]
    unchanged = [p for p in plans if p.writable and not p.changed]
    conflict  = [p for p in plans if not p.writable]
    warns     = [p for p in plans if p.mi.warnings]

    _print_preview_header('ComicInfo 写入预览')

    if changed:
        emit(f'\n计划处理: {len(changed)} 个\n')
        for idx, p in enumerate(changed, 1):
            emit(f'   📄 [{idx}] {p.filename}')
            emit_parse_debug(p.mi)
            print_metadata_diff_table(
                p.existing_fields, p.fields, p.pub_conflict,
                indent='     ',
            )
            for w in p.mi.warnings:
                emit(f'     🟡 {w}')
            cur_enc = p.existing_encoding or '—'
            new_enc = p.new_encoding
            enc_line = (f'{cur_enc} → {new_enc}' if cur_enc != new_enc
                        else cur_enc)
            emit(f'     Encoding: {enc_line}')
            emit()
    else:
        emit('\n没有需要写入的 ComicInfo.xml。')

    if unchanged: emit(f'无需处理: {len(unchanged)} 个')
    if conflict:  emit(f'⛔  出版商冲突: {len(conflict)} 个')
    if warns:     emit(f'🟡  有警告:    {len(warns)} 个')

    _print_preview_footer(
        len(plans),
        [('计划处理', len(changed)), ('无需处理', len(unchanged)),
         ('冲突',   len(conflict)), ('警告',     len(warns))],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Metadata 字段块（ComicInfo 字段名为 spec 名，不做改动）
# ═══════════════════════════════════════════════════════════════════════════════

def print_metadata_diff_table(
    old_fields:   dict[str, str],
    new_fields:   dict[str, str],
    pub_conflict: list[str] | None = None,
    *,
    indent:       str = '         ',
) -> None:
    """旧/新两列表格，行标题为 ComicInfo.xml 的标签。

    - 列标题: 旧 / 新
    - 行标题: COMICINFO_TAGS 中的每个 tag
    - 新列差异字符用 RED 高亮（与 sourcefile 卡片体的 highlight_diff 对齐）
    - 行尾「*」标记本行新旧不一致（含字段从无到有 / 从有到无）
    - Publisher 出版商冲突时在表下追加冲突文件列表
    """
    tag_w = max(len(t) for t in COMICINFO_TAGS)
    old_w = max(_vis_width('旧'), *(_vis_width(old_fields.get(t, '')) for t in COMICINFO_TAGS))
    new_w = max(_vis_width('新'), *(_vis_width(new_fields.get(t, '')) for t in COMICINFO_TAGS))

    sep = f'{indent}{"─"*tag_w}  {"─"*old_w}  {"─"*new_w}'
    emit(f'{indent}{_pad("Tag", tag_w)}  {_pad("旧", old_w)}  {_pad("新", new_w)}')
    emit(sep)
    for tag in COMICINFO_TAGS:
        ov = old_fields.get(tag, '')
        nv = new_fields.get(tag, '')
        if ov == nv:
            new_cell = _pad(nv, new_w)
            marker   = ''
        else:
            colored  = highlight_diff(ov, nv, RED)
            # ANSI 转义不占显示宽度，按原 nv 宽度补齐
            new_cell = colored + ' ' * max(0, new_w - _vis_width(nv))
            marker   = f'  {YELLOW}*{RESET}'
        emit(f'{indent}{_pad(tag, tag_w)}  {_pad(ov, old_w)}  {new_cell}{marker}')
    emit(sep)

    if pub_conflict:
        emit(f'{indent}🟡 Publisher: 多个社团文件，请手动确认！')
        for p in pub_conflict:
            emit(f'{indent}  • {os.path.basename(p)}')


# ═══════════════════════════════════════════════════════════════════════════════
# Cover 预览（结构对齐 sourcefile / metadata）
# ═══════════════════════════════════════════════════════════════════════════════

def print_cover_preview(plans: list[CoverPlan]) -> None:
    """打印封面写入计划，逐卡片渲染。

    目标文件名取决于源图：源 ``0001.*`` → ``0000.webp``；源 ``cover.*``
    → ``cover.webp``。

    卡片骨架：
      ``   📄 [N] {filename}{ 🔁 替换}``  (3 空格)
      ``     源:   {src_name} {W}×{H}``   (5 空格)
      ``     目标: {dst_name} {W}×{H} [mode]``

    只渲染 ``writable && changed`` 的卡片；其余（已是最新 / 跳过）仅计数提示。
    """
    changed   = [p for p in plans if p.writable and p.changed]
    unchanged = [p for p in plans if p.writable and not p.changed]
    failed    = [p for p in plans if not p.writable]
    replaced  = [p for p in changed if p.replaced]

    _print_preview_header('封面写入预览')

    if changed:
        emit(f'\n计划处理: {len(changed)} 个\n')
        for idx, p in enumerate(changed, 1):
            note = ' 🔁 替换现有' if p.replaced else ''
            emit(f'   📄 [{idx}] {p.filename}{note}')
            sw, sh = p.src_size or (0, 0)
            dw, dh = p.dst_size or (0, 0)
            emit(f'     源:   {p.src_name}  {sw}×{sh}')
            emit(f'     目标: {p.dst_name}  {dw}×{dh}  [{p.mode}]')
            emit()
    else:
        emit('\n没有需要写入的封面。')

    if unchanged:
        emit(f'无需处理: {len(unchanged)} 个')
    if failed:
        emit(f'⛔ 跳过 ({len(failed)} 个):')
        for p in failed:
            emit(f'   • {p.filename} — {p.error or "无源图"}')

    _print_preview_footer(
        len(plans),
        [('计划处理', len(changed)), ('替换现有', len(replaced)),
         ('无需处理', len(unchanged)), ('跳过', len(failed))],
    )
