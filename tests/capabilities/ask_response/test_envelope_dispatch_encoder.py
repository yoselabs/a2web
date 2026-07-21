"""Wire-contract tests over the REAL envelope encoder (envelope-wire-hygiene).

Both scenarios were `xfail(strict=True)` against a2kit `v0.49.2` — see
`docs/history/A2KIT_FEEDBACK_v0.49-envelope-leak.md`, round 17, whose status
line read *"OPEN — one-line fix requested; no a2web workaround exists"*
because a2web had no formatter seam: the encoding plan was inferred at
registration time from the return type and a2web never touched the formatter.

The sunset gave a2web the seam. `a2web.wire.encode_envelope` is now the
encoder, both defects are fixed there, and the markers are off:

1. **Empty conditionals stay pruned.** a2kit looped the static field tuple and
   re-inserted every absent key as `"\n"` plus a `_<name>_format` sidecar,
   undoing `_prune_wire` one level up — ten dead keys on every healthy answer.
2. **Populated conditionals survive.** An already-TSV *string* field failed
   a2kit's `isinstance(rows, (list, tuple))` test and was overwritten with the
   empty marker, so a real off-page index reached the caller as "nothing here"
   (ADR-0015).

`strict=True` is what made this land: the moment the constraint lifted, the
XPASS became a hard failure and the fix could not be quietly skipped.
"""

from __future__ import annotations

import json

from a2web.models import AskResponse, OtherPage
from a2web.wire import encode_envelope, tsv_fields_for

# The five optional conditional fields that a2web's `_prune_wire` omits when
# empty. `operator_hints` rides along on failures; the other four are the
# ADR-0015 index + query-grammar conditionals.
_CONDITIONALS = ("operator_hints", "headings", "other_pages", "refinement_axes", "options")


def _encode_over_dispatch(response: AskResponse) -> dict:
    """Encode `response` exactly as `EnvelopeContentMiddleware` would.

    The middleware sees the pruned dict FastMCP derives from the model, then
    calls `encode_envelope(structured, tsv_fields_for(tool))`. This mirrors
    both halves.
    """
    fields = tsv_fields_for("query")
    assert fields, "query renders as an envelope with TSV blocks"
    structured = response.model_dump(mode="json")
    return json.loads(encode_envelope(structured, fields))


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


def test_populated_conditional_survives_over_mcp() -> None:
    """A populated `other_pages` DOES render as TSV — only the empty case is
    omitted, never a populated one."""
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
