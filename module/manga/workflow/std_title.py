"""标题标准化工作流层：扫描作者目录下的 ``.zip`` / ``.cbz`` 源文件并重命名。

两种输入模式：

- **批量模式** :func:`preview_plans` ← 给定根目录，按 ``{root}/{author}/*.{zip,cbz}``
  结构扫描；作者目录名即作者，社团从同目录旧方案 ``[社团]：XX.txt`` 兼容读取
  （即「迁移路径」），apply 后顺手清理。
- **单文件 / 混合模式** :func:`derive_inputs` → :func:`preview_plans_for_inputs`
  ← 单文件作者推导（含 ``[社团 (作者)]`` 嵌套抽取）统一在 :func:`derive_inputs`
  完成：``auto_author`` 命中即直采，否则回调 ``resolve_fn`` 交互式补全；apply
  阶段统一保证文件落入 ``{父目录}/{作者}/`` 子目录（必要时新建），抽取出的社团
  会以 ``[社团 (作者)]`` 形式回写到目标文件名上。
"""

from __future__ import annotations
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from module.manga.core.models import StdTitlePlan
from module.manga.core.config import FILE_EXTS
from module.manga.naming.parser import parse_name
from module.manga.naming.builder import build_new_name
from module.manga.naming.text import strip_leading_prefix, parse_bracket_head
from base.fs import try_rename
from base.console import print_op_result, warn, error, info, emit
from module.manga.infra.parallel import run_plans


#: 旧方案发版商标识文件名分隔符（全角冒号），仅作迁移兼容读取使用
_FCOLON = '\uff1a'
_LEGACY_PUBLISHER_RE = re.compile(
    rf'^[\[［]社团[\]］][{_FCOLON}:]\s*(?P<name>.+)\.txt$',
    re.IGNORECASE,
)


def find_legacy_publisher(dir_path: Path) -> tuple[str, str | None]:
    """旧方案兼容：扫 ``dir_path`` 下的 ``[社团]：XX.txt``，返回 ``(社团, txt 路径)``。

    用于一次性迁移：找到即把社团信息合入新文件名 ``[社团 (作者)]``，
    apply 成功后顺手删除该 ``.txt``。多文件冲突或无文件时返回 ``('', None)``。
    """
    if not dir_path.is_dir():
        return '', None
    hits: list[tuple[str, str]] = []
    try:
        for f in os.scandir(dir_path):
            if not f.is_file(follow_symlinks=False):
                continue
            m = _LEGACY_PUBLISHER_RE.match(f.name)
            if m:
                hits.append((m.group('name').strip(), f.path))
    except OSError:
        return '', None
    if len(hits) == 1:
        return hits[0]
    return '', None


# ═══════════════════════════════════════════════════════════════════════════════
# 作者推导（单文件场景）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuthorDerivation:
    """从源文件路径推导出的作者候选信息。

    供 CLI / GUI 共享：双路一致 → 自动采纳；冲突 → 交互式选择；全空 → 手填。

    :ivar parent_author:     文件父目录名（始终填充，但调用方可视情况忽略）。
    :ivar bracket_author:    文件名首个 ``[xxx]`` 提取的作者；嵌套
        ``[社团 (作者)]`` 时为 ``作者``，单层 ``[作者]`` 时为 ``作者``，未命中为 ``''``。
    :ivar bracket_publisher: 嵌套 ``[社团 (作者)]`` 时为 ``社团``；其它为 ``''``。
    """
    src_path:          str
    parent_author:     str
    bracket_author:    str
    bracket_publisher: str

    @property
    def auto_author(self) -> str:
        """无歧义即返回作者；冲突或全空时返回 ``''``。

        - 仅父目录命中 → 父目录
        - 仅 ``[]`` 命中 → ``[]``
        - 双路一致 → 任一
        - 双路冲突 / 全空 → ``''``
        """
        if self.parent_author and self.bracket_author:
            return (self.parent_author
                    if self.parent_author == self.bracket_author else '')
        return self.parent_author or self.bracket_author

    @property
    def conflict(self) -> bool:
        """双路都命中且不一致。"""
        return bool(self.parent_author and self.bracket_author
                    and self.parent_author != self.bracket_author)

    @property
    def empty(self) -> bool:
        """双路都未命中。"""
        return not self.parent_author and not self.bracket_author


