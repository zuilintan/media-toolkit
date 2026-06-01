"""PySide6 桌面前端（artifact 单模块视图）。

包入口 :func:`main` 对应 pyproject scripts 的 ``artifact-gui``，启动顺序：

1. :func:`~base.gui.app_check.check_pyside6` 体检 PySide6
2. 触发 :mod:`~module.artifact.workflow.classify.config` 首次加载，确保
   ``<user_config>/media-toolkit/config/artifact.json`` 已落盘
3. :func:`~base.console.setup_logging`
4. 构造 :class:`~base.gui.shell.Shell` + 注册
   :class:`~module.artifact.gui.module.ArtifactModule`
5. 启动事件循环
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='media-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run artifact-gui',
    )

    from PySide6.QtWidgets import QApplication

    from base.console import setup_logging
    from base.gui.shell import Shell
    from module.artifact.gui.module import ArtifactModule
    from module.artifact.workflow.classify.config import load_config

    # 启动期确保 artifact.json 已落盘
    load_config()

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    shell = Shell(title='media-toolkit  —  artifact',
                  config_key_prefix='artifact-only')
    module = ArtifactModule()
    shell.register_module('artifact', module, default_sink=module.default_sink())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
