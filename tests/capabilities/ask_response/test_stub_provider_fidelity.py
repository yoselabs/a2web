"""The shared LLM stub must honor the output contract it is handed.

`_StubProvider` backs the MCP wire goldens and most `query` capability tests. It
used to `del system, user` and return prose unconditionally. On the
`request_routing=True` path — the one `query` actually uses — that made it a
FALSE WITNESS: `EXTRACT_ROUTER_V1` says "Output strict JSON only", the stub
returned prose, `_split_answer_and_routing` raised `ParseError`, and every test
driven through it silently exercised the routing-LOST branch while presenting as
a healthy `query`.

The cost was not cosmetic. It is why the ADR-0015 index-loss signal was measured
as "fires on every query — permanent noise" and shelved to BACKLOG.md as blocked
on a discriminator that does not need to exist. The measurement was of the stub,
not of production. Once the stub answers the contract, `routing_lost` is False on
the healthy path and the signal is available to fire only when routing is
genuinely lost.

This file exists so the fidelity cannot rot back. A stub regression would not
fail any other test — it would just quietly re-route the whole `query` suite down
the degraded branch again, which is exactly how it went unnoticed the first time.
Related: `tests/architecture/_walk.py` non-vacuity floors, and CLAUDE.md's "never
treat a golden as proof of correctness" — a golden captured through a lying
fixture freezes the lie.
"""

from __future__ import annotations

import pytest

from a2web.packages.llm_extract import EXTRACT_ROUTER_V1, TERSE_V1, Extractor, ModelSpec
from tests.capabilities.ask_response.test_ask_response import _DEFAULT_ANSWER, _StubProvider


@pytest.mark.asyncio
async def test_stub_satisfies_the_router_contract() -> None:
    """Handed the router contract, the stub returns a RECOVERABLE envelope."""
    ex = Extractor(provider=_StubProvider(_DEFAULT_ANSWER), model=ModelSpec("m"), template=EXTRACT_ROUTER_V1)

    result = await ex.extract(content="some page content", ask="what is this?", request_routing=True)

    # The claim that matters: routing was asked for AND recovered.
    assert result.routing is not None, (
        "_StubProvider no longer satisfies the router contract. Every wire golden and `query` "
        "capability test is now silently exercising the routing-LOST branch."
    )
    assert result.routing_lost is False
    # The answer survives the envelope — the ~50 assertions that compare
    # `data['answer']` against this exact string still mean what they mean.
    assert result.answer == _DEFAULT_ANSWER


@pytest.mark.asyncio
async def test_stub_returns_prose_when_the_contract_does_not_ask_for_json() -> None:
    """Non-vacuity: the stub is contract-SENSITIVE, not unconditionally JSON.

    Without this, a stub hard-wired to always emit an envelope would pass the
    test above while being just as blind to the prompt as the version it
    replaced — failing the same way in the opposite direction.
    """
    ex = Extractor(provider=_StubProvider(_DEFAULT_ANSWER), model=ModelSpec("m"), template=TERSE_V1)

    result = await ex.extract(content="some page content", ask="what is this?")

    assert result.answer == _DEFAULT_ANSWER
    assert result.routing is None, "No routing was requested, so none should be parsed"
    assert result.routing_lost is False, "`routing_lost` means ASKED-AND-MISSING, not merely absent"
