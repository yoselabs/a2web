"""Adaptive duration formatter — five canonical cases."""

from __future__ import annotations

import pytest

from a2web.utils.time import fmt_dur


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "0ms"),
        (420, "420ms"),
        (999, "999ms"),
        (1000, "1.0s"),
        (1900, "1.9s"),
        (6999, "7.0s"),  # boundary lands at 7.0s by formatting (still <7000 ms)
        (7000, "7s"),
        (8000, "8s"),
        (45_000, "45s"),
        (60_000, "1m00s"),
        (72_000, "1m12s"),
        (124_000, "2m04s"),
    ],
)
def test_fmt_dur(ms: int, expected: str) -> None:
    assert fmt_dur(ms) == expected
