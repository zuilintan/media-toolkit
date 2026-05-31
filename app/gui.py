"""
gui.py — 媒体工作台总入口（单窗口装载 manga + artifact 两个业务模块）

启动顺序
--------
1. 体检 PySide6（共用 base.gui.app_check）
2. set_default_app_dir_name('media-toolkit')   — 双模块共用一份配置目录
3. 构造 Shell + 依次注册 MangaModule / ArtifactModule
4. 首次注册的 MangaModule.default_sink 被 set_output；运行时各 module
   自己的子 Tab 触发任务前再 set_output 到对应 sink，路由互不干扰

可通过 ``uv run app-gui`` 启动（pyproject scripts）。

注：保留 manga-gui / artifact-gui 单模块入口，便于只需用单一业务时启动。
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='media-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run app-gui',
        doctor_cmd='uv run manga-cli doctor',
    )

    from PySide6.QtWidgets import QApplication

    from base.console import setup_logging
    from base.gui.config import set_default_app_dir_name
    from base.gui.shell import Shell
    from module.artifact.gui.module import ArtifactModule
    from module.manga import __version__
    from module.manga.gui.module import MangaModule

    set_default_app_dir_name('media-toolkit')

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    shell = Shell(
        title=f'media-toolkit  —  manga {__version__}',
        config_key_prefix='media',
    )
    mm = MangaModule()
    shell.register_module('manga', mm, default_sink=mm.default_sink())
    shell.register_module('files', ArtifactModule())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
