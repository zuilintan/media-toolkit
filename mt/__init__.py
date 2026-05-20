"""
manga-toolkit — 漫画文件整理工具集

子模块:
    models     — 数据模型（Chapter / Volume / MangaInfo / RenamePlan）
    patterns   — 正则表达式常量
    utils      — 纯工具函数（无 I/O）
    console    — 终端输出 & 日志
    parser     — 文件名解析
    builder    — 新文件名构建
    scanner    — 目录扫描 & 重命名执行
    session    — 操作记录 & 回退
    comicinfo  — ComicInfo.xml 生成 & 写入

CLI 入口（由 pyproject.toml scripts 注册）:
    manga-rename      → cli.rename_cmd:main
    manga-comicinfo   → cli.comicinfo_cmd:main
"""

__version__ = "0.1.0"
