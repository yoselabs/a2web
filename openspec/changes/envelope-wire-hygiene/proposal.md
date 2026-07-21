## Why

The MCP wire envelope carries avoidable noise that the CLI envelope does not.
The noise splits by who controls it:

**a2kit-controlled (the acute leak).** `encode_envelope`
(`a2kit/packages/formatter/render.py:94-98`) iterates a *static* `tsv_fields`
list and, for each, does `envelope.get(name)` → `None` (a2web's `_prune_wire`
already dropped the empty field) → coerces to `[]` → `encode_tsv([])` == `"\n"` →
**re-inserts the key** plus a `_<name>_format = "tsv"` sidecar. So a healthy
`query` response that should omit its empty conditionals instead carries
`other_pages:"\n"`, `_other_pages_format:"tsv"`, `headings:"\n"`,
`_headings_format:"tsv"`, `refinement_axes:"\n"`, `_refinement_axes_format:"tsv"`,
`options:"\n"`, `_options_format:"tsv"` — eight junk keys, undoing the omit-empty
pruning a2web already performed. This is MCP-only: the CLI's `json` path never
reaches `encode_envelope`, which is exactly why it went unseen — and why a2web's
own tests miss it (`client.call_wire` routes through `format_response`, whose
`_plan_for_hint` can only yield `tsv`/`page-tsv`/`json`, never the `envelope`
plan, so `encode_envelope` is executed by NO a2web test).

a2web has no seam to post-process this — the encoding plan is inferred by a2kit
at router-registration time from the return type; a2web never touches the
formatter. So the fix is upstream (a one-line presence guard: skip a `tsv_field`
absent from the pruned envelope), delivered as an a2kit feedback round, plus the
adoption once a2kit ships it.

**a2web-controlled (the schema trim).** Beyond the leak, some always-present or
low-value fields ride the wire on every call. Which of these are genuinely noise
to an AI caller is a schema decision (breaking for parsers — Ask First), captured
here as open questions rather than assumed.

## What Changes

- **a2kit feedback (blocking the leak fix).** File the `encode_envelope`
  empty-field defect in `docs/history/A2KIT_FEEDBACK_v0.*.md` with: the exact bug,
  the one-line fix, AND the test-gap finding — `call_wire` is not
  fidelity-equivalent to the MCP dispatch encoder, so an entire production
  encoding path (`encode_envelope`) is untested from a2web. The `"\n"` leak is the
  first bug anyone noticed in that untested path; the gap is the real report.

- **Adopt the a2kit fix** once shipped; add an a2web wire-contract test that
  exercises the real MCP dispatch encoder (not `call_wire`) and asserts empty
  conditionals are ABSENT — closing the test gap on a2web's side so the next
  encoder regression is caught here.

- **Schema trim (DEFERRED — decide after the leak fix lands).** Reduce always-on
  wire fields that carry little signal for an AI caller. The exact set is the
  human's call because it is breaking for parsers, and is intentionally deferred:
  the empty-TSV leak was the dominant noise source, so the envelope should be
  re-felt once it is gone before deciding whether any field trim is still worth a
  breaking change. Candidates are enumerated in the open questions.

**Decision locked (2026-07-21):** the a2kit-side work is **feedback-only** — no
request for a post-serialize hook, no new a2web↔a2kit coupling. a2web stays a
pure consumer and adopts the fix when a2kit ships it.

## Open questions (need confirmation before the trim lands)

Grounded in the actual pasted MCP envelopes. `also_here` / `other_pages` are the
ADR-0015 cheap index and are NOT on the table — withholding them violates the
never-withhold-the-index invariant. Candidates:

- The `_<name>_format: "tsv"` sidecars even when the field is PRESENT — an AI
  caller can see the value is TSV; does any consumer parse the discriminator?
  (a2kit-controlled; bundle into the same feedback if we want them gone.)
- `confidence` — always present (`high`/`medium`/`low`). Signal or noise?
- `meta` (curated to `og.description`) on a successful `query` — it often
  restates what the answer already covers.
- `tier` — already dropped when `raw`; keep the deviation-only rule or drop
  entirely on success?
- On a FAILED envelope, the trio `narrative` + `diagnostics_summary` + per-hint
  `message`/`fix` overlap heavily. Collapse to one authoritative failure story?

## Impact

- a2kit feedback: `docs/history/A2KIT_FEEDBACK_v0.*.md` (no a2web code until the
  fix ships).
- Schema trim: `src/a2web/models.py` (`AskResponse` field tiers + `_prune_wire`),
  and the four-axis output-benchmark tests that assert envelope shape.
- **Breaking for parsers** — Ask First. The trim set is confirmed before landing.
- Wire-contract test added regardless, to cover the previously-untested MCP
  dispatch encoder.
