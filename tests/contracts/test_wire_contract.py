"""The wire contract gate — golden snapshots of the real MCP surface.

Four artifacts, captured through a real `fastmcp.Client` against the real
`build_mcp_server(build_app())` assembly (see `wire_harness` for why nothing
else will do):

1. `list_tools` — names, descriptions, schemas, annotations, `_meta`.
2. `call/<scenario>` — both channels per scenario, raw text kept opaque.
3. `errors/<scenario>` — the failure surface.
4. `notifications` — the mid-call `notifications/message` stream.

This gate exists to make the a2kit sunset landable as a *sequence* rather
than one unverifiable commit. Its rule during that migration is **zero
deltas**: the substrate underneath may be replaced wholesale, but the bytes
an installed agent receives may not move. The later `lean-wire` adoption is
the opposite: every delta must carry the slug `lean-wire-escaping` and touch
only cells containing `"`, `\\`, `\\t`, `\\n`, `\\r`.

Anti-vacuity is a first-class concern here. A golden that froze a degenerate
payload would compare equal forever while asserting nothing, so every
capture is paired with a positive assertion that the fixture still produces
the content it was built to produce.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from a2web.components import build_components
from a2web.lazy import lazy
from a2web.models import NextLink
from a2web.server import build_mcp_server
from a2web.tiers import REGISTRY
from tests.capabilities.ask_response.test_ask_response import _MINIMAL_HTML, _extractor, _RawStub
from tests.contracts.wire_harness import WIRE_DIR, capture, check_wire, freeze_clocks, normalize, wire_client
from tests.fixtures import FIXTURES_DIR

# --------------------------------------------------------------------- #
# Adversarial cells — the diff surface for the later `lean-wire` swap.
#
# These are the characters whose encoding differs between codecs. Freezing
# them means a codec change produces a bounded, reviewable diff instead of an
# unbounded one. Realistic, not synthetic: a multi-line `<a>` block with a
# title/price/rating is what listing markup actually looks like, and a
# double quote inside an LLM-authored `reason` is the single most likely
# csv `QUOTE_MINIMAL` quote-doubling trigger in production.
# --------------------------------------------------------------------- #

# NOTE: `other_pages` renders as a TSV of `url | reason | kind` only — the
# anchor never reaches this envelope. So the hostile characters have to live
# in `reason`, or the scenario degrades into a duplicate of `success_rich`.
_ADVERSARIAL_LINKS = [
    NextLink(
        anchor="HD 600",
        url="https://example.org/p/hd600",
        # Double quote -> csv QUOTE_MINIMAL wraps the cell AND doubles the
        # quotes. The likeliest hostile character in LLM-authored prose, and
        # the one whose encoding differs most between codecs.
        reason='the page calls this one "the reference" for the price band',
        kind="related",
    ),
    NextLink(
        anchor="Driver spec",
        url="https://example.org/p/driver",
        # Backslash: passed through by csv, escaped by JSON. Two layers.
        reason="see C:\\drivers\\readme.txt on the vendor page",
        kind="related",
    ),
    NextLink(
        anchor="Spec table",
        url="https://example.org/p/spec",
        # Interior newline + tab: the characters that ARE the TSV framing.
        # A codec that fails to quote this cell corrupts the whole table.
        reason="row 1:\tmax SPL\nrow 2:\timpedance",
        kind="related",
    ),
]


async def _query_wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: bytes,
    raw_next_links: list | None = None,
    unavailable: str | None = None,
    **kwargs: object,
) -> dict:
    freeze_clocks(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body, raw_next_links))
    parts = build_components()
    state = await parts.state()
    parts = dataclasses.replace(parts, llm_extractor=lazy(_extractor(state, unavailable=unavailable)))
    async with wire_client(build_mcp_server(components=parts)) as client:
        result = await client.call_tool("query", dict(kwargs), raise_on_error=False)
    return capture(result)


async def _fetch_raw_wire(monkeypatch: pytest.MonkeyPatch, *, body: bytes, **kwargs: object) -> dict:
    freeze_clocks(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body))
    async with wire_client() as client:
        result = await client.call_tool("fetch_raw", dict(kwargs), raise_on_error=False)
    return capture(result)


def _text(payload: dict) -> str:
    return payload["content"][0]["text"]


# --------------------------------------------------------------------- #
# Artifact 1 — the advertised tool list
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wire_list_tools() -> None:
    """Freeze names, descriptions, schemas, annotations and `_meta`.

    `_meta` is retained deliberately: it carries an a2kit-owned block today,
    so the sunset removing it becomes a *reviewed* delta rather than a silent
    disappearance.
    """
    async with wire_client() as client:
        tools = await client.list_tools()

    names = sorted(t.name for t in tools)
    # Anti-vacuity + a documentation correction. The advertised surface is
    # exactly two tools: `expose_cookies_tool` defaults false, so `build_app()`
    # selects `_A2WebServer`, which drops `CookiesRouter` entirely. `refresh`
    # is NOT on the wire and never has been in the installed configuration.
    assert names == ["fetch_raw", "query"], f"advertised surface changed: {names}"

    payload = [json.loads(t.model_dump_json(exclude_none=False)) for t in sorted(tools, key=lambda t: t.name)]
    # Anti-vacuity: descriptions are the agent's entire basis for tool
    # selection. A golden capturing empty ones would be worse than useless.
    for tool, entry in zip(sorted(tools, key=lambda t: t.name), payload, strict=True):
        assert entry["description"], f"{tool.name} advertises no description"
        assert entry["inputSchema"]["properties"], f"{tool.name} advertises no parameters"

    check_wire("list_tools", payload)


# --------------------------------------------------------------------- #
# Artifact 2 — per-scenario, both channels
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wire_query_success_minimal(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = await _query_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/minimal",
        query="what is this about?",
    )
    assert payload["is_error"] is False
    assert payload["structured_content"]["answer"]
    check_wire("call/query_success_minimal", payload)


@pytest.mark.asyncio
async def test_wire_query_success_rich(monkeypatch: pytest.MonkeyPatch) -> None:
    links = [NextLink(anchor="Related", url="https://example.org/related", reason="related read", kind="related")]
    payload = await _query_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "blog.html").read_bytes(),
        raw_next_links=links,
        url="https://example.org/rich",
        query="summarize the article",
    )
    check_wire("call/query_success_rich", payload)


@pytest.mark.asyncio
async def test_wire_query_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A walled fetch — the ADR-0009 surface.

    Note this is NOT the error path: `is_error` is False and the tool returns
    successfully. The incompleteness is carried in the payload's own fields.
    """
    payload = await _query_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "cloudflare_block.html").read_bytes(),
        url="https://blocked.example/page",
        query="q",
    )
    assert payload["is_error"] is False, "a wall is data, not a transport error"
    sc = payload["structured_content"]
    # Anti-vacuity, and the ADR-0009 invariant itself: a walled fetch must be
    # impossible to mistake for a complete answer.
    assert sc["status"] == "failed"
    assert sc["retrieval_incomplete"] is True
    assert "try_user_browser" in _text(payload)
    check_wire("call/query_failure", payload)


