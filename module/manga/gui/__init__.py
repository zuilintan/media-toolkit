"""``manga-gui`` 入口（PySide6 桌面前端，单模块视图）。

启动顺序: 体检 PySide6 → 设置 app dir / logging → 构造 ``Shell`` + 注册
:class:`~module.manga.gui.module.MangaModule` → 启动事件循环。

完全复用 :mod:`~module.manga.workflow` 的 plan / apply；不调 ``cli.cmd_*``
（后者用 ``input()`` 阻塞确认，与 GUI 互斥）。
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
    from module.manga import __version__
    from module.manga.gui.module import MangaModule

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
