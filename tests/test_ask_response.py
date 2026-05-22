"""ask-response-diet: the lean `AskResponse` envelope.

Every test drives the `ask` tool through the in-process MCP test client
(`call_wire` → the real formatter wrapper chain) and asserts on the
decoded wire dict — so the field-presence rules are verified on the exact
payload an agent receives, not on `.model_dump()`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from a2kit.testing import client as make_client

from a2web.llm_resource import LlmExtractorResource
from a2web.packages.llm_extract import Extractor, ModelSpec, ProviderResponse
from a2web.server import app
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult

_FIX = Path(__file__).parent / "fixtures"

# A metadata-free article body: no title, byline, date, or og/twitter tags —
# so byline / published / meta all resolve empty and SHALL be omitted.
_MINIMAL_HTML = (
    b"<html><body><main>"
    + b"<p>Adaptive web fetching keeps the calling agent's context small.</p>" * 30
    + b"</main></body></html>"
)


# --------------------------------------------------------------------- #
# Stubs
# --------------------------------------------------------------------- #


class _RawStub:
    """Fixed-body tier stand-in — no network. Defaults to the `raw` tier;
    pass `name` / `handler_name` to stand in for a site handler instead.
    """

    def __init__(
        self,
        body: bytes,
        next_links: list | None = None,
        *,
        name: str = "raw",
        handler_name: str | None = None,
    ) -> None:
        self.name = name
        self._body = body
        self._next_links = next_links or []
        self._handler_name = handler_name

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=self._body,
            content_type="text/html",
            status_code=200,
            final_url=url,
            next_links=self._next_links,
            handler_name=self._handler_name,
        )


class _StubProvider:
    """LLM provider stub — returns a canned answer regardless of input."""

    name = "stub"

    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
        del system, user
        return ProviderResponse(
            text=self._answer,
            model=model,
            prompt_tokens=120,
            completion_tokens=14,
            cost_usd=0.0003,
            latency_ms=88,
        )


_DEFAULT_ANSWER = "The page is about adaptive web fetching."


def _extractor(state: AppState, *, answer: str = _DEFAULT_ANSWER, unavailable: str | None = None) -> LlmExtractorResource:
    res = LlmExtractorResource(state.settings, state.sqlite)
    if unavailable is not None:
        res._unavailable_reason = unavailable
    else:
        res._extractor = Extractor(provider=_StubProvider(answer), model=ModelSpec("stub", "stub-model"))
    return res


async def _ask_wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: bytes | None = None,
    raw_next_links: list | None = None,
    unavailable: str | None = None,
    **ask_kwargs: object,
) -> dict:
    """Invoke `ask` through the MCP transport; return the decoded wire dict."""
    raw_body = body if body is not None else (_FIX / "blog.html").read_bytes()
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(raw_body, raw_next_links))
    async with make_client(app) as client:
        state = await app.container().get(AppState)
        client.override(LlmExtractorResource, _extractor(state, unavailable=unavailable))
        wire = await client.call_wire("ask", **ask_kwargs)
    return json.loads(wire)


_REQUIRED = {"confidence", "extracted_answer"}


# --------------------------------------------------------------------- #
# 2.1 — required fields, no fit_md / tokens / is_user_authored
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_success_carries_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="what is this about?")
    assert _REQUIRED <= set(data)
    assert data["extracted_answer"] == "The page is about adaptive web fetching."


@pytest.mark.asyncio
async def test_ask_omits_fit_md_tokens_is_user_authored(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "fit_md" not in data
    assert "tokens" not in data
    assert "is_user_authored" not in data


# --------------------------------------------------------------------- #
# 2.2 — content_md / headings are opt-in
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_default_omits_content_and_headings(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "content_md" not in data
    assert "headings" not in data


@pytest.mark.asyncio
async def test_ask_include_content_returns_content_and_headings(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?", include_content=True)
    assert data["content_md"]
    assert isinstance(data["headings"], list)
    # headings render as [level, text] tuples
    for heading in data["headings"]:
        assert isinstance(heading, list)
        assert len(heading) == 2


# --------------------------------------------------------------------- #
# 2.3 — empty optionals omitted, populated optionals present
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_omits_empty_optionals(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/post",
        question="q?",
        next_links=False,
    )
    for key in ("byline", "published", "operator_hints", "next_links", "original_url", "meta"):
        assert key not in data, f"empty optional {key!r} leaked onto the wire"


@pytest.mark.asyncio
async def test_ask_includes_populated_optionals(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.models import NextLink

    handler_links = [NextLink(anchor="Related post", url="https://example.org/related", reason="related", kind="related")]
    # An unavailable LLM still succeeds the fetch and surfaces an operator hint.
    data = await _ask_wire(
        monkeypatch,
        raw_next_links=handler_links,
        unavailable="No Anthropic API key found.",
        url="https://example.org/post",
        question="q?",
    )
    assert "status" not in data  # success → status omitted
    assert "operator_hints" in data
    assert any(h["code"] == "llm_unavailable" for h in data["operator_hints"])
    # next_links is a TSV string, not a JSON array
    assert isinstance(data["next_links"], str)
    assert "https://example.org/related" in data["next_links"]


# --------------------------------------------------------------------- #
# 2.1 / 2.5 — status failure-only; next_links TSV
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_status_is_failure_only(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "status" not in ok
    body = (_FIX / "cloudflare_block.html").read_bytes()
    failed = await _ask_wire(monkeypatch, body=body, url="https://blocked.example/page", question="q?")
    assert failed["status"] == "failed"


@pytest.mark.asyncio
async def test_ask_next_links_tsv_drops_kind_when_all_drilldown(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.models import NextLink

    links = [
        NextLink(anchor="One", url="https://example.org/1", reason="r1", kind="drilldown"),
        NextLink(anchor="Two", url="https://example.org/2", reason="r2", kind="drilldown"),
    ]
    data = await _ask_wire(monkeypatch, raw_next_links=links, url="https://example.org/post", question="q?")
    tsv = data["next_links"]
    assert isinstance(tsv, str)
    assert tsv.splitlines()[0] == "anchor\turl\treason"  # no kind column
    assert len(tsv.splitlines()) == 3  # header + 2 rows


@pytest.mark.asyncio
async def test_ask_next_links_tsv_keeps_kind_when_mixed(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.models import NextLink

    links = [
        NextLink(anchor="One", url="https://example.org/1", reason="r1", kind="drilldown"),
        NextLink(anchor="Two", url="https://example.org/2", reason="r2", kind="related"),
    ]
    data = await _ask_wire(monkeypatch, raw_next_links=links, url="https://example.org/post", question="q?")
    assert data["next_links"].splitlines()[0] == "anchor\turl\treason\tkind"


# --------------------------------------------------------------------- #
# 2.4 — narrative / diagnostics_summary are failure-only
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_success_omits_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "status" not in data
    assert "narrative" not in data
    assert "diagnostics_summary" not in data


@pytest.mark.asyncio
async def test_ask_failure_carries_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "cloudflare_block.html").read_bytes()
    data = await _ask_wire(monkeypatch, body=body, url="https://blocked.example/page", question="q?")
    assert data["status"] == "failed"
    assert data["narrative"]
    assert data["diagnostics_summary"]


# --------------------------------------------------------------------- #
# 2.5 — timing / cache / diagnostics are debug-only
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_default_omits_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "debug" not in data
    for key in ("started_at", "total_ms", "cache", "diagnostics"):
        assert key not in data


@pytest.mark.asyncio
async def test_ask_debug_includes_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?", debug=True)
    debug = data["debug"]
    for key in ("started_at", "total_ms", "cache"):
        assert key in debug


# --------------------------------------------------------------------- #
# 2.2 / 2.3 / 2.4 — extraction is debug-only; truncation → operator hint
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_omits_extraction_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "extraction" not in data


@pytest.mark.asyncio
async def test_ask_truncation_surfaces_operator_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    # A tiny content cap forces the extractor to truncate its input.
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/post",
        question="q?",
        max_content_chars=200,
    )
    assert "extraction" not in data
    assert any(h["code"] == "answer_truncated" for h in data["operator_hints"])


@pytest.mark.asyncio
async def test_ask_extraction_full_under_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?", debug=True)
    extraction = data["debug"]["extraction"]
    assert "truncated" in extraction
    assert extraction["model"] == "stub-model"
    assert "prompt_tokens" in extraction
    assert "latency_ms" in extraction


# --------------------------------------------------------------------- #
# deviation-only tier / url
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_tier_omitted_for_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "tier" not in data


@pytest.mark.asyncio
async def test_ask_url_omitted_when_no_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", question="q?")
    assert "url" not in data


@pytest.mark.asyncio
async def test_ask_url_carried_when_host_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    # A Google search URL is captcha-rewritten to DuckDuckGo before tier dispatch.
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://www.google.com/search?q=adaptive+web+fetching",
        question="q?",
    )
    assert data["url"].startswith("https://duckduckgo.com/html/")
