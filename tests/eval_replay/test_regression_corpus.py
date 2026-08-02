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
#: `akakce-cloudflare-bot-wall` (2026-08-02): its blessed `steps` end
#: `jina:paywall`, and that step was never frozen. The jina tier hand-rolled an
#: `httpx.AsyncClient`, which `patch_fetch_bytes` does not intercept, so the
#: capture recorded no jina exchange and every replay re-fetched `r.jina.ai`
#: LIVE (measured with a `getaddrinfo` spy: one lookup, `r.jina.ai`). Routing
#: jina through the primitive made the gap visible as the `CassetteMiss` it
#: always was.
#:
#: **Re-capture is not the fix, and that is the operator's call.** A live refresh
#: on 2026-08-02 shows akakce no longer walls: raw now returns the page in one
#: hop, and the fresh answer is a real "Fiyat Yok / offerCount 0" reading. That
#: is a DIFFERENT case — arguably the "genuine no-current-price specimen" this
#: case's own notes say akakce could not provide — and blessing it would retire
#: a bot-wall regression guard by accident while appearing to update it. Decide
#: deliberately: re-point this case at a currently-walled URL, or split it.
_UNREPRODUCIBLE = {
    "akakce-cloudflare-bot-wall": (
        "blessed `jina:paywall` step was never frozen; site no longer walls "
        "— needs a deliberate re-capture decision"
    ),
}


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
# akakce-cloudflare-bot-wall) never call the extractor, so they have no
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
