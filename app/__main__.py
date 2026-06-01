"""适配 ``python -m app`` 调用 / PyInstaller 入口。

实际实现位于 :func:`app.gui.main`；此处仅做转发。
"""
import sys

from app.gui import main

if __name__ == '__main__':
    sys.exit(main())
