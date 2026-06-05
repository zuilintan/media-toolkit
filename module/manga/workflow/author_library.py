"""漫画库作者索引：扫描 ``{root}/{author}/`` 一级目录 + 目录内 ``[别名]：xxx.txt``，
建立 ``主名 / 别名 → 主名`` 的归一映射，落盘到 ``cache/author_library.json``。

供 :func:`~module.manga.workflow.std_title.derive_inputs` 在作者推导后做一道
规范化：简繁归一后命中库里主名或别名时，统一替换为主名，避免库里出现简繁
不同的两份同名作者目录。

别名文件命名严格对齐 :mod:`module.artifact.workflow.classify.alias` 的约定：
``[别名]：`` + 全角冒号 (U+FF1A) + 别名 + ``.txt``；文件内容可空，数据载体在
文件名上。

索引结构（每个库根独立条目，按绝对路径作 key）::

    {
      "$schema_version": 1,
      "libraries": {
        "C:/Manga": {
          "scanned_at": 1717000000.0,
          "primary_to_aliases": {
            "作者甲": ["A仔", "作家甲"],
            "作者乙": []
          }
        }
      }
    }
"""

from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from base.app_config import cache_dir
from base.console import emit, warn
from module.manga.naming.text import normalize, trad_to_simp


_ALIAS_PREFIX = '[别名]\uff1a'   # 全角冒号 U+FF1A，与 artifact 对齐
_ALIAS_SUFFIX = '.txt'
_CACHE_FILENAME = 'author_library.json'
_CACHE_SCHEMA_VERSION = 1


def _norm_key(name: str) -> str:
    """归一 key：简繁归一 + NFKC + 去空白 + lower。

    简繁归一靠 :func:`~module.manga.naming.text.trad_to_simp`（zhconv 全量
    + ``姊→姐`` 手工修补，与 parser 的翻译者归一保持一致）。后续 NFKC / 去
    空白 / lower 复用 :func:`~module.manga.naming.text.normalize`。
    """
    return normalize(trad_to_simp(name))


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描
# ═══════════════════════════════════════════════════════════════════════════════

def _scan_one_author_dir(author_dir_path: str) -> list[str]:
    """扫描单个作者目录下的 ``[别名]：xxx.txt``，返回别名列表。

    复用 :mod:`module.artifact.workflow.classify.alias` 同款 ``os.scandir`` +
    廉价字符串前缀过滤，避免 SMB / 网络盘上 N+1 次 stat。
    """
    aliases: list[str] = []
    try:
        with os.scandir(author_dir_path) as it:
            for f in it:
                name = f.name
                if not name.startswith(_ALIAS_PREFIX):
                    continue
                if not name.endswith(_ALIAS_SUFFIX):
                    continue
                if not f.is_file(follow_symlinks=False):
                    continue
                alias = name[len(_ALIAS_PREFIX):-len(_ALIAS_SUFFIX)].strip()
                if alias:
                    aliases.append(alias)
    except (PermissionError, OSError, FileNotFoundError):
        pass
    return aliases


def _scan_library_root(root: Path) -> dict[str, list[str]]:
    """扫描 ``{root}/`` 一级子目录：每个子目录名即主名（作者），目录内
    ``[别名]：xxx.txt`` 即别名。返回 ``主名 → [别名…]``。
    """
    primary_to_aliases: dict[str, list[str]] = {}
    try:
        with os.scandir(root) as it:
            author_entries = [
                e for e in it if e.is_dir(follow_symlinks=False)
            ]
    except (PermissionError, OSError, FileNotFoundError) as e:
        warn(f'漫画库扫描失败: {root} — {e}')
        return primary_to_aliases

    for ae in author_entries:
        primary_to_aliases[ae.name] = _scan_one_author_dir(ae.path)
    return primary_to_aliases


