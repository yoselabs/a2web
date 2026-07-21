"""Wire-contract test over the REAL MCP dispatch encoder (envelope-wire-hygiene).

The other wire tests here use `client.call_wire`, which routes through
`format_response` → `_plan_for_hint` and can only ever yield the
`tsv`/`page-tsv`/`json` plans — NEVER the `envelope` plan the `query` tool
actually uses over MCP. So `encode_envelope` (invoked by the real
`FormatRoutingMiddleware` as `render_plain(structured, plan)` for
`plan.kind == "envelope"`) is exercised by no other a2web test.

These tests drive that exact call: `build_encoding_plan(AskResponse)` gives
the envelope plan the middleware caches per-tool, and `dump_model_for_wire`
produces the pruned `structured_content` FastMCP hands the middleware. The
assertion is the ADR-0015-adjacent contract: an empty conditional is ABSENT
from the wire, not present as an empty TSV `"\n"` — absence is the caller's
signal that the field has no content.

The omit-empty scenario is `xfail(strict=True)` because a2kit `v0.49.2`
leaks (see docs/history/A2KIT_FEEDBACK_v0.49-envelope-leak.md). When a2kit
ships the presence guard and a2web bumps the pin, this test XPASSes — which
`strict=True` turns into a hard failure, forcing the marker off. The tripwire
un-xfails itself.
"""

from __future__ import annotations

import json

import pytest
from a2kit.packages.formatter import build_encoding_plan, render_plain
from a2kit.packages.formatter.render import dump_model_for_wire

from a2web.models import AskResponse, OtherPage

# The five optional conditional fields that a2web's `_prune_wire` omits when
# empty. `operator_hints` rides along on failures; the other four are the
# ADR-0015 index + query-grammar conditionals.
_CONDITIONALS = ("operator_hints", "headings", "other_pages", "refinement_axes", "options")


def _encode_over_dispatch(response: AskResponse) -> dict:
    """Encode `response` exactly as the MCP dispatch middleware would.

    `FormatRoutingMiddleware.on_call_tool` calls `render_plain(structured, plan)`
    for `plan.kind == "envelope"` (format_routing.py); `structured` is the
    pruned dict FastMCP derives from the model. This mirrors both.
    """
    plan = build_encoding_plan(AskResponse)
    assert plan.kind == "envelope", "query returns an envelope-planned model"
    structured = dump_model_for_wire(response)
    return json.loads(render_plain(structured, plan))


@pytest.mark.xfail(
    reason="a2kit v0.49.2 encode_envelope re-inserts pruned tsv_fields as empty "
    "'\\n' + _*_format sidecars (round-17 feedback); un-xfail when the a2kit "
    "presence guard ships and the pin bumps.",
    strict=True,
)
def test_healthy_answer_omits_empty_conditionals_over_mcp() -> None:
    """A healthy `query` answer with no conditionals emits none of them — and
    no `_<name>_format` sidecar for them — over the real dispatch encoder."""
    response = AskResponse(
        url="https://en.wikipedia.org/wiki/Coil_noise",
        status="ok",
        tier="site_handler:wikipedia",
        confidence="high",
        answer="Coil whine is caused by magnetostriction in the windings.",
    )

    wire = _encode_over_dispatch(response)

    leaked = [name for name in _CONDITIONALS if name in wire]
    sidecars = [k for k in wire if k.startswith("_") and k.endswith("_format")]
    assert not leaked, f"empty conditionals must be absent from the wire, leaked: {leaked}"
    assert not sidecars, f"no _*_format sidecars for pruned fields, found: {sidecars}"


@pytest.mark.xfail(
    reason="a2kit v0.49.2 encode_envelope re-encodes a2web's ALREADY-TSV-encoded "
    "string field as an empty list -> '\\n', DESTROYING populated conditionals on "
    "the content[] channel (round-17 feedback). Latent for structuredContent-"
    "forwarding hosts; un-xfail when the str-aware a2kit guard ships.",
    strict=True,
)
def test_populated_conditional_survives_over_mcp() -> None:
    """A populated `other_pages` DOES render as TSV — only the empty case is
    omitted, never a populated one. On the real dispatch encoder today it is
    instead DESTROYED (a2web pre-encodes it to a TSV string; a2kit re-encodes
    the string as an empty list), which this test documents until the fix."""
    response = AskResponse(
        url="https://example.org/docs",
        status="ok",
        tier="raw",
        confidence="high",
        answer="The docs index links to the download and changelog pages.",
        other_pages=[
            OtherPage(url="https://example.org/download", reason="Download page", kind="drilldown"),
        ],
    )

    wire = _encode_over_dispatch(response)

    assert "other_pages" in wire, "a populated conditional must survive to the wire"
    assert wire["other_pages"] != "\n", "a populated conditional is real TSV, not the empty marker"
    assert "example.org/download" in wire["other_pages"]
