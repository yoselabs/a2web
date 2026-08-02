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

3. `encode_tsv` raises on rows it cannot tabulate, and a2kit swallowed the
   raise — so one unencodable field (`headings`, a list of `[level, text]`
   pairs) voided the encode for the WHOLE envelope and nothing on `fetch_raw`
   was ever TSV-encoded.

All three are guarded below, and each is pinned by a test that was
`xfail(strict=True)` (1 and 2) or newly written (3) while a2kit owned the code.

**The codec itself is the shelf's `lean-wire`, not a2web's** (adopted
2026-07-22, retiring the vendored `_tsv_compat.py`). The split is deliberate
and worth keeping straight: `lean-wire` owns *how a row becomes a line*,
a2web owns *which fields become tables and what happens when one cannot*.
All three guards above live on a2web's side of that line, which is why
adopting the shelf codec could not reintroduce any of them — and why guard 3
is still required, since `lean-wire` raises the same `TypeError` a2kit did.
That is the correct contract for a codec; deciding what to do about it is the
caller's job.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp.server.middleware import Middleware
from lean_wire import PruneEmpty, encode_tsv
from mcp.types import TextContent
from pydantic import BaseModel

_log = logging.getLogger(__name__)
_ENCODE_FAILURES: set[str] = set()

__all__ = [
    "EnvelopeContentMiddleware",
    "PruneEmpty",
    "encode_envelope",
    "encode_rows",
    "tsv_fields_for",
]

#: Per-tool TSV field order. Transcribed from a2kit's `build_encoding_plan`
#: output at v0.49.2 — see the module docstring for why this is a literal.
#: **`headings` is deliberately NOT here (decided 2026-08-01).**
#:
#: It was in both tuples, transcribed from a2kit's 2026-07-22 inference, and it
#: never rendered as TSV in either. It cannot: `Heading` serializes to a compact
#: `[level, text]` PAIR, so the dump is a list of LISTS, and `encode_tsv` raises
#: `TypeError` on a row that is neither a model nor a dict. The shape guard
#: caught it every time and the field stayed a JSON array.
#:
#: That is the whole reason the shape guard exists — under a2kit the raise was
#: swallowed, so this ONE unencodable field voided the encode for the entire
#: envelope and `fetch_raw` shipped no `_<field>_format` discriminator at all.
#: Removing `headings` from the table changes NO bytes (verified: no
#: `_headings_format` was ever emitted); it stops the declaration claiming
#: something the encoder structurally cannot do. The guard stays, as the
#: backstop for the next unencodable field.
_TSV_FIELDS: dict[str, tuple[str, ...]] = {
    "query": ("operator_hints", "other_pages", "refinement_axes", "options"),
    "fetch_raw": ("links", "operator_hints", "next_links", "content_candidates"),
}


def tsv_fields_for(tool_name: str) -> tuple[str, ...]:
    """TSV field order for `tool_name`; empty tuple means "plain JSON".

    `cookies_refresh` is deliberately absent — a2kit inferred a `json` plan for
    `CookiesRefreshResult` (it has no list-of-model fields), so it renders as
    compact JSON with no TSV blocks.
    """
    return _TSV_FIELDS.get(tool_name, ())


def _encode_json(value: Any) -> str:
    """Compact JSON in one pass. Separators are wire contract, not style."""
    return json.dumps(value, separators=(",", ":"), default=str, ensure_ascii=False)


def encode_rows(rows: list[Any]) -> str:
    """Render model or dict `rows` as a TSV block with union-derived columns.

    The ONE column rule, shared by both TSV producers: `encode_envelope`, which
    encodes already-dumped payload fields, and the `models.py` serializers,
    which encode model instances before the parent dump. They diverged once —
    three hand-rolled conditional-column helpers in `models.py`, each
    approximating this rule differently, while `encode_envelope` had no
    conditional at all and silently dropped the elided fields.

    **The rule itself now lives in `lean_wire.derive_columns`** (adopted with
    lean-wire v0.2.0, 2026-08-01), which is where it belongs: `encode_tsv` is
    the only party that sees every row at once, and asking each caller for the
    header produced the same bug in all THREE callers that answered — a2web's
    copy here plus `page_tsv.render` and `page_tsv.page`, each reading `rows[0]`
    as the schema. Omitting `columns=` takes the union.

    Rows are heterogeneous BY CONSTRUCTION: model serializers elide fields at
    their default (`OperatorHint._omit_default_severity` drops an `info`
    severity, `PruneEmpty` drops empties), so which keys a row carries is a
    property of its data. Reading only `rows[0]` therefore DELETED data — an
    `info` hint followed by a `critical` one produced a table with no
    `severity` column and the ADR-0009 klaxon reached the agent unmarked.

    This is not the inference `_TSV_FIELDS` exists to forbid. *Which fields
    become tables* is a contract and stays literal; *which columns a table has*
    is a property of the rows.
    """
    dumped = [row.model_dump(mode="json") if isinstance(row, BaseModel) else row for row in rows]
    return encode_tsv(dumped)


def _is_tsv_shaped(rows: list[Any]) -> bool:
    """Can `rows` become a TSV table at all? Only dict-shaped rows can.

    `encode_tsv` accepts `BaseModel` or dict rows and raises `TypeError` on
    anything else. Not every field in `_TSV_FIELDS` produces those: `Heading`
    serializes as a compact `[level, text]` pair (deliberately — it is already
    lean), so `headings` arrives as a list of *lists*.
    """
    return bool(rows) and all(isinstance(row, dict) for row in rows)


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
        if not _is_tsv_shaped(rows):
            # SHAPE GUARD — the third a2kit encoder defect, and the only one of
            # the three that was still live in a2web. `headings` renders as
            # `[[1, "Title"], [2, "Section"]]`, which `encode_tsv` rejects with
            # `TypeError: expected BaseModel or dict rows, got list`. a2kit
            # swallowed that in a bare `except` and a2web inherited the same
            # rescue in `EnvelopeContentMiddleware`, so the failure was invisible
            # — but it was NOT harmless, which is how it survived review as a
            # "happens to be fine" finding.
            #
            # One unencodable field aborted the encode for the WHOLE envelope,
            # and the rescue returned FastMCP's plain JSON. Since `headings` is
            # on essentially every `fetch_raw`, that means `fetch_raw` has never
            # shipped a `_<field>_format` discriminator, and `operator_hints` /
            # `content_candidates` have never been TSV-encoded at all. `links`
            # looked fine only because `FetchResponse._omit_empty` pre-encodes it
            # one layer down, so the fallback preserved it by accident.
            #
            # Leaving a non-tabular field as JSON is the honest outcome: a
            # `[level, text]` pair is already lean, and TSV would need invented
            # positional column names. The point is that it no longer takes the
            # rest of the envelope down with it. Pinned by
            # `test_headings_do_not_abort_the_envelope_encode`.
            continue
        envelope[name] = encode_tsv(rows)
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
