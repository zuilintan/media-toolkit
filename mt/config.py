"""
config.py — 全局默认配置

所有可通过 CLI 参数覆盖的默认值都集中在此处。
硬编码路径仅作占位，实际使用时请通过 --root / --target 传入。
"""

# ── 重命名工具 ──────────────────────────────────────────────────────────────

# 批量模式默认扫描根目录（留空，强制用户通过 --root 指定）
DEFAULT_ROOT_DIR: str = ""

# 拖入模式：处理完成后将作者目录移动至此（留空则不移动）
DEFAULT_DRAG_TARGET_DIR: str = ""

# 操作记录文件路径（相对当前工作目录）
SESSIONS_FILE: str = "rename_sessions.json"

# 支持处理的文件后缀
FILE_EXTS: frozenset[str] = frozenset({".zip", ".cbz"})

# ── ComicInfo 工具 ─────────────────────────────────────────────────────────

SCRIPT_NAME: str    = "manga-comicinfo"
SCRIPT_VERSION: str = "0.1.0"

# ComicInfo.xml 文件名（ZIP 内）
COMICINFO_FILENAME: str = "ComicInfo.xml"
