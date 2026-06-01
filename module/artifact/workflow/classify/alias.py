"""别名扫描（在 :class:`~module.artifact.core.runtime_config.WorkDir` 下查
``[别名]：XXX.txt`` 文件）。

文件本身可空（数据载体在文件名上）；前缀 :data:`ALIAS_PREFIX` 中的 ``：``
为全角冒号 (U+FF1A)，与 ps1 兼容。:func:`scan_aliases` 用 ThreadPoolExecutor
并行扫多个 WorkDir，输出大小写不敏感的 ``alias → 作者目录`` 映射。
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from base.fs import Reporter, _default_reporter

ALIAS_PREFIX = '[别名]：'   # 全角冒号 U+FF1A
ALIAS_SUFFIX = '.txt'


def _scan_one_workdir(workdir: Path) -> list[tuple[str, Path]]:
    """扫描单个 WorkDir 下所有作者目录里的别名文件。

    缺失或不可读的目录返回空 list（由调用方决定是否报告）。

    :return: ``[(别名, 作者目录)]``。
    """
    out: list[tuple[str, Path]] = []
    if not workdir.is_dir():
        return out
    for author_dir in workdir.iterdir():
        if not author_dir.is_dir():
            continue
        try:
            for f in author_dir.iterdir():
                if (f.is_file()
                        and f.name.startswith(ALIAS_PREFIX)
                        and f.suffix == ALIAS_SUFFIX):
                    alias = f.stem[len(ALIAS_PREFIX):].strip()
                    if alias:
                        out.append((alias, author_dir))
        except (PermissionError, OSError):
            continue
    return out


class _CaseInsensitiveDict(dict):
    """大小写不敏感的字符串键字典（内部用 lower 索引；保留任一原始 key）。"""
    def __setitem__(self, key: str, value):
        super().__setitem__(key.lower(), value)

    def __getitem__(self, key: str):
        return super().__getitem__(key.lower())

    def __contains__(self, key) -> bool:
        return super().__contains__(key.lower() if isinstance(key, str) else key)

    def get(self, key, default=None):
        return super().get(key.lower() if isinstance(key, str) else key, default)


def scan_aliases(
    workdirs: list[Path],
    *,
    reporter: Reporter = _default_reporter,
    max_workers: int = 8,
) -> dict[str, Path]:
    """并行扫描所有 WorkDir，返回大小写不敏感的 ``alias → 作者目录`` 映射。

    :param workdirs:    要扫描的 WorkDir 列表。
    :param reporter:    状态回调（每个目录扫描结果）。
    :param max_workers: 并行线程数。
    :return: ``alias_name (大小写不敏感) → author_dir Path``。
    """
    result: dict[str, Path] = _CaseInsensitiveDict()

    valid = []
    for wd in workdirs:
        if wd.is_dir():
            valid.append(wd)
            reporter('info', f'📁 发现工作目录: {wd}')
        else:
            reporter('warn', f'目录不存在，跳过: {wd}')
    if not valid:
        reporter('error', '无有效工作目录')
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_scan_one_workdir, wd): wd for wd in valid}
        for fut in as_completed(futures):
            wd = futures[fut]
            try:
                pairs = fut.result()
            except Exception as e:
                reporter('error', f'扫描失败 {wd}: {e}')
                continue
            for alias, author_dir in pairs:
                # 先到先得：相同 alias 不覆盖（多 WorkDir 重名时保留最先扫描到的）
                if alias not in result:
                    result[alias] = author_dir

    reporter('info', f'✅ 别名加载完成: {len(result)} 条')
    return result
