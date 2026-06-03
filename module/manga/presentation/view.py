"""领域对象的终端渲染（banner / 卡片预览 / diff 表格）。"""

from __future__ import annotations
import os
import unicodedata

from module.manga.core.models import MakeCoverPlan, MakeMetaPlan, PackPicPlan, StdTitlePlan
from module.manga.core.config import COMICINFO_TAGS
from base.console import SEP, SEP2, RED, YELLOW, RESET, highlight_diff, emit
from module.manga.naming.parser import emit_parse_debug


# ── 显示宽度工具（中文 / 全角字符占 2 列）─────────────────────────────────────
def _vis_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


def _pad(s: str, w: int) -> str:
    """按显示宽度右侧补空格。"""
    return s + ' ' * max(0, w - _vis_width(s))


# ═══════════════════════════════════════════════════════════════════════════════
# 运行 banner（所有子命令共用）
# ═══════════════════════════════════════════════════════════════════════════════

def print_run_banner(cmd: str, subtitle: str, root: object, mode_apply: bool) -> None:
    """统一的命令运行 banner：``═══`` + 命令标题 + 根目录 + 模式。

    具体「找到 N 项」一行因各子命令的扫描成本和 DEBUG 时序而异，由调用方在
    banner 之后自行追加。
    """
    emit(SEP2)
    emit(f'  manga-cli  —  {cmd} ({subtitle})')
    emit(SEP2)
    emit(f'  根目录:   {root}')
    emit(f'  模式:     '
         f'{"【写入模式】实际修改文件" if mode_apply else "【预览模式】仅展示解析结果，不修改文件"}')


# ═══════════════════════════════════════════════════════════════════════════════
# 卡片骨架（所有子命令共用）
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

