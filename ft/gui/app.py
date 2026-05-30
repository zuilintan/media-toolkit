"""
app.py — PySide6 桌面入口（file-toolkit）

启动顺序
--------
1. 体检 PySide6（共用 base.gui.app_check）
2. 设置默认 GUI 配置目录名（base.gui.config）— 必须早于任何 PathPicker
3. 创建 QApplication
4. 构造 MainWindow（内部 set_output(QtSink) 接管输出到日志框）
5. 启动事件循环

可通过 ``uv run ft-gui`` 启动（pyproject scripts）。

阶段 D 会把 MainWindow 重构为 ModuleWidget，被顶层单窗口 shell 装载。
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='file-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run ft-gui',
    )

    from PySide6.QtWidgets import QApplication

    from base.console import setup_logging
    from base.gui.config import set_default_app_dir_name
    from ft.gui.main_window import MainWindow

    set_default_app_dir_name('file-toolkit')

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
