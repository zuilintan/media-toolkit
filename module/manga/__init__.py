"""
manga-toolkit — 漫画文件整理工具集

分层架构:
    core/      — 纯数据层（config / models / patterns）
    infra/     — 基础设施层（utils / console）
    naming/    — 名称解析与构建（parser / builder）
    workflow/  — 高层工作流（scanner / comicinfo）
    cli/       — 命令行子命令（examples / rename / comicinfo）
    data/      — 随包数据（examples.json）

CLI 入口:
    cli/__init__.py             — main() 与 build_parser() 主入口
    cli/<subcmd>.py             — 各子命令具体实现
    __main__.py                 — 适配 `python -m manga` 调用

console 命令:
    manga-cli           — 由 pyproject.toml 注册，指向 manga.cli:main
    manga-gui           — 由 pyproject.toml 注册，指向 manga.gui:main

子命令:
    rename     — 批量重命名漫画文件 / 目录
    comicinfo  — 向 CBZ 写入 ComicInfo.xml
"""

from base import __version__  # noqa: F401
