"""
app_check.py — PySide6 安装/版本体检（GUI 入口共用）

各业务 GUI 入口（mt/gui/app.py、ft/gui/app.py 等）应在 main() 开头调用
``check_pyside6(...)``，把硬编码的提示信息（用什么命令安装、怎么诊断）参数化
传入，确保用户拿到的是适配自己包的可执行指引。
"""

from __future__ import annotations
import sys


# PySide6 上游 wheel 覆盖范围（与 pyproject.toml 的 python marker 保持一致）
PYSIDE6_PY_MIN = (3, 10)
PYSIDE6_PY_MAX_EXCL = (3, 14)


def _python_in_pyside6_range() -> bool:
    v = sys.version_info[:2]
    return PYSIDE6_PY_MIN <= v < PYSIDE6_PY_MAX_EXCL


def check_pyside6(
    *,
    app_name:       str,
    install_cmd:    str,
    run_cmd:        str,
    doctor_cmd:     str | None = None,
) -> None:
    """检测 PySide6 是否可用；不可用时给出可执行的解决步骤后 ``sys.exit(2)``。

    Args:
        app_name:    应用显示名（出现在 emoji 行后），用于错误提示开头。
        install_cmd: 推荐的安装命令（如 ``uv sync --extra gui``）。
        run_cmd:     成功安装后的启动命令（如 ``uv run mt-gui``）。
        doctor_cmd:  可选诊断命令（如 ``uv run mt-cli doctor``）。

    分两种失败场景给出不同指引：
      1) 当前 Python 不在 PySide6 wheel 覆盖范围 → 引导切 Python 版本
      2) Python 在范围内但 PySide6 没装 → 引导安装命令
    """
    try:
        import PySide6  # noqa: F401
        return
    except ImportError:
        pass

    py = f'{sys.version_info.major}.{sys.version_info.minor}'
    lo = f'{PYSIDE6_PY_MIN[0]}.{PYSIDE6_PY_MIN[1]}'
    hi = f'{PYSIDE6_PY_MAX_EXCL[0]}.{PYSIDE6_PY_MAX_EXCL[1] - 1}'
    doctor_line = f'体检命令: {doctor_cmd}\n' if doctor_cmd else ''

    if _python_in_pyside6_range():
        # 场景 2：版本 OK，只是没装
        sys.stderr.write(
            f'\n❌ 未检测到 PySide6（当前 Python {py}）—— {app_name}\n\n'
            '原因: 你忘了带 `--extra gui` 安装可选依赖组。\n\n'
            '解决:\n'
            f'  {install_cmd}\n'
            f'  {run_cmd}\n\n'
            f'{doctor_line}'
        )
    else:
        # 场景 1：版本超出 PySide6 支持区间
        sys.stderr.write(
            f'\n❌ 未检测到 PySide6（当前 Python {py}）—— {app_name}\n\n'
            f'原因: PySide6 官方 wheel 仅覆盖 Python {lo}–{hi}，\n'
            f'你当前环境是 {py}，`{install_cmd}` 时被静默跳过。\n\n'
            f'解决: 用 uv 切到 {lo}–{hi} 区间内的 Python 重建 venv，例如 Python 3.13：\n'
            '  uv python install 3.13\n'
            f'  {install_cmd} --python 3.13\n'
            f'  {run_cmd}\n\n'
            f'{doctor_line}'
        )
    sys.exit(2)
