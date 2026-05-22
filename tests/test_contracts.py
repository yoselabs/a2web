"""Golden contract tests for the `ask` / `fetch_raw` wire envelopes.

Each scenario invokes a tool through the in-process MCP test client
(`call_wire` — the real formatter wrapper chain) and compares the decoded
wire payload against a checked-in golden JSON under `tests/contracts/`.
This guards the conditional field-presence logic (empty-omission, debug /
failure tiers, `include_content` gating) against silent regressions, and
also surfaces any a2kit-side serialization change as a conscious re-bless.

When the contract changes intentionally, re-bless the goldens:

    make bless-contracts
    # or: A2WEB_BLESS_CONTRACTS=1 uv run pytest tests/test_contracts.py

A mismatch without blessing is a regression.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from a2kit.testing import client as make_client
from a2kit.testing import compute_schema

from a2web.llm_resource import LlmExtractorResource
from a2web.models import AskResponse, FetchResponse, NextLink
from a2web.server import app
from a2web.state import AppState
from a2web.tiers import REGISTRY
from tests.test_ask_response import _MINIMAL_HTML, _extractor, _RawStub

_GOLDEN_DIR = Path(__file__).parent / "contracts"
_FIX = Path(__file__).parent / "fixtures"
_BLESS = os.environ.get("A2WEB_BLESS_CONTRACTS") == "1"

# Keys whose values are timing- or environment-dependent — scrubbed before
# compare so the golden captures the contract *shape*, not the wall clock or
# cache state. Field presence (the actual contract) is still verified.
_VOLATILE_KEYS = frozenset({"started_at", "total_ms", "t_ms", "dur_ms", "latency_ms", "cache"})


def _scrub_str(value: str) -> str:
    """Replace timing/timestamp substrings baked into string fields.

    `narrative` and `diagnostics_summary` embed durations (`raw → ok
    (140ms)`, `total_ms=140`) and the content wrapper embeds `fetched_at`.
    """
    value = re.sub(r"fetched_at=[0-9T:+\-Z]+", "fetched_at=<volatile>", value)
    value = re.sub(r"total_ms=\d+", "total_ms=<volatile>", value)
    return re.sub(r"\d+(?:\.\d+)?\s?m?s\b", "<dur>", value)


def _normalize(obj: object) -> object:
    """Recursively replace volatile values with a placeholder."""
    if isinstance(obj, dict):
        return {k: ("<volatile>" if k in _VOLATILE_KEYS else _normalize(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, str):
        return _scrub_str(obj)
    return obj


def _check(name: str, payload: object) -> None:
    """Compare `payload` to its golden, or (re)write it when blessing."""
    path = _GOLDEN_DIR / f"{name}.json"
    serialized = json.dumps(_normalize(payload), indent=2, sort_keys=True) + "\n"
    if _BLESS:
        _GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(serialized)
        return
    if not path.exists():
        _GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(serialized)
        pytest.fail(f"golden contracts/{name}.json did not exist — created it; re-run to verify, then commit it.")
    expected = path.read_text()
    if expected != serialized:
        pytest.fail(
            f"API contract drift in contracts/{name}.json.\n"
            "If intended, re-bless: `make bless-contracts`. Otherwise this is a regression.\n\n"
            f"--- expected ---\n{expected}\n--- actual ---\n{serialized}"
        )


async def _ask_wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: bytes,
    raw_next_links: list | None = None,
    unavailable: str | None = None,
    **kwargs: object,
) -> dict:
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body, raw_next_links))
    async with make_client(app) as client:
        state = await app.container().get(AppState)
        client.override(LlmExtractorResource, _extractor(state, unavailable=unavailable))
        return json.loads(await client.call_wire("ask", **kwargs))


async def _fetch_raw_wire(monkeypatch: pytest.MonkeyPatch, *, body: bytes, **kwargs: object) -> dict:
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body))
    async with make_client(app) as client:
        return json.loads(await client.call_wire("fetch_raw", **kwargs))


# --------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_contract_ask_success_minimal(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/minimal",
        question="what is this about?",
    )
    _check("ask_success_minimal", data)


@pytest.mark.asyncio
async def test_contract_ask_success_rich(monkeypatch: pytest.MonkeyPatch) -> None:
    links = [NextLink(anchor="Related", url="https://example.org/related", reason="related read", kind="related")]
    data = await _ask_wire(
        monkeypatch,
        body=(_FIX / "blog.html").read_bytes(),
        raw_next_links=links,
        url="https://example.org/rich",
        question="summarize the article",
    )
    _check("ask_success_rich", data)


@pytest.mark.asyncio
async def test_contract_ask_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        body=(_FIX / "cloudflare_block.html").read_bytes(),
        url="https://blocked.example/page",
        question="q",
    )
    _check("ask_failure", data)


@pytest.mark.asyncio
async def test_contract_ask_include_content(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/grounded",
        question="q",
        include_content=True,
        wrap_content=False,
    )
    _check("ask_include_content", data)


@pytest.mark.asyncio
async def test_contract_ask_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _ask_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/debugged",
        question="q",
        debug=True,
    )
    _check("ask_debug", data)


@pytest.mark.asyncio
async def test_contract_fetch_raw_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/raw",
        wrap_content=False,
    )
    _check("fetch_raw_basic", data)


def test_contract_tool_schemas() -> None:
    """Snapshot the declared MCP tool schemas — catches signature / param /
    field-shape drift that a sample payload would not surface (e.g. a new
    optional param or a renamed model field).

    `compute_schema` collapses `outputSchema` to a bare `$ref`, so the
    return model's own `model_json_schema()` is snapshotted for field detail.
    """
    container = app.container()
    by_name = {d.name: d for d in app.tools()}
    snapshot = {
        "ask": {
            "inputSchema": compute_schema(by_name["ask"].fn, container)["inputSchema"],
            "outputModel": AskResponse.model_json_schema(),
        },
        "fetch_raw": {
            "inputSchema": compute_schema(by_name["fetch_raw"].fn, container)["inputSchema"],
            "outputModel": FetchResponse.model_json_schema(),
        },
    }
    _check("tool_schemas", snapshot)
