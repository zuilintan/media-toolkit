"""
mt.cli — 命令行子命令实现

各子命令拆分为独立模块，由 mt.manga_toolkit_cli 组装为统一 CLI:
    examples.py   — 内置示例数据加载与展示（rename / comicinfo 共用一份数据）
    rename.py     — rename 子命令
    comicinfo.py  — comicinfo 子命令
"""
