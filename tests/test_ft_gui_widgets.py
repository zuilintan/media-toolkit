"""tests for artifact.gui.widgets (pure functions + minimal Qt smoke)."""

from __future__ import annotations
from pathlib import Path

import pytest

# 标记：未装 PySide6 时整套跳过
PySide6 = pytest.importorskip('PySide6')

from PySide6.QtCore import QUrl                          # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

from module.artifact.gui.widgets.candidate_dialog import CandidateDialog   # noqa: E402
from module.artifact.gui.widgets.drop_area import urls_to_paths            # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    """共享一个 QApplication 实例，避免重复初始化。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ═══════════════════════════════════════════════════════════════════════════════
# urls_to_paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestUrlsToPaths:
    def test_local_existing_files_kept(self, tmp_path: Path) -> None:
        f1 = tmp_path / 'a.txt'; f1.write_text('')
        f2 = tmp_path / 'sub'; f2.mkdir()
        urls = [QUrl.fromLocalFile(str(f1)), QUrl.fromLocalFile(str(f2))]
        out = urls_to_paths(urls)
        assert out == [f1, f2]

    def test_missing_paths_filtered(self, tmp_path: Path) -> None:
        urls = [QUrl.fromLocalFile(str(tmp_path / 'nope.txt'))]
        assert urls_to_paths(urls) == []

    def test_non_local_url_filtered(self) -> None:
        urls = [QUrl('https://example.com/x.txt')]
        assert urls_to_paths(urls) == []


# ═══════════════════════════════════════════════════════════════════════════════
# CandidateDialog（构造 + 选中索引）
# ═══════════════════════════════════════════════════════════════════════════════

class TestCandidateDialog:
    def test_default_select_first(self, qapp, tmp_path: Path) -> None:
        a = tmp_path / 'A'; b = tmp_path / 'B'
        dlg = CandidateDialog('t', 'p', [a, b])
        assert dlg.selected_index() == 0
        dlg.deleteLater()

    def test_empty_candidates_no_selection(self, qapp) -> None:
        dlg = CandidateDialog('t', 'p', [])
        assert dlg.selected_index() is None
        dlg.deleteLater()
