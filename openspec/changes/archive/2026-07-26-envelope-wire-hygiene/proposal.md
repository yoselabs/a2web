## Why

The MCP wire envelope carries avoidable noise that the CLI envelope does not.
The noise splits by who controls it:

**a2kit-controlled (the `encode_envelope` defect — verified, two faces).**
`encode_envelope` (`a2kit/packages/formatter/render.py:94-98`) iterates a
*static* `tsv_fields` list and, for each, does `envelope.get(name)` then a
type-blind `list(x) if isinstance(x,(list,tuple)) else []` coercion. This has
two faces, both verified on `v0.49.2` via `render_plain(structured, plan)` — the
exact call `FormatRoutingMiddleware` makes at `format_routing.py:73`:

- *Empty leak.* A pruned (absent) field → `None` → `[]` → `encode_tsv([])` ==
  `"\n"` → the key is **re-inserted** plus a `_<name>_format="tsv"` sidecar.
  Ten junk keys undo a2web's omit-empty pruning.
- *Populated destruction (sharper).* a2web's `@model_serializer` pre-encodes
  `other_pages`/`headings`/`options`/`refinement_axes` into TSV **strings** (so
  the CLI/JSON path gets TSV too). `encode_envelope` sees a `str`, `isinstance`
  is False → `[]` → `"\n"` — a **populated** page pointer is silently
  **destroyed** on the `content[]` channel, not just an empty one leaked.

**Blast radius (keeps this honest).** Both faces bite ONLY hosts that read
`content[].text` and ignore `structuredContent`. a2web ships dual-emit
(`structured_output=False`); on hosts that forward `structuredContent` to the
model (Anthropic API, Claude Code/Desktop/.ai — a2web's primary deployment) the
model reads the model's own correct serialization and never sees the damage.
There it is **latent**. So this is a correctness/portability defect on the
spec-guaranteed channel, NOT the noise the operator currently feels (see below).

a2web has no seam to post-process this — the encoding plan is inferred by a2kit
at router-registration time from the return type; a2web never touches the
formatter. The fix is upstream: a **str-aware guard** (skip a `tsv_field` that is
absent OR already a `str`), delivered as an a2kit feedback round, plus adoption
once a2kit ships it. It went unseen because `client.call_wire` re-derives from
`structured_content` via `format_response` (json path), never executing
`encode_envelope` — no a2web test exercised the real dispatch encoder.

**a2web-controlled (the schema trim — the ACTUALLY-felt noise).** The operator's
"too noisy" complaint is about the `structuredContent` shape itself — a2web's own
`@model_serializer` output, the channel Claude actually reads — NOT the
`encode_envelope` leak (latent on that host). The original deferral rationale
("re-feel the envelope once the leak is gone") is therefore **invalidated**: the
leak is not on the read channel, so the schema breadth is the primary noise lever,
not a downstream afterthought. Still breaking for parsers (Ask First); the exact
trim set stays the human's call.

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

- **Schema trim (the actual felt-noise lever — still Ask First).** Reduce
  always-on `structuredContent` fields that carry little signal for an AI caller.
  This is the channel Claude reads, so it — not the latent `encode_envelope`
  leak — is what makes the output feel noisy. The exact set is the human's call
  because it is breaking for parsers. Candidates are enumerated in the open
  questions. (Recalibrated 2026-07-21: the earlier "defer until the leak fix
  lands" rationale is void — the leak is not on the read channel.)

**Decision locked (2026-07-21):** the a2kit-side work is **feedback-only** — no
request for a post-serialize hook, no new a2web↔a2kit coupling. a2web stays a
pure consumer and adopts the fix when a2kit ships it. The str-aware guard
supersedes the earlier presence-only guard (it must also fix populated-field
destruction, not just the empty leak).

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
