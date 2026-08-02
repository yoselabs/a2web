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


#: Cases whose frozen `inputs/` cannot reproduce their blessed baseline, with the
#: reason. `strict=True` on purpose — an entry that starts passing FAILS, so this
#: table cannot quietly become a list of cases nobody re-examines.
#:
#: **Empty since 2026-08-02, and the emptying is the point.** Its one entry was
#: `akakce-cloudflare-bot-wall`, parked here because its blessed `jina:paywall`
#: step was never frozen: the jina tier hand-rolled an `httpx.AsyncClient` the
#: capture harness did not intercept, so every replay re-fetched `r.jina.ai` LIVE
#: (measured with a `getaddrinfo` spy). Routing jina through the fetch primitive
#: made the gap visible as the `CassetteMiss` it always was.
#:
#: The deliberate decision that entry was waiting on has been taken and the case
#: was SPLIT, because a re-capture alone would have retired a bot-wall guard by
#: accident: akakce still walls a naive client, but a2web's curl_cffi
#: impersonation now passes it in one hop, so the case measured a success while
#: claiming to guard a failure. It is `akakce-no-current-price` now — the
#: fabrication-trap specimen its own notes said it could not provide — and the
#: bot-wall half is `zoro-datadome-bot-wall`, which reaches the browser rung that
#: akakce's `rate_limited`-classified 429 never did.
_UNREPRODUCIBLE: dict[str, str] = {}


@pytest.mark.skipif(not _CASES, reason="no regression cases captured yet")
@pytest.mark.parametrize("case", _CASES, ids=[c.slug for c in _CASES])
async def test_regression_replay(monkeypatch: pytest.MonkeyPatch, case, request: pytest.FixtureRequest) -> None:
    if case.slug in _UNREPRODUCIBLE:
        request.applymarker(pytest.mark.xfail(reason=_UNREPRODUCIBLE[case.slug], strict=True))
    observed = await replay_case(monkeypatch, case)
    if BLESS_EVAL:
        bless_contract(case, observed)
        return
    assert_contract(case, observed)


# Cases with a recorded LLM egress — bot-wall / honest-failure cases (e.g.
# zoro-datadome-bot-wall) never call the extractor, so they have no
# `inputs/llm/` to reproduce; this byte-for-byte assertion is about the LLM
# egress specifically and must run on a case that actually has one.
_LLM_CASES = [c for c in _CASES if c.inputs.llm]


@pytest.mark.skipif(not _LLM_CASES, reason="no regression case with a recorded LLM egress")
async def test_llm_egress_is_reproduced_byte_for_byte(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded LLM answer is replayed exactly, identically across runs."""
    case = _LLM_CASES[0]
    first = await replay_case(monkeypatch, case)
    second = await replay_case(monkeypatch, case)
    assert first == second  # tier path, token cost, content, answer all identical

    recorded = json.loads((case.path / "inputs" / "llm" / "extract.json").read_text())["answer"]
    assert first["answer"] == recorded  # served from the cassette, not re-sampled
