"""
classify.py — artifact-cli classify 子命令

模式
----
1. 拖入循环 (推荐): ``artifact-cli classify --drag``
2. 单次/批量:        ``artifact-cli classify <path> [<path> ...]``
3. 指定目标:         ``artifact-cli classify <path> --target /M/MK/作者/AuthorA``
                     （跳过候选交互；目标必须是已存在的目录）

交互
----
- 0 候选 → 列出所有 WorkDir，输入数字选择创建新作者目录；输入 q 跳过
- 1 候选 → 自动使用
- N 候选 → 列出候选，输入数字选择；输入 q 跳过

依赖: artifact.workflow.classify.* / base.drag_loop / base.console
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from base.console import emit, error, warn
from base.drag_loop import run_drag_loop
from base.fs import Reporter
from module.artifact.workflow.classify.alias import scan_aliases
from module.artifact.workflow.classify.config import Config, WorkDir, load_config
from module.artifact.workflow.classify.matcher import find_candidates
from module.artifact.workflow.classify.ops import classify_one
from module.artifact.workflow.classify.path import path_to_author_name


# 适配 base.fs.Reporter 协议 → base.console 函数（自动走 GUI sink 路由）
def _reporter(level: str, msg: str) -> None:
    {'info': emit, 'warn': warn, 'error': error}.get(level, emit)(msg)


def _prompt_index(prompt: str, n: int) -> int | None:
    while True:
        try:
            raw = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return None
        if not raw or raw.lower() == 'q':
            return None
        try:
            idx = int(raw)
        except ValueError:
            print(f'⚠️  请输入 1-{n} 之间的数字（或 q 跳过）')
            continue
        if 1 <= idx <= n:
            return idx - 1
        print(f'⚠️  请输入 1-{n} 之间的数字')


def _choose_target(
    author_name: str,
    candidates: list[Path],
    workdirs: list[WorkDir],
) -> Path | None:
    """根据候选数走 0/1/N 分支；返回选定目标作者目录或 None（跳过）。"""
    if not candidates:
        print(f'\n📭 未找到 "{author_name}" 的已有作者目录，请选择创建位置：')
        for i, wd in enumerate(workdirs, 1):
            print(f'  [{i}] {wd.path}')
        idx = _prompt_index('选择工作目录 (q 跳过): ', len(workdirs))
        if idx is None:
            return None
        return workdirs[idx].path / author_name

    if len(candidates) == 1:
        target = candidates[0]
        print(f'\n✅ 唯一候选: {target}')
        return target

    print(f'\n📋 "{author_name}" 找到 {len(candidates)} 个候选目录：')
    for i, c in enumerate(candidates, 1):
        print(f'  [{i}] {c}')
    idx = _prompt_index('选择目标 (q 跳过): ', len(candidates))
    if idx is None:
        return None
    return candidates[idx]


def _process_one(
    src: Path,
    cfg: Config,
    workdirs_paths: list[Path],
    alias_map: dict[str, Path],
    *,
    target_override: Path | None,
    open_target: bool,
    reporter: Reporter,
) -> None:
    if not src.exists():
        reporter('error', f'路径不存在: {src}')
        return

    reporter('info', f'\n📂 处理: {src}')
    author_name = path_to_author_name(src)
    reporter('info', f'👤 作者: {author_name}')

    if target_override is not None:
        if not target_override.is_dir():
            reporter('error', f'--target 不是已存在的目录: {target_override}')
            return
        target = target_override
    else:
        candidates = find_candidates(author_name, workdirs_paths, alias_map)
        target = _choose_target(author_name, candidates, cfg.workdirs)
        if target is None:
            reporter('warn', '已跳过')
            return

    classify_one(
        src=src,
        dst=target,
        workdir=cfg.find_workdir(target),
        author_name=author_name,
        open_target=open_target,
        reporter=reporter,
    )


def cmd_classify(args: argparse.Namespace) -> int:
    """classify 子命令调度。"""
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        sys.stderr.write(f'\n{e}\n')
        return 2

    if not cfg.workdirs:
        sys.stderr.write('❌ 配置中 artifact.workdirs 为空\n')
        return 2

    target_override = Path(args.target).resolve() if args.target else None
    open_target = not args.no_open

    if args.drag and target_override:
        sys.stderr.write('❌ --target 不可与 --drag 一起用\n')
        return 2
    if not args.drag and not args.paths:
        sys.stderr.write('❌ 请提供至少一个路径，或使用 --drag 进入循环模式\n')
        return 2

    workdirs_paths = [wd.path for wd in cfg.workdirs]
    # --target 直接绑定目录，无需别名映射；scan_aliases 走网络盘较慢，能跳就跳
    alias_map: dict[str, Path] = (
        {} if target_override
        else scan_aliases(workdirs_paths, reporter=_reporter)
    )

    if args.drag:
        run_drag_loop(
            process_one=lambda p: _process_one(
                p, cfg, workdirs_paths, alias_map,
                target_override=None,
                open_target=open_target,
                reporter=_reporter,
            ),
            title='classify',
            reporter=_reporter,
        )
        return 0

    for raw in args.paths:
        _process_one(
            Path(raw), cfg, workdirs_paths, alias_map,
            target_override=target_override,
            open_target=open_target,
            reporter=_reporter,
        )
    return 0


def add_classify_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        'paths', nargs='*', metavar='PATH',
        help='要归类的文件或目录路径（可多个；与 --drag 互斥）',
    )
    p.add_argument(
        '--drag', action='store_true',
        help='循环拖入模式（终端持续等待拖入）',
    )
    p.add_argument(
        '--target', default='', metavar='DIR',
        help='直接指定目标作者目录（已存在），跳过候选交互',
    )
    p.add_argument(
        '--no-open', action='store_true',
        help='完成后不自动打开目标资源管理器',
    )
