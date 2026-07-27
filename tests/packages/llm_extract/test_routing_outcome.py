"""`RoutingOutcome` — one test per arm, each driven by a declared double.

The field this replaces (`routing_lost: bool`) collapsed three unlike events
into one: an envelope that never parsed, an envelope that parsed but carried no
classification, and a provider that never returned text. They have different
causes and different correct responses, so a consumer that can only ask "was it
lost?" is forced to guess — which is why `routing_lost` ended up written by the
extractor and read by nothing at all.

Every double here declares its `DOUBLES_ARM` and is verified to actually produce
the arm it claims. That is the point: an arm asserted by a double nobody checked
is the exact failure this repo has now paid for four times.
"""

from __future__ import annotations

import json

import pytest
from anyllm import AnyLLMError, Completion

from a2web.packages.llm_extract import EXTRACT_ROUTER_V1, Extractor, ModelSpec, RoutingOutcome
from tests._helpers.llm_doubles import DoubleArm, honor_contract


class _FaithfulProvider:
    """Returns a full, healthy router envelope — the RECOVERED arm."""

    DOUBLES_ARM = DoubleArm.ROUTER_FAITHFUL
    name = "faithful"

    @classmethod
    def for_fidelity_check(cls) -> _FaithfulProvider:
        return cls()

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> Completion:
        del user
        return Completion(text=honor_contract("Rust rejects aliased mutation.", system), model=model)


class _UnparsableProvider:
    """Returns prose where the contract demands JSON — the UNPARSABLE arm."""

    DOUBLES_ARM = DoubleArm.UNPARSABLE
    name = "unparsable"

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> Completion:
        del system, user
        return Completion(text="I could not find that on the page, sorry.", model=model)


class _UnclassifiedProvider:
    """Valid envelope, no `structural_form` / `shape` — the UNCLASSIFIED arm.

    Carries an index, because that is the case the decoupling exists for: the
    label is missing, the index is not, and the two must not fall together.
    """

    DOUBLES_ARM = DoubleArm.UNCLASSIFIED
    name = "unclassified"

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> Completion:
        del system, user
        payload = {
            "answer": "Rust rejects aliased mutation.",
            "also_here": ["what are lifetimes?", "how does NLL change this?"],
        }
        return Completion(text=json.dumps(payload), model=model)


class _DeadProvider:
    """Raises the way a dead backend does — the PROVIDER_ERROR arm."""

    DOUBLES_ARM = DoubleArm.PROVIDER_ERROR
    name = "dead"

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> Completion:
        del system, user, model
        raise AnyLLMError("backend unreachable")


def _extractor(provider: object) -> Extractor:
    return Extractor(provider=provider, model=ModelSpec("m"), template=EXTRACT_ROUTER_V1)


async def _run(provider: object):
    return await _extractor(provider).extract(content="page content", ask="what does it say?", request_routing=True)


@pytest.mark.asyncio
async def test_healthy_envelope_reports_recovered() -> None:
    result = await _run(_FaithfulProvider())
    assert result.routing_outcome is RoutingOutcome.RECOVERED
    assert result.routing is not None
    assert result.routing.structural_form == "article"


@pytest.mark.asyncio
async def test_prose_where_json_was_asked_reports_unparsable() -> None:
    result = await _run(_UnparsableProvider())
    assert result.routing_outcome is RoutingOutcome.UNPARSABLE
    assert result.routing is None
    # The answer still survives — a lost envelope must never cost the answer.
    assert result.answer


@pytest.mark.asyncio
async def test_envelope_without_classification_reports_unclassified() -> None:
    result = await _run(_UnclassifiedProvider())
    assert result.routing_outcome is RoutingOutcome.UNCLASSIFIED
    assert result.routing is not None
    assert result.routing.structural_form is None


@pytest.mark.asyncio
async def test_unclassified_is_not_unparsable_and_keeps_its_index() -> None:
    """The distinction the bool could not draw, stated as a difference.

    Both arms leave the envelope without a classification to route on. Only one
    of them leaves the caller without an index — and telling them apart is the
    whole reason the type exists.
    """
    unclassified = await _run(_UnclassifiedProvider())
    unparsable = await _run(_UnparsableProvider())
    assert unclassified.routing_outcome is not unparsable.routing_outcome
    assert unclassified.routing is not None
    assert len(unclassified.routing.also_here) == 2
    assert unparsable.routing is None


@pytest.mark.asyncio
async def test_dead_backend_reports_provider_error_not_unparsable() -> None:
    """A dead provider produced no text, so there was nothing to fail to parse.

    Reporting `unparsable` here would blame the model's formatting for an
    infrastructure failure, and would double-report a failure `provider_error`
    already carries.
    """
    result = await _run(_DeadProvider())
    assert result.routing_outcome is RoutingOutcome.PROVIDER_ERROR
    assert result.provider_error is not None


@pytest.mark.asyncio
async def test_outcome_is_none_when_routing_was_never_requested() -> None:
    """`None` is not a fifth arm — it means the question was never asked.

    `fetch_raw` and plain `ask` never request routing, so an outcome there would
    be a fact about a call that did not happen.
    """
    result = await _extractor(_FaithfulProvider()).extract(content="page content", ask="what?", request_routing=False)
    assert result.routing_outcome is None