def derive_author(src_path: str) -> AuthorDerivation:
    """从源文件路径推导作者候选，返回 :class:`AuthorDerivation` 供调用方决策。

    预处理顺序与 :func:`~module.manga.naming.parser.parse_name` 对齐：复用
    :func:`~module.manga.naming.text.strip_leading_prefix` 剥离 ``(同人CG集)``
    这类开头噪音前缀，再交 :func:`~module.manga.naming.text.parse_bracket_head`
    解析方括号头。
    """
    p = Path(src_path)
    stem = strip_leading_prefix(p.stem)
    bracket_author, bracket_publisher = parse_bracket_head(stem)
    return AuthorDerivation(
        src_path          = str(p),
        parent_author     = p.parent.name,
        bracket_author    = bracket_author,
        bracket_publisher = bracket_publisher,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 输入项构造（主线程 scan 阶段调用）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StdTitleInput:
    """已确定作者归属的单个 plan 输入项（picklable，可入并行 worker）。

    :ivar author_dir:     目标作者目录完整路径；父目录名 == ``author`` 时即父目录，
        否则为 ``父目录/{author}/`` 新建目标。
    :ivar publisher:      社团名；空表示无社团。
    :ivar legacy_publisher_txt: 旧方案 ``[社团]：XX.txt`` 路径，apply 成功后清理；
        ``None`` 表示无需清理。
    """
    src_path:             str
    author:               str
    author_dir:           str
    publisher:            str = ''
    legacy_publisher_txt: str | None = None


def build_input(
    src_path: str, author: str, publisher: str = '',
    legacy_publisher_txt: str | None = None,
) -> StdTitleInput:
    """根据已确定作者构造 :class:`StdTitleInput`。

    - 父目录名 == ``author`` → ``author_dir`` 沿用父目录，不新建
    - 否则 → ``author_dir`` 指向 ``父目录/{author}/``，apply 阶段创建
    """
    p          = Path(src_path)
    parent     = p.parent
    author_dir = parent if parent.name == author else parent / author
    return StdTitleInput(
        src_path             = str(p),
        author               = author,
        author_dir           = str(author_dir),
        publisher            = publisher,
        legacy_publisher_txt = legacy_publisher_txt,
    )


#: ``resolve_fn(path, derivation) -> (author, publisher) | None``；返回 ``None``
#: 表示跳过该文件。详见 :func:`derive_inputs`。
AuthorResolveFn = Callable[[Path, AuthorDerivation], tuple[str, str] | None]


class StdTitleAbort(Exception):
    """``resolve_fn`` 抛出以中止整批推导。

    典型场景：CLI non-tty 模式遇到无法自动推导且无法 prompt 的文件，必须整批
    停下让用户先整理输入。:func:`derive_inputs` 让它原样冒泡，调用方捕获即可。
    """


def auto_fallback(path: Path, deriv: AuthorDerivation) -> tuple[str, str] | None:
    """编排器 / GUI 自动模式的默认 ``resolve_fn``。

    优先级：``bracket_author`` → ``parent_author``；两者皆空才放弃。
    pack_pic 产物常落在「漫画根目录」（``Comic/``）而非作者目录，``parent_author``
    不可用，故 bracket 优先。"""
    author = deriv.bracket_author or deriv.parent_author
    if not author:
        return None
    publisher = (deriv.bracket_publisher
                 if author == deriv.bracket_author else '')
    return author, publisher


def derive_inputs(
    paths: list[Path],
    resolve_fn: AuthorResolveFn | None = None,
    normalize_author: Callable[[str], str] | None = None,
) -> list[StdTitleInput]:
    """主线程批量推导作者并构造 :class:`StdTitleInput` 列表（单文件 / 混合模式入口）。

    - ``auto_author`` 命中 → 直采（无副作用）
    - 否则调用 ``resolve_fn(path, deriv)``；返回 ``None`` 即跳过该文件，
      ``resolve_fn`` 为 ``None`` 时不可解析项一律跳过（auto-only 语义）
    - ``resolve_fn`` 抛 :class:`StdTitleAbort` 表示整批终止，原样向外冒泡
    - 拿到 ``author`` 后（无论来源）若提供 ``normalize_author``，统一过一道
      规范化——典型用法是
      :meth:`~module.manga.workflow.author_library.AuthorLibrary.resolve`，按
      简繁归一对齐到库里既有主名，避免出现"作者甲（繁）"与"作者甲（简）"
      两份目录
    - 若文件名首块没有抽到社团，但父目录里有旧方案 ``[社团]：XX.txt``，按迁移
      路径自动采纳并把 .txt 路径挂在输入上，apply 成功后清理

    所有交互（CLI prompt / GUI 弹窗）由调用方在 ``resolve_fn`` 内完成，本函数
    本身不做任何 I/O，便于在 :class:`~module.manga.gui.tabs.base_tab.BaseTab._validate_scan_target`
    主线程内同步调用。
    """
    inputs: list[StdTitleInput] = []
    for p in paths:
        path  = Path(p)
        deriv = derive_author(str(path))
        author = deriv.auto_author
        if author:
            publisher = (deriv.bracket_publisher
                         if author == deriv.bracket_author else '')
        elif resolve_fn is not None:
            result = resolve_fn(path, deriv)
            if result is None:
                continue
            author, publisher = result
        else:
            continue
        if normalize_author is not None:
            author = normalize_author(author) or author
        # 迁移路径：bracket 没抽到社团时回退扫父目录旧方案 .txt
        legacy_txt: str | None = None
        if not publisher:
            legacy_pub, legacy_txt = find_legacy_publisher(path.parent)
            if legacy_pub:
                publisher = legacy_pub
        inputs.append(build_input(str(path), author, publisher, legacy_txt))
    return inputs


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描 & 计划
# ═══════════════════════════════════════════════════════════════════════════════

def _plan_one(inp: StdTitleInput) -> StdTitlePlan:
    """模块级 worker（picklable）：:class:`StdTitleInput` → :class:`~module.manga.core.models.StdTitlePlan`。

    DEBUG 由 :func:`~module.manga.presentation.view.print_std_title_preview`
    在渲染卡片时统一触发，本函数无副作用，安全用于子进程。
    """
    file     = Path(inp.src_path)
    mi       = parse_name(inp.author, file.stem)
    # 显式 publisher 覆盖：bracket head 未抽到，但 derive_inputs 通过旧方案
    # .txt 或 GUI/CLI 交互拿到了社团名，需把这一信息塞回 mi 才能在 builder
    # 输出 [社团 (作者)] 形态
    if inp.publisher and not mi.publisher:
        mi.publisher = inp.publisher
    suffix   = '.cbz' if file.suffix.lower() == '.zip' else file.suffix
    new_name = build_new_name(mi) + suffix
    return StdTitlePlan(
        src_path             = inp.src_path,
        author_dir           = inp.author_dir,
        author               = inp.author,
        old_name             = file.name,
        new_name             = new_name,
        info                 = mi,
        legacy_publisher_txt = inp.legacy_publisher_txt,
    )


def _progress_line(idx: int, total: int, plan: StdTitlePlan) -> str:
    icon = ('!' if plan.needs_review
            else '*' if plan.changed
            else '-')
    return f'   {icon} [{idx}/{total}] {plan.old_name}'


def _iter_root_inputs(root: Path) -> list[StdTitleInput]:
    """批量模式：``{root}/{author}/*.{zip,cbz}`` → :class:`StdTitleInput` 列表。

    父目录名即作者；若作者目录下存在旧方案 ``[社团]：XX.txt``，按迁移路径采纳
    该社团并把 .txt 路径挂在每个输入上，apply 成功后清理。
    """
    inputs: list[StdTitleInput] = []
    for author_dir in sorted(root.iterdir()):
        if not author_dir.is_dir():
            continue
        author = author_dir.name
        legacy_pub, legacy_txt = find_legacy_publisher(author_dir)
        for f in sorted(author_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in FILE_EXTS:
                inputs.append(StdTitleInput(
                    src_path             = str(f),
                    author               = author,
                    author_dir           = str(author_dir),
                    publisher            = legacy_pub,
                    legacy_publisher_txt = legacy_txt,
                ))
    return inputs


def preview_plans_for_inputs(
    inputs: list[StdTitleInput],
    jobs: int = 1,
    on_progress=None,
    cancel_token=None,
) -> list[StdTitlePlan]:
    """对已确定输入项批量产出 plan。

    供单文件 / 混合模式使用：调用方负责用 :func:`derive_inputs` 统一推导 +
    交互式补全作者，再喂入本函数。

    :param jobs: 1=串行；>1=并行进程数；0=自动 ``min(cpu, 4)``。
    """
    return run_plans(
        inputs, _plan_one, jobs=jobs, progress_line=_progress_line,
        on_progress=on_progress, cancel_token=cancel_token,
    )


def preview_plans(
    root: str, jobs: int = 1, on_progress=None, cancel_token=None,
) -> list[StdTitlePlan]:
    """扫描根目录下所有作者目录，汇总重命名计划（批量模式）。

    plan 阶段是纯字符串处理（毫秒级），并行收益有限，主要作用是统一接口
    + 大规模目录下的进度反馈。

    :param jobs: 1=串行；>1=并行进程数；0=自动 ``min(cpu, 4)``。
        ≥ 4 个文件时才实际启用并行。
    :param on_progress: 每完成一项即回调 ``f(done, total)``。
    :param cancel_token: ``threading.Event``，已 set 时提前退出。
    """
    root_path = Path(root)
    if not root_path.exists():
        error(f'目录不存在: {root}')
        return []
    inputs      = _iter_root_inputs(root_path)
    author_dirs = {Path(inp.author_dir) for inp in inputs}
    zip_n = sum(1 for inp in inputs if inp.src_path.lower().endswith('.zip'))
    cbz_n = len(inputs) - zip_n
    emit(f'  找到文件: {zip_n} 个 .zip，{cbz_n} 个 .cbz'
         f'（{len(author_dirs)} 个作者目录）')
    return preview_plans_for_inputs(
        inputs, jobs=jobs, on_progress=on_progress, cancel_token=cancel_token,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 执行重命名
# ═══════════════════════════════════════════════════════════════════════════════

def _cleanup_legacy_txt(path_str: str) -> None:
    """旧方案 ``[社团]：XX.txt`` 一次性清理（best effort，失败仅 warn）。"""
    p = Path(path_str)
    try:
        if p.exists():
            p.unlink()
            emit(f'   🧹 已清理旧标识: {p.name}')
    except OSError as e:
        warn(f'旧标识清理失败: {p.name} — {e}')


def apply_plan(plan: StdTitlePlan) -> str:
    """执行单个 plan 的重命名。

    apply 顺序：

    1. ``author_dir`` 不存在则 ``mkdir``（仅在父目录下建一层）
    2. ``try_rename(src_path, author_dir / new_name)``
    3. rename 成功后若挂有旧方案 ``[社团]：XX.txt``，best-effort 清理

    :return: ``'ok'`` / ``'skip'`` / ``'error'``；``'skip'`` 表示需审核 /
        无变化 / 目标已存在等不阻断的跳过原因。
    """
    if not plan.changed:
        return 'skip'
    if plan.needs_review:
        warn(f'跳过（需审核）: {plan.old_name}')
        return 'skip'

    src_path   = Path(plan.src_path)
    author_dir = Path(plan.author_dir)
    new_path   = author_dir / plan.new_name
    try:
        author_dir.mkdir(parents=False, exist_ok=True)
        result = try_rename(src_path, new_path)
        if result == 'exists':
            warn(f'跳过（目标已存在）: {plan.new_name}')
            return 'skip'
        emit(f'   ✅ {plan.old_name} — 已处理')
    except Exception as e:
        error(f'{plan.old_name} — {e}')
        return 'error'

    # rename 成功后清理旧方案 .txt（迁移路径专用，幂等）
    if plan.legacy_publisher_txt:
        _cleanup_legacy_txt(plan.legacy_publisher_txt)

    return 'ok'


def apply_plans(
    plans: list[StdTitlePlan], dry_run: bool = True, cancel_token=None,
) -> int:
    """执行重命名计划。

    :param dry_run: ``True`` 时仅预览，不实际执行。
    :param cancel_token: ``threading.Event``，已 set 时提前退出。
    :return: 失败数量（``dry_run`` 时为 0）。
    """
    if dry_run:
        info('\n🔍 预览模式 — 未做任何更改。使用 --apply 参数执行。')
        return 0

    def _cancelled() -> bool:
        return cancel_token is not None and cancel_token.is_set()

    ok_n = fail = skip = 0
    for p in plans:
        if _cancelled():
            emit('  ⏹️  已取消')
            break
        result = apply_plan(p)
        if result == 'ok':
            ok_n += 1
        elif result == 'skip':
            skip += 1
        else:
            fail += 1

    print_op_result(ok_n, fail, skip)
    return fail
