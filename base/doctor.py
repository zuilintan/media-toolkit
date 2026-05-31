"""
base/doctor.py — 通用环境体检引擎

提供 run_doctor(checks) 供各 CLI 的 doctor 子命令调用，各模块只需声明
自身所需的包列表，无需重复实现检查与渲染逻辑。

CheckSpec: (显示名, distribution 名, 所属组, 安装提示)

输出形如::

    Python:    3.13.3       ✅
    zhconv:    1.4.3        ✅
    Pillow:    12.2.0       ✅
    PySide6:   未安装        ⚠️  uv sync --extra gui

依赖: 仅标准库 + base.console
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from base.console import emit


# PySide6 上游 wheel 支持的 Python 版本区间（与 base.gui.app_check 保持一致）
PYSIDE6_PY_MIN = (3, 10)
PYSIDE6_PY_MAX_EXCL = (3, 14)

# 类型别名：(显示名, distribution 名, 所属组, 安装提示)
CheckSpec = tuple[str, str, str, str]


def _python_status() -> tuple[str, str]:
    v = sys.version_info
    py = f'{v.major}.{v.minor}.{v.micro}'
    in_range = PYSIDE6_PY_MIN <= (v.major, v.minor) < PYSIDE6_PY_MAX_EXCL
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


def run_doctor(checks: list[CheckSpec]) -> int:
    """打印环境体检表；任一项异常时返回 1，全部正常返回 0。"""
    rows: list[tuple[str, str, str]] = []

    py_ver, py_note = _python_status()
    rows.append(('Python', py_ver, py_note))

    pyside6_in_range = PYSIDE6_PY_MIN <= sys.version_info[:2] < PYSIDE6_PY_MAX_EXCL

    for label, dist, _group, hint in checks:
        ver, note = _pkg_status(dist, hint)
        # PySide6 在 Python 超范围时本就装不上：把缺失提示降级为说明，
        # 避免给用户两个看似独立的错误。
        if label == 'PySide6' and ver == '未安装' and not pyside6_in_range:
            note = 'ℹ️  当前 Python 不在 PySide6 支持区间，详见上方 Python 行'
        rows.append((label, ver, note))

    name_w = max(len(r[0]) for r in rows)
    ver_w  = max(len(r[1]) for r in rows)
    for name, ver, note in rows:
        emit(f'  {name:<{name_w}}  {ver:<{ver_w}}  {note}')

    return 1 if any('⚠️' in r[2] for r in rows) else 0
