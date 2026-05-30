"""
app.py — PySide6 桌面入口（file-toolkit 单模块视图）

启动顺序
--------
1. 体检 PySide6（共用 base.gui.app_check）
2. 设置默认 GUI 配置目录名（base.gui.config）
3. 创建 QApplication
4. 构造 Shell + 注册 FtModule
5. 启动事件循环

可通过 ``uv run ft-gui`` 启动。
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
    from base.gui.shell import Shell
    from ft.gui.module import FtModule

    set_default_app_dir_name('file-toolkit')

    app = QApplication(argv if argv is not None else sys.argv)
    setup_logging(debug=False)

    shell = Shell(title='file-toolkit', config_key_prefix='ft-only')
    module = FtModule()
    shell.register_module('files', module, default_sink=module.default_sink())
    shell.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
