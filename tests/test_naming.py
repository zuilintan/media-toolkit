"""文件名解析与构建的回归测试网（改动
:mod:`~module.manga.naming.parser` / :mod:`~module.manga.core.patterns` /
:mod:`~module.manga.naming.builder` 前的安全网）。

将 ``module/manga/data/examples.json`` 的每条用例参数化，验证完整往返::

    build_new_name(parse_name(author, input)) == expected
"""

from __future__ import annotations

import pytest

from module.manga.naming.parser import parse_name
from module.manga.naming.builder import build_new_name
from module.manga.extras.examples import load_examples

_EXAMPLES = load_examples()


@pytest.mark.parametrize(
    "author,name,expected",
    _EXAMPLES,
    ids=[name for _author, name, _expected in _EXAMPLES],
)
def test_example_roundtrip(author: str, name: str, expected: str) -> None:
    assert build_new_name(parse_name(author, name)) == expected
