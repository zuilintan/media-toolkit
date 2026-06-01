"""别名扫描（在 :class:`~module.artifact.core.runtime_config.WorkDir` 下查
``[别名]：XXX.txt`` 文件）+ 扫描结果落盘缓存。

文件本身可空（数据载体在文件名上）；前缀 :data:`ALIAS_PREFIX` 中的 ``：``
为全角冒号 (U+FF1A)，与 ps1 兼容。:func:`scan_aliases` 用 ThreadPoolExecutor
并行扫多个 WorkDir，输出大小写不敏感的 ``alias → 作者目录`` 映射，并把结果
落盘到 :func:`aliases_cache_path`（同步副作用）；下次启动可经
:func:`load_aliases` 直接从缓存恢复，无需重复跨网络盘扫描。

启动期校验：:func:`load_aliases` 对缓存中每条 ``author_dir`` 调 ``is_dir()``，
失效条目从返回的 map 中剔除，但 JSON **不主动重写** —— 失效原因可能只是
临时未挂载，让用户看到提示后自行点「刷新别名」决定是否重建。

性能要点（针对 SMB / 网络盘的大目录树）::

    使用 os.scandir() 而非 Path.iterdir()，避免 DirEntry → Path 转换后
    is_file() 调用触发的独立 stat()；并把廉价的 name.startswith() 字符串过滤
    放在最前面，只在命中前缀后才用 DirEntry.is_file()（也走预填属性，无额外
    往返）。每个作者目录的 SMB 调用从 N+1 降到 1（仅一次 readdir）。
"""

from __future__ import annotations
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from base.app_config import cache_dir
from base.fs import Reporter, _default_reporter

ALIAS_PREFIX = '[别名]：'   # 全角冒号 U+FF1A
ALIAS_SUFFIX = '.txt'
ALIAS_CACHE_FILENAME = 'aliases.json'
_CACHE_SCHEMA_VERSION = 1


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
    _save_aliases(result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 持久化缓存：scan_aliases 完成后落盘 / 启动期 load_aliases 恢复并校验
# ═══════════════════════════════════════════════════════════════════════════════

def aliases_cache_path() -> Path:
    """``<cache>/aliases.json`` 的绝对路径（不保证存在）。"""
    return cache_dir() / ALIAS_CACHE_FILENAME


def _save_aliases(alias_map: dict[str, Path]) -> None:
    """把当前 ``alias_map`` 落盘为 :func:`aliases_cache_path` 指向的 JSON。

    内部副作用，仅在 :func:`scan_aliases` 末尾调用。写盘失败不抛错（缓存损失
    可重建，不应阻断业务），仅返回 False。
    """
    payload = {
        '$schema_version': _CACHE_SCHEMA_VERSION,
        'aliases': {alias: str(p) for alias, p in alias_map.items()},
    }
    try:
        aliases_cache_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), 'utf-8'
        )
    except OSError:
        pass


def load_aliases(
    *, reporter: Reporter = _default_reporter,
) -> tuple[dict[str, Path], list[str]]:
    """从持久化缓存恢复别名映射，并校验每条记录指向的目录是否仍存在。

    :return: ``(valid_map, invalid_aliases)``::

        valid_map        — 校验通过的 ``alias → author_dir``（大小写不敏感），
                           供 :func:`~module.artifact.workflow.classify.matcher.find_candidates` 使用
        invalid_aliases  — 目录已失效的别名名称列表（lower-case 形式）；UI 据此
                           提示用户考虑刷新

    缓存缺失 / 解析失败 / 版本未来都按"空缓存"处理（返回 ``({}, [])``），不抛错；
    本函数只读不写 —— 失效条目保留在 JSON，由 :func:`scan_aliases` 在用户主动
    刷新时整体重写。
    """
    valid: dict[str, Path] = _CaseInsensitiveDict()
    invalid: list[str] = []
    path = aliases_cache_path()
    if not path.exists():
        return valid, invalid
    try:
        payload = json.loads(path.read_text('utf-8'))
    except (OSError, ValueError) as e:
        reporter('warn', f'别名缓存读取失败（按空缓存处理）: {e}')
        return valid, invalid
    raw = payload.get('aliases', {}) if isinstance(payload, dict) else {}

    for alias, path_str in raw.items():
        p = Path(path_str)
        try:
            ok = p.is_dir()
        except OSError:
            ok = False
        if ok:
            valid[alias] = p
        else:
            invalid.append(alias)
    return valid, invalid
