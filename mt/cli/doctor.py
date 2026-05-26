"""
doctor.py — 环境体检子命令

诊断 Python 版本与各依赖的安装状态，方便用户在提 issue 前自查、
也方便维护者快速定位问题。

输出形如::

    Python:    3.13.13      ✅
    zhconv:    1.4.3        ✅
    Pillow:    12.2.0       ✅
    smartcrop: 0.5.0        ✅
    PySide6:   未安装        ⚠️  poetry install --with gui

依赖: 仅标准库 + mt.infra.console
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from mt.infra.console import emit


# 与 mt/gui/app.py 保持一致：PySide6 上游 wheel 覆盖范围
PYSIDE6_PY_MIN = (3, 10)
PYSIDE6_PY_MAX_EXCL = (3, 14)

# 体检项：(显示名, distribution 名, 所属组, 安装提示)
# distribution 名按 PyPI 的规范名（大小写敏感处用 importlib.metadata 处理）
_CHECKS: list[tuple[str, str, str, str]] = [
    ('zhconv',    'zhconv',    'CLI/GUI 必选', 'poetry install'),
    ('Pillow',    'Pillow',    'CLI/GUI 必选', 'poetry install'),
    ('smartcrop', 'smartcrop', 'CLI/GUI 必选', 'poetry install'),
    ('PySide6',   'PySide6',   'GUI 可选',     'poetry install --with gui'),
]


def _python_status() -> tuple[str, str]:
    v = sys.version_info
    py = f'{v.major}.{v.minor}.{v.micro}'
    in_range = (
        PYSIDE6_PY_MIN <= (v.major, v.minor) < PYSIDE6_PY_MAX_EXCL
    )
    if in_range:
        return py, '✅'
    lo = f'{PYSIDE6_PY_MIN[0]}.{PYSIDE6_PY_MIN[1]}'
    hi = f'{PYSIDE6_PY_MAX_EXCL[0]}.{PYSIDE6_PY_MAX_EXCL[1] - 1}'
    return py, f'⚠️  PySide6 仅支持 Python {lo}–{hi}'


def _pkg_status(dist: str, hint: str) -> tuple[str, str]:
    try:
        return _pkg_version(dist), '✅'
    except PackageNotFoundError:
        return '未安装', f'⚠️  {hint}'


def add_doctor_args(p: argparse.ArgumentParser) -> None:
    # 当前没有可调参数；保留位置以便日后扩展（如 --verbose 列环境变量等）
    del p


def cmd_doctor(args: argparse.Namespace) -> int:
    """打印环境体检表；任一项异常时返回 1，全部正常返回 0。"""
    del args

    rows: list[tuple[str, str, str]] = []

    py_ver, py_note = _python_status()
    rows.append(('Python', py_ver, py_note))

    pyside6_in_range = (
        PYSIDE6_PY_MIN <= sys.version_info[:2] < PYSIDE6_PY_MAX_EXCL
    )

    for label, dist, _group, hint in _CHECKS:
        ver, note = _pkg_status(dist, hint)
        # PySide6 在 Python 超范围时本就装不上：把缺失提示降级为说明，
        # 避免给用户两个看似独立的错误。
        if (
            label == 'PySide6'
            and ver == '未安装'
            and not pyside6_in_range
        ):
            note = 'ℹ️  当前 Python 不在 PySide6 支持区间，详见上方 Python 行'
        rows.append((label, ver, note))

    # 列宽
    name_w = max(len(r[0]) for r in rows)
    ver_w  = max(len(r[1]) for r in rows)
    for name, ver, note in rows:
        emit(f'  {name:<{name_w}}  {ver:<{ver_w}}  {note}')

    # 任一项有 ⚠️ 返回 1，便于脚本判断
    has_issue = any('⚠️' in r[2] for r in rows)
    return 1 if has_issue else 0
