"""v0.4 step 4: EvalSystem adapter tests.

Cover WebFetchBaseline + A2WebDetail + A2WebExtract using mocked HTTP and
mocked providers — no real API calls, no live network.
"""

from __future__ import annotations

import httpx
import pytest

from a2web.llm_eval import (
    A2WebDetail,
    A2WebExtract,
    EvalSystem,
    SystemResult,
    WebFetchBaseline,
)
from a2web.llm_eval.systems import WEBFETCH_MARKDOWN_CAP, WEBFETCH_MODEL
from a2web.packages.llm_extract import Extractor, ModelSpec, ProviderResponse
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult

# --------------------------------------------------------------------- #
# Test helpers
# --------------------------------------------------------------------- #


class _RecordingProvider:
    """Provider that records every call and returns a canned answer."""

    name = "rec"

    def __init__(self, *, answer: str = "stub answer") -> None:
        self.answer = answer
        self.calls: list[dict] = []

    async def complete(
        self,
        *,
        system,
        user,
        model,
        max_tokens=1024,
        temperature=0.0,
        thinking_disabled=True,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "thinking_disabled": thinking_disabled,
            }
        )
        return ProviderResponse(
            text=self.answer,
            model=model,
            prompt_tokens=150,
            completion_tokens=30,
            cost_usd=0.0008,
            latency_ms=200,
        )


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))


# --------------------------------------------------------------------- #
# WebFetchBaseline
# --------------------------------------------------------------------- #


def test_webfetch_baseline_protocol_satisfied() -> None:
    bl = WebFetchBaseline(provider=_RecordingProvider())
    assert isinstance(bl, EvalSystem)


@pytest.mark.asyncio
async def test_webfetch_baseline_fetches_converts_and_extracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end happy path: HTTP 200 → markdownify → provider with
    WEBFETCH_DEFAULT_V1 template + Haiku model id + empty system."""
    html = "<!doctype html><html><body><h1>Rust</h1><p>Rust was designed by Graydon Hoare at Mozilla.</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    _patch_httpx(monkeypatch, handler)

    provider = _RecordingProvider(answer="Graydon Hoare designed Rust.")
    bl = WebFetchBaseline(provider=provider)

    result = await bl.fetch(url="https://example.com/rust", ask="Who designed Rust?")

    assert isinstance(result, SystemResult)
    assert result.system == "webfetch_baseline"
    assert result.answer == "Graydon Hoare designed Rust."
    assert result.error is None
    assert result.cost_usd == pytest.approx(0.0008)
    assert result.prompt_tokens == 150
    assert result.completion_tokens == 30
    assert result.metadata["http_status"] == 200
    assert result.metadata["truncated"] is False

    # Provider received exactly one call with the WebFetch prompt template.
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["model"] == WEBFETCH_MODEL
    assert call["system"] == ()  # iK([]) parity
    assert call["thinking_disabled"] is True
    assert "Web page content:" in call["user"]
    assert "Who designed Rust?" in call["user"]
    # The markdownified body should be in there (heading turned into "# Rust").
    assert "Rust" in call["user"]


@pytest.mark.asyncio
async def test_webfetch_baseline_handles_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4xx response → SystemResult with empty answer + populated error,
    no provider call."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch_httpx(monkeypatch, handler)

    provider = _RecordingProvider()
    bl = WebFetchBaseline(provider=provider)
    result = await bl.fetch(url="https://example.com/missing", ask="?")

    assert result.answer == ""
    assert result.error is not None
    assert "404" in result.error
    assert len(provider.calls) == 0


@pytest.mark.asyncio
async def test_webfetch_baseline_truncates_huge_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Markdown over the 100K cap is truncated with the marker and the
    metadata flag is set."""
    huge_html = "<html><body>" + ("<p>x</p>" * 30_000) + "</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=huge_html)

    _patch_httpx(monkeypatch, handler)

    provider = _RecordingProvider(answer="ok")
    # Use a tiny cap so we can deterministically force truncation.
    bl = WebFetchBaseline(provider=provider, markdown_cap=500)
    result = await bl.fetch(url="https://example.com/large", ask="?")

    assert result.metadata["truncated"] is True
    assert "Content truncated" in provider.calls[0]["user"]


