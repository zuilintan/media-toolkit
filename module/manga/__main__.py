"""
__main__.py — 适配 `python -m manga` 调用。

实际实现位于 manga.cli 包的 main()；此处仅做转发。
"""
from module.manga.cli import main

if __name__ == '__main__':
    import sys
    sys.exit(main())
