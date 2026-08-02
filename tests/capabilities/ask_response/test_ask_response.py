"""ask-response-diet: the lean `AskResponse` envelope.

Every test drives the `ask` tool through the in-process MCP test client
(`call_wire` → the real formatter wrapper chain) and asserts on the
decoded wire dict — so the field-presence rules are verified on the exact
payload an agent receives, not on `.model_dump()`.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from async_scope import lazy

from a2web.components import build_components
from a2web.llm_resource import LlmExtractorResource
from a2web.packages.llm_extract import Provider, ProviderResponse
from a2web.state import AppState, unavailable_lazy
from a2web.tiers import REGISTRY, TierResult
from tests._helpers.llm_doubles import DoubleArm, honor_contract
from tests._helpers.mcp import call_wire, mcp_client
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR

# A metadata-free article body: no title, byline, date, or og/twitter tags —
# so byline / published / meta all resolve empty and SHALL be omitted.
_MINIMAL_HTML = (
    b"<html><body><main>" + b"<p>Adaptive web fetching keeps the calling agent's context small.</p>" * 30 + b"</main></body></html>"
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
    """LLM provider stub that HONORS the output contract it is handed.

    It used to `del system, user` and return prose unconditionally, which made
    it a false witness on the `request_routing=True` path: `EXTRACT_ROUTER_V1`
    says "Output strict JSON only", a real model returns an envelope, this
    returned prose, the router parse raised, and every test driven through it
    silently exercised the routing-LOST branch while presenting as a healthy
    `query`. That is why the ADR-0015 index signal was measured as "fires on
    every query — permanent noise" and shelved against a fixture rather than a
    model.

    The contract logic lives in `honor_contract`, shared by every pass-through
    double. Eight private copies would drift, and a drifted copy is
    indistinguishable from the bug.
    """

    DOUBLES_ARM = DoubleArm.ROUTER_FAITHFUL
    name = "stub"

    def __init__(self, answer: str) -> None:
        self._answer = answer

    @classmethod
    def for_fidelity_check(cls) -> _StubProvider:
        return cls(_DEFAULT_ANSWER)

    async def complete(self, *, system: str, user: str, model: str, **_: object) -> ProviderResponse:
        del user
        return ProviderResponse(
            text=honor_contract(self._answer, system),
            model=model,
            prompt_tokens=120,
            completion_tokens=14,
            cost_usd=0.0003,
            latency_ms=88,
        )


_DEFAULT_ANSWER = "The page is about adaptive web fetching."


def _extractor(state: AppState, *, answer: str = _DEFAULT_ANSWER, unavailable: str | None = None) -> LlmExtractorResource:
    provider = unavailable_lazy(Provider, reason=unavailable) if unavailable is not None else lazy(_StubProvider(answer))
    return LlmExtractorResource(state.settings, state.sqlite, provider)


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
    parts = build_components()
    state = await parts.state()
    parts = dataclasses.replace(parts, llm_extractor=lazy(_extractor(state, unavailable=unavailable)))
    async with mcp_client(components=parts) as client:
        wire = await call_wire(client, "query", **ask_kwargs)
    return json.loads(wire)


_REQUIRED = {"confidence", "answer"}


# --------------------------------------------------------------------- #
# 2.1 — required fields, no fit_md / tokens / is_user_authored
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_success_carries_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="what is this about?")
    assert _REQUIRED <= set(data)
    assert data["answer"] == "The page is about adaptive web fetching."


@pytest.mark.asyncio
async def test_ask_omits_fit_md_tokens_is_user_authored(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "fit_md" not in data
    assert "tokens" not in data
    assert "is_user_authored" not in data


# --------------------------------------------------------------------- #
# 2.2 — content_md / headings are opt-in
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_default_omits_content_and_headings(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "content_md" not in data
    assert "headings" not in data


@pytest.mark.asyncio
async def test_ask_include_content_returns_content_and_headings(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?", include_content=True)
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
        query="q?",
        other_pages=False,
    )
    for key in ("byline", "published", "operator_hints", "other_pages", "next_links", "original_url", "meta"):
        assert key not in data, f"empty optional {key!r} leaked onto the wire"


@pytest.mark.asyncio
async def test_ask_includes_populated_optionals(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.models import NextLink

    handler_links = [NextLink(anchor="Related post", url="https://example.org/related", reason="related", kind="related")]
    # An unavailable LLM fails the ask hard (no answer delivered), but the
    # handler-derived continuation links still surface on the wire — now folded
    # into `other_pages` as kind=structural (ADR-0015).
    data = await _ask_wire(
        monkeypatch,
        raw_next_links=handler_links,
        unavailable="No Anthropic API key found.",
        url="https://example.org/post",
        query="q?",
    )
    assert data["status"] == "failed"  # ask delivered no answer → loud failure
    assert "operator_hints" in data
    assert any(h["code"] == "llm_unavailable" for h in data["operator_hints"])
    # other_pages is a TSV string, not a JSON array; handler links are structural
    assert isinstance(data["other_pages"], str)
    assert "https://example.org/related" in data["other_pages"]
    # Corrected 2026-08-01: a `related` handler link is a distinct page, so it
    # folds in as `drilldown`. It used to be relabelled `structural`.
    assert "drilldown" in data["other_pages"]


# --------------------------------------------------------------------- #
# 2.1 / 2.5 — status failure-only; other_pages TSV
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_status_is_failure_only(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "status" not in ok
    body = (_FIX / "cloudflare_block.html").read_bytes()
    failed = await _ask_wire(monkeypatch, body=body, url="https://blocked.example/page", query="q?")
    assert failed["status"] == "failed"


@pytest.mark.asyncio
async def test_ask_other_pages_tsv_carries_the_handlers_own_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    """A handler-assigned kind must survive the fold into `other_pages`.

    **This test previously asserted the defect**, down to its name
    (`..._are_structural`): it required every handler link to arrive as
    `kind="structural"` whatever the handler said. Measured across the tree, 7
    of 7 handler-constructed `NextLink`s carry `discussion`, `drilldown` or
    `related` — never `structural` — so the wire value was false for all of
    them, and a handler that explicitly said `drilldown` had it rewritten to
    the opposite claim.

    `structural` means "more of the SAME listing" (pagination). None of the four
    `NextLinkKind` values means that, so all four map to `drilldown`, and
    `structural` is now produced only by the LLM's own routing — the only place
    that can actually see a pagination affordance.

    `anchor` is carried too. It used to be dropped on the same line that
    relabelled the kind, so a caller reading `other_pages` got a URL and a
    machine-written `reason` with no trace of what the page CALLED the link —
    on a listing, the item's title, which is the most useful thing for deciding
    whether to spend a fetch on it.
    """
    from a2web.models import NextLink

    links = [
        NextLink(anchor="One", url="https://example.org/1", reason="r1", kind="drilldown"),
        NextLink(anchor="Two", url="https://example.org/2", reason="r2", kind="related"),
    ]
    data = await _ask_wire(monkeypatch, raw_next_links=links, url="https://example.org/post", query="q?")
    tsv = data["other_pages"]
    assert isinstance(tsv, str)
    lines = tsv.splitlines()
    assert lines[0] == "url\treason\tkind\tanchor"
    assert len(lines) == 3  # header + 2 rows
    assert all("\tdrilldown\t" in row for row in lines[1:]), f"handler kind did not survive the fold:\n{tsv}"
    assert "\tstructural" not in tsv, "a handler link must not be relabelled a pagination continuation"
    # The page's own link text now reaches the caller.
    assert lines[1].endswith("\tOne") and lines[2].endswith("\tTwo"), f"anchor did not survive the fold:\n{tsv}"


# --------------------------------------------------------------------- #
# 2.4 — narrative / diagnostics_summary are failure-only
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_success_omits_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "status" not in data
    assert "narrative" not in data
    assert "diagnostics_summary" not in data


@pytest.mark.asyncio
async def test_ask_failure_carries_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "cloudflare_block.html").read_bytes()
    data = await _ask_wire(monkeypatch, body=body, url="https://blocked.example/page", query="q?")
    assert data["status"] == "failed"
    assert data["narrative"]
    assert data["diagnostics_summary"]


# --------------------------------------------------------------------- #
# 2.5 — timing / cache / diagnostics are debug-only
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_default_omits_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "debug" not in data
    for key in ("started_at", "total_ms", "cache", "diagnostics"):
        assert key not in data


@pytest.mark.asyncio
async def test_ask_debug_includes_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?", debug=True)
    debug = data["debug"]
    for key in ("started_at", "total_ms", "cache"):
        assert key in debug


# --------------------------------------------------------------------- #
# 2.2 / 2.3 / 2.4 — extraction is debug-only; truncation → operator hint
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_omits_extraction_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "extraction" not in data


@pytest.mark.asyncio
async def test_ask_truncation_surfaces_operator_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    # A tiny content cap forces the extractor to truncate its input.
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/post",
        query="q?",
        max_content_chars=200,
    )
    assert "extraction" not in data
    assert any(h["code"] == "answer_truncated" for h in data["operator_hints"])


@pytest.mark.asyncio
async def test_ask_extraction_full_under_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?", debug=True)
    extraction = data["debug"]["extraction"]
    assert "truncated" in extraction
    # Model id reflects the configured model (the resource builds the Extractor).
    assert extraction["model"] == "claude-haiku-4-5-20251001"
    assert "prompt_tokens" in extraction
    assert "latency_ms" in extraction


# --------------------------------------------------------------------- #
# deviation-only tier / url
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_tier_omitted_for_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "tier" not in data


@pytest.mark.asyncio
async def test_ask_url_omitted_when_no_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "url" not in data


@pytest.mark.asyncio
async def test_ask_url_carried_when_host_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    # A Google search URL is captcha-rewritten to DuckDuckGo before tier dispatch.
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://www.google.com/search?q=adaptive+web+fetching",
        query="q?",
    )
    assert data["url"].startswith("https://duckduckgo.com/html/")


# --------------------------------------------------------------------- #
# meta allowlist (ask-extraction-token-tuning)
# --------------------------------------------------------------------- #

# A page carrying both allowlisted (og:description) and non-allowlisted
# (og:title, og:site_name, og:image, og:image:width, twitter:card,
# twitter:label1) metadata — og:title duplicates the promoted `title` field
# and og:site_name duplicates the domain already visible in the requested URL.
_RICH_META_HTML = (
    b"<html><head>"
    b'<meta property="og:title" content="Rich Meta Post">'
    b'<meta property="og:description" content="A post with curated-worthy metadata.">'
    b'<meta property="og:site_name" content="Example Site">'
    b'<meta property="og:image" content="https://example.org/cover.jpg">'
    b'<meta property="og:image:width" content="1200">'
    b'<meta name="twitter:card" content="summary_large_image">'
    b'<meta name="twitter:label1" content="Written by">'
    b"</head><body><main>" + b"<p>Adaptive web fetching keeps the calling agent's context small.</p>" * 30 + b"</main></body></html>"
)


async def _fetch_raw_wire(monkeypatch: pytest.MonkeyPatch, *, body: bytes, **kwargs: object) -> dict:
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body))
    async with mcp_client() as client:
        wire = await call_wire(client, "fetch_raw", **kwargs)
    return json.loads(wire)


@pytest.mark.asyncio
async def test_ask_meta_curates_to_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(monkeypatch, body=_RICH_META_HTML, url="https://example.org/post", query="q?")
    assert data["meta"] == {
        "og.description": "A post with curated-worthy metadata.",
    }
    assert "og.title" not in data["meta"]  # duplicates the promoted `title` field
    assert "og.site_name" not in data["meta"]  # duplicates the domain in the URL
    assert "og.image" not in data["meta"]
    assert "og.image:width" not in data["meta"]
    assert "twitter.card" not in data["meta"]
    assert "twitter.label1" not in data["meta"]


@pytest.mark.asyncio
async def test_ask_meta_omitted_when_curation_leaves_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    # blog.html carries only non-allowlisted keys (og.type/title/image/url,
    # twitter.card/site) — curation leaves an empty dict, which is omitted.
    data = await _ask_wire(monkeypatch, url="https://example.org/post", query="q?")
    assert "meta" not in data


@pytest.mark.asyncio
async def test_fetch_raw_meta_keeps_full_uncurated_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(monkeypatch, body=_RICH_META_HTML, url="https://example.org/post")
    assert data["meta"]["og.title"] == "Rich Meta Post"
    assert data["meta"]["og.description"] == "A post with curated-worthy metadata."
    assert data["meta"]["og.site_name"] == "Example Site"
    assert data["meta"]["og.image"] == "https://example.org/cover.jpg"
    assert data["meta"]["twitter.card"] == "summary_large_image"
