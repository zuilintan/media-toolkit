"""核心数据模型（纯数据，不导入项目内其他模块）。"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass
from pathlib import Path


_XML_ENCODING_RE = re.compile(rb'<\?xml[^?]*?encoding=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)


def _detect_xml_encoding(xml_bytes: bytes | None) -> str:
    """从 ``<?xml … encoding="…"?>`` 提取编码名；无声明按 XML 规范默认 ``utf-8``。"""
    if not xml_bytes:
        return ''
    m = _XML_ENCODING_RE.search(xml_bytes[:200])
    return m.group(1).decode('ascii', errors='replace') if m else 'utf-8'


# ═══════════════════════════════════════════════════════════════════════════════
# 数字格式化
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_num(v: float) -> str:
    """两位整数格式（``1 → "01"``, ``4.5 → "04.5"``）。"""
    i = int(v)
    if v == i:
        return f"{i:02d}"
    return f"{i:02d}.{str(v).split('.')[1]}"


# ═══════════════════════════════════════════════════════════════════════════════
# Chapter
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Chapter:
    """话数：单话、连续范围或附带 ``bonus`` 附录词（``CH.`` 前缀）。

    示例: ``Chapter(4.5)`` → ``CH.04.5``、``Chapter(1, 5, bonus='番外篇')`` → ``CH.01-05+番外篇``。

    :ivar start: 起始话数。
    :ivar end:   终止话数（范围模式），``None`` 表示单话。
    :ivar bonus: 附录词（``番外篇`` / ``后日谈`` 等），空串表示无附录。
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
        """仅数字部分，不含 ``CH.`` 前缀，供 ComicInfo ``<Number>`` 使用。"""
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
    """卷数（``VOL.`` 前缀），如 ``Volume(2)`` → ``VOL.02``。"""
    start: float

    def __str__(self) -> str:
        return f"VOL.{fmt_num(self.start)}"


