"""
gui_config.py — GUI 持久化配置

JSON 文件，存放在系统通用配置目录下的 manga-toolkit/ 子目录：
  Windows : %LOCALAPPDATA%/manga-toolkit/gui_config.json
  Linux   : ~/.config/manga-toolkit/gui_config.json

接口
----
  get(key, default=None)          → 读取标量值
  set(key, value)                 → 写入标量值（立即落盘）
  get_history(key)                → 读取历史列表（最近优先）
  push_history(key, value)        → 将值推入历史首位，超出上限时截断（立即落盘）
"""

from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_HISTORY_MAX = 10


class GUIConfig:
    """JSON 持久化配置，每次 set / push_history 后自动落盘。"""

    def __init__(self) -> None:
        base = Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericConfigLocation
        ))
        cfg_dir = base / 'manga-toolkit'
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


# ── 模块级单例 ─────────────────────────────────────────────────────────
_instance: GUIConfig | None = None


def get_config() -> GUIConfig:
    """返回全局唯一的 GUIConfig 实例（懒初始化，首次调用时创建）。"""
    global _instance
    if _instance is None:
        _instance = GUIConfig()
    return _instance
