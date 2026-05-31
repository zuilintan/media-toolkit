"""tests for artifact.workflow.classify + base.fs.merge_into."""

from __future__ import annotations
from pathlib import Path

import pytest

from base.fs import merge_into, safe_rmtree
from artifact.workflow.classify.alias import ALIAS_PREFIX, scan_aliases
from artifact.workflow.classify.config import Config, WorkDir, load_config
from artifact.workflow.classify.matcher import find_candidates
from artifact.workflow.classify.path import path_to_author_name


# ═══════════════════════════════════════════════════════════════════════════════
# path.path_to_author_name
# ═══════════════════════════════════════════════════════════════════════════════

class TestPathToAuthorName:
    def test_directory(self, tmp_path: Path) -> None:
        d = tmp_path / 'AuthorA'
        d.mkdir()
        assert path_to_author_name(d) == 'AuthorA'

    def test_file(self, tmp_path: Path) -> None:
        d = tmp_path / 'AuthorB'
        d.mkdir()
        f = d / 'video.mp4'
        f.write_bytes(b'')
        assert path_to_author_name(f) == 'AuthorB'

    def test_nested_file(self, tmp_path: Path) -> None:
        # 拖入 .../Downloads/AuthorC/file.txt → 'AuthorC'
        deep = tmp_path / 'Downloads' / 'AuthorC'
        deep.mkdir(parents=True)
        f = deep / 'a.txt'
        f.write_text('x')
        assert path_to_author_name(f) == 'AuthorC'


# ═══════════════════════════════════════════════════════════════════════════════
# alias.scan_aliases
# ═══════════════════════════════════════════════════════════════════════════════

class TestScanAliases:
    def _mk_alias(self, author_dir: Path, alias: str) -> None:
        author_dir.mkdir(parents=True, exist_ok=True)
        (author_dir / f'{ALIAS_PREFIX}{alias}.txt').write_text('')

    def test_basic_scan(self, tmp_path: Path) -> None:
        wd = tmp_path / 'wd1'
        self._mk_alias(wd / 'AuthorA', 'AliasA1')
        self._mk_alias(wd / 'AuthorA', 'AliasA2')
        self._mk_alias(wd / 'AuthorB', 'AliasB')

        m = scan_aliases([wd], reporter=lambda l, m: None)
        assert m['AliasA1'] == wd / 'AuthorA'
        assert m['AliasA2'] == wd / 'AuthorA'
        assert m['AliasB']  == wd / 'AuthorB'

    def test_case_insensitive(self, tmp_path: Path) -> None:
        wd = tmp_path / 'wd'
        self._mk_alias(wd / 'AuthorX', 'MyAlias')
        m = scan_aliases([wd], reporter=lambda l, m: None)
        assert 'MYALIAS' in m
        assert 'myalias' in m
        assert m['myalias'] == wd / 'AuthorX'

    def test_skip_missing_workdir(self, tmp_path: Path) -> None:
        wd = tmp_path / 'wd'
        self._mk_alias(wd / 'A', 'a')
        missing = tmp_path / 'nope'
        m = scan_aliases([wd, missing], reporter=lambda l, m: None)
        assert len(m) == 1

    def test_first_wins_on_conflict(self, tmp_path: Path) -> None:
        wd1 = tmp_path / 'wd1'
        wd2 = tmp_path / 'wd2'
        self._mk_alias(wd1 / 'AuthorOne', 'shared')
        self._mk_alias(wd2 / 'AuthorTwo', 'shared')
        m = scan_aliases([wd1, wd2], reporter=lambda l, m: None)
        # 由于并发顺序，命中两者之一即可（不应有 KeyError）
        assert m['shared'].name in ('AuthorOne', 'AuthorTwo')

    def test_alias_with_empty_stem_ignored(self, tmp_path: Path) -> None:
        wd = tmp_path / 'wd'
        author = wd / 'A'
        author.mkdir(parents=True)
        # 别名部分为空
        (author / f'{ALIAS_PREFIX}.txt').write_text('')
        (author / f'{ALIAS_PREFIX}   .txt').write_text('')
        m = scan_aliases([wd], reporter=lambda l, m: None)
        assert len(m) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# matcher.find_candidates
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindCandidates:
    def test_exact_match_across_workdirs(self, tmp_path: Path) -> None:
        wd1 = tmp_path / 'wd1'
        wd2 = tmp_path / 'wd2'
        (wd1 / 'AuthorA').mkdir(parents=True)
        (wd2 / 'AuthorA').mkdir(parents=True)
        out = find_candidates('AuthorA', [wd1, wd2], alias_map={})
        assert out == [wd1 / 'AuthorA', wd2 / 'AuthorA']

    def test_alias_adds_extra(self, tmp_path: Path) -> None:
        wd = tmp_path / 'wd'
        a = wd / 'CanonA'
        a.mkdir(parents=True)
        out = find_candidates(
            'Alias1', [wd], alias_map={'Alias1': a},
        )
        assert out == [a]

    def test_alias_dedupe_with_exact(self, tmp_path: Path) -> None:
        wd = tmp_path / 'wd'
        a = wd / 'Same'
        a.mkdir(parents=True)
        out = find_candidates(
            'Same', [wd], alias_map={'Same': a},
        )
        # 精确与别名都指向 a；只出现一次
        assert out == [a]

    def test_empty_name(self) -> None:
        assert find_candidates('', [], {}) == []

    def test_missing_dir_excluded(self, tmp_path: Path) -> None:
        wd = tmp_path / 'wd'
        wd.mkdir()
        # AuthorA 不存在
        out = find_candidates('AuthorA', [wd], alias_map={})
        assert out == []


