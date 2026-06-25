"""Router-shape wire-level tests (v0.21).

Drives the `ask` tool through the in-process MCP client and asserts on the
decoded wire dict — so envelope discipline (omit empty conditionals;
required fields always present) is verified on the exact payload an agent
receives, not on `.model_dump()`.
"""

from __future__ import annotations

import json

import pytest
from a2kit.testing import client as make_client
from a2kit.testing import lazy

from a2web.llm_resource import LlmExtractorResource
from a2web.packages.llm_extract import ProviderResponse
from a2web.server import build_app
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

    The Extractor's router-shape path parses the JSON, so the stub must return
    exactly the router envelope (answer + structural_form + shape + ...).
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
    return LlmExtractorResource(state.settings, state.sqlite, lazy(_JsonEnvelopeProvider(envelope)))


async def _ask_wire(monkeypatch: pytest.MonkeyPatch, *, envelope: dict, **ask_kwargs: object) -> dict:
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(_MINIMAL_HTML))
    app = build_app()
    state = await app.container().get(AppState)
    fake = _build_extractor(state, envelope)
    app.provide(LlmExtractorResource, lambda: fake)
    async with make_client(app) as client:
        wire = await client.call_wire("ask", **ask_kwargs)
    return json.loads(wire)


# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #


_HEALTHY_ENVELOPE = {
    "answer": "Adaptive fetching keeps context small.",
    "structural_form": "article",
    "shape": "prose",
    "genre": "personal",
    "ask_here": [
        "Why does context size matter for agents?",
        "What is the cost of streaming raw HTML to a large model?",
    ],
}


_HEALTHY_MINIMAL_ENVELOPE = {
    "answer": "Adaptive fetching keeps context small.",
    "structural_form": "article",
    "shape": "prose",
}


_OBSTACLE_ENVELOPE = {
    "answer": "The page returns a 404 error.",
    "structural_form": "article",
    "shape": "prose",
    "obstacle": "error",
    "try_url": [
        {"url": "https://example.org/missing", "reason": "wayback snapshot may have the article"},
    ],
}


# --------------------------------------------------------------------- #
# Default behavior — router-shape fields present, default ON
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_default_ask_includes_required_router_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default `ask` (no `include_routing` kwarg) returns the 3 required + populated optionals."""
    data = await _ask_wire(
        monkeypatch,
        envelope=_HEALTHY_ENVELOPE,
        url="https://example.org/post",
        question="What is this page about?",
    )
    assert data["answer"] == "Adaptive fetching keeps context small."
    assert data["structural_form"] == "article"
    assert data["shape"] == "prose"
    assert data["genre"] == "personal"
    assert "ask_here" in data
    assert len(data["ask_here"]) == 2
    # No obstacle / try_url emitted → omitted from wire.
    assert "obstacle" not in data
    assert "try_url" not in data


@pytest.mark.asyncio
async def test_healthy_page_omits_all_four_conditionals(monkeypatch: pytest.MonkeyPatch) -> None:
    """A minimal healthy payload (no genre / obstacle / ask_here / try_url) drops them all."""
    data = await _ask_wire(
        monkeypatch,
        envelope=_HEALTHY_MINIMAL_ENVELOPE,
        url="https://example.org/post",
        question="What is this?",
    )
    assert data["structural_form"] == "article"
    assert data["shape"] == "prose"
    assert "genre" not in data
    assert "obstacle" not in data
    assert "ask_here" not in data
    assert "try_url" not in data


@pytest.mark.asyncio
async def test_obstacle_page_populates_obstacle_and_try_url(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        envelope=_OBSTACLE_ENVELOPE,
        url="https://example.org/missing",
        question="What is this page?",
    )
    assert data["obstacle"] == "error"
    assert "try_url" in data
    assert len(data["try_url"]) == 1
    assert data["try_url"][0]["url"] == "https://example.org/missing"
    # genre / ask_here not emitted → omitted.
    assert "genre" not in data
    assert "ask_here" not in data


@pytest.mark.asyncio
async def test_opt_out_via_include_routing_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """`include_routing=False` MUST omit all seven router-shape fields from the wire."""
    # With routing off, the extractor uses EXTRACT_CACHEABLE_V1 — no JSON parse —
    # so the JSON envelope IS the answer text. We only verify field absence.
    data = await _ask_wire(
        monkeypatch,
        envelope=_HEALTHY_ENVELOPE,
        url="https://example.org/post",
        question="What is this page about?",
        include_routing=False,
    )
    # Required (with routing on) and conditional router fields all absent.
    assert "structural_form" not in data
    assert "shape" not in data
    assert "genre" not in data
    assert "obstacle" not in data
    assert "ask_here" not in data
    assert "try_url" not in data


# --------------------------------------------------------------------- #
# Parse failure degrades gracefully — answer survives, 7 fields absent
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_malformed_envelope_drops_routing_keeps_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the model returns plain text (no JSON envelope), the extractor
    returns the text as `answer` and all 7 router-shape fields are absent."""

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
    app = build_app()
    state = await app.container().get(AppState)
    res = LlmExtractorResource(state.settings, state.sqlite, lazy(_PlainTextProvider()))
    app.provide(LlmExtractorResource, lambda: res)
    async with make_client(app) as client:
        wire = await client.call_wire(
            "ask",
            url="https://example.org/post",
            question="What is this?",
        )
    data = json.loads(wire)
    assert data["answer"] == "Just plain text, no JSON."
    # All 7 router-shape fields absent — parse failure degraded gracefully.
    for field in ("structural_form", "shape", "genre", "obstacle", "ask_here", "try_url"):
        assert field not in data


@pytest.mark.asyncio
async def test_unknown_enum_value_drops_router_keeps_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `structural_form` outside the closed 9-value enum fails pydantic
    validation at the seam; the 7 router fields are absent but `answer` survives."""
    envelope = {
        "answer": "Some answer.",
        "structural_form": "blog-post",  # not in the 9-value enum
        "shape": "prose",
    }
    data = await _ask_wire(
        monkeypatch,
        envelope=envelope,
        url="https://example.org/post",
        question="What is this?",
    )
    assert data["answer"] == "Some answer."
    for field in ("structural_form", "shape", "genre", "obstacle", "ask_here", "try_url"):
        assert field not in data
