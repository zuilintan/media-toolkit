"""跨业务模块的共通基础设施（manga / artifact 共用）。

:mod:`base.gui` 内的模块依赖 PySide6，按需懒导入；其余子模块仅依赖标准库。
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("media-toolkit")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
