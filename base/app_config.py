"""统一持久化目录与 JSON 配置基类（不依赖 PySide6，CLI/GUI 均可用）。

目录约定（统一根 ``<user_config>/media-toolkit/``）::

    config/   — 用户编辑的配置（GUI 提供「修改配置」按钮指向之）
    cache/    — 程序管理的缓存数据（启动期可重建，用户不需要直接编辑）

具体跨平台路径::

    Windows : %LOCALAPPDATA%/media-toolkit/{config,cache}/<file>.json
    macOS   : ~/Library/Application Support/media-toolkit/{config,cache}/<file>.json
    Linux   : ${XDG_CONFIG_HOME:-~/.config}/media-toolkit/{config,cache}/<file>.json

``config/`` 下三个固定 JSON：

- ``gui.json``      — GUI 用户状态（路径历史 / jobs / quality / 窗口几何 …）
- ``artifact.json`` — artifact 业务配置（workdirs 等）
- ``manga.json``    — manga 业务运行期配置（占位预留）

artifact / manga 文件缺失时由各自的 :class:`JsonConfig` 子类用 ``default`` 自动落盘。

``cache/`` 下当前仅 ``aliases.json``（artifact 别名扫描结果缓存）。
"""

from __future__ import annotations
import json
from pathlib import Path

from base.config_paths import user_config_dir


APP_DIR_NAME = 'media-toolkit'


def config_dir() -> Path:
    """``<user_config>/media-toolkit/config/``（自动创建）。"""
    d = user_config_dir(APP_DIR_NAME) / 'config'
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    """``<user_config>/media-toolkit/cache/``（自动创建）。"""
    d = user_config_dir(APP_DIR_NAME) / 'cache'
    d.mkdir(parents=True, exist_ok=True)
    return d


class JsonConfig:
    """JSON 持久化基类。每次 :meth:`set` 后自动落盘。

    :ivar path:    配置文件绝对路径。
    :ivar data:    当前内存中的 dict（可读不可改，修改请走 :meth:`set`）。
    """

    def __init__(self, filename: str, default: dict | None = None) -> None:
        self._path: Path = config_dir() / filename
        self._default: dict = default or {}
        self._data: dict = {}
        self._load_or_create()

    # ── 落盘 ──────────────────────────────────────────────────────────
    def _load_or_create(self) -> None:
        """文件存在则加载；不存在则用 ``default`` 落盘。损坏视作缺失。"""
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text('utf-8'))
                return
            except Exception:
                pass
        self._data = dict(self._default)
        self._save()

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), 'utf-8'
        )

    def reload(self) -> None:
        """重新从磁盘读取（用户外部编辑后调用）。"""
        self._load_or_create()

    # ── 标量 get / set ─────────────────────────────────────────────────
    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()

    # ── 暴露给需要整块结构的调用方 ────────────────────────────────────
    @property
    def path(self) -> Path:
        return self._path

    @property
    def data(self) -> dict:
        return self._data
