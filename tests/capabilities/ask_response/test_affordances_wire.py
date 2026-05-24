"""Affordances wire-level tests (v0.20).

Drives the `ask` tool through the in-process MCP client and asserts on the
decoded wire dict — so envelope discipline (omit content_value/shapes/
follow_ups on obstacle pages) is verified on the exact payload an agent
receives, not on `.model_dump()`.
"""

from __future__ import annotations

import json

import pytest
from a2kit.testing import client as make_client

from a2web.llm_resource import LlmExtractorResource
from a2web.packages.llm_extract import Extractor, ModelSpec, ProviderResponse
from a2web.server import app
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult

_MINIMAL_HTML = (
    b"<html><body><main>" + b"<p>Adaptive web fetching keeps the calling agent's context small.</p>" * 30 + b"</main></body></html>"
)


class _RawStub:
    name = "raw"

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=self._body, content_type="text/html", status_code=200, final_url=url)


class _JsonEnvelopeProvider:
    """LLM provider stub — returns a chosen JSON envelope verbatim.

    The Extractor's affordances path parses the JSON, so the stub must return
    exactly the V_CTX_V3 envelope shape (extracted_answer + page_kind + ...).
    """

    name = "stub"

    def __init__(self, envelope: dict) -> None:
        self._text = json.dumps(envelope)

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
        del system, user
        return ProviderResponse(
            text=self._text,
            model=model,
            prompt_tokens=120,
            completion_tokens=200,
            cost_usd=0.0003,
            latency_ms=88,
        )


def _build_extractor(state: AppState, envelope: dict) -> LlmExtractorResource:
    res = LlmExtractorResource(state.settings, state.sqlite)
    res._extractor = Extractor(
        provider=_JsonEnvelopeProvider(envelope),
        model=ModelSpec("stub", "stub-model"),
    )
    return res


async def _ask_wire(monkeypatch: pytest.MonkeyPatch, *, envelope: dict, **ask_kwargs: object) -> dict:
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(_MINIMAL_HTML))
    async with make_client(app) as client:
        state = await app.container().get(AppState)
        client.override(LlmExtractorResource, _build_extractor(state, envelope))
        wire = await client.call_wire("ask", **ask_kwargs)
    return json.loads(wire)


# --------------------------------------------------------------------- #
# Default behavior — affordances field present, default ON
# --------------------------------------------------------------------- #


_CONTENT_PAGE_ENVELOPE = {
    "extracted_answer": "Adaptive fetching keeps context small.",
    "page_kind": "blog-post",
    "page_kind_confidence": "medium",  # cluster F (longform): forced ≤ medium
    "reasoning": "Short article with a single body section.",
    "content_value": "high",
    "shapes": [
        {"label": "list", "where": "middle", "size": "small"},
    ],
    "follow_up_questions": [
        "Why does context size matter for agents?",
        "What is the cost of streaming raw HTML to a large model?",
    ],
}


_OBSTACLE_PAGE_ENVELOPE = {
    "extracted_answer": "The page returns a 404 error.",
    "page_kind": "error",
    "page_kind_confidence": "high",
    "reasoning": "HTTP 404 with explicit 'not found' headline.",
}


@pytest.mark.asyncio
async def test_default_ask_includes_affordances_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default `ask` (no `include_affordances` kwarg) returns affordances."""
    data = await _ask_wire(
        monkeypatch,
        envelope=_CONTENT_PAGE_ENVELOPE,
        url="https://example.org/post",
        question="What is this page about?",
    )
    assert "affordances" in data
    aff = data["affordances"]
    assert aff["page_kind"] == "blog-post"
    assert aff["page_kind_confidence"] == "medium"
    assert aff["content_value"] == "high"
    assert isinstance(aff["shapes"], list) and len(aff["shapes"]) == 1
    assert aff["shapes"][0]["label"] == "list"
    assert len(aff["follow_up_questions"]) == 2


@pytest.mark.asyncio
async def test_opt_out_via_include_affordances_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """`include_affordances=False` MUST omit the field from the wire entirely."""
    # The stub returns a JSON envelope regardless; but with affordances off,
    # the extractor uses EXTRACT_CACHEABLE_V1 (no JSON parsing path) and the
    # raw JSON IS the answer. We verify only that `affordances` is absent.
    data = await _ask_wire(
        monkeypatch,
        envelope=_CONTENT_PAGE_ENVELOPE,
        url="https://example.org/post",
        question="What is this page about?",
        include_affordances=False,
    )
    assert "affordances" not in data


# --------------------------------------------------------------------- #
# Envelope discipline — obstacle pages drop content_value/shapes/follow_ups
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_obstacle_page_omits_content_value(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        envelope=_OBSTACLE_PAGE_ENVELOPE,
        url="https://example.org/missing",
        question="What is this page?",
    )
    assert "affordances" in data
    aff = data["affordances"]
    assert aff["page_kind"] == "error"
    assert aff["page_kind_confidence"] == "high"
    # Envelope discipline: these MUST be absent on obstacle pages.
    assert "content_value" not in aff
    assert "shapes" not in aff
    assert "follow_up_questions" not in aff


@pytest.mark.asyncio
async def test_content_page_carries_all_affordance_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mirror of the obstacle case: content pages MUST have all three."""
    data = await _ask_wire(
        monkeypatch,
        envelope=_CONTENT_PAGE_ENVELOPE,
        url="https://example.org/post",
        question="What is this about?",
    )
    aff = data["affordances"]
    assert "content_value" in aff
    assert "shapes" in aff
    assert "follow_up_questions" in aff


# --------------------------------------------------------------------- #
# Parse failure degrades gracefully
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_malformed_envelope_drops_affordances_keeps_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the model returns plain text (no JSON envelope), the extractor
    returns the text as the answer and affordances is None — the field is
    omitted from the wire."""

    # The "envelope" here is actually plain text; the parser fails over.
    class _PlainTextProvider:
        name = "stub"

        async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
            del system, user
            return ProviderResponse(
                text="Just plain text, no JSON.",
                model=model,
                prompt_tokens=120,
                completion_tokens=8,
                cost_usd=0.0003,
                latency_ms=50,
            )

    monkeypatch.setitem(REGISTRY, "raw", _RawStub(_MINIMAL_HTML))
    async with make_client(app) as client:
        state = await app.container().get(AppState)
        res = LlmExtractorResource(state.settings, state.sqlite)
        res._extractor = Extractor(
            provider=_PlainTextProvider(),
            model=ModelSpec("stub", "stub-model"),
        )
        client.override(LlmExtractorResource, res)
        wire = await client.call_wire(
            "ask",
            url="https://example.org/post",
            question="What is this?",
        )
    data = json.loads(wire)
    # Answer falls back to the plain text the model returned.
    assert data["extracted_answer"] == "Just plain text, no JSON."
    # Affordances absent — parse failure degraded gracefully.
    assert "affordances" not in data
