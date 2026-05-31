"""
manga.gui — PySide6 桌面前端（manga-toolkit 单模块视图）

包入口 ``main()`` 对应 pyproject scripts 的 ``manga-gui``，启动顺序：
  1. 体检 PySide6（共用 base.gui.app_check）
  2. set_default_app_dir_name + setup_logging
  3. 构造 Shell + 注册 MangaModule（首次注册自动 set_output 到默认 sink）
  4. 启动事件循环

完全复用 manga.workflow 的 plan/apply 函数，不再走 manga.cli.cmd_*
（cmd_* 内部用 input() 阻塞确认，不适配 GUI）。

模块布局:
    module.py        — MangaModule（QSplitter + 4 子 Tab + 独立日志栈）
    tabs/            — 4 个子命令独立 Tab
    workers/         — QThread 后台任务包装
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='manga-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run manga-gui',
        doctor_cmd='uv run manga-cli doctor',
    )

    from PySide6.QtWidgets import QApplication

    from base.console import setup_logging
    from base.gui.config import set_default_app_dir_name
    from base.gui.shell import Shell
    from manga import __version__
    from manga.gui.module import MangaModule

    set_default_app_dir_name('manga-toolkit')

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    shell = Shell(
        title=f'manga-toolkit  —  {__version__}',
        config_key_prefix='manga-only',
    )
    module = MangaModule()
    shell.register_module('manga', module, default_sink=module.default_sink())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
