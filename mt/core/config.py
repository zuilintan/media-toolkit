"""
config.py — 全局默认配置

所有可通过 CLI 参数覆盖的默认值都集中在此处。
"""

from mt import __version__  # 版本号唯一来源

# ── 重命名工具 ──────────────────────────────────────────────────────────────

# 批量模式默认扫描根目录（留空，强制用户通过 --root 指定）
DEFAULT_ROOT_DIR: str = ""

# 操作记录文件路径（相对当前工作目录）
SESSIONS_FILE: str = "rename_sessions.json"

# 支持处理的文件后缀
FILE_EXTS: frozenset[str] = frozenset({".zip", ".cbz"})

# ── ComicInfo 工具 ─────────────────────────────────────────────────────────

SCRIPT_NAME: str    = "mt-cli"
SCRIPT_VERSION: str = __version__

# ComicInfo.xml 文件名（ZIP 内）
COMICINFO_FILENAME: str = "ComicInfo.xml"

# ComicInfo 字段顺序（XML 写入与终端打印共用，单一来源）
COMICINFO_TAGS: list[str] = [
    "Publisher", "Writer", "Title", "Volume", "Number",
    "Series", "Format", "LanguageISO", "Genre", "Tags", "PageCount", "Notes",
]

# 用于统计 <PageCount> 的图片文件后缀（小写，含点号）
PAGE_EXTS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".bmp", ".gif",
    ".psd", ".webp", ".avif", ".jxl",
})
