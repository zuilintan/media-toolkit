"""
examples.py — 内置示例数据加载与演示运行器

示例数据集中存放于 ``module/manga/data/examples.json``，每条为
``{"author", "i", "e"}``（i=input, e=expected），由 rename-kit 与 meta-kit
两个子命令的 ``--examples`` 选项共用:

  - rename-kit 使用 (author, i, e)，验证「输入 → 规范化输出」转换；
  - meta-kit  使用 (author, e)，将规范化文件名解析为 ComicInfo 字段并展示。

依赖: naming.parser / naming.builder / workflow.meta_kit / infra.console / presentation
"""

from __future__ import annotations

import json
from pathlib import Path

from module.manga.core.config import COMICINFO_TAGS
from module.manga.naming.parser import parse_name, emit_parse_debug
from module.manga.naming.builder import build_new_name
from module.manga.workflow.meta_kit import collect_fields, _extract_publisher_name
from base.console import highlight_diff, SEP2, RED, GREEN, emit, print_summary
from module.manga.presentation.view import print_meta_kit_diff_table

# 示例数据文件（随包分发）
_DATA_PATH = Path(__file__).resolve().parent.parent / 'data' / 'examples.json'

# meta_kit 示例用的模拟出版商文件名
_EXAMPLES_PUBLISHER_FILE = '[社团]：青年晚报.txt'


def load_examples() -> list[tuple[str, str, str]]:
    """加载示例数据，返回 (author, input, expected) 三元组列表。"""
    raw = json.loads(_DATA_PATH.read_text(encoding='utf-8'))
    author = raw['author']
    return [(author, e['i'], e['e']) for e in raw['cases']]


def run_rename_kit_examples() -> int:
    """运行内建示例测试，逐条验证「输入 → 规范化输出」解析结果。

    Returns:
        失败条数（0 表示全部通过），供调用方据此设定退出码。
    """
    emit(f'\n{SEP2}')
    emit('🧪 解析示例')
    emit(SEP2)
    fail = warn_n = 0
    for idx, (author, name, expected) in enumerate(load_examples(), 1):
        info   = parse_name(author, name)
        result = build_new_name(info)
        passed = result == expected
        if not passed:
            fail += 1
        if info.warnings:
            warn_n += 1
        mark = '✅' if passed else '❌'
        emit(f'   📄 [{idx}] {mark}')
        emit_parse_debug(info)
        emit(f'     旧: {name}')
        emit(f'     新: {highlight_diff(name, result, RED)}')
        if not passed:
            emit(f'     预期: {highlight_diff(result, expected, GREEN)}')
        for w in info.warnings:
            emit(f'     🟡 {w}')
        emit()
    parts = ['  全部通过 ✅' if not fail else f'  {fail} 个失败 ❌']
    if warn_n:
        parts.append(f'🟡 {warn_n} 个有警告')
    emit('   '.join(parts))
    emit()
    return fail


def run_meta_kit_examples() -> int:
    """将规范化文件名（示例的 expected）解析为 ComicInfo 字段并展示。

    Publisher 由常量模拟，PageCount 留空。

    Returns:
        失败条数（0 表示全部通过），供调用方据此设定退出码。
    """
    examples = load_examples()
    sim_pub  = _extract_publisher_name(_EXAMPLES_PUBLISHER_FILE)

    emit(SEP2)
    emit(f'  meta_kit  —  内置示例解析（共 {len(examples)} 条）')
    emit(f'  模拟出版商文件: {_EXAMPLES_PUBLISHER_FILE}  →  Publisher: {sim_pub}')
    emit(SEP2)

    ok_n = fail = warn_n = 0
    empty_old = {tag: '' for tag in COMICINFO_TAGS}
    for idx, (author, _input, expected) in enumerate(examples, 1):
        if not author:
            emit(f'   📄 [{idx}] ❌ 无法提取作者，跳过: {expected}')
            emit()
            fail += 1
            continue
        emit(f'   📄 [{idx}] {expected}')
        mi = parse_name(author, expected)
        emit_parse_debug(mi)
        fields = collect_fields(mi, sim_pub)
        # 旧列恒空（examples 模拟"首次写入"语义），新列即 build 结果
        print_meta_kit_diff_table(empty_old, fields, indent='     ')
        for w in mi.warnings:
            emit(f'     🟡 {w}')
        emit()
        if mi.warnings:
            warn_n += 1
        ok_n += 1

    emit(f'\n{SEP2}')
    print_summary(
        '示例解析完成',
        [('✅', ok_n, '成功'), ('🟡', warn_n, '警告'), ('❌', fail, '失败')],
    )
    emit(SEP2)
    return fail