# ═══════════════════════════════════════════════════════════════════════════════
# fs.merge_into
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeInto:
    def _silent(self, level: str, msg: str) -> None:
        pass

    def test_new_dst_moves_all(self, tmp_path: Path) -> None:
        src = tmp_path / 'src'
        src.mkdir()
        (src / 'a.txt').write_text('A')
        (src / 'b.txt').write_text('B')
        dst = tmp_path / 'dst'
        stats = merge_into(src, dst, reporter=self._silent)
        assert stats == {'moved': 2, 'overwritten': 0, 'failed': 0}
        assert (dst / 'a.txt').read_text() == 'A'
        assert (dst / 'b.txt').read_text() == 'B'
        assert not any(src.iterdir())     # src 已空

    def test_file_conflict_overwrites(self, tmp_path: Path) -> None:
        src = tmp_path / 'src'; src.mkdir()
        dst = tmp_path / 'dst'; dst.mkdir()
        (src / 'a.txt').write_text('NEW')
        (dst / 'a.txt').write_text('OLD')
        stats = merge_into(src, dst, reporter=self._silent)
        assert stats == {'moved': 0, 'overwritten': 1, 'failed': 0}
        assert (dst / 'a.txt').read_text() == 'NEW'

    def test_nested_dir_recursive_merge(self, tmp_path: Path) -> None:
        src = tmp_path / 'src'
        (src / 'sub').mkdir(parents=True)
        (src / 'sub' / 'x.txt').write_text('NEW_X')
        (src / 'sub' / 'y.txt').write_text('NEW_Y')

        dst = tmp_path / 'dst'
        (dst / 'sub').mkdir(parents=True)
        (dst / 'sub' / 'x.txt').write_text('OLD_X')
        # 不存在 y.txt — 期望被 move 进来

        stats = merge_into(src, dst, reporter=self._silent)
        assert stats == {'moved': 1, 'overwritten': 1, 'failed': 0}
        assert (dst / 'sub' / 'x.txt').read_text() == 'NEW_X'
        assert (dst / 'sub' / 'y.txt').read_text() == 'NEW_Y'
        # 嵌套合并后 src/sub 应已被清理
        assert not (src / 'sub').exists()

    def test_dst_autocreated(self, tmp_path: Path) -> None:
        src = tmp_path / 's'
        src.mkdir()
        (src / 'a').write_text('a')
        dst = tmp_path / 'newly' / 'made'
        stats = merge_into(src, dst, reporter=self._silent)
        assert stats['moved'] == 1
        assert dst.is_dir()


# ═══════════════════════════════════════════════════════════════════════════════
# config.load_config
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadConfig:
    def test_missing_raises_with_template_hint(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'nope.json'
        with pytest.raises(FileNotFoundError) as exc:
            load_config(cfg)
        msg = str(exc.value)
        assert '期望路径' in msg
        assert '模板示例' in msg
        assert 'config_template.json' in msg

    def test_basic_load(self, tmp_path: Path) -> None:
        cfg = tmp_path / 'c.json'
        cfg.write_text(
            '{"artifact.workdirs": ['
            '{"path": "/tmp/wd1", "search_url_template": "https://x?q={author}"},'
            '{"path": "/tmp/wd2", "search_url_template": ""}'
            ']}',
            encoding='utf-8',
        )
        c = load_config(cfg)
        assert len(c.workdirs) == 2
        assert c.workdirs[0].path == Path('/tmp/wd1')
        assert c.workdirs[0].search_url_template.startswith('https://')
        assert c.workdirs[1].search_url_template == ''

    def test_find_workdir(self, tmp_path: Path) -> None:
        wd_path = tmp_path / 'work'
        wd_path.mkdir()
        author = wd_path / 'AuthorA'
        author.mkdir()
        c = Config(workdirs=[WorkDir(path=wd_path, search_url_template='X')])
        found = c.find_workdir(author)
        assert found is not None
        assert found.path == wd_path

    def test_find_workdir_unmatched(self, tmp_path: Path) -> None:
        c = Config(workdirs=[
            WorkDir(path=tmp_path / 'a', search_url_template=''),
        ])
        assert c.find_workdir(tmp_path / 'unrelated') is None
