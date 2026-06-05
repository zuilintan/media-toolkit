"""标题标准化工作流层：扫描作者目录下的 ``.zip`` / ``.cbz`` 源文件并重命名。

两种输入模式：

- **批量模式** :func:`preview_plans` ← 给定根目录，按 ``{root}/{author}/*.{zip,cbz}``
  结构扫描；作者目录名即作者，无 publisher 推导。
- **单文件 / 混合模式** :func:`preview_plans_for_inputs` ← 调用方先用
  :func:`derive_author` 推导作者（含 ``[社团 (作者)]`` 嵌套抽取），交互式解决
  冲突 / 缺失，再以 :class:`StdTitleInput` 喂入；apply 阶段统一保证文件落入
  ``{父目录}/{作者}/`` 子目录（必要时新建），抽取出的社团顺带写入
  ``[社团]：{社团名}.txt`` 标识（下游 :func:`~module.manga.workflow.make_meta.find_publisher` 自动识别）。
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

from module.manga.core.models import StdTitlePlan
from module.manga.core.config import FILE_EXTS
from module.manga.naming.parser import parse_name
from module.manga.naming.builder import build_new_name
from module.manga.naming.text import strip_leading_prefix
from base.fs import try_rename
from base.console import print_op_result, warn, error, info, emit
from module.manga.infra.parallel import run_plans


#: 发版商标识文件名分隔符（全角冒号），与
#: :data:`~module.manga.workflow.make_meta.FCOLON` 对齐
_FCOLON = '\uff1a'

_BRACKET_HEAD_RE = re.compile(r'^\s*\[([^\]]+)\]')
_NESTED_PAREN_RE = re.compile(r'^(.+?)\s*\(([^)]+)\)\s*$')


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


def _parse_bracket_head(stem: str) -> tuple[str, str]:
    """解析文件名首个 ``[xxx]`` 块，返回 ``(作者, 社团)``。

    - ``[社团 (作者)]`` → ``('作者', '社团')``
    - ``[作者]`` → ``('作者', '')``
    - 未命中 → ``('', '')``

    本函数仅做方括号解析，不处理开头噪音前缀；调用方负责先剥离
    ``(同人CG集)`` 这类噪音（参见 :func:`derive_author`）。
    """
    m = _BRACKET_HEAD_RE.match(stem)
    if not m:
        return '', ''
    inner = m.group(1).strip()
    nm = _NESTED_PAREN_RE.match(inner)
    if nm:
        return nm.group(2).strip(), nm.group(1).strip()
    return inner, ''


def derive_author(src_path: str) -> AuthorDerivation:
    """从源文件路径推导作者候选，返回 :class:`AuthorDerivation` 供调用方决策。

    预处理顺序与 :func:`~module.manga.naming.parser.parse_name` 对齐：复用
    :func:`~module.manga.naming.text.strip_leading_prefix` 剥离 ``(同人CG集)``
    这类开头噪音前缀，再交 :func:`_parse_bracket_head` 解析方括号头。
    """
    p = Path(src_path)
    stem = strip_leading_prefix(p.stem)
    bracket_author, bracket_publisher = _parse_bracket_head(stem)
    return AuthorDerivation(
        src_path          = str(p),
        parent_author     = p.parent.name,
        bracket_author    = bracket_author,
        bracket_publisher = bracket_publisher,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 输入项构造
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StdTitleInput:
    """已确定作者归属的单个 plan 输入项（picklable，可入并行 worker）。

    :ivar author_dir:     目标作者目录完整路径；父目录名 == ``author`` 时即父目录，
        否则为 ``父目录/{author}/`` 新建目标。
    :ivar publisher_file: 发版商标识文件完整路径；``None`` 表示本项不创建。
    """
    src_path:       str
    author:         str
    author_dir:     str
    publisher_file: str | None = None


def build_input(src_path: str, author: str, publisher: str = '') -> StdTitleInput:
    """根据已确定作者构造 :class:`StdTitleInput`。

    - 父目录名 == ``author`` → ``author_dir`` 沿用父目录，不新建
    - 否则 → ``author_dir`` 指向 ``父目录/{author}/``，apply 阶段创建
    - ``publisher`` 非空时同步生成 ``[社团]：{publisher}.txt`` 路径
    """
    p          = Path(src_path)
    parent     = p.parent
    author_dir = parent if parent.name == author else parent / author
    pub_file   = (str(author_dir / f'[社团]{_FCOLON}{publisher}.txt')
                  if publisher else None)
    return StdTitleInput(
        src_path       = str(p),
        author         = author,
        author_dir     = str(author_dir),
        publisher_file = pub_file,
    )


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
    suffix   = '.cbz' if file.suffix.lower() == '.zip' else file.suffix
    new_name = build_new_name(mi) + suffix
    return StdTitlePlan(
        src_path       = inp.src_path,
        author_dir     = inp.author_dir,
        author         = inp.author,
        old_name       = file.name,
        new_name       = new_name,
        info           = mi,
        publisher_file = inp.publisher_file,
    )


def _progress_line(idx: int, total: int, plan: StdTitlePlan) -> str:
    icon = ('!' if plan.needs_review
            else '*' if plan.changed
            else '-')
    return f'   {icon} [{idx}/{total}] {plan.old_name}'


def _iter_root_inputs(root: Path) -> list[StdTitleInput]:
    """批量模式：``{root}/{author}/*.{zip,cbz}`` → :class:`StdTitleInput` 列表。

    父目录名即作者，无 publisher 推导（批量模式假设输入已按作者归档）。
    """
    inputs: list[StdTitleInput] = []
    for author_dir in sorted(root.iterdir()):
        if not author_dir.is_dir():
            continue
        author = author_dir.name
        for f in sorted(author_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in FILE_EXTS:
                inputs.append(StdTitleInput(
                    src_path       = str(f),
                    author         = author,
                    author_dir     = str(author_dir),
                    publisher_file = None,
                ))
    return inputs


def preview_plans_for_inputs(
    inputs: list[StdTitleInput],
    jobs: int = 1,
    on_progress=None,
    cancel_token=None,
) -> list[StdTitlePlan]:
    """对已确定输入项批量产出 plan。

    供单文件 / 混合模式使用：调用方负责用 :func:`derive_author` 推导 + 交互式
    解决冲突 / 缺失，再 :func:`build_input` 构造每一项。

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

def _write_publisher_file(path: Path) -> str:
    """落 ``[社团]：XX.txt`` 标识。

    幂等：同名已存在直接复用；同目录存在不同社团文件则 warn 并跳过创建（罕见，
    通常表示原始数据需人工介入）。

    :return: ``'created'`` / ``'exists'`` / ``'conflict'``
    """
    if path.exists():
        return 'exists'
    # 同目录扫一遍是否已有「[社团]：XX.txt」（不同社团名）
    for sibling in path.parent.iterdir():
        if (sibling.is_file()
                and sibling.name != path.name
                and sibling.name.startswith(f'[社团]{_FCOLON}')
                and sibling.name.endswith('.txt')):
            warn(f'已存在不同社团标识，跳过创建: {sibling.name} (本次预期 {path.name})')
            return 'conflict'
    path.write_bytes(b'')
    return 'created'


def apply_plan(plan: StdTitlePlan) -> str:
    """执行单个 plan 的重命名 + publisher 标识写入。

    apply 顺序：

    1. ``author_dir`` 不存在则 ``mkdir``（仅在父目录下建一层）
    2. ``try_rename(src_path, author_dir / new_name)``
    3. rename 成功后处理 ``publisher_file``（幂等 + 多社团 warn 跳过）

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

    # rename 成功后再落 publisher（失败仅 warn，不影响主流程）
    if plan.publisher_file:
        try:
            _write_publisher_file(Path(plan.publisher_file))
        except Exception as e:
            warn(f'发版商标识写入失败: {Path(plan.publisher_file).name} — {e}')

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