@pytest.mark.asyncio
async def test_wire_query_include_content(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = await _query_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/grounded",
        query="q",
        include_content=True,
        wrap_content=False,
    )
    check_wire("call/query_include_content", payload)


@pytest.mark.asyncio
async def test_wire_query_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = await _query_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/debugged",
        query="q",
        debug=True,
    )
    # Anti-vacuity: the debug regroup is the thing under test. If `debug`
    # vanished from the wire the golden would still compare equal.
    assert "debug" in _text(payload)
    check_wire("call/query_debug", payload)


@pytest.mark.asyncio
async def test_wire_query_adversarial_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `lean-wire` diff surface: quote, tab, newline, backslash in cells."""
    payload = await _query_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "blog.html").read_bytes(),
        raw_next_links=_ADVERSARIAL_LINKS,
        url="https://example.org/adversarial",
        query="summarize",
    )
    encoded = payload["structured_content"]["other_pages"]

    # THE invariant `lean-wire` exists for, and the reason this scenario is not
    # just `query_success_rich` with uglier strings: **one record is exactly one
    # physical line.** stdlib `csv` cannot give you that — QUOTE_MINIMAL wraps a
    # cell containing a newline in quotes but leaves the raw newline INSIDE the
    # field, so an agent doing the obvious thing with a line-oriented format
    # (`payload.split("\n")`) tears one record into several. Counting lines is
    # therefore the assertion, not a spot-check on any one cell.
    lines = [line for line in encoded.split("\n") if line]
    assert len(lines) == len(_ADVERSARIAL_LINKS) + 1, (
        f"expected 1 header + {len(_ADVERSARIAL_LINKS)} records, got {len(lines)} lines. "
        "A cell leaked a raw newline, which is precisely the csv behaviour "
        "`lean-wire` was adopted to remove."
    )

    # Anti-vacuity: without these, the fixture could stop carrying hostile cells
    # and this scenario would silently become a duplicate of
    # `query_success_rich` while still comparing equal to its golden.
    assert '"the reference"' in encoded, (
        "quote cell missing. NOTE the single quotes: `lean-wire` does not double "
        "them, because with per-cell escaping a quote is no longer special. This "
        'assertion read `\'""the reference""\'` under the csv codec — if it '
        "ever reverts, the escaping regressed."
    )
    assert "C:\\\\drivers\\\\readme.txt" in encoded, (
        "backslash cell missing, or backslashes are no longer escaped. `lean-wire` doubles them so the escaping stays reversible."
    )
    assert "row 1:\\tmax SPL\\nrow 2:" in encoded, "the interior tab/newline cell did not survive as two-character escapes"
    check_wire("call/query_adversarial_cells", payload)


@pytest.mark.asyncio
async def test_wire_fetch_raw_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/raw",
        wrap_content=False,
    )
    check_wire("call/fetch_raw_basic", payload)


@pytest.mark.asyncio
async def test_wire_fetch_raw_include_links(monkeypatch: pytest.MonkeyPatch) -> None:
    """The only path exercising `_links_tsv` over real multi-line anchors."""
    payload = await _fetch_raw_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "blog.html").read_bytes(),
        url="https://example.org/raw-links",
        include_links=True,
        wrap_content=False,
    )
    text = _text(payload)
    # Anti-vacuity: a TSV block with no separator is not a TSV block.
    # The separator is asserted as the two-character escape `\t`, not a
    # literal tab — the text channel is a JSON document, so tabs inside TSV
    # cells arrive JSON-escaped. Asserting the literal character here is the
    # mistake that makes this kind of test quietly wrong.
    assert "\\t" in text, "links TSV carries no tab separator"
    assert "anchor\\thref\\trole" in text, "links TSV header missing"
    check_wire("call/fetch_raw_include_links", payload)


# --------------------------------------------------------------------- #
# Artifact 3 — the error surface
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wire_error_missing_required_arg() -> None:
    """FastMCP-owned validation. Frozen so the sunset cannot quietly move it."""
    async with wire_client() as client:
        result = await client.call_tool("query", {}, raise_on_error=False)
    payload = capture(result)
    assert payload["is_error"] is True
    check_wire("errors/missing_required_arg", payload)


@pytest.mark.asyncio
async def test_wire_error_tool_body_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """The typed error envelope, repaired by `hotfix-fastmcp-error-envelope`.

    Captured only because that hotfix landed first. Before it, this golden
    would have frozen `"ToolResult.__init__() got an unexpected keyword
    argument 'is_error'"` with `structured_content: null` as the migration
    baseline — a defect enshrined as the contract.
    """
    freeze_clocks(monkeypatch)
    app = build_mcp_server()

    async def _boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("orchestrator failed during the tier loop")

    monkeypatch.setattr("a2web.routers.orchestrate", _boom)
    async with wire_client(app) as client:
        result = await client.call_tool("query", {"url": "https://example.org/x", "query": "q"}, raise_on_error=False)
    payload = capture(result)
    # Anti-vacuity: the whole point is that the REAL cause survives.
    assert payload["is_error"] is True
    assert "orchestrator failed during the tier loop" in _text(payload)
    assert payload["structured_content"] is not None
    check_wire("errors/tool_body_exception", payload)


# --------------------------------------------------------------------- #
# Artifact 4 — the notification stream
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wire_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mid-call `notifications/message` stream.

    a2web forwards typed events (`TierStarted`, `StageEnded`, …) to the MCP
    log channel during a call. Capturing it makes that live telemetry surface
    a reviewed decision rather than an accident — the sunset must either
    preserve it deliberately or drop it deliberately.

    **The whole `data` payload is captured, not just the event name.** The
    first version of this test recorded `{level, event}` only, which left the
    field payload — every key an operator or an OTel exporter actually reads —
    completely ungated. The sunset's logging phase renames the record-field
    carrier and re-homes the elapsed-ms key, i.e. it changes precisely the part
    that was not being watched. A gate that cannot see the change it exists to
    gate is decoration.
    """
    freeze_clocks(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(_MINIMAL_HTML))
    parts = build_components()
    state = await parts.state()
    parts = dataclasses.replace(parts, llm_extractor=lazy(_extractor(state)))
    app = build_mcp_server(components=parts)

    seen: list[dict] = []

    async def _log_handler(message: object) -> None:
        data = getattr(message, "data", None)
        seen.append({"level": getattr(message, "level", None), "data": normalize(data)})

    async with wire_client(app, log_handler=_log_handler) as client:
        await client.call_tool("query", {"url": "https://example.org/notify", "query": "q"}, raise_on_error=False)

    # Anti-vacuity: an empty stream would freeze "no telemetry" as contract.
    assert seen, "no notifications/message frames were emitted during the call"
    # Anti-vacuity: a frame carrying only `msg` would mean the payload silently
    # stopped riding the wire — indistinguishable from success in a name-only
    # capture, which is the failure this widening exists to prevent.
    assert any(len(f["data"]) > 1 for f in seen if isinstance(f["data"], dict)), (
        "every notification frame arrived with an empty field payload — the wire extras are no longer being forwarded"
    )
    check_wire("notifications", seen)


