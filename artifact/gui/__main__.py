"""
__main__.py — 适配 `python -m artifact.gui` 调用 / PyInstaller 入口。

实际实现位于 artifact.gui 包的 main()；此处仅做转发。
"""
import sys

from artifact.gui import main

if __name__ == '__main__':
    sys.exit(main())
