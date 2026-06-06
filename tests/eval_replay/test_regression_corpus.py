"""Regression corpus — cases the product has actually gotten stuck on.

Deterministic replay over frozen cassettes; gates `make check`. Asserts
each case's blessed `baseline/contract.json` (shape: tier, status, content
presence, token bound, next_links) — NOT answer *correctness*, which is the
LLM-judged axis under `make bench`. A class-C case can therefore document a
wrong answer (frozen in its cassette) while still passing the deterministic
gate; the fix flips the judged axis, not this test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval._capture.corpus import load_corpus
from tests.eval_replay.bless import BLESS_EVAL, bless_contract
from tests.eval_replay.replay import assert_contract, replay_case

_REGRESSION = Path(__file__).resolve().parents[2] / "eval" / "corpus" / "regression"
_CASES = load_corpus(_REGRESSION)


@pytest.mark.skipif(not _CASES, reason="no regression cases captured yet")
@pytest.mark.parametrize("case", _CASES, ids=[c.slug for c in _CASES])
async def test_regression_replay(monkeypatch: pytest.MonkeyPatch, case) -> None:
    observed = await replay_case(monkeypatch, case)
    if BLESS_EVAL:
        bless_contract(case, observed)
        return
    assert_contract(case, observed)


@pytest.mark.skipif(not _CASES, reason="no regression cases captured yet")
async def test_llm_egress_is_reproduced_byte_for_byte(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded LLM answer is replayed exactly, identically across runs."""
    case = _CASES[0]
    first = await replay_case(monkeypatch, case)
    second = await replay_case(monkeypatch, case)
    assert first == second  # tier path, token cost, answer all identical

    recorded = json.loads((case.path / "inputs" / "llm" / "extract.json").read_text())["answer"]
    assert first["answer"] == recorded  # served from the cassette, not re-sampled
