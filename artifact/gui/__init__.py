"""
artifact.gui — PySide6 桌面前端（file-toolkit 单模块视图）

包入口 ``main()`` 对应 pyproject scripts 的 ``artifact-gui``，启动顺序：
  1. 体检 PySide6（共用 base.gui.app_check）
  2. set_default_app_dir_name + setup_logging
  3. 构造 Shell + 注册 FtModule
  4. 启动事件循环

模块布局:
    module.py        — FtModule（QSplitter + 顶部 QTabWidget + 独立日志栈）
    tabs/            — 业务子 Tab（当前仅 classify_tab）
    widgets/         — 业务专属部件（drop_area / candidate_dialog）
"""

from __future__ import annotations
import sys

from base.gui.app_check import check_pyside6


def main(argv: list[str] | None = None) -> int:
    check_pyside6(
        app_name='file-toolkit',
        install_cmd='uv sync --extra gui',
        run_cmd='uv run artifact-gui',
    )

    from PySide6.QtWidgets import QApplication

    from base.console import setup_logging
    from base.gui.config import set_default_app_dir_name
    from base.gui.shell import Shell
    from artifact.gui.module import FtModule

    set_default_app_dir_name('file-toolkit')

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    shell = Shell(title='file-toolkit', config_key_prefix='artifact-only')
    module = FtModule()
    shell.register_module('files', module, default_sink=module.default_sink())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
