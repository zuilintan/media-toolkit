"""别名扫描（在 :class:`~module.artifact.core.runtime_config.WorkDir` 下查
``[别名]：XXX.txt`` 文件）。

文件本身可空（数据载体在文件名上）；前缀 :data:`ALIAS_PREFIX` 中的 ``：``
为全角冒号 (U+FF1A)，与 ps1 兼容。:func:`scan_aliases` 用 ThreadPoolExecutor
并行扫多个 WorkDir，输出大小写不敏感的 ``alias → 作者目录`` 映射。

性能要点（针对 SMB / 网络盘的大目录树）::

    使用 os.scandir() 而非 Path.iterdir()，避免 DirEntry → Path 转换后
    is_file() 调用触发的独立 stat()；并把廉价的 name.startswith() 字符串过滤
    放在最前面，只在命中前缀后才用 DirEntry.is_file()（也走预填属性，无额外
    往返）。每个作者目录的 SMB 调用从 N+1 降到 1（仅一次 readdir）。
"""

from __future__ import annotations
import os
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
    try:
        with os.scandir(workdir) as wd_it:
            author_entries = [e for e in wd_it if e.is_dir(follow_symlinks=False)]
    except (PermissionError, OSError, FileNotFoundError):
        return out

    for ae in author_entries:
        try:
            with os.scandir(ae.path) as a_it:
                for f in a_it:
                    name = f.name
                    # 廉价字符串过滤优先：绝大多数文件（zip/cbz/...）在此被丢弃
                    if not name.startswith(ALIAS_PREFIX):
                        continue
                    if not name.endswith(ALIAS_SUFFIX):
                        continue
                    # DirEntry.is_file 走 readdir 预填属性，不再触发 stat
                    if not f.is_file(follow_symlinks=False):
                        continue
                    alias = name[len(ALIAS_PREFIX):-len(ALIAS_SUFFIX)].strip()
                    if alias:
                        out.append((alias, Path(ae.path)))
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
    :param reporter:    状态回调（启动列出 WorkDir + 每个完成时报告数量 + 总计）。
    :param max_workers: 并行线程数；多 WorkDir 在不同物理盘上才有收益，同盘上
        过高反而会因 SMB 锁竞争反向劣化。
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
            reporter('info', f'  ✓ {wd}: {len(pairs)} 条')
            for alias, author_dir in pairs:
                # 先到先得：相同 alias 不覆盖（多 WorkDir 重名时保留最先扫描到的）
                if alias not in result:
                    result[alias] = author_dir

    reporter('info', f'✅ 别名加载完成: {len(result)} 条')
    return result
