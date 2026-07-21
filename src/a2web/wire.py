"""The MCP wire layer a2web owns: envelope encoding + the typed error envelope.

a2kit rendered these through `FormatRoutingMiddleware` + a per-tool
`EncodingPlan` *inferred* from the return model's field types. Inference is the
wrong tool here for the same reason D1 rejected the implicit wire/injected
partition: a2web has exactly two response models, and which of their fields
render as TSV is a **contract**, not something to re-derive at import time. So
`_TSV_FIELDS` states it literally. A field added to `AskResponse` cannot
silently change the wire shape; changing the wire now requires editing the
table, which is exactly the edit a reviewer should see.

The tuples below are the values a2kit's inference produced on 2026-07-22,
transcribed. They are pinned by the wire goldens.

**Two channels, non-overlapping.**

- `structured_content` is FastMCP's own `model_dump(mode="json")` of the
  returned model, so `_prune_wire` drops the empty fields. Machine consumers
  read this.
- `content[0].text` is re-derived here: the same dump, with each *present* TSV
  field rendered as a TSV block plus a `_<field>_format` discriminator. The LLM
  reads this.

**Absence is the signal — the encoder never resurrects a pruned field.** This
is the fix for the two defects a2web filed against a2kit as round 17
(`docs/history/A2KIT_FEEDBACK_v0.49-envelope-leak.md`), where the note reads
"no a2web workaround exists — this must be fixed upstream." Owning the encoder
is the workaround.

1. a2kit looped the *static* field tuple and re-inserted every pruned key as
   the bare `"\\n"` marker plus a sidecar, silently undoing the model's
   omit-empty discipline one level up. Five conditionals became ten dead keys
   on every healthy answer.
2. When a field arrived as an already-encoded TSV *string* (which
   `AskResponse._prune_wire` produces), the `isinstance(rows, (list, tuple))`
   test fell through to `[]` and overwrote real content with the empty marker.

Both are guarded below, and both are pinned by tests that were
`xfail(strict=True)` while a2kit owned the code.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp.server.middleware import Middleware
from mcp.types import TextContent
from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer

from ._tsv_compat import encode_tsv

_log = logging.getLogger(__name__)
_ENCODE_FAILURES: set[str] = set()

__all__ = [
    "EnvelopeContentMiddleware",
    "PruneEmpty",
    "encode_envelope",
    "prune_dict",
    "tsv_fields_for",
]

#: Per-tool TSV field order. Transcribed from a2kit's `build_encoding_plan`
#: output at v0.49.2 — see the module docstring for why this is a literal.
_TSV_FIELDS: dict[str, tuple[str, ...]] = {
    "query": ("operator_hints", "headings", "other_pages", "refinement_axes", "options"),
    "fetch_raw": ("links", "headings", "operator_hints", "next_links", "content_candidates"),
}


def tsv_fields_for(tool_name: str) -> tuple[str, ...]:
    """TSV field order for `tool_name`; empty tuple means "plain JSON".

    `cookies_refresh` is deliberately absent — a2kit inferred a `json` plan for
    `CookiesRefreshResult` (it has no list-of-model fields), so it renders as
    compact JSON with no TSV blocks.
    """
    return _TSV_FIELDS.get(tool_name, ())


def _is_empty(value: Any) -> bool:
    """Empty per the wire contract: `None` / `""` / `[]` / `{}`.

    `0`, `False` and empty `frozenset` are NOT empty — they carry information.
    """
    if value is None:
        return True
    return isinstance(value, (str, list, dict)) and len(value) == 0


def prune_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values from the top level. Non-recursive by design."""
    return {k: v for k, v in payload.items() if not _is_empty(v)}


