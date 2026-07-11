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
    `structural_form`/`shape` are still required in the LLM-side envelope —
    `RouterPayload` (internal boundary) still validates them, and internal
    consumers (`content_guidance`, the `refinement_axes` gate) still need
    them — they're just no longer projected onto the `AskResponse` wire (see
    `drop-structural-form-shape-wire`).
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


_PRODUCT_ENVELOPE = {
    "answer": "Price: 42.00 USD. In stock.",
    "structural_form": "product",
    "shape": "key-value",
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
    """Default `ask` (no `include_routing` kwarg) returns `answer` + populated optionals.
    `structural_form`/`shape` are never on the wire (drop-structural-form-shape-wire)."""
    data = await _ask_wire(
        monkeypatch,
        envelope=_HEALTHY_ENVELOPE,
        url="https://example.org/post",
        question="What is this page about?",
    )
    assert data["answer"] == "Adaptive fetching keeps context small."
    assert "ask_here" in data
    assert len(data["ask_here"]) == 2
    # No obstacle / try_url emitted → omitted from wire. genre never exists.
    # structural_form / shape are never projected onto the wire at all.
    assert "obstacle" not in data
    assert "try_url" not in data
    assert "genre" not in data
    assert "structural_form" not in data
    assert "shape" not in data


@pytest.mark.asyncio
async def test_healthy_page_omits_all_three_conditionals(monkeypatch: pytest.MonkeyPatch) -> None:
    """A minimal healthy payload (no obstacle / ask_here / try_url) drops them all."""
    data = await _ask_wire(
        monkeypatch,
        envelope=_HEALTHY_MINIMAL_ENVELOPE,
        url="https://example.org/post",
        question="What is this?",
    )
    assert data["answer"] == "Adaptive fetching keeps context small."
    assert "genre" not in data
    assert "obstacle" not in data
    assert "ask_here" not in data
    assert "try_url" not in data
    assert "structural_form" not in data
    assert "shape" not in data


@pytest.mark.asyncio
async def test_structural_form_consumed_internally_but_absent_from_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    """`structural_form: "product"` drives the internal `content_guidance` hint
    (RouterPayload still requires it, content_guidance.kind_guidance() still
    reads it) but neither `structural_form` nor `shape` ever reaches the wire."""
    data = await _ask_wire(
        monkeypatch,
        envelope=_PRODUCT_ENVELOPE,
        url="https://example.org/product",
        question="What is the price?",
    )
    assert data["answer"] == "Price: 42.00 USD. In stock."
    codes = [h["code"] for h in data.get("operator_hints", [])]
    assert "content_guidance" in codes
    assert "structural_form" not in data
    assert "shape" not in data


@pytest.mark.asyncio
async def test_stray_genre_key_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `genre` key from a stale prompt version or non-conforming provider is
    silently dropped — the extractor no longer reads it, so it never reaches
    `RouterPayload` or the wire, and the rest of the envelope parses normally."""
    envelope = {**_HEALTHY_MINIMAL_ENVELOPE, "genre": "encyclopedia"}
    data = await _ask_wire(
        monkeypatch,
        envelope=envelope,
        url="https://example.org/post",
        question="What is this?",
    )
    assert data["answer"] == "Adaptive fetching keeps context small."
    assert "genre" not in data


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
    # ask_here not emitted → omitted. genre never exists.
    assert "genre" not in data
    assert "ask_here" not in data


@pytest.mark.asyncio
async def test_opt_out_via_include_routing_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """`include_routing=False` MUST omit all router-shape fields from the wire."""
    # With routing off, the extractor uses EXTRACT_CACHEABLE_V1 — no JSON parse —
    # so the JSON envelope IS the answer text. We only verify field absence.
    data = await _ask_wire(
        monkeypatch,
        envelope=_HEALTHY_ENVELOPE,
        url="https://example.org/post",
        question="What is this page about?",
        include_routing=False,
    )
    assert "genre" not in data
    assert "obstacle" not in data
    assert "ask_here" not in data
    assert "try_url" not in data
    assert "structural_form" not in data
    assert "shape" not in data


# --------------------------------------------------------------------- #
# Parse failure degrades gracefully — answer survives, router fields absent
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_malformed_envelope_drops_routing_keeps_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the model returns plain text (no JSON envelope), the extractor
    returns the text as `answer` and all router-shape fields are absent."""

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
    # All router-shape fields absent — parse failure degraded gracefully.
    for field in ("obstacle", "ask_here", "try_url", "structural_form", "shape"):
        assert field not in data
    assert "genre" not in data


@pytest.mark.asyncio
async def test_unknown_enum_value_drops_router_keeps_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `structural_form` outside the closed 9-value enum fails pydantic
    validation at the seam (internal `RouterPayload` boundary); the router
    fields are absent but `answer` survives."""
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
    for field in ("obstacle", "ask_here", "try_url", "structural_form", "shape"):
        assert field not in data
    assert "genre" not in data
