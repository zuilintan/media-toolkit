"""
doctor.py — manga-cli 环境体检子命令

声明 manga 所需的包并委托给 base.doctor.run_doctor 执行检查与渲染。
"""

from __future__ import annotations

import argparse

from base.doctor import CheckSpec, run_doctor

_CHECKS: list[CheckSpec] = [
    ('zhconv',    'zhconv',    'CLI/GUI 必选', 'uv sync'),
    ('Pillow',    'Pillow',    'CLI/GUI 必选', 'uv sync'),
    ('smartcrop', 'smartcrop', 'CLI/GUI 必选', 'uv sync'),
    ('PySide6',   'PySide6',   'GUI 可选',     'uv sync --extra gui'),
]


def add_doctor_args(p: argparse.ArgumentParser) -> None:
    del p


def cmd_doctor(args: argparse.Namespace) -> int:
    del args
    return run_doctor(_CHECKS)
