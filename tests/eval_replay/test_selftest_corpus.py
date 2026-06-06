"""Harness self-test — proves the raw-egress freeze + real-pipeline replay
path offline, with no network and no LLM.

This is the instrument testing itself: the `_selftest` corpus is a
hand-authored deterministic fixture, so a green run here means the cassette
format, the centralized `fetch_bytes` patch, and the contract assertion all
work before any real case is captured.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval._capture.corpus import load_corpus
from tests.eval_replay.bless import BLESS_EVAL, bless_contract
from tests.eval_replay.replay import assert_contract, replay_case

_SELFTEST_CORPUS = Path(__file__).resolve().parents[2] / "eval" / "corpus" / "_selftest"
_CASES = load_corpus(_SELFTEST_CORPUS)


@pytest.mark.parametrize("case", _CASES, ids=[c.slug for c in _CASES])
async def test_selftest_replay(monkeypatch: pytest.MonkeyPatch, case) -> None:
    observed = await replay_case(monkeypatch, case)
    if BLESS_EVAL:
        bless_contract(case, observed)
        return
    assert_contract(case, observed)


async def test_selftest_replay_is_reproducible(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same case replayed twice yields a byte-identical projection."""
    case = _CASES[0]
    first = await replay_case(monkeypatch, case)
    second = await replay_case(monkeypatch, case)
    assert first == second
