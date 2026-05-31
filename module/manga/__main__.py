"""``python -m module.manga`` 调用入口；转发到 :func:`module.manga.cli.main`。"""
from module.manga.cli import main

if __name__ == '__main__':
    import sys
    sys.exit(main())
