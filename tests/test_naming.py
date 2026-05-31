"""
test_naming.py — 文件名解析与构建的回归测试网

将 module/manga/data/examples.json 的每条用例参数化，验证完整往返:
    build_new_name(parse_name(author, input)) == expected

这是改动 parser.py / patterns.py / builder.py 前的安全网。
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