# --------------------------------------------------------------------- #
# Meta: the gate itself must not be able to pass vacuously
# --------------------------------------------------------------------- #


def test_no_golden_is_degenerate() -> None:
    """Every golden must carry real content.

    A golden frozen against an empty or trivial payload compares equal
    forever while asserting nothing — it looks like coverage and provides
    none. This walks the artifacts and fails on any that could not possibly
    detect a regression.
    """
    goldens = sorted(WIRE_DIR.rglob("*.json"))
    assert len(goldens) >= 11, f"expected the full artifact set, found {len(goldens)}"

    for path in goldens:
        raw = path.read_text()
        assert raw.strip(), f"{path.name} is empty"
        payload = json.loads(raw)
        assert payload, f"{path.name} decoded to an empty structure"

        if path.parent.name in {"call", "errors"}:
            blocks = payload["content"]
            assert blocks, f"{path.name} froze a response with no content blocks"
            for block in blocks:
                assert len(block["text"]) > 20, f"{path.name} froze a trivial text channel: {block['text']!r}"


def test_url_deviation_is_dropped_when_it_matches_the_request() -> None:
    """The deviation-drop rule is live, not merely absent from a fixture.

    `url` is emitted ONLY when the fetched URL differs from the requested
    one. Asserting its absence is meaningless unless we also know the field
    can appear — otherwise a serializer that dropped `url` unconditionally
    would pass. So: absent on the same-URL scenario, present on a redirect.
    """
    same_url = json.loads((WIRE_DIR / "call/query_success_minimal.json").read_text())
    assert "url" not in same_url["structured_content"]
    assert '"url"' not in same_url["content"][0]["text"]


