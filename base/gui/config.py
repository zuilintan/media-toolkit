"""GUI 持久化配置（统一 ``gui.json`` 单文件）。

存放位置由 :func:`base.app_config.config_dir` 决定；所有 module / Tab 通过
:func:`get_config` 取同一实例。key 仍保持平铺（如 ``'std_title.root__hist'`` /
``'make_cover.quality'` / ``'manga.splitter'``），无需按 module 分嵌套。
"""

from __future__ import annotations

from base.app_config import JsonConfig


_HISTORY_MAX = 10


class GUIConfig(JsonConfig):
    """``gui.json`` 包装；除标量 get/set 外，再提供有界历史列表 API。"""

    def __init__(self) -> None:
        super().__init__('gui.json')

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


_instance: GUIConfig | None = None


def get_config() -> GUIConfig:
    """获取全局 :class:`GUIConfig` 单例（懒初始化）。"""
    global _instance
    if _instance is None:
        _instance = GUIConfig()
    return _instance
