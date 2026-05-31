"""漫画文件整理工具集（CLI + 可选 GUI）。

分层架构:

- :mod:`~module.manga.core`         纯数据层（config / models / patterns）
- :mod:`~module.manga.infra`        基础设施（plan 调度 + 进度反馈）
- :mod:`~module.manga.naming`       名称解析与构建
- :mod:`~module.manga.workflow`     高层工作流（每个 *-kit 一个模块）
- :mod:`~module.manga.presentation` 表示层（领域对象 → 终端视图）
- :mod:`~module.manga.cli`          CLI 入口与 *-kit 子命令实现
- :mod:`~module.manga.extras`       旁路辅助（doctor + examples）
- :mod:`~module.manga.gui`          桌面 GUI（PySide6，可选依赖）
- ``data/``                          随包数据（``examples.json``）

console 入口（由 ``pyproject.toml`` 注册）:

- ``manga-cli`` → :func:`module.manga.cli.main`
- ``manga-gui`` → :func:`module.manga.gui.main`

子命令: ``rename-kit`` / ``meta-kit`` / ``cover-kit`` / ``pack-kit`` / ``doctor``。
"""

from base import __version__  # noqa: F401
