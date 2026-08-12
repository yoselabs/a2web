"""End-to-end: raw HTML with a click-gated tab -> extractor sees a `## gated
sections` digest -> `blocked_gate` handle resolves -> the wire envelope caps
confidence and carries `interaction_required`.

Drives the real `query` tool through `mcp_client`, nothing faked below the LLM
provider boundary (`tests/_helpers/mcp.py` seam) — this is the ONLY test that
exercises the actual wiring in `fetcher/answer/prompt_call.py` and
`fetcher/answer/digest.py`, not just the pure pieces each unit test covers.

The cross-language case is the whole point of ADR-0020's design (design.md
D2): a deterministic term-overlap match between the English query and the
Turkish "Soru Cevap" label fails outright, which is exactly why relevance is
the MODEL's job, not a server-side heuristic. This test proves the MECHANISM
carries a cross-language selection correctly end-to-end; it cannot prove a
real model chooses to emit `blocked_gate` for a real cross-language question —
that is an `eval/corpus.yaml` question, not a unit-test one (see the
`hepsiburada-carraro-gravel-g2-qa-tab-gated` entry).
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from async_scope import lazy

from a2web.components import build_components
from a2web.llm_resource import LlmExtractorResource
from a2web.packages.llm_extract import ProviderResponse
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult
from tests._helpers.llm_doubles import DoubleArm
from tests._helpers.mcp import call_wire, mcp_client

_GATED_HTML = (
    b"<html><body><main>"
    b'<div role="tablist">'
    b'<button role="tab" aria-controls="Description" aria-label="Selected">Description</button>'
    b'<button role="tab" aria-controls="QuestionAnswers" aria-label=" Soru Cevap 4">Soru Cevap</button>'
    b"</div>"
    b'<div id="Description">' + b"<p>A gravel bike with a hydraulic disc brake groupset.</p>" * 60 + b"</div>"
    b'<div id="QuestionAnswers" style="display:none"></div>'
    b"</main></body></html>"
)


class _RawStub:
    name = "raw"

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=self._body, content_type="text/html", status_code=200, final_url=url)


class _RouterEnvelopeProvider:
    DOUBLES_ARM = DoubleArm.ROUTER_FAITHFUL
    name = "stub"

    @classmethod
    def for_fidelity_check(cls) -> _RouterEnvelopeProvider:
        return cls({"answer": "a", "structural_form": "article", "shape": "prose"})

    def __init__(self, envelope: dict) -> None:
        self._text = json.dumps(envelope)
        self.last_user_prompt: str | None = None

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
        del system
        self.last_user_prompt = user
        return ProviderResponse(
            text=self._text,
            model=model,
            prompt_tokens=120,
            completion_tokens=200,
            cost_usd=0.0003,
            latency_ms=88,
        )


async def _ask_wire_with_provider(monkeypatch: pytest.MonkeyPatch, *, provider: _RouterEnvelopeProvider, **ask_kwargs: object) -> dict:
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(_GATED_HTML))
    parts = build_components()
    state = await parts.state()
    fake = LlmExtractorResource(state.settings, state.sqlite, lazy(provider))
    parts = dataclasses.replace(parts, llm_extractor=lazy(fake))
    async with mcp_client(components=parts) as client:
        wire = await call_wire(client, "query", **ask_kwargs)
    return json.loads(wire)


@pytest.mark.asyncio
async def test_the_gate_digest_reaches_the_model_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `## gated sections` menu block, with the real detected label and
    count, must be in what the model was shown — otherwise `blocked_gate`
    could never be a grounded choice."""
    provider = _RouterEnvelopeProvider({"answer": "irrelevant", "structural_form": "product", "shape": "key-value"})
    await _ask_wire_with_provider(
        monkeypatch,
        provider=provider,
        url="https://example.org/bike",
        query="seller Q&A questions and answers full text",
    )
    assert provider.last_user_prompt is not None
    assert "## gated sections" in provider.last_user_prompt
    assert "{{1}} Soru Cevap (4)" in provider.last_user_prompt


@pytest.mark.asyncio
async def test_a_resolved_blocked_gate_caps_confidence_and_emits_the_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = {
        "answer": "The page's Q&A section was not retrieved; it loads only on click.",
        "structural_form": "product",
        "shape": "key-value",
        "blocked_gate": 1,
    }
    data = await _ask_wire_with_provider(
        monkeypatch,
        provider=_RouterEnvelopeProvider(envelope),
        url="https://example.org/bike",
        query="seller Q&A questions and answers full text",
    )
    assert data["confidence"] in ("medium", "low")  # capped from the default high a 20-paragraph body would earn
    assert data["confidence"] != "high"
    hints = data.get("operator_hints", [])
    codes = {h["code"] for h in hints}
    assert "interaction_required" in codes
    hint = next(h for h in hints if h["code"] == "interaction_required")
    assert "Soru Cevap" in hint["message"]
    assert "4" in hint["message"]
    assert data.get("retrieval_incomplete") is not True


@pytest.mark.asyncio
async def test_an_unknown_handle_is_dropped_not_fabricated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Closed-set: the model referencing a handle the digest never issued must
    never surface a fabricated section on the wire."""
    envelope = {
        "answer": "The page describes a gravel bike.",
        "structural_form": "product",
        "shape": "key-value",
        "blocked_gate": 999,
    }
    data = await _ask_wire_with_provider(
        monkeypatch,
        provider=_RouterEnvelopeProvider(envelope),
        url="https://example.org/bike",
        query="what kind of bike is this?",
    )
    hints = data.get("operator_hints", [])
    assert not any(h["code"] == "interaction_required" for h in hints)


@pytest.mark.asyncio
async def test_no_blocked_gate_leaves_the_wire_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = {
        "answer": "A gravel bike with a hydraulic disc brake groupset.",
        "structural_form": "product",
        "shape": "key-value",
    }
    data = await _ask_wire_with_provider(
        monkeypatch,
        provider=_RouterEnvelopeProvider(envelope),
        url="https://example.org/bike",
        query="what kind of bike is this?",
    )
    hints = data.get("operator_hints", [])
    assert not any(h["code"] == "interaction_required" for h in hints)
    assert data["confidence"] == "high"
