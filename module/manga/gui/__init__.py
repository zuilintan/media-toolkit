"""``manga-gui`` 入口（PySide6 桌面前端，单模块视图）。

启动顺序: 体检 PySide6 → 触发 manga.json 落盘 → setup_logging → 构造 ``Shell``
+ 注册 :class:`~module.manga.gui.module.MangaModule` → 启动事件循环。

完全复用 :mod:`~module.manga.workflow` 的 plan / apply；不调 ``cli.cmd_*``
（后者用 ``input()`` 阻塞确认，与 GUI 互斥）。
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='media-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run manga-gui',
        doctor_cmd='uv run manga-cli doctor',
    )

    from PySide6.QtWidgets import QApplication

    from base.console import setup_logging
    from base.gui.palette import stylesheet
    from base.gui.shell import Shell
    from module.manga import __version__
    from module.manga.core.runtime_config import get_manga_config
    from module.manga.gui.module import MangaModule

    # 启动期确保 manga.json 已落盘
    get_manga_config()

    app = QApplication(argv if argv is not None else sys.argv)
    app.setStyleSheet(stylesheet())
    setup_logging(debug=False)

    shell = Shell(
        title=f'media-toolkit  —  manga {__version__}',
        config_key_prefix='manga-only',
    )
    module = MangaModule()
    shell.register_module('manga', module, default_sink=module.default_sink())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