# ═══════════════════════════════════════════════════════════════════════════════
# AuthorLibrary
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AuthorLibrary:
    """单个漫画库根目录的作者索引快照。

    :ivar root:               扫描时使用的库根（绝对路径，用 ``/`` 分隔符）。
    :ivar primary_to_aliases: ``主名 → 别名列表``；空列表表示该作者无别名文件。
    """
    root:               str
    primary_to_aliases: dict[str, list[str]] = field(default_factory=dict)

    @cached_property
    def lookup(self) -> dict[str, str]:
        """归一 key → 主名（原始大小写 / 简繁形态保留）。

        同时包含 ``_norm_key(primary) → primary`` 与
        ``_norm_key(alias) → primary``，让 :meth:`resolve` 两条路径都一次表查。
        """
        m: dict[str, str] = {}
        for primary, aliases in self.primary_to_aliases.items():
            m.setdefault(_norm_key(primary), primary)
            for a in aliases:
                # 别名归一后若与某主名冲突，主名优先（已 setdefault）
                m.setdefault(_norm_key(a), primary)
        return m

    @property
    def conflicts(self) -> list[tuple[str, str, str]]:
        """``[(归一 key, 期望主名, 已注册主名)]``：构建 lookup 时发现的别名 / 主名重名。

        惰性计算，只用于诊断输出；resolve 走 lookup 的 first-wins 策略不受影响。
        """
        seen: dict[str, str] = {}
        out: list[tuple[str, str, str]] = []
        for primary, aliases in self.primary_to_aliases.items():
            for n in [primary, *aliases]:
                key = _norm_key(n)
                if key in seen and seen[key] != primary:
                    out.append((key, primary, seen[key]))
                else:
                    seen[key] = primary
        return out

    def resolve(self, author: str) -> str:
        """规范化 ``author``：归一 key 在库里命中即返回库主名，否则原样返回。

        - 推导作者 ``作者甲（繁体）`` + 库主名 ``作者甲（简体）`` → 简体主名
        - 推导作者 ``A仔`` + 库里 ``[别名]：A仔.txt`` 落在 ``作者甲/`` → ``作者甲``
        - 库中无对应 → 原样返回（不阻断新作者入库）
        """
        if not author:
            return author
        return self.lookup.get(_norm_key(author), author)

    def __len__(self) -> int:
        return len(self.primary_to_aliases)


# ═══════════════════════════════════════════════════════════════════════════════
# 持久化
# ═══════════════════════════════════════════════════════════════════════════════

def _cache_path() -> Path:
    """``<cache>/author_library.json``（按需创建父目录）。"""
    return cache_dir() / _CACHE_FILENAME


def _normalize_root_key(root: Path) -> str:
    """库根路径作为缓存 key：绝对路径 + 正斜杠（跨平台稳定）。"""
    return str(root.resolve()).replace('\\', '/')


def _load_payload() -> dict:
    """读 cache JSON；缺失 / 损坏 / 版本不匹配按"空"处理。"""
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text('utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if payload.get('$schema_version') != _CACHE_SCHEMA_VERSION:
        return {}
    return payload.get('libraries', {}) or {}


def _save_library(lib: AuthorLibrary) -> None:
    """把 ``lib`` 合并入现有 cache 并落盘（保留其它库根的条目）。"""
    libs = _load_payload()
    libs[lib.root] = {
        'scanned_at':         time.time(),
        'primary_to_aliases': lib.primary_to_aliases,
    }
    payload = {
        '$schema_version': _CACHE_SCHEMA_VERSION,
        'libraries':       libs,
    }
    try:
        _cache_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), 'utf-8'
        )
    except OSError as e:
        warn(f'作者索引落盘失败: {e}')


def load_library(root: Path) -> AuthorLibrary | None:
    """从 cache 恢复某库根的索引；缺失或不匹配返回 ``None``。

    本函数只读不写，不校验主名目录是否仍存在（cache 失效由用户主动重建解决；
    部分作者目录被改名属于异常情况，自动剔除反而可能掩盖问题）。
    """
    if not root.is_dir():
        return None
    libs = _load_payload()
    entry = libs.get(_normalize_root_key(root))
    if not isinstance(entry, dict):
        return None
    p2a = entry.get('primary_to_aliases', {})
    if not isinstance(p2a, dict):
        return None
    return AuthorLibrary(
        root               = _normalize_root_key(root),
        primary_to_aliases = {k: list(v) for k, v in p2a.items()},
    )


def scan_library(root: Path) -> AuthorLibrary:
    """扫描 ``root`` 并落盘缓存，返回最新 :class:`AuthorLibrary`。

    库不存在时返回空 :class:`AuthorLibrary`（不落盘）。
    """
    if not root.is_dir():
        warn(f'漫画库根目录不存在: {root}')
        return AuthorLibrary(root=_normalize_root_key(root))
    p2a = _scan_library_root(root)
    lib = AuthorLibrary(
        root               = _normalize_root_key(root),
        primary_to_aliases = p2a,
    )
    n_alias = sum(len(v) for v in p2a.values())
    emit(f'📚 漫画库扫描完成: {len(p2a)} 个作者 / {n_alias} 个别名 — {lib.root}')
    if lib.conflicts:
        for key, expect, registered in lib.conflicts[:5]:
            warn(f'  ⚠️ 归一冲突: "{key}" → 期望 {expect}，已注册 {registered}')
        if len(lib.conflicts) > 5:
            warn(f'  ⚠️ 余 {len(lib.conflicts) - 5} 条同类冲突（详见详细日志）')
    _save_library(lib)
    return lib


def load_or_scan(root: Path, force_rescan: bool = False) -> AuthorLibrary:
    """缓存命中即返回，否则扫一次并落盘。

    :param force_rescan: 显式重建索引（CLI ``--rebuild-author-index`` /
        GUI「重建索引」按钮触发）。
    """
    if not force_rescan:
        lib = load_library(root)
        if lib is not None:
            return lib
    return scan_library(root)
