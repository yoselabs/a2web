"""The vendored TSV codec must stay byte-identical to a2kit's.

`src/a2web/_tsv_compat.py` is a deliberate copy (`sunset-a2kit-dependency`
Phase 2). While a2kit is still installed we can check the copy the strongest
way available: run both encoders over the same adversarial inputs and demand
identical output. The moment they diverge, the wire goldens are lying about
what the swap changed.

**This file dies with a2kit.** Phase 4.9 removes the dependency, at which point
the import below fails and this module should be deleted, not skipped — a
`pytest.importorskip` here would turn a real signal into permanent silence.
"""

from __future__ import annotations

import pytest
from a2kit.packages.formatter.tsv import encode_tsv as upstream_encode_tsv
from pydantic import BaseModel

from a2web._tsv_compat import encode_tsv as vendored_encode_tsv


class _Row(BaseModel):
    a: str
    b: str | None = None
    c: list[str] = []


#: Every cell class the escaping distinction turns on, plus the shapes that
#: exercise the non-string branches (None -> "", list/dict -> JSON blob).
_CASES: list[tuple[str, list[object], list[str]]] = [
    ("empty rows", [], ["a", "b"]),
    ("plain dicts", [{"a": "x", "b": "y"}], ["a", "b"]),
    ("models", [_Row(a="x", b="y")], ["a", "b", "c"]),
    ("none becomes empty", [_Row(a="x", b=None)], ["a", "b"]),
    ("list cell is json-blobbed", [_Row(a="x", c=["p", "q"])], ["a", "c"]),
    ("dict cell is json-blobbed", [{"a": {"k": "v"}}], ["a"]),
    ("missing column is skipped", [{"a": "x"}], ["a", "zzz"]),
    ("extra key is ignored", [{"a": "x", "unlisted": "z"}], ["a"]),
    # The five characters that make csv.QUOTE_MINIMAL reach for quoting —
    # i.e. exactly where `lean-wire` will legitimately differ later.
    ("embedded quote", [{"a": 'he said "hi"'}], ["a"]),
    ("embedded backslash", [{"a": r"C:\drivers\readme.txt"}], ["a"]),
    ("embedded tab", [{"a": "left\tright"}], ["a"]),
    ("embedded newline", [{"a": "line1\nline2"}], ["a"]),
    ("embedded carriage return", [{"a": "line1\r\nline2"}], ["a"]),
    ("all five at once", [{"a": '"\\\t\n\r'}], ["a"]),
    ("unicode is not escaped", [{"a": "naïve — 日本語"}], ["a"]),
    ("column order is declared, not sorted", [{"a": "1", "b": "2"}], ["b", "a"]),
]


@pytest.mark.parametrize(("label", "rows", "columns"), _CASES, ids=[c[0] for c in _CASES])
def test_vendored_matches_upstream(label: str, rows: list[object], columns: list[str]) -> None:
    del label
    assert vendored_encode_tsv(rows, columns=columns) == upstream_encode_tsv(rows, columns=columns)


def test_non_row_input_raises_the_same_way() -> None:
    """The error path is contract too — a2kit's message is asserted against in
    at least one place (the `FormatRoutingMiddleware` fallback log this repo
    observed while capturing goldens), so the text must not drift either."""
    with pytest.raises(TypeError) as vendored:
        vendored_encode_tsv(["not a row"], columns=["a"])
    with pytest.raises(TypeError) as upstream:
        upstream_encode_tsv(["not a row"], columns=["a"])
    assert str(vendored.value) == str(upstream.value)


def test_the_case_table_is_not_empty() -> None:
    """Anti-vacuity: a parametrized parity test with an emptied table passes."""
    assert len(_CASES) >= 15
