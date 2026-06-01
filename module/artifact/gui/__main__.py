"""适配 ``python -m module.artifact.gui`` 调用 / PyInstaller 入口。

实际实现位于 :func:`module.artifact.gui.main`；此处仅做转发。
"""
import sys

from module.artifact.gui import main

if __name__ == '__main__':
    sys.exit(main())
