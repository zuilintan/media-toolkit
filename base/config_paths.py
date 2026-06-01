"""跨平台用户配置目录定位（独立于 PySide6，CLI/GUI 都可调用）。

三平台约定::

    Windows : %LOCALAPPDATA%/<app>           （fallback: ~/AppData/Local/<app>）
    macOS   : ~/Library/Application Support/<app>
    Linux   : $XDG_CONFIG_HOME/<app>         （fallback: ~/.config/<app>）
"""

from __future__ import annotations
import os
import sys
from pathlib import Path


def user_config_dir(app_name: str) -> Path:
    """返回 ``<user_config>/<app_name>`` 的 Path（不自动创建）。"""
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or str(
            Path.home() / 'AppData' / 'Local'
        )
    elif sys.platform == 'darwin':
        base = str(Path.home() / 'Library' / 'Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / app_name
