"""``make_meta`` 预览的批量导出（CSV / JSON）。

万级 CBZ 的预览看「特例」走 :func:`~module.manga.presentation.view.print_make_meta_preview`
的分组采样；要做整批审查 / 跨工具二次处理时则导出本模块的结构化数据，
扔进 Excel / 文本编辑器筛选。

格式由目标文件后缀决定（``.csv`` / ``.json``），由 :func:`export_plans` 分派。
"""

from __future__ import annotations
import csv
import json
from pathlib import Path

from module.manga.core.config import COMICINFO_TAGS
from module.manga.core.models import MakeMetaPlan


def _status(plan: MakeMetaPlan) -> str:
    if not plan.writable:
        return 'conflict'
    if not plan.changed:
        return 'unchanged'
    return 'changed' if plan.existing_xml is not None else 'new'


def _plan_to_record(plan: MakeMetaPlan) -> dict:
    """把单个 plan 序列化为扁平 dict（JSON 友好；CSV 由调用方再展平）。"""
    return {
        'path':            plan.cbz_path,
        'filename':        plan.filename,
        'status':          _status(plan),
        'writable':        plan.writable,
        'changed':         plan.changed,
        'diff_keys':       sorted(plan.diff_keys),
        'warnings':        list(plan.mi.warnings),
        'pub_conflict':    plan.pub_conflict or [],
        'page_count':      plan.page_count,
        'existing_encoding': plan.existing_encoding,
        'new_encoding':    plan.new_encoding,
        'fields':          dict(plan.fields),
        'existing_fields': dict(plan.existing_fields),
    }


def _write_json(plans: list[MakeMetaPlan], path: Path) -> None:
    records = [_plan_to_record(p) for p in plans]
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _write_csv(plans: list[MakeMetaPlan], path: Path) -> None:
    """扁平化每个 plan 为一行；按 :data:`~module.manga.core.config.COMICINFO_TAGS`
    展开 ``{tag}.old`` / ``{tag}.new`` 双列，便于 Excel 筛选与对照。
    """
    base_cols = [
        'path', 'filename', 'status', 'writable', 'changed',
        'diff_keys', 'warnings', 'pub_conflict',
        'page_count', 'existing_encoding', 'new_encoding',
    ]
    diff_cols = [f'{t}.{side}' for t in COMICINFO_TAGS for side in ('old', 'new')]
    cols = base_cols + diff_cols

    # newline='' 是 csv 模块对 Windows 的标准要求，避免空行
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in plans:
            rec = _plan_to_record(p)
            row = {
                'path':              rec['path'],
                'filename':          rec['filename'],
                'status':            rec['status'],
                'writable':          rec['writable'],
                'changed':           rec['changed'],
                'diff_keys':         '|'.join(rec['diff_keys']),
                'warnings':          '|'.join(rec['warnings']),
                'pub_conflict':      '|'.join(rec['pub_conflict']),
                'page_count':        rec['page_count'],
                'existing_encoding': rec['existing_encoding'],
                'new_encoding':      rec['new_encoding'],
            }
            for tag in COMICINFO_TAGS:
                row[f'{tag}.old'] = rec['existing_fields'].get(tag, '')
                row[f'{tag}.new'] = rec['fields'].get(tag, '')
            w.writerow(row)


_WRITERS = {
    '.json': _write_json,
    '.csv':  _write_csv,
}


def export_plans(plans: list[MakeMetaPlan], path: str | Path) -> Path:
    """按 ``path`` 后缀分派序列化（``.csv`` / ``.json``）。

    :raises ValueError: 后缀不在 ``.csv`` / ``.json`` 之列。
    :return: 实际写入的绝对路径，供调用方提示用户。
    """
    p   = Path(path)
    ext = p.suffix.lower()
    if ext not in _WRITERS:
        raise ValueError(
            f'不支持的导出格式: {ext!r}（仅支持 .csv / .json）'
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    _WRITERS[ext](plans, p)
    return p.resolve()
