"""
config.py — GUI 持久化配置（按 app_dir_name 区分实例）

JSON 文件，存放在系统通用配置目录下的 ``<app_dir_name>/gui_config.json``：
  Windows : %LOCALAPPDATA%/<app_dir_name>/gui_config.json
  Linux   : ~/.config/<app_dir_name>/gui_config.json

接口
----
  GUIConfig(app_dir_name)        → 显式构造（多 app 共存场景）
  get_config(app_dir_name=None)  → 全局获取/缓存（不传则用默认）
  set_default_app_dir_name(name) → 设置默认 app_dir_name（启动期调用一次）

  cfg.get(key, default=None)     → 读取标量值
  cfg.set(key, value)            → 写入标量值（立即落盘）
  cfg.get_history(key)           → 读取历史列表（最近优先）
  cfg.push_history(key, value)   → 推入历史首位，超限截断（立即落盘）
"""

from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_HISTORY_MAX = 10


class GUIConfig:
    """JSON 持久化配置，每次 set / push_history 后自动落盘。"""

    def __init__(self, app_dir_name: str) -> None:
        base = Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericConfigLocation
        ))
        cfg_dir = base / app_dir_name
        cfg_dir.mkdir(parents=True, exist_ok=True)
        self._path = cfg_dir / 'gui_config.json'
        self._data: dict = {}
        self._load()

    # ── 落盘 ──────────────────────────────────────────────────────────
    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text('utf-8'))
            except Exception:
                self._data = {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), 'utf-8'
        )

    # ── 标量 get / set ─────────────────────────────────────────────────
    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()

    # ── 历史列表 ───────────────────────────────────────────────────────
    def get_history(self, key: str) -> list[str]:
        return list(self._data.get(f'{key}__hist', []))

    def push_history(self, key: str, value: str) -> None:
        """将 value 推入历史首位；已存在则先移除再插入（去重）。"""
        if not value:
            return
        hist: list[str] = self.get_history(key)
        if value in hist:
            hist.remove(value)
        hist.insert(0, value)
        self._data[f'{key}__hist'] = hist[:_HISTORY_MAX]
        self._save()


# ── 多实例缓存 + 默认 app_dir_name ─────────────────────────────────────
_instances: dict[str, GUIConfig] = {}
_default_app_dir_name: str | None = None


def set_default_app_dir_name(name: str) -> None:
    """设置 get_config() 不带参时使用的默认 app_dir_name。

    各业务的 GUI 入口（manga.gui、artifact.gui 等的 main()）应在早期
    调用一次，避免下游每处 get_config() 都要显式传参。
    """
    global _default_app_dir_name
    _default_app_dir_name = name


def get_config(app_dir_name: str | None = None) -> GUIConfig:
    """获取按 app_dir_name 缓存的 GUIConfig 实例（懒初始化）。

    Args:
        app_dir_name: 不传则使用 set_default_app_dir_name 设置的默认值；
            两者都未设置则抛 RuntimeError。
    """
    name = app_dir_name or _default_app_dir_name
    if name is None:
        raise RuntimeError(
            'get_config() 未指定 app_dir_name，且未调用 '
            'set_default_app_dir_name() 设置默认值'
        )
    if name not in _instances:
        _instances[name] = GUIConfig(name)
    return _instances[name]
