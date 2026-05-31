"""``python -m module.manga.gui`` / PyInstaller 入口；转发到 :func:`module.manga.gui.main`。"""
import sys

from module.manga.gui import main

if __name__ == '__main__':
    sys.exit(main())