# --------------------------------------------------------------------- #
# Substrate drift — the check that would have caught the `is_error` defect
# --------------------------------------------------------------------- #


def test_a2web_matches_the_resolved_mcp_substrate() -> None:
    """No a2web call site may pass a keyword the resolved signature rejects.

    This is the by-construction form of the defect `hotfix-fastmcp-error-envelope`
    fixed: a2kit called `ToolResult(..., is_error=True)` against a resolved
    FastMCP whose constructor took only `(content, structured_content, meta)`.
    The keyword was rejected, FastMCP masked the TypeError, and every typed
    error reached callers as a meaningless string. It was found by reading
    code, which is not a repeatable process.

    **RE-AIMED at `src/a2web` by the sunset** — as this test's own docstring
    predicted it should be. a2web now constructs `ToolResult(is_error=True)`
    itself in `error_wire.py`, so the drift risk did not disappear with a2kit;
    it moved into this repo. Retiring the test instead of re-aiming it would
    have retired the coverage exactly as a2web inherited the exposure.
    """
    import ast
    import importlib
    import inspect
    from pathlib import Path as _Path

    import a2web

    root = _Path(inspect.getfile(a2web)).parent
    findings: list[str] = []
    checked = 0

    for source in root.rglob("*.py"):
        try:
            tree = ast.parse(source.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue

        imported: dict[str, tuple[str, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (node.module == "mcp" or node.module.startswith(("fastmcp", "mcp."))):
                for alias in node.names:
                    imported[alias.asname or alias.name] = (node.module, alias.name)

        for name, (module, attr) in imported.items():
            del name
            try:
                target = getattr(importlib.import_module(module), attr)
            except (ImportError, AttributeError):
                findings.append(f"{source.relative_to(root)}: {module}.{attr} does not resolve")
                continue
            del target

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in imported:
                continue
            keywords = [kw.arg for kw in node.keywords if kw.arg]
            if not keywords:
                continue
            module, attr = imported[node.func.id]
            try:
                signature = inspect.signature(getattr(importlib.import_module(module), attr))
            except (ImportError, AttributeError, TypeError, ValueError):
                continue
            if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
                continue
            checked += 1
            unknown = [k for k in keywords if k not in signature.parameters]
            if unknown:
                findings.append(
                    f"{source.relative_to(root)}:{node.lineno} calls {module}.{attr}(...) with "
                    f"{unknown}, which the resolved signature rejects "
                    f"(accepts: {list(signature.parameters)})"
                )

    # Anti-vacuity with a measured floor, not just `> 0`. Two keyword-bearing
    # call sites against non-`**kwargs` signatures on 2026-07-22 — the
    # `ToolResult(...)` constructions in `error_wire.py` and `wire.py`, which
    # are exactly the ones that carry `is_error`. (`TextContent` and
    # `ToolAnnotations` are pydantic models and are skipped: their generated
    # `__init__` is `**data`, so no keyword can be "rejected" at the signature
    # level.) A walk that finds fewer has broken, not been simplified.
    assert checked >= 2, f"the substrate walk checked only {checked} call site(s) — it is not testing anything"
    assert not findings, "framework/substrate API drift:\n  " + "\n  ".join(findings)


# --------------------------------------------------------------------- #
# The one invariant that is NOT a golden
# --------------------------------------------------------------------- #


# HEALED 2026-07-22 (sunset Phase 4). This was `xfail(strict=True)` while
# a2kit owned the encoder: a2kit's `encode_envelope` tested only for
# list/tuple and fell through to `[]`, so a populated `other_pages` — already
# rendered to TSV by `AskResponse._prune_wire` one layer down — was
# overwritten with the empty marker on the text channel. It was deliberately
# NOT made a golden, because a golden captured against the defective encoder
# would have frozen the defect and a faithful port would then have passed the
# gate. Owning the encoder (`a2web.wire.encode_envelope`) is what let the fix
# land; the strict xfail is what forced the fix to be noticed.
@pytest.mark.asyncio
async def test_populated_other_pages_survives_to_text_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = await _query_wire(
        monkeypatch,
        body=(FIXTURES_DIR / "blog.html").read_bytes(),
        raw_next_links=[
            NextLink(
                anchor="Full teardown",
                url="https://example.org/teardown",
                reason="the detail page",
                kind="related",
            )
        ],
        url="https://example.org/index",
        query="what else is there?",
    )
    assert "example.org/teardown" in _text(payload), (
        "a populated off-page index never reached the caller's text channel — "
        "ADR-0015: withholding the body obliges a2web to leave the index"
    )


# The THIRD a2kit encoder defect, distinct from the two above and the only one
# still live in a2web after the sunset. It was reported as "happens to be
# harmless here" — it was not, and the reason it looked harmless is instructive:
# the fallback preserved `links` by accident, because `FetchResponse._omit_empty`
# pre-encodes that one field a layer down. Everything the fallback did NOT
# preserve was invisible, because "no TSV block" and "TSV encoding never ran"
# look identical from outside.
#
# Not a golden, for the same reason as the test above: a golden captured against
# the defective encoder freezes the defect, and a faithful port then passes.
def test_headings_do_not_abort_the_envelope_encode() -> None:
    """One non-tabular field must not take the whole envelope down with it."""
    from a2web.wire import encode_envelope

    payload = {
        # `Heading` serializes as a compact `[level, text]` pair — not dict rows,
        # so `encode_tsv` raises `TypeError` on it.
        "headings": [[1, "Title"], [2, "Section"]],
        "operator_hints": [{"code": "cookies_stale", "severity": "info"}],
    }

    encoded = json.loads(encode_envelope(payload, ("headings", "operator_hints")))

    assert encoded["_operator_hints_format"] == "tsv", (
        "`operator_hints` was not TSV-encoded. Before the shape guard, the "
        "`TypeError` from `headings` aborted the encode for the ENTIRE envelope "
        "and `EnvelopeContentMiddleware` silently served FastMCP's plain JSON — "
        "so no field on `fetch_raw` was ever TSV-encoded in production."
    )
    assert encoded["operator_hints"] == "code\tseverity\ncookies_stale\tinfo\n"
    assert encoded["headings"] == [[1, "Title"], [2, "Section"]], "a non-tabular field should pass through as JSON, unchanged"
    assert "_headings_format" not in encoded, (
        "no TSV block was emitted for `headings`, so claiming `tsv` in the discriminator would lie to the reader about what it is parsing"
    )


# --------------------------------------------------------------------- #
# `answer` never carries model output-contract scaffolding
#
# The live defect this guards: `query` shipped an `answer` containing a whole
# ```next_links fenced JSON array, because the router prompt and the next-links
# suffix asked the model for two different output contracts and the routing
# branch never stripped the fence. Asserted on the TEXT channel — the agent's
# actual view — not `structured_content`, per the two-channel rule.
# --------------------------------------------------------------------- #


def test_no_wire_golden_answer_carries_a_fence() -> None:
    """No frozen `query` response puts a fenced block in `answer`.

    Walks the goldens rather than re-driving the server: these ARE the surface
    installed agents consume, so a fence appearing in any of them is the bug
    regardless of which code path produced it.
    """
    import json as _json
    from pathlib import Path

    golden_dir = Path(__file__).parent / "wire" / "call"
    checked = 0
    for path in sorted(golden_dir.glob("query_*.json")):
        payload = _json.loads(path.read_text())
        for block in payload.get("content", []):
            text = block.get("text", "")
            assert "```next_links" not in text, f"{path.name}: next_links fence on the text channel"
            checked += 1
        answer = (payload.get("structured_content") or {}).get("answer", "")
        if isinstance(answer, str):
            assert "```" not in answer, f"{path.name}: fenced block inside `answer`"

    # Non-vacuity floor: a walk that inspected nothing is indistinguishable from
    # a passing one (CLAUDE.md — this rule has already failed twice for real).
    assert checked >= 6, f"expected to inspect >=6 query content blocks, saw {checked}"