@pytest.mark.asyncio
async def test_webfetch_baseline_strips_script_and_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """script / style / noscript / iframe must not bleed into the markdown
    sent to the model (WebFetch's Turndown does the same)."""
    html = (
        "<html><head>"
        "<style>body{color:red}</style>"
        "<script>alert('x')</script>"
        "</head><body>"
        "<noscript>SHOULD_NOT_APPEAR</noscript>"
        "<iframe src='https://evil'></iframe>"
        "<p>real content paragraph</p>"
        "</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    _patch_httpx(monkeypatch, handler)
    provider = _RecordingProvider()
    bl = WebFetchBaseline(provider=provider)
    await bl.fetch(url="https://example.com/script", ask="?")

    user = provider.calls[0]["user"]
    assert "alert" not in user
    assert "color:red" not in user
    assert "SHOULD_NOT_APPEAR" not in user
    assert "real content paragraph" in user


def test_webfetch_baseline_constants_match_research() -> None:
    """Constants in systems.py must match the binary-extracted values
    (research/123). If Claude Code ships a new build with different
    constants, this test forces a conscious update."""
    assert WEBFETCH_MODEL == "claude-haiku-4-5-20251001"
    assert WEBFETCH_MARKDOWN_CAP == 100_000


# --------------------------------------------------------------------- #
# A2WebDetail / A2WebExtract — drive the real fetcher with mocked tier
# --------------------------------------------------------------------- #


class _MockRawTier:
    name = "raw"

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        return TierResult(
            body=self._body,
            content_type="text/html",
            status_code=200,
            final_url=url,
            headers={"etag": '"v1"'},
        )


def _make_state() -> AppState:
    from a2web.state import build_state

    return build_state(settings=AppSettings(log_enabled=False))


@pytest.mark.asyncio
async def test_a2web_detail_returns_content_md(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"<!doctype html><html><body><article><h1>Detail</h1>" + b"<p>substantive body. </p>" * 80 + b"</article></body></html>"
    monkeypatch.setitem(REGISTRY, "raw", _MockRawTier(body))
    state = _make_state()

    system = A2WebDetail(state=state)
    result = await system.fetch(url="https://example.com/p", ask="ignored")

    assert isinstance(result, SystemResult)
    assert result.system == "a2web_detail"
    assert "substantive body" in result.answer
    assert result.error is None
    assert result.cost_usd == 0.0  # detail mode never calls LLM


@pytest.mark.asyncio
async def test_a2web_extract_runs_extractor_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"<!doctype html><html><body><article><h1>Extract</h1>" + b"<p>content body. </p>" * 80 + b"</article></body></html>"
    monkeypatch.setitem(REGISTRY, "raw", _MockRawTier(body))
    state = _make_state()

    # Inject a stub extractor on the state to bypass real API construction.
    provider = _RecordingProvider(answer="Extract speaks.")
    state.llm_extractor._extractor = Extractor(provider=provider, model=ModelSpec("rec", "rec-model"))

    system = A2WebExtract(state=state)
    result = await system.fetch(url="https://example.com/p", ask="What does it say?")

    assert result.system == "a2web_extract"
    assert result.answer == "Extract speaks."
    assert result.cost_usd == pytest.approx(0.0008)
    assert result.prompt_tokens == 150
    assert result.completion_tokens == 30
    assert result.metadata["extraction_model"] == "rec-model"
    assert result.error is None


@pytest.mark.asyncio
async def test_a2web_extract_falls_back_to_content_md_when_no_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the extractor is unavailable, A2WebExtract still returns
    content_md (the extracted markdown) as the answer — graceful degrade."""
    body = b"<!doctype html><html><body><article><h1>NoLLM</h1>" + b"<p>content. </p>" * 80 + b"</article></body></html>"
    monkeypatch.setitem(REGISTRY, "raw", _MockRawTier(body))
    state = _make_state()
    state.llm_extractor._unavailable_reason = "No API key in env."

    system = A2WebExtract(state=state)
    result = await system.fetch(url="https://example.com/p", ask="ignored")

    assert result.system == "a2web_extract"
    # No LLM ran, so answer falls back to content_md (non-empty).
    assert result.answer  # truthy
    assert result.cost_usd == 0.0
    assert result.metadata["extraction_model"] is None
