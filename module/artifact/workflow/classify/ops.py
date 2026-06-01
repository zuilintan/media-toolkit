"""文件归类核心搬移（只支持 move 模式，ps1 ``Invoke-ContentOperation`` 简化版）。

入口 :func:`classify_one`：

- 拖入目录 → :func:`~base.fs.merge_into` 递归合并；合并后 src 为空则删除
- 拖入文件 → 目标已存在则跳过（与 ps1 单文件分支一致），否则 ``shutil.move``
- 操作完成后调 ``reporter`` 输出统计 + iwara 搜索 URL（若 :class:`~module.artifact.core.runtime_config.WorkDir` 配置了模板）
- 可选：``open_target=True`` 时用系统默认动作打开目标目录
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from base.fs import (
    Reporter, _default_reporter, merge_into, safe_rmtree,
)

from module.artifact.core.runtime_config import WorkDir


@dataclass(frozen=True)
class ClassifyResult:
    """单次归类的结果摘要。

    :ivar skipped_file: 单文件且目标已存在。
    :ivar src_removed:  源目录是否已被清理。
    """
    src:          Path
    dst:          Path
    moved:        int = 0
    overwritten:  int = 0
    failed:       int = 0
    skipped_file: bool = False
    src_removed:  bool = False

    @property
    def ok(self) -> bool:
        return self.failed == 0 and not self.skipped_file


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def classify_one(
    src: Path,
    dst: Path,
    workdir: WorkDir | None = None,
    *,
    author_name: str | None = None,
    open_target: bool = True,
    reporter:    Reporter = _default_reporter,
) -> ClassifyResult:
    """把 ``src``（文件或目录）归类到 ``dst`` 目录里。

    :param src:         拖入的源（文件或目录）。
    :param dst:         目标作者目录（文件 / 子内容会被放入其中）。
    :param workdir:     ``dst`` 所属的 :class:`~module.artifact.core.runtime_config.WorkDir`；
                        用于打印 iwara 搜索 URL；``None`` 跳过。
    :param author_name: 用于 URL 占位符填充；``None`` 时跳过 URL 打印。
    :param open_target: 操作成功后是否打开 ``dst`` 资源管理器。
    :param reporter:    日志输出回调。
    :return: :class:`ClassifyResult` 摘要。
    """
    dst.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        result = _classify_dir(src, dst, reporter=reporter)
    elif src.is_file():
        result = _classify_file(src, dst, reporter=reporter)
    else:
        reporter('error', f'源既非文件也非目录，跳过: {src}')
        return ClassifyResult(src=src, dst=dst, failed=1)

    if result.ok:
        if open_target:
            _open_in_file_manager(dst, reporter=reporter)
        if workdir is not None and author_name:
            _print_search_url(workdir, author_name, reporter=reporter)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 子流程
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_dir(
    src: Path, dst: Path, *, reporter: Reporter,
) -> ClassifyResult:
    """目录归类：:func:`~base.fs.merge_into` 合并 → 若源空则删源。"""
    reporter('info', f'\n🔄 合并目录: {src.name} → {dst}')
    stats = merge_into(src, dst, reporter=reporter)

    src_removed = False
    if stats['failed'] == 0:
        try:
            if not any(src.iterdir()):
                safe_rmtree(src)
                src_removed = True
                reporter('info', f'🗑 源目录已清空并删除: {src}')
        except OSError as e:
            reporter('warn', f'清理源目录失败（保留）: {src} — {e}')

    if stats['failed']:
        reporter('error', f'⚠️ 合并完成但有 {stats["failed"]} 项失败')
    else:
        reporter('info',
                 f'✅ 合并完成: 新移 {stats["moved"]} | '
                 f'覆盖 {stats["overwritten"]}')

    return ClassifyResult(
        src=src, dst=dst,
        moved=stats['moved'], overwritten=stats['overwritten'],
        failed=stats['failed'], src_removed=src_removed,
    )


def _classify_file(
    src: Path, dst: Path, *, reporter: Reporter,
) -> ClassifyResult:
    """文件归类：目标已存在 → 跳过；否则 ``shutil.move``。"""
    target = dst / src.name
    if target.exists():
        reporter('warn', f'⏭️ 目标文件已存在，跳过: {target}')
        return ClassifyResult(src=src, dst=dst, skipped_file=True)
    try:
        shutil.move(str(src), str(target))
    except Exception as e:
        reporter('error', f'移动失败: {src.name} — {e}')
        return ClassifyResult(src=src, dst=dst, failed=1)
    reporter('info', f'✅ 已移动: {src.name}\n   → {target}')
    return ClassifyResult(src=src, dst=dst, moved=1)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _open_in_file_manager(p: Path, *, reporter: Reporter) -> None:
    """用系统默认动作打开目录；失败仅警告，不抛。"""
    try:
        if sys.platform == 'win32':
            os.startfile(str(p))                                # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(p)], check=False)
        else:
            subprocess.run(['xdg-open', str(p)], check=False)
        reporter('info', f'📂 已打开: {p}')
    except Exception as e:
        reporter('warn', f'打开资源管理器失败: {e}')


def _print_search_url(
    workdir: WorkDir, author_name: str, *, reporter: Reporter,
) -> None:
    """按 :attr:`WorkDir.search_url_template` 格式化并打印搜索 URL（空模板跳过）。"""
    tpl = workdir.search_url_template
    if not tpl:
        return
    url = tpl.replace('{author}', quote(author_name))
    reporter('info', f'🌐 搜索: {url}')
