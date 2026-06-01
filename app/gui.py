"""媒体工作台总入口（单窗口装载 manga + artifact 两个业务模块）。

可通过 ``uv run app-gui`` 启动；保留 ``manga-gui`` / ``artifact-gui`` 单模块入口，
便于只需用单一业务时启动。启动顺序：

1. :func:`~base.gui.app_check.check_pyside6` 体检 PySide6
2. 触发 :mod:`~module.manga.core.runtime_config` /
   :mod:`~module.artifact.workflow.classify.config` 首次加载，确保
   ``<user_config>/media-toolkit/config/`` 三个 JSON 已落盘
3. 构造 :class:`~base.gui.shell.Shell` + 依次注册
   :class:`~module.manga.gui.module.MangaModule` /
   :class:`~module.artifact.gui.module.ArtifactModule`
4. 首次注册的 :meth:`MangaModule.default_sink` 被
   :func:`~base.console.set_output`；运行时各 module 自己的子 Tab 触发任务前
   再 ``set_output`` 到对应 sink，路由互不干扰
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
    from base.gui.shell import Shell
    from module.artifact.gui.module import ArtifactModule
    from module.artifact.workflow.classify.config import load_config as _load_artifact
    from module.manga import __version__
    from module.manga.core.runtime_config import get_manga_config
    from module.manga.gui.module import MangaModule

    # 启动期确保两份业务 JSON 已落盘（缺失则用默认值生成）
    get_manga_config()
    _load_artifact()

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    shell = Shell(
        title=f'media-toolkit  —  manga {__version__}',
        config_key_prefix='media',
    )
    mm = MangaModule()
    shell.register_module('manga', mm, default_sink=mm.default_sink())
    shell.register_module('artifact', ArtifactModule())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
