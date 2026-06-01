"""manga 业务运行期配置（统一 ``<user_config>/media-toolkit/config/manga.json``）。

当前**仅占位**：默认内容 ``{"$schema_version": 1}``；后续在此挂业务字段（如默认
jobs / 默认裁剪参数 / Notes 模板等）时，可直接通过 :class:`~base.app_config.JsonConfig`
的 :meth:`~base.app_config.JsonConfig.get` / :meth:`~base.app_config.JsonConfig.set`
访问，无需重新设计文件路径。
"""

from __future__ import annotations

from base.app_config import JsonConfig


CONFIG_FILENAME = 'manga.json'
_DEFAULT_DATA: dict = {'$schema_version': 1}


class MangaRuntimeConfig(JsonConfig):
    """``manga.json`` 句柄；缺失时落盘 ``{"$schema_version": 1}`` 占位。"""

    def __init__(self) -> None:
        super().__init__(CONFIG_FILENAME, default=dict(_DEFAULT_DATA))


_instance: MangaRuntimeConfig | None = None


def get_manga_config() -> MangaRuntimeConfig:
    """获取全局 :class:`MangaRuntimeConfig` 单例（懒初始化）。"""
    global _instance
    if _instance is None:
        _instance = MangaRuntimeConfig()
    return _instance
