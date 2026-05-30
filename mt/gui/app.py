"""
app.py — PySide6 桌面入口（manga-toolkit 单模块视图）

启动顺序
--------
1. 体检：PySide6 是否安装；未装则打印中文指引退出
2. 设置默认 GUI 配置目录名（base.gui.config）
3. 创建 QApplication
4. 构造 Shell + 注册 MangaModule（首次注册自动 set_output 到默认 sink）
5. 启动事件循环

可通过 ``uv run mt-gui`` 启动。

阶段 D：MainWindow → MangaModule + Shell 拆分；窗口几何由 shell 持久化，
splitter 状态由 module 自己持久化。
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='manga-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run mt-gui',
        doctor_cmd='uv run mt-cli doctor',
    )

    from PySide6.QtWidgets import QApplication

    from base.console import setup_logging
    from base.gui.config import set_default_app_dir_name
    from base.gui.shell import Shell
    from mt import __version__
    from mt.gui.module import MangaModule

    set_default_app_dir_name('manga-toolkit')

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    shell = Shell(
        title=f'manga-toolkit  —  {__version__}',
        config_key_prefix='mt-only',
    )
    module = MangaModule()
    shell.register_module('manga', module, default_sink=module.default_sink())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