class PruneEmpty(BaseModel):
    """Base for wire-facing models that drop empty fields when dumped.

    Cascades naturally: pydantic uses each model's own serializer when
    serializing a parent's nested field, so a `PruneEmpty` nested inside a
    non-pruning parent is still pruned. A subclass defining its own
    `@model_serializer` overrides this one and owns its pruning — which is
    exactly what `AskResponse` / `FetchResponse` do via `_prune_wire`.

    The JSON schema is unaffected; only the payload is.
    """

    @model_serializer(mode="wrap")
    def _prune(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return prune_dict(handler(self))


def _encode_json(value: Any) -> str:
    """Compact JSON in one pass. Separators are wire contract, not style."""
    return json.dumps(value, separators=(",", ":"), default=str, ensure_ascii=False)


def _derive_columns(rows: list[Any]) -> list[str]:
    """TSV header columns from the first row's keys.

    Rows reaching here are already plain dicts — this runs after the model has
    been dumped, so declared-field order survives as dict insertion order.
    """
    if not rows:
        return []
    first = rows[0]
    return [str(k) for k in first] if isinstance(first, dict) else []


def encode_envelope(payload: dict[str, Any], tsv_fields: tuple[str, ...]) -> str:
    """Render the `content[0].text` channel from an already-dumped payload.

    Every field stays JSON except those in `tsv_fields`, each of which becomes
    one TSV string plus a `_<field>_format` discriminator. A field the model
    already pruned stays pruned — see the module docstring.
    """
    envelope = dict(payload)
    for name in tsv_fields:
        if name not in envelope:
            # PRESENCE GUARD. The field tuple is static; the payload is not.
            # A conditional the model omitted must stay omitted — resurrecting
            # it as `"\n"` + a sidecar turns "there is nothing here" into two
            # dead keys, and does it five times over on every healthy answer.
            continue
        value = envelope[name]
        if isinstance(value, str):
            # ALREADY TSV — leave it alone. `AskResponse._prune_wire` renders
            # `other_pages` (and friends) to TSV itself, so by the time the
            # payload reaches here the field can be a finished TSV string, not
            # a list of rows. a2kit's encoder tested only for list/tuple and
            # fell through to `[]`, silently replacing a populated off-page
            # index with the empty marker — a caller was told "a2web looked and
            # found nothing" when a2web had in fact found something and encoded
            # it one layer down. That is an ADR-0015 violation (withholding the
            # body obliges a2web to leave the index) and it is fixed here
            # rather than ported. Pinned by
            # `test_populated_other_pages_survives_to_text_channel`.
            envelope[f"_{name}_format"] = "tsv"
            continue
        rows = list(value) if isinstance(value, (list, tuple)) else []
        envelope[name] = encode_tsv(rows, columns=_derive_columns(rows))
        envelope[f"_{name}_format"] = "tsv"
    return _encode_json(envelope)


class EnvelopeContentMiddleware(Middleware):
    """Re-derive `content[0].text` from the final `structured_content`.

    Runs as a middleware rather than inside the tool so it sees the payload
    *after* FastMCP has dumped the model — the same plain dict the machine
    channel carries. Deriving both channels from one dump is what keeps them
    equivalent; a tool that built its own text would be free to drift.

    Failures degrade to FastMCP's own JSON rather than propagating: a broken
    encoder must not turn a successful fetch into a tool error. It logs once
    per tool so the degradation is visible instead of silent.
    """

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        result = await call_next(context)
        if getattr(result, "is_error", False):
            return result  # the error envelope owns both channels
        tool_name: str | None = getattr(context.message, "name", None)
        if tool_name is None:
            return result
        fields = tsv_fields_for(tool_name)
        structured = getattr(result, "structured_content", None)
        if not fields or not isinstance(structured, dict):
            return result
        try:
            text = encode_envelope(structured, fields)
        except Exception as exc:
            if tool_name not in _ENCODE_FAILURES:
                _ENCODE_FAILURES.add(tool_name)
                _log.warning("envelope encoding failed for %s: %s", tool_name, exc)
            return result
        return type(result)(
            content=[TextContent(type="text", text=text)],
            structured_content=structured,
            meta=getattr(result, "meta", None),
        )