def print_std_title_preview(plans: list[StdTitlePlan]) -> None:
    """逐卡片打印源文件重命名计划。

    卡片骨架与 :func:`~module.manga.extras.examples.run_std_title_examples` 对齐：

    - ``   📄 [N]{note}``   (3 空格)
    - ``     DEBUG: …``     (5 空格，与 :func:`~module.manga.naming.parser.emit_parse_debug` 一致)
    - ``     旧: …``        (5 空格)
    - ``     新: …``        (5 空格)
    """
    changed   = [p for p in plans if p.changed]
    unchanged = [p for p in plans if not p.changed]
    reviews   = [p for p in plans if p.needs_review]
    warns     = [p for p in plans if p.info and p.info.warnings]

    _print_preview_header('预览')

    if changed:
        emit()
        for idx, p in enumerate(changed, 1):
            note = ' 🟡 需审核' if p.needs_review else ''
            emit(f'   📄 [{idx}]{note}')
            if p.info is not None:
                emit_parse_debug(p.info)
            emit(f'     旧: {p.old_name}')
            if p.old_name != p.new_name:
                emit(f'     新: {highlight_diff(p.old_name, p.new_name, RED)}')
            src_parent = os.path.dirname(p.src_path)
            if os.path.normcase(src_parent) != os.path.normcase(p.author_dir):
                emit(f'     📁 归入: ./{os.path.basename(p.author_dir)}/')
            if p.publisher_file:
                emit(f'     📌 标识: {os.path.basename(p.publisher_file)}')
            if p.info:
                for w in p.info.warnings:
                    emit(f'     🟡 {w}')
            emit()
    else:
        emit('\n没有需要改名的项目。')


    if reviews:   emit(f'🟡  需人工审核: {len(reviews)} 个')
    if warns:     emit(f'🟡  有警告:    {len(warns)} 个')

    _print_preview_footer(
        len(plans),
        [('计划处理', len(changed)), ('无需处理', len(unchanged)),
         ('需审核', len(reviews)), ('警告', len(warns))],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# make_meta 预览（结构与 std_title 对齐）
# ═══════════════════════════════════════════════════════════════════════════════

def emit_make_meta_card(plan: MakeMetaPlan, idx: int) -> None:
    """单个 ComicInfo 计划的完整卡片（diff 表 + warnings + encoding 行）。"""
    emit(f'   📄 [{idx}] {plan.filename}')
    emit_parse_debug(plan.mi)
    print_make_meta_diff_table(
        plan.existing_fields, plan.fields, plan.pub_conflict,
        indent='     ',
    )
    for w in plan.mi.warnings:
        emit(f'     🟡 {w}')
    cur_enc = plan.existing_encoding or '—'
    new_enc = plan.new_encoding
    enc_line = (f'{cur_enc} → {new_enc}' if cur_enc != new_enc
                else cur_enc)
    emit(f'     Encoding: {enc_line}')
    emit()


def diff_signature(plan: MakeMetaPlan) -> tuple[bool, frozenset[str]]:
    """分组键：``(是否首次新增 ComicInfo.xml, 改动字段集合)``。"""
    return (plan.existing_xml is None, plan.diff_keys)


def format_signature(is_new: bool, keys: frozenset[str]) -> str:
    """分组键的人类可读形式：``新增 [Publisher+Tags]`` / ``修改 [Title]``。"""
    tag = '新增' if is_new else '修改'
    key_str = '+'.join(sorted(keys)) if keys else '(无字段变动)'
    return f'{tag} [{key_str}]'


def print_make_meta_preview(
    plans: list[MakeMetaPlan],
    *,
    sample_per_group: int = 3,
    rare_threshold:   int = 5,
) -> None:
    """按差异签名分组渲染 ComicInfo 写入计划，避免万级文件下日志爆炸。

    分组键 = ``(是否首次新增 XML, 改动字段集合)``。各组按出现次数降序输出：

    - **稀有组**（``count ≤ rare_threshold``）→ 全量渲染（用户真正想审的特例）
    - **常见组** → 仅渲染前 ``sample_per_group`` 个样本卡，其余折叠为计数行
    - ``sample_per_group == 0`` 时强制全量渲染（小批量场景退化为旧行为）

    冲突 / 警告同样采样输出（默认前 ``sample_per_group``）以兼顾"看全特例"和"不刷屏"。

    :param plans: :func:`~module.manga.workflow.make_meta.preview_plans` 的产物。
    :param sample_per_group: 常见组的样本卡数；``0`` 表示全量。
    :param rare_threshold:   出现次数 ≤ 此值的组视为稀有，强制全量渲染。
    """
    changed   = [p for p in plans if p.writable and p.changed]
    unchanged = [p for p in plans if p.writable and not p.changed]
    conflict  = [p for p in plans if not p.writable]
    warns     = [p for p in plans if p.mi.warnings]

    _print_preview_header('预览')

    if changed:
        # ── 分组 + 汇总 ────────────────────────────────────────────────
        groups: dict[tuple[bool, frozenset[str]], list[MakeMetaPlan]] = {}
        for p in changed:
            groups.setdefault(diff_signature(p), []).append(p)
        sorted_groups = sorted(groups.items(), key=lambda kv: -len(kv[1]))

        emit(f'\n📊 计划处理 {len(changed)} 个，共 {len(groups)} 类差异：')
        for (is_new, keys), gp in sorted_groups:
            mark = '  ⚠ 稀有' if len(gp) <= rare_threshold else ''
            emit(f'   • {format_signature(is_new, keys)} ─ {len(gp)} 个{mark}')

        # ── 逐组渲染（稀有 → 全量；常见 → 前 K 个样本）─────────────────
        for (is_new, keys), gp in sorted_groups:
            is_rare = len(gp) <= rare_threshold
            show_n  = (
                len(gp)
                if sample_per_group <= 0 or is_rare
                else min(sample_per_group, len(gp))
            )
            note = '稀有，全量' if is_rare and len(gp) > 1 else ''
            emit(f'\n{SEP}')
            head = f'   ▸  {format_signature(is_new, keys)} ─ {len(gp)} 个'
            emit(f'{head}{f"（{note}）" if note else ""}')
            emit(SEP)
            for idx, p in enumerate(gp[:show_n], 1):
                emit_make_meta_card(p, idx)
            if show_n < len(gp):
                emit(f'   … 另有 {len(gp) - show_n} 个同类条目已折叠')
    else:
        emit('\n没有需要写入的 ComicInfo.xml。')

    # ── 冲突 / 警告（独立段，采样输出避免再次刷屏）──────────────────────
    cap = sample_per_group if sample_per_group > 0 else None
    if conflict:
        emit(f'\n⛔ 出版商冲突: {len(conflict)} 个（apply 阶段会自动跳过）')
        shown = conflict if cap is None else conflict[:cap]
        for p in shown:
            emit(f'   • {p.filename}')
            for pc in (p.pub_conflict or []):
                emit(f'     - {os.path.basename(pc)}')
        if cap is not None and len(conflict) > cap:
            emit(f'   … 另有 {len(conflict) - cap} 个未列出')

    if warns:
        emit(f'\n🟡 有警告: {len(warns)} 个')
        shown = warns if cap is None else warns[:cap]
        for p in shown:
            emit(f'   • {p.filename}: {", ".join(p.mi.warnings)}')
        if cap is not None and len(warns) > cap:
            emit(f'   … 另有 {len(warns) - cap} 个未列出')

    _print_preview_footer(
        len(plans),
        [('计划处理', len(changed)), ('无需处理', len(unchanged)),
         ('冲突',   len(conflict)), ('警告',     len(warns))],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# make_meta 字段块（ComicInfo 字段名为 spec 名，不做改动）
# ═══════════════════════════════════════════════════════════════════════════════

def print_make_meta_diff_table(
    old_fields:   dict[str, str],
    new_fields:   dict[str, str],
    pub_conflict: list[str] | None = None,
    *,
    indent:       str = '         ',
) -> None:
    """旧 / 新两列表格，行标题为 :data:`~module.manga.core.config.COMICINFO_TAGS` 中的每个 tag。

    - 新列差异字符用 RED 高亮（与 :func:`print_std_title_preview` 的
      :func:`~base.console.highlight_diff` 对齐）
    - 行尾 ``*`` 标记本行新旧不一致（含字段从无到有 / 从有到无）
    - ``pub_conflict`` 非空时在表下追加冲突文件列表
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
# make_cover 预览（结构对齐 std_title / make_meta）
# ═══════════════════════════════════════════════════════════════════════════════

def print_make_cover_preview(plans: list[MakeCoverPlan]) -> None:
    """逐卡片打印封面写入计划。

    目标文件名取决于源图：源 ``0001.*`` 或 ``cover.*`` → ``0000.webp``
    （``cover.*`` 写入后会从 ZIP 中删除自身）。只渲染 ``writable && changed``
    的卡片；其余（已是最新 / 跳过）仅计数提示。
    """
    changed   = [p for p in plans if p.writable and p.changed]
    unchanged = [p for p in plans if p.writable and not p.changed]
    failed    = [p for p in plans if not p.writable]
    replaced  = [p for p in changed if p.replaced]

    _print_preview_header('预览')

    if changed:
        emit()
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


# ═══════════════════════════════════════════════════════════════════════════════
# Pack 预览（结构对齐 std_title / make_meta / make_cover）
# ═══════════════════════════════════════════════════════════════════════════════

def print_pack_pic_preview(plans: list[PackPicPlan]) -> None:
    """逐卡片打印打包计划。

    只渲染 ``writable`` 卡片；不可写（无图 / 错误）仅作计数提示。卡片骨架：

    - ``   📄 [N] {name}  [单层|嵌套×K]{ 🔁 覆盖现有 zip}``
    - ``     图片: {n_total}（改名 {n_renamed}）``
    - ``     zip:  {zip_path}``
    - ``     首末: 0001.ext … 0123.ext`` （≥ 2 张时）
    - ``     🟡 N 项非图片不进 zip，将随源目录一并删除: …`` （有 ``extras`` 时）
    """
    writable = [p for p in plans if p.writable]
    failed   = [p for p in plans if not p.writable]
    replaced = [p for p in writable if p.zip_exists]
    nested   = [p for p in writable if p.kind == 'nested']

    _print_preview_header('预览')

    if writable:
        emit()
        for idx, p in enumerate(writable, 1):
            kind_tag = (f'[嵌套×{p.n_subdirs}]' if p.kind == 'nested'
                        else '[单层]')
            note = ' 🔁 覆盖现有 zip' if p.zip_exists else ''
            emit(f'   📄 [{idx}] {p.name}  {kind_tag}{note}')
            emit(f'     图片: {len(p.renames)}（改名 {p.n_renamed}）')
            emit(f'     zip:  {p.zip_path}')
            if len(p.renames) >= 2:
                first_new = p.renames[0][1]
                last_new  = p.renames[-1][1]
                emit(f'     首末: {first_new} … {last_new}')
            elif p.renames:
                emit(f'     首末: {p.renames[0][1]}')
            if p.extras:
                preview_extras = ', '.join(p.extras[:5])
                more = f'，… 等 {len(p.extras)} 项' if len(p.extras) > 5 else ''
                emit(f'     🟡 {len(p.extras)} 项非图片不进 zip，'
                     f'将随源目录一并删除: {preview_extras}{more}')
            emit()
    else:
        emit('\n没有需要打包的单位。')

    if failed:
        emit(f'⛔ 跳过 ({len(failed)} 个):')
        for p in failed:
            emit(f'   • {p.name} — {p.error or "无图片"}')

    _print_preview_footer(
        len(plans),
        [('计划处理', len(writable)), ('嵌套', len(nested)),
         ('覆盖现有', len(replaced)), ('跳过', len(failed))],
    )
