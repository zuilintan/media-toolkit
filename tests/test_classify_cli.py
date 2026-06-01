"""tests for artifact.cli.classify (interactive selection + dispatcher)."""

from __future__ import annotations
from pathlib import Path

import pytest

from module.artifact.cli.classify import _choose_target, _prompt_index
from module.artifact.core.runtime_config import WorkDir


# ═══════════════════════════════════════════════════════════════════════════════
# _prompt_index
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromptIndex:
    def test_valid_number(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr('builtins.input', lambda _: '2')
        assert _prompt_index('?', 3) == 1   # 1-based → 0-based

    def test_quit(self, monkeypatch) -> None:
        monkeypatch.setattr('builtins.input', lambda _: 'q')
        assert _prompt_index('?', 3) is None

    def test_empty_quits(self, monkeypatch) -> None:
        monkeypatch.setattr('builtins.input', lambda _: '')
        assert _prompt_index('?', 3) is None

    def test_ctrl_c_quits(self, monkeypatch, capsys) -> None:
        def raise_kbd(_): raise KeyboardInterrupt
        monkeypatch.setattr('builtins.input', raise_kbd)
        assert _prompt_index('?', 3) is None

    def test_reject_invalid_then_accept(self, monkeypatch, capsys) -> None:
        inputs = iter(['abc', '99', '0', '2'])
        monkeypatch.setattr('builtins.input', lambda _: next(inputs))
        assert _prompt_index('?', 3) == 1
        out = capsys.readouterr().out
        # 3 次错误提示
        assert out.count('请输入') == 3


# ═══════════════════════════════════════════════════════════════════════════════
# _choose_target
# ═══════════════════════════════════════════════════════════════════════════════

class TestChooseTarget:
    def _wd(self, p: Path) -> WorkDir:
        return WorkDir(path=p, search_url_template='')

    def test_single_candidate_auto(
        self, tmp_path: Path, monkeypatch, capsys,
    ) -> None:
        only = tmp_path / 'wd' / 'AuthorA'
        only.mkdir(parents=True)
        # 不该调 input
        monkeypatch.setattr(
            'builtins.input',
            lambda _: pytest.fail('单候选不应交互'),
        )
        chosen = _choose_target('AuthorA', [only], [self._wd(tmp_path / 'wd')])
        assert chosen == only

    def test_multi_candidate_pick(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        a = tmp_path / 'wd1' / 'AuthorA'; a.mkdir(parents=True)
        b = tmp_path / 'wd2' / 'AuthorA'; b.mkdir(parents=True)
        monkeypatch.setattr('builtins.input', lambda _: '2')
        chosen = _choose_target(
            'AuthorA', [a, b],
            [self._wd(tmp_path / 'wd1'), self._wd(tmp_path / 'wd2')],
        )
        assert chosen == b

    def test_multi_candidate_quit(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        a = tmp_path / 'wd1' / 'A'; a.mkdir(parents=True)
        b = tmp_path / 'wd2' / 'A'; b.mkdir(parents=True)
        monkeypatch.setattr('builtins.input', lambda _: 'q')
        # 多候选分支不使用 workdirs，传 [] 让"无关参数"显式可见
        assert _choose_target('A', [a, b], []) is None

    def test_zero_candidate_creates(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        wd1 = tmp_path / 'wd1'; wd1.mkdir()
        wd2 = tmp_path / 'wd2'; wd2.mkdir()
        monkeypatch.setattr('builtins.input', lambda _: '1')
        chosen = _choose_target(
            'NewAuthor', [], [self._wd(wd1), self._wd(wd2)],
        )
        # 0 候选时返回 "WorkDir1 / 作者名"（目录此时尚不存在）
        assert chosen == wd1 / 'NewAuthor'

    def test_zero_candidate_quit(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.setattr('builtins.input', lambda _: 'q')
        assert _choose_target(
            'X', [], [self._wd(tmp_path)],
        ) is None
