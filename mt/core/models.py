"""
models.py — 核心数据模型

依赖: 无（纯数据，不导入项目内其他模块）
"""

from __future__ import annotations
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════════════════════
# 数字格式化
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_num(v: float) -> str:
    """将数字格式化为两位整数或含小数的字符串。

    Examples:
        1   → "01"
        4.5 → "04.5"
    """
    i = int(v)
    if v == i:
        return f"{i:02d}"
    return f"{i:02d}.{str(v).split('.')[1]}"


# ═══════════════════════════════════════════════════════════════════════════════
# Chapter
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Chapter:
    """表示话数：单话、连续范围，或附带额外附录词的章节组合（CH. 前缀）。

    Attributes:
        start: 起始话数，如 1、2.5。
        end:   终止话数（范围模式），None 表示单话。
        bonus: 附加在末尾的附录词，空字符串表示无附录。
               常见值：'番外篇'、'后日谈'，以及未来可能出现的其他词汇。

    格式化示例:
        Chapter(4.5)                    → "CH.04.5"
        Chapter(1, 5)                   → "CH.01-05"
        Chapter(1, 5, bonus='番外篇')   → "CH.01-05+番外篇"
        Chapter(1, 5, bonus='后日谈')   → "CH.01-05+后日谈"
    """
    start: float
    end:   float | None = None
    bonus: str          = ""

    def __str__(self) -> str:
        s = f"CH.{fmt_num(self.start)}"
        if self.end is not None:
            s += f"-{fmt_num(self.end)}"
        if self.bonus:
            s += f"+{self.bonus}"
        return s

    def number_str(self) -> str:
        """仅数字部分，不含 'CH.' 前缀，供 ComicInfo <Number> 使用。

        Examples:
            Chapter(1, 5)                  → "01-05"
            Chapter(1, 5, bonus='番外篇')  → "01-05+番外篇"
        """
        s = fmt_num(self.start)
        if self.end is not None:
            s += f"-{fmt_num(self.end)}"
        if self.bonus:
            s += f"+{self.bonus}"
        return s


# ═══════════════════════════════════════════════════════════════════════════════
# Volume
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Volume:
    """表示卷数：仅单卷（VOL. 前缀）。

    格式化示例:
        Volume(2) → "VOL.02"
    """
    start: float

    def __str__(self) -> str:
        return f"VOL.{fmt_num(self.start)}"


# ═══════════════════════════════════════════════════════════════════════════════
# MangaInfo
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MangaInfo:
    """解析后的漫画元数据。

    Attributes:
        author:        作者名。
        main_title:    主标题。
        volume:        卷数对象（None 表示无卷信息）。
        chapter:       话数对象（None 表示无话数信息）。
        chapter_title: 话标题文本（不含 ～ 定界符）。
        series:        系列名。
        translation:   译名（不含 ¦ 定界符）。
        language:      语言代码：'zh'、'ja'、'ko'、'en'、'zxx' 或 ''。
        is_uncensored: 是否无修正。
        is_colorized:  是否彩色化。
        is_ongoing:    是否连载中。
        part_tag:      分编标记（非数字章节分类词）。三类：
                         附录类（与 CH. 同级且互斥）：番外篇 / 后日谈
                         结构类（与 CH. 同级且互斥）：上篇 / 中篇 / 下篇
                         合集类（作为 [总集篇] tag 输出）：总集篇
        original:      解析前的原始输入字符串。
    """
    author:        str
    main_title:    str
    volume:        Volume  | None = None
    chapter:       Chapter | None = None
    chapter_title: str            = ""
    series:        str            = ""
    translation:   str            = ""
    language:      str            = ""
    is_uncensored: bool           = False
    is_colorized:  bool           = False
    is_ongoing:    bool           = False
    part_tag:      str            = ""
    original:      str            = ""

    @property
    def warnings(self) -> list[str]:
        """解析后发现的非阻断性问题，用于在预览/处理流程中提示用户。"""
        warns: list[str] = []
        if not self.language:
            warns.append('缺少语言标签')
        return warns


# ═══════════════════════════════════════════════════════════════════════════════
# RenamePlan
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RenamePlan:
    """单个条目的重命名计划。

    Attributes:
        author_dir: 作者目录路径（字符串，便于 JSON 序列化）。
        author:     作者名。
        old_name:   原始文件/目录名（含后缀）。
        new_name:   目标文件/目录名（含后缀）。
        info:       解析后的 MangaInfo（解析失败时为 None）。
        is_file:    True 为文件，False 为目录。
        suffix:     文件后缀（含点号），目录时为空字符串。
    """
    author_dir: str
    author:     str
    old_name:   str
    new_name:   str
    info:       MangaInfo | None
    is_file:    bool
    suffix:     str

    @property
    def changed(self) -> bool:
        """名称是否发生变化。"""
        return self.old_name != self.new_name

    @property
    def needs_review(self) -> bool:
        """主标题过短（< 2 字），需人工审核。"""
        return self.info is not None and len(self.info.main_title) < 2
