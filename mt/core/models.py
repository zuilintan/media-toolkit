"""
models.py — 核心数据模型

依赖: 无（纯数据，不导入项目内其他模块）
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass


# ── 内部工具 ────────────────────────────────────────────────────────────────
_XML_ENCODING_RE = re.compile(rb'<\?xml[^?]*?encoding=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)


def _detect_xml_encoding(xml_bytes: bytes | None) -> str:
    """从 ``<?xml … encoding="…"?>`` 提取编码名；无声明按 XML 规范默认 'utf-8'。"""
    if not xml_bytes:
        return ''
    m = _XML_ENCODING_RE.search(xml_bytes[:200])
    return m.group(1).decode('ascii', errors='replace') if m else 'utf-8'


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
# SourcefilePlan（sourcefile 子命令：源文件重命名计划）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SourcefilePlan:
    """单个源文件的重命名计划（sourcefile 子命令仅处理 .zip / .cbz 文件）。

    Attributes:
        author_dir: 作者目录路径（字符串，便于 JSON 序列化）。
        author:     作者名。
        old_name:   原始文件名（含后缀）。
        new_name:   目标文件名（含后缀）。
        info:       解析后的 MangaInfo（解析失败时为 None）。
    """
    author_dir: str
    author:     str
    old_name:   str
    new_name:   str
    info:       MangaInfo | None

    @property
    def changed(self) -> bool:
        """名称是否发生变化。"""
        return self.old_name != self.new_name

    @property
    def needs_review(self) -> bool:
        """主标题过短（< 2 字），需人工审核。"""
        return self.info is not None and len(self.info.main_title) < 2


# ═══════════════════════════════════════════════════════════════════════════════
# MetadataPlan（metadata 子命令：单个 CBZ 的 ComicInfo 写入计划）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MetadataPlan:
    """单个 CBZ 的 ComicInfo.xml 写入计划（解析阶段产出，写入阶段消费）。

    与 SourcefilePlan 一样属于「批量 plan → 整批 apply」流程的中间数据。

    plan 阶段即构建 new_xml（确定性），写入阶段直接复用，并据 ``changed``
    实现幂等：已有 ComicInfo.xml 完全一致则跳过。
    """
    cbz_path:     str
    mi:           MangaInfo
    publisher:    str | None
    pub_conflict: list[str] | None
    page_count:   int
    tags_val:     str
    fields:       dict[str, str]
    existing_xml: bytes | None     # 现有 ComicInfo.xml 原始字节（无则 None）
    new_xml:      bytes            # 本次构建的目标字节

    @property
    def writable(self) -> bool:
        """是否可写入：无出版商冲突即可。"""
        return not self.pub_conflict

    @property
    def changed(self) -> bool:
        """是否需要实际写入：无现有版本，或现有版本与目标不一致。"""
        return self.existing_xml is None or self.existing_xml != self.new_xml

    @property
    def existing_encoding(self) -> str:
        """现有 ComicInfo.xml 的声明编码；无现有版本返回 ''。"""
        return _detect_xml_encoding(self.existing_xml)

    @property
    def new_encoding(self) -> str:
        """目标 ComicInfo.xml 的声明编码（恒为 'utf-8'）。"""
        return _detect_xml_encoding(self.new_xml)

    @property
    def author(self) -> str:
        return self.mi.author

    @property
    def filename(self) -> str:
        return os.path.basename(self.cbz_path)
