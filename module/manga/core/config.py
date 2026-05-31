"""全局默认配置（可通过 CLI 参数覆盖）。"""

from module.manga import __version__

# ── rename-kit ────────────────────────────────────────────────────────────────

# 留空：强制用户通过 ``--root`` 指定
DEFAULT_ROOT_DIR: str = ""

FILE_EXTS: frozenset[str] = frozenset({".zip", ".cbz"})

# ── meta-kit ──────────────────────────────────────────────────────────────────

SCRIPT_NAME: str    = "manga-cli"
SCRIPT_VERSION: str = __version__

COMICINFO_FILENAME: str = "ComicInfo.xml"

#: ComicInfo 字段顺序，XML 写入与终端打印共用（单一来源）
COMICINFO_TAGS: list[str] = [
    "Publisher", "Writer", "Title", "Volume", "Number",
    "Series", "Format", "LanguageISO", "Genre", "Tags", "PageCount", "Notes",
]

#: 用于统计 ``<PageCount>`` 的图片后缀（小写，含点号）
PAGE_EXTS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".bmp", ".gif",
    ".psd", ".webp", ".avif", ".jxl",
})
