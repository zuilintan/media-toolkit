"""
manga-toolkit — 漫画文件整理工具集

分层架构:
    core/      — 纯数据层（config / models / patterns）
    infra/     — 基础设施层（utils / console）
    naming/    — 名称解析与构建（parser / builder）
    workflow/  — 高层工作流（scanner / session / comicinfo）

CLI 入口:
    manga_toolkit_cli.py        — 统一命令行实现（PEP 8 模块名）
    __main__.py                 — 适配 `python -m mt` 调用

console 命令:
    manga-toolkit-cli           — 由 pyproject.toml 注册，指向 mt.manga_toolkit_cli:main

子命令:
    rename     — 批量重命名漫画文件 / 目录
    comicinfo  — 向 CBZ 写入 ComicInfo.xml
"""

__version__ = "0.1.0"
