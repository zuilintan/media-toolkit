"""
console.py — 终端输出 & 统一日志

提供:
  - ANSI 颜色常量
  - debug() / info() / warn() / error() 日志函数
  - setup_logging()    — CLI 调用，设定日志级别
  - highlight_diff()   — 差异高亮
  - print_preview()    — 重命名预览
  - print_op_result()  — 操作统计行
  - SEP / SEP2         — 分隔线常量

依赖: core.models（RenamePlan）/ core.config（COMICINFO_TAGS）
"""

from __future__ import annotations
import inspect
import logging
import os
from itertools import zip_longest

from mt.core.models import RenamePlan
from mt.core.config import COMICINFO_TAGS

# ── ANSI 颜色 ─────────────────────────────────────────────────────────────────
RESET  = '\033[0m'
RED    = '\033[31m'
YELLOW = '\033[33m'
GREEN  = '\033[32m'
CYAN   = '\033[36m'

# ── 分隔线 ────────────────────────────────────────────────────────────────────
SEP  = '─' * 72
SEP2 = '═' * 72

# ── 内部 logger ───────────────────────────────────────────────────────────────
_log = logging.getLogger('mt')


def setup_logging(debug: bool = False) -> None:
    """初始化日志，debug=True 时输出调试信息到 stderr。"""
    level = logging.DEBUG if debug else logging.WARNING
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('     DEBUG: %(message)s'))
    _log.setLevel(level)
    if not _log.handlers:
        _log.addHandler(handler)


# ── 日志便捷函数 ──────────────────────────────────────────────────────────────

def debug(msg: str) -> None:
    """带调用函数名的调试日志（DEBUG 级别时输出）。"""
    frame = inspect.currentframe().f_back
    func  = frame.f_code.co_name
    _log.debug('[%s] → %s', func, msg)


def info(msg: str)  -> None: print(msg)
def warn(msg: str)  -> None: print(f'⚠️  {msg}')
def error(msg: str) -> None: print(f'❌ {msg}')
def ok(msg: str)    -> None: print(f'✅ {msg}')


# ═══════════════════════════════════════════════════════════════════════════════
# 差异高亮
# ═══════════════════════════════════════════════════════════════════════════════

def highlight_diff(original: str, new: str, color: str = RED) -> str:
    """逐字符比较两个字符串，将不同位置以 color 高亮。"""
    return ''.join(
        f'{color}{n}{RESET}' if o != n else n
        for o, n in zip_longest(original, new, fillvalue='')
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 操作统计
# ═══════════════════════════════════════════════════════════════════════════════

def print_op_result(ok_n: int, fail: int, skip: int = 0, label: str = '完成') -> None:
    """统一格式输出操作统计行。"""
    parts = [f'成功 {ok_n}', f'失败 {fail}']
    if skip:
        parts.append(f'跳过 {skip}')
    print(f'\n{label}: {" | ".join(parts)}')


# ═══════════════════════════════════════════════════════════════════════════════
# 重命名预览
# ═══════════════════════════════════════════════════════════════════════════════

def print_preview(plans: list[RenamePlan]) -> None:
    """以可读格式打印重命名计划。"""
    changed   = [p for p in plans if p.changed]
    unchanged = [p for p in plans if not p.changed]
    reviews   = [p for p in plans if p.needs_review]

    print(f'\n{SEP2}')
    print('📁 漫画重命名预览')
    print(SEP2)

    if changed:
        print(f'\n✅ 将重命名 ({len(changed)} 个):\n')
        last_author = None
        for idx, p in enumerate(changed, 1):
            if p.author != last_author:
                print(f'  📂 {p.author}')
                last_author = p.author
            icon = '📄' if p.is_file else '🗂 '
            note = ' ⚠️  需审核' if p.needs_review else ''
            print(f'    {icon} [{idx:>3}]')
            print(f'       旧: {p.old_name}')
            print(f'       新: {highlight_diff(p.old_name, p.new_name, RED)}{note}')
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
                    print(f'       Flag: {" | ".join(flags)}')
                print(f'       Path:\n       {p.author_dir}\\{p.old_name}\n')
            print()
    else:
        print('\n没有需要改名的项目。')

    if unchanged:
        print(f'➡️   无需修改: {len(unchanged)} 个')
    if reviews:
        print(f'⚠️   需人工审核: {len(reviews)} 个')
    print(SEP)
    print(f'合计: {len(plans)} 项 | 需改名: {len(changed)} | 需审核: {len(reviews)}')
    print(SEP)


# ═══════════════════════════════════════════════════════════════════════════════
# ComicInfo 字段打印
# ═══════════════════════════════════════════════════════════════════════════════

def print_comicinfo_fields(fields: dict[str, str],
                           pub_conflict: list[str] | None = None) -> None:
    """以 'TagName: value' 格式打印 ComicInfo 字段。"""
    for tag in COMICINFO_TAGS:
        if tag == 'Publisher' and pub_conflict:
            print(f'  {tag}: ⚠️  多个社团文件，请手动确认！')
            for p in pub_conflict:
                print(f'           • {os.path.basename(p)}')
        elif tag == 'Tags':
            val = fields.get(tag, '')
            suffix = '  (保留)' if val else ''
            print(f'  {tag}: {val}{suffix}')
        else:
            val = fields.get(tag, '')
            print(f'  {tag}: {val}' if val else f'  {tag}:')
