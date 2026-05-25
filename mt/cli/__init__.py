"""
mt.cli — 命令行子命令实现

各子命令拆分为独立模块，由 mt.manga_toolkit_cli 组装为统一 CLI:
    examples.py   — 内置示例数据加载与展示（sourcefile / metadata 共用一份数据）
    sourcefile.py — sourcefile 子命令（源文件批量重命名）
    metadata.py   — metadata 子命令（向 CBZ 写入 ComicInfo.xml）
"""