# ═══════════════════════════════════════════════════════════════════════════════
# MangaInfo
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MangaInfo:
    """解析后的漫画元数据，由 :func:`~module.manga.naming.parser.parse_name` 产出。

    :ivar part_tag: 分编标记（非数字章节分类词），三类：

        - 附录类：``番外篇`` / ``后日谈``（与 ``CH.`` 同级且互斥）
        - 结构类：``上篇`` / ``中篇`` / ``下篇``（与 ``CH.`` 同级且互斥）
        - 合集类：``总集篇``（作为 ``[总集篇]`` tag 输出）
    :ivar language: 语言代码（``zh`` / ``ja`` / ``ko`` / ``en`` / ``zxx`` / ``''``）。
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
        """解析后发现的非阻断性问题，用于在预览 / 处理流程中提示用户。"""
        warns: list[str] = []
        if not self.language:
            warns.append('缺少语言标签')
        return warns


# ═══════════════════════════════════════════════════════════════════════════════
# StdTitlePlan
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StdTitlePlan:
    """单个源文件（``.zip`` / ``.cbz``）的标题标准化重命名计划。

    :ivar src_path:       源文件完整路径（apply 阶段 rename 的源端）。
    :ivar author_dir:     **目标**作者目录完整路径；apply 时必要时创建。
        批量模式下与 ``src_path`` 父目录一致；单文件模式下当 ``[]`` 抽取的作者
        与父目录不一致时，会指向父目录下新建的 ``{author}/`` 子目录。
    :ivar publisher_file: 发版商标识文件完整路径（``[社团]：XX.txt``），仅在
        ``[社团 (作者)]`` 形态被采纳时非 ``None``；apply 阶段幂等落盘。
    """
    src_path:       str
    author_dir:     str
    author:         str
    old_name:       str
    new_name:       str
    info:           MangaInfo | None
    publisher_file: str | None = None

    @property
    def changed(self) -> bool:
        return (
            self.old_name != self.new_name
            or Path(self.src_path).parent != Path(self.author_dir)
        )

    @property
    def needs_review(self) -> bool:
        """主标题过短（< 2 字），需人工审核。"""
        return self.info is not None and len(self.info.main_title) < 2


# ═══════════════════════════════════════════════════════════════════════════════
# MakeMetaPlan
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MakeMetaPlan:
    """单个 CBZ 的 ``ComicInfo.xml`` 元数据写入计划。

    plan 阶段即构建 ``new_xml``（确定性），apply 阶段直接复用并据 :attr:`changed`
    实现幂等：已有 ``ComicInfo.xml`` 与目标完全一致则跳过。
    """
    cbz_path:        str
    mi:              MangaInfo
    publisher:       str | None
    pub_conflict:    list[str] | None
    page_count:      int
    tags_val:        str
    fields:          dict[str, str]  #: 本次构建的字段（新值）
    existing_fields: dict[str, str]  #: 现有 ``ComicInfo.xml`` 解析出的字段（旧值）
    existing_xml:    bytes | None    #: 现有 ``ComicInfo.xml`` 原始字节（无则 ``None``）
    new_xml:         bytes           #: 本次构建的目标字节

    @property
    def writable(self) -> bool:
        """是否可写入：无出版商冲突即可。"""
        return not self.pub_conflict

    @property
    def changed(self) -> bool:
        """无现有版本或与目标不一致时为 True。"""
        return self.existing_xml is None or self.existing_xml != self.new_xml

    @property
    def diff_keys(self) -> frozenset[str]:
        """新旧字段值不一致的 tag 集合（供预览分组用，不含 Notes 之外的逻辑过滤）。"""
        keys = set(self.fields) | set(self.existing_fields)
        return frozenset(
            k for k in keys
            if self.existing_fields.get(k, '') != self.fields.get(k, '')
        )

    @property
    def existing_encoding(self) -> str:
        """现有 XML 的声明编码；无现有版本返回 ``''``。"""
        return _detect_xml_encoding(self.existing_xml)

    @property
    def new_encoding(self) -> str:
        """目标 XML 的声明编码（恒为 ``utf-8``）。"""
        return _detect_xml_encoding(self.new_xml)

    @property
    def author(self) -> str:
        return self.mi.author

    @property
    def filename(self) -> str:
        return os.path.basename(self.cbz_path)


# ═══════════════════════════════════════════════════════════════════════════════
# MakeCoverPlan
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MakeCoverPlan:
    """单个 CBZ 的封面写入计划。

    plan 阶段就真正解码源图、裁剪、转为 WebP 字节，apply 阶段只追加写入；
    这样确保预览展示的尺寸与最终写入完全一致。:attr:`existing_bytes` 用于
    幂等判定：与目标完全一致则跳过。

    :ivar mode:    本次使用的裁剪算法（``'center'`` / ``'smart'``）。
    :ivar dst_name: 目标文件名（依源图推导：源 ``cover.*`` / ``0001.*`` → ``0000.webp``）。
    :ivar error:   plan 阶段发生的错误（如源图损坏 / 解码失败）；正常时为 ``''``。
    """
    cbz_path:       str
    src_name:       str | None
    src_size:       tuple[int, int] | None
    dst_size:       tuple[int, int] | None
    mode:           str
    dst_name:       str | None
    webp_bytes:     bytes | None
    existing_bytes: bytes | None
    error:          str = ""

    @property
    def filename(self) -> str:
        return os.path.basename(self.cbz_path)

    @property
    def writable(self) -> bool:
        """有源图、有输出字节、无错误时为 True。"""
        return self.src_name is not None and self.webp_bytes is not None and not self.error

    @property
    def replaced(self) -> bool:
        """CBZ 内已存在同名目标文件（无论字节是否一致）。"""
        return self.existing_bytes is not None

    @property
    def changed(self) -> bool:
        """无现有版本或与目标字节不一致时为 True。"""
        return self.existing_bytes is None or self.existing_bytes != self.webp_bytes


# ═══════════════════════════════════════════════════════════════════════════════
# PackPicPlan
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PackPicPlan:
    """单个「打包单位」的图片序号化重命名 + 打包计划。

    打包单位由 :func:`~module.manga.workflow.pack_pic._find_units` 递归识别，分两种：

    - ``'flat'``：直接含图片、无子目录（zip 内平铺）
    - ``'nested'``：仅含子目录且每个子目录都是 flat（zip 内保留子目录路径）

    plan 阶段只扫描 / 算目标名 / 收集非图片，不动盘；apply 阶段以
    ``zipfile.ZIP_STORED`` 写入同级 ``<dir>.zip``，写完后整树 ``rmtree``。

    :ivar renames: ``(old_rel, new_rel)`` 列表；nested 模式带子目录前缀（如
        ``Ch01/0001.jpg``，分隔符统一用 ``/``）。
    :ivar extras:  非图片文件（相对 src_dir 的路径，用 ``/``）；不进 zip，
        但会随源目录被 ``rmtree`` 一并删除。
    :ivar error:   plan 阶段发现的阻断性问题；非空则该计划不会被执行。
    """
    src_dir:    str
    zip_path:   str
    renames:    list[tuple[str, str]]
    extras:     list[str]
    zip_exists: bool = False
    kind:       str  = 'flat'
    error:      str  = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.src_dir)

    @property
    def writable(self) -> bool:
        """无错误且至少有一张图片时为 True。"""
        return not self.error and bool(self.renames)

    @property
    def n_renamed(self) -> int:
        """实际会发生改名的文件数（已是目标名的不计）。"""
        return sum(1 for o, n in self.renames if o != n)

    @property
    def n_subdirs(self) -> int:
        """nested 模式下涉及的子目录数；flat 模式恒为 0。

        只统计含 ``/`` 的条目；nested 顶层文件（``cover.*`` / ``ComicInfo.xml`` 等）
        的 ``old`` 是裸文件名，不计入。
        """
        if self.kind != 'nested':
            return 0
        return len({old.split('/', 1)[0] for old, _ in self.renames if '/' in old})
