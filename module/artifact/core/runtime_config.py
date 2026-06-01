"""artifact 业务配置加载（统一 ``<user_config>/media-toolkit/config/artifact.json``）。

无参 :func:`load_config` 缺失时自动创建空 workdirs；用户可在 GUI 中点
「修改配置」用关联程序编辑，编辑保存后点「重载配置」重新读取。

显式传入 ``path`` 时保持严格语义：不存在 → :exc:`FileNotFoundError`
（用于显式自定义路径场景与测试，避免悄悄落盘到非默认位置）。
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

from base.app_config import JsonConfig, config_dir


CONFIG_FILENAME = 'artifact.json'
_DEFAULT_DATA: dict = {'artifact.workdirs': []}


@dataclass(frozen=True)
class WorkDir:
    """工作目录（含归类作者文件夹）+ 搜索 URL 模板。

    :ivar search_url_template: 含 ``{author}`` 占位符；空串表示不打印 URL。
    """
    path: Path
    search_url_template: str


@dataclass(frozen=True)
class Config:
    workdirs: list[WorkDir]

    def find_workdir(self, p: Path) -> WorkDir | None:
        """根据一个候选目录路径反查所属 :class:`WorkDir`（匹配规则：``p`` 的某个祖先 == :attr:`WorkDir.path`）。"""
        try:
            resolved = p.resolve()
        except Exception:
            resolved = p
        for wd in self.workdirs:
            try:
                resolved.relative_to(wd.path)
                return wd
            except ValueError:
                continue
        return None


class _ArtifactJsonConfig(JsonConfig):
    """``artifact.json`` 句柄；缺失时落盘 ``{"artifact.workdirs": []}``。"""

    def __init__(self) -> None:
        super().__init__(CONFIG_FILENAME, default=dict(_DEFAULT_DATA))


def config_path() -> Path:
    """配置文件的期望位置（不保证内容已加载）。"""
    return config_dir() / CONFIG_FILENAME


def _build_config(raw: dict) -> Config:
    workdirs_raw = raw.get('artifact.workdirs', [])
    workdirs = [
        WorkDir(
            path=Path(item['path']),
            search_url_template=item.get('search_url_template', ''),
        )
        for item in workdirs_raw
    ]
    return Config(workdirs=workdirs)


def load_config(path: Path | None = None) -> Config:
    """加载 artifact 业务配置。

    :param path: ``None`` → 使用 :func:`config_path`，缺失自动创建空 workdirs；
        显式路径 → 不存在时抛 :exc:`FileNotFoundError`。
    :raises FileNotFoundError: 仅在显式 ``path`` 不存在时抛出。
    """
    if path is not None:
        if not path.is_file():
            raise FileNotFoundError(
                f'未找到 artifact 配置文件\n'
                f'  期望路径: {path}\n'
            )
        raw = json.loads(path.read_text('utf-8'))
        return _build_config(raw)

    return _build_config(_ArtifactJsonConfig().data)
