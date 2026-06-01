"""artifact-toolkit 配置加载（``<user_config>/artifact-toolkit/config.json``）。

跨平台路径由 :func:`~base.config_paths.user_config_dir` 解析；模板预置在
``module/artifact/config_template.json``（随 wheel 一起分发）。

设计：找不到 config 时抛 :exc:`FileNotFoundError`，消息中含期望路径与模板路径；
禁止静默自动落盘（避免悄悄写入默认值让用户搞不清来源）。
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

from base.config_paths import user_config_dir

APP_DIR_NAME = 'artifact-toolkit'
CONFIG_FILENAME = 'config.json'
TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / 'config_template.json'


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


def config_path() -> Path:
    """配置文件的期望位置（不保证存在）。"""
    return user_config_dir(APP_DIR_NAME) / CONFIG_FILENAME


def load_config(path: Path | None = None) -> Config:
    """从 JSON 加载配置；找不到时给出带模板路径的指引。

    :param path: 自定义配置路径；``None`` 走默认 :func:`config_path`。
    :raises FileNotFoundError: 文件不存在时；消息含期望路径与模板路径。
    """
    cfg_path = path or config_path()
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f'未找到 artifact-toolkit 配置文件\n'
            f'  期望路径: {cfg_path}\n'
            f'  模板示例: {TEMPLATE_PATH}\n'
            f'\n'
            f'请参考模板创建上述配置文件后重试。'
        )
    raw = json.loads(cfg_path.read_text('utf-8'))
    workdirs_raw = raw.get('artifact.workdirs', [])
    workdirs = [
        WorkDir(
            path=Path(item['path']),
            search_url_template=item.get('search_url_template', ''),
        )
        for item in workdirs_raw
    ]
    return Config(workdirs=workdirs)
