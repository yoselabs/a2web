"""fetch-response-diet: the lean `FetchResponse` wire envelope.

Every test drives the `fetch_raw` tool through the in-process MCP test
client (`call_wire` → the real formatter wrapper chain) and asserts on the
decoded wire dict — so the field-presence rules (empty-omission, failure /
debug tiers, TSV rendering) are verified on the exact payload an agent
receives, not on `.model_dump()`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from a2kit.testing import client as make_client

from a2web.models import NextLink
from a2web.server import app
from a2web.tiers import REGISTRY
from tests.test_ask_response import _MINIMAL_HTML, _RawStub

_FIX = Path(__file__).parent / "fixtures"


async def _fetch_raw_wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: bytes,
    raw_next_links: list | None = None,
    **kwargs: object,
) -> dict:
    """Invoke `fetch_raw` through the MCP transport; return the decoded wire dict."""
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body, raw_next_links))
    async with make_client(app) as client:
        wire = await client.call_wire("fetch_raw", **kwargs)
    return json.loads(wire)


# --------------------------------------------------------------------- #
# Empty-omission + failure-only status / narrative
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_success_omits_status_and_empty_optionals(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/raw",
        next_links=False,
    )
    # confidence is the one always-present field
    assert "confidence" in data
    # deviation-only: raw tier + no redirect → tier / url / status all absent
    for key in ("status", "tier", "url"):
        assert key not in data, f"deviation-only field {key!r} leaked on the default path"
    # failure-only fields absent on success
    for key in ("narrative", "diagnostics_summary"):
        assert key not in data, f"failure-only field {key!r} leaked on a successful fetch"
    # empty optionals absent (metadata-free body, no LLM, no links)
    for key in ("byline", "published", "meta", "links", "next_links", "operator_hints", "extraction", "extracted_answer"):
        assert key not in data, f"empty optional {key!r} leaked onto the wire"
    # original_url is gone from the envelope entirely
    assert "original_url" not in data


@pytest.mark.asyncio
async def test_fetch_raw_failure_carries_status_and_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "cloudflare_block.html").read_bytes()
    data = await _fetch_raw_wire(monkeypatch, body=body, url="https://blocked.example/page")
    assert data["status"] == "failed"
    assert data["narrative"]
    assert data["diagnostics_summary"]


# --------------------------------------------------------------------- #
# Debug sub-object — timing / cache / diagnostics / tokens
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_default_omits_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(monkeypatch, body=_MINIMAL_HTML, url="https://example.org/raw")
    assert "debug" not in data
    for key in ("started_at", "total_ms", "cache", "diagnostics", "tokens"):
        assert key not in data


@pytest.mark.asyncio
async def test_fetch_raw_debug_nests_full_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(monkeypatch, body=_MINIMAL_HTML, url="https://example.org/raw", debug=True)
    debug = data["debug"]
    for key in ("started_at", "total_ms", "cache", "tokens", "diagnostics"):
        assert key in debug
    assert debug["tokens"]["full"] == len(data["content_md"])


# --------------------------------------------------------------------- #
# Deviation-only tier / url
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_tier_omitted_for_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(monkeypatch, body=_MINIMAL_HTML, url="https://example.org/raw")
    assert "tier" not in data


@pytest.mark.asyncio
async def test_fetch_raw_tier_carried_for_site_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    # A tier-0 site handler wins — its identifier deviates from `raw`.
    handler = _RawStub(_MINIMAL_HTML, name="site_handler:stub", handler_name="site_handler:stub")
    monkeypatch.setitem(REGISTRY, "site_handler", handler)
    async with make_client(app) as client:
        data = json.loads(await client.call_wire("fetch_raw", url="https://example.org/raw"))
    assert data.get("tier") == "site_handler:stub"


@pytest.mark.asyncio
async def test_fetch_raw_url_omitted_when_no_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(monkeypatch, body=_MINIMAL_HTML, url="https://example.org/raw")
    assert "url" not in data


@pytest.mark.asyncio
async def test_fetch_raw_url_carried_when_host_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    # A Google search URL is captcha-rewritten to DuckDuckGo before tier dispatch.
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://www.google.com/search?q=adaptive+web+fetching",
    )
    assert data["url"].startswith("https://duckduckgo.com/html/")


# --------------------------------------------------------------------- #
# TSV rendering for links / next_links
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_links_render_as_tsv(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "blog.html").read_bytes()
    data = await _fetch_raw_wire(monkeypatch, body=body, url="https://example.org/post", include_links=True)
    tsv = data["links"]
    assert isinstance(tsv, str)
    assert tsv.splitlines()[0] == "anchor\thref\trole"
    assert len(tsv.splitlines()) >= 2  # header + at least one link


@pytest.mark.asyncio
async def test_fetch_raw_next_links_render_as_tsv(monkeypatch: pytest.MonkeyPatch) -> None:
    links = [
        NextLink(anchor="One", url="https://example.org/1", reason="r1", kind="drilldown"),
        NextLink(anchor="Two", url="https://example.org/2", reason="r2", kind="drilldown"),
    ]
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        raw_next_links=links,
        url="https://example.org/raw",
    )
    tsv = data["next_links"]
    assert isinstance(tsv, str)
    assert tsv.splitlines()[0] == "anchor\turl\treason"  # all-drilldown → no kind column
    assert len(tsv.splitlines()) == 3


@pytest.mark.asyncio
async def test_fetch_raw_empty_link_arrays_stay_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/raw",
        include_links=True,
        next_links=False,
    )
    assert "links" not in data
    assert "next_links" not in data
