"""
session.py — 操作记录 & 回退

记录每次 apply_sourcefile_plans 的成功条目，支持按 session 逐条撤销。
记录文件: config.SESSIONS_FILE（JSON 格式）

注：当前 apply_sourcefile_plans 暂不调用 append_session（"暂时不需要写
session"）；本模块的 list_sessions / rollback 仅用于读取历史 session 数据。

依赖: models / config / utils / console
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from mt.core.models import SourceFilePlan
from mt.core.config import SESSIONS_FILE
from mt.infra.utils import try_rename
from mt.infra.console import print_op_result, SEP, warn, error, info, emit


# ═══════════════════════════════════════════════════════════════════════════════
# 持久化
# ═══════════════════════════════════════════════════════════════════════════════

def _load() -> list[dict]:
    p = Path(SESSIONS_FILE)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []


def _save(sessions: list[dict]) -> None:
    Path(SESSIONS_FILE).write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2), encoding='utf-8'
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════════════════

def append_session(renamed: list[SourceFilePlan]) -> None:
    """将本次成功重命名的条目记录为新 session。"""
    now     = datetime.now()
    session = {
        'session_id': now.strftime('%Y%m%d_%H%M%S'),
        'timestamp':  now.isoformat(timespec='seconds'),
        'entries': [
            {'author_dir': p.author_dir, 'old_name': p.old_name, 'new_name': p.new_name}
            for p in renamed
        ],
    }
    sessions = _load()
    sessions.append(session)
    _save(sessions)
    emit(f'🔖 已记录本次操作 [session {session["session_id"]}，共 {len(renamed)} 条]')


def list_sessions() -> None:
    """打印所有可回退的 session。"""
    sessions = _load()
    if not sessions:
        info('📭 没有可回退的操作记录。')
        return
    emit(f'\n{SEP}')
    emit(f'  共 {len(sessions)} 条操作记录（最新在下，--rollback 默认撤销最后一条）')
    emit(SEP)
    for s in sessions:
        emit(f'  [{s["session_id"]}]  {s["timestamp"]}  ({len(s["entries"])} 项)')
    emit(f'{SEP}\n')


def rollback(session_id: str | None = None) -> None:
    """撤销一次 apply 操作。

    Args:
        session_id: None 则撤销最近一次；否则撤销指定 session。
    """
    sessions = _load()
    if not sessions:
        info('📭 没有可回退的操作记录。')
        return

    if session_id is None:
        target = sessions[-1]
    else:
        matches = [s for s in sessions if s['session_id'] == session_id]
        if not matches:
            error(f'找不到 session: {session_id}')
            list_sessions()
            return
        target = matches[0]

    n = len(target['entries'])
    emit(f'\n🔄 回退 [{target["session_id"]}]  {target["timestamp"]}  ({n} 项)')
    ok_n = fail = 0

    for e in target['entries']:
        new_path = Path(e['author_dir']) / e['new_name']
        old_path = Path(e['author_dir']) / e['old_name']
        if not new_path.exists():
            warn(f'已不存在（可能已被移动）: {new_path}')
            fail += 1
            continue
        try:
            result = try_rename(new_path, old_path)
            if result == 'exists':
                warn(f'跳过（回退目标已存在）: {old_path.name}')
                fail += 1
            else:
                emit(f'  ✅ {e["new_name"]} → {e["old_name"]}')
                ok_n += 1
        except Exception as ex:
            error(f'{e["new_name"]} — {ex}')
            fail += 1

    print_op_result(ok_n, fail, label='回退完成')
    if fail == 0:
        sessions = [s for s in sessions if s['session_id'] != target['session_id']]
        _save(sessions)
        emit(f'🗑  session [{target["session_id"]}] 已从记录中移除')
    else:
        warn('存在失败项，session 记录保留，请手动检查后重试。')
