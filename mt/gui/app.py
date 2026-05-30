"""
app.py — PySide6 桌面入口（manga-toolkit）

启动顺序
--------
1. 体检：PySide6 是否安装；未装则打印中文指引退出（避免裸 ImportError 让用户懵）
2. 创建 QApplication
3. 设置默认 GUI 配置目录名（base.gui.config）
4. 创建 QtSink，**先** 调用 base.console.set_output(sink)，把后续所有
   emit() 的目的地切到 GUI；这必须在创建 MainWindow / 任何 plan 调用前完成
5. 构造 MainWindow，把 sink 注入它，由它连接到 LogView
6. 启动事件循环

可通过 `uv run manga-toolkit-gui` 启动（见 pyproject scripts）。
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='manga-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run manga-toolkit-gui',
        doctor_cmd='uv run manga-toolkit-cli doctor',
    )

    # 通过体检后才导入 Qt，避免装饰器/类构造在 import 阶段失败
    from PySide6.QtWidgets import QApplication

    from base.gui.config import set_default_app_dir_name
    from mt.gui.main_window import MainWindow
    from base.console import setup_logging

    # 让下游 get_config()（path_picker、base_tab、main_window 等）拿到正确的
    # 配置目录；必须在创建 MainWindow / 任何 PathPicker 之前调用。
    set_default_app_dir_name('manga-toolkit')

    app = QApplication(argv if argv is not None else sys.argv)

    setup_logging(debug=False)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
