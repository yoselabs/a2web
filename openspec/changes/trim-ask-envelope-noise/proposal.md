## Why

The operator's standing "the `query` envelope is too noisy" complaint is about the
`structuredContent` shape itself — a2web's own `@model_serializer` output, the
channel Claude actually reads — not the encoder. It is the surviving half of
`envelope-wire-hygiene` (archived 2026-07-26); that change's other half (the a2kit
`encode_envelope` empty-leak + populated-destruction defect) is **gone with a2kit**
— a2web owns the encoder in `wire.py` and both faces are fixed and pinned there.
What was deferred behind "revisit after the leak fix lands" (its §4) is now
unblocked and is the only live work.

The trim is a **breaking change for parsers** (the ADR "Ask First" list names the
response envelope shape), so the field-tier decision is a human call, not an
automatic prune — this change exists to make that decision deliberately and prove
it against the benchmark rather than by eye.

## What Changes

- **Re-assess `AskResponse` field tiers** against the current envelope and decide,
  per candidate, whether it earns wire presence on the default (`debug=False`)
  path: `confidence`, `tier`, the failure-story fields, any residual `meta`. The
  ADR-0015 index (`also_here` / `other_pages`) and the always-present `answer`
  are **out of scope — never trimmed**.
- **Apply the confirmed trim** in `models.py` (`AskResponse` field tiers +
  `_prune_wire`), preserving the wire-only serializer contract (attribute access
  unaffected, internal callers keep reading flat fields).
- **Update the four-axis output-benchmark envelope-shape assertions**
  (`tests/capabilities/output_benchmark/`) to the new shape.

## Impact

- Breaking for wire parsers on the `query` tool — the reason it is its own gated
  change, not a silent tidy.
- Validation is the **clarity axis of `make bench`** (live-network, spends LLM
  quota, run under the ADR-0016 subscription provider — never metered) confirming
  the axis moved up or held while nothing else regressed. Not in `make check`.
- Non-goal: touching `FetchResponse` (`fetch_raw` stays page-shaped) or the
  encoder (already correct in `wire.py`).
