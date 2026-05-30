"""
app.py — PySide6 桌面入口

启动顺序
--------
1. 体检：PySide6 是否安装；未装则打印中文指引退出（避免裸 ImportError 让用户懵）
2. 创建 QApplication
3. 创建 QtSink，**先** 调用 mt.infra.console.set_output(sink)，把后续所有
   emit() 的目的地切到 GUI；这必须在创建 MainWindow / 任何 plan 调用前完成
4. 构造 MainWindow，把 sink 注入它，由它连接到 LogView
5. 启动事件循环

可通过 `uv run manga-toolkit-gui` 启动（见 pyproject scripts）。
"""

from __future__ import annotations
import sys


# PySide6 上游 wheel 覆盖范围（与 pyproject.toml 的 python marker 保持一致）
PYSIDE6_PY_MIN = (3, 10)
PYSIDE6_PY_MAX_EXCL = (3, 14)


def _python_in_pyside6_range() -> bool:
    v = sys.version_info[:2]
    return PYSIDE6_PY_MIN <= v < PYSIDE6_PY_MAX_EXCL


def _check_pyside6() -> None:
    """检测 PySide6 是否可用；不可用时给出可执行的解决步骤。

    分两种失败场景给出不同指引：
    1) 当前 Python 不在 PySide6 wheel 覆盖范围 → 引导切 venv
    2) Python 在范围内但 PySide6 没装 → 引导 ``uv sync --extra gui``
    """
    try:
        import PySide6  # noqa: F401
        return
    except ImportError:
        pass

    py = f'{sys.version_info.major}.{sys.version_info.minor}'
    lo  = f'{PYSIDE6_PY_MIN[0]}.{PYSIDE6_PY_MIN[1]}'
    hi  = f'{PYSIDE6_PY_MAX_EXCL[0]}.{PYSIDE6_PY_MAX_EXCL[1] - 1}'

    if _python_in_pyside6_range():
        # 场景 2：版本 OK，只是没装
        sys.stderr.write(
            f'\n❌ 未检测到 PySide6（当前 Python {py}）\n\n'
            '原因: 你忘了带 `--extra gui` 安装可选依赖组。\n\n'
            '解决:\n'
            '  uv sync --extra gui\n'
            '  uv run manga-toolkit-gui\n\n'
            '体检命令: uv run manga-toolkit-cli doctor\n'
        )
    else:
        # 场景 1：版本超出 PySide6 支持区间
        sys.stderr.write(
            f'\n❌ 未检测到 PySide6（当前 Python {py}）\n\n'
            f'原因: PySide6 官方 wheel 仅覆盖 Python {lo}–{hi}，\n'
            f'你当前环境是 {py}，`uv sync --extra gui` 时被静默跳过。\n\n'
            f'解决: 用 uv 切到 {lo}–{hi} 区间内的 Python 重建 venv，例如 Python 3.13：\n'
            '  uv python install 3.13\n'
            '  uv sync --extra gui --python 3.13\n'
            '  uv run manga-toolkit-gui\n\n'
            '体检命令: uv run manga-toolkit-cli doctor\n'
        )
    sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    _check_pyside6()

    # 通过体检后才导入 Qt，避免装饰器/类构造在 import 阶段失败
    from PySide6.QtWidgets import QApplication

    from mt.gui.main_window import MainWindow
    from mt.infra.console import setup_logging

    app = QApplication(argv if argv is not None else sys.argv)

    setup_logging(debug=False)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
