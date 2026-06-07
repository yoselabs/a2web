## Why

The extraction ladder picks **one** structured payload, renders it, and
**replaces** `content_md` only when the render is longer — a value-blind
length proxy (`fetcher.py:1102`, `:1133`). This is the same class ADR-0002
bans (volume-as-fidelity) and ADR-0005 names the menu: the server-side
extractor (Haiku) only ever sees a *single* source, so a short-but-correct
structured payload silently loses to longer prose — or, worse, a longer
*wrong* source clobbers the answer-bearing one.

The captured regression `regression/recipe-nutrition-volume-gate` (frozen
2026-06-07, live BBC Good Food banana-loaf) makes the class concrete and
deterministic: the record detector false-fires on the page's sidebar
widgets, the volume gate lets that 2,055-char junk **replace** the real
recipe, and Haiku — fed only the sidebar — confidently answers "the page
has no nutrition, it's a listing." The answer (`268 kcal`, `34g sugar`)
sits in the page bytes in three places (DOM nutrition list, 3× `Recipe`
JSON-LD, 3× `NutritionInformation` JSON-LD) and is discarded by the gate.
`fc.headings` still proves the real recipe was parsed — the loss is purely
the single-source replacement.

Two defects compound: a record-detector precision miss, and the gate's
single-source replacement. The menu cures the second and makes the system
**robust** to the first — when Haiku is fed every coarsely-selected source,
the answer-bearing one survives and the LLM picks it, regardless of which
source a detector mis-grabbed.

## What Changes

- **Feed the extractor the menu, not one source.** Collect prose +
  embedded-JSON/JSON-LD + structural records into an immutable
  `fc.content_candidates: list[ContentCandidate]` (ADR-0005). Haiku
  receives all coarsely-selected candidates; it chooses. This is the fix —
  internal to the extraction input, **non-breaking** on the wire.
- **Retire the volume gate** (`len(synthetic) > original_len` in
  `_escalate_via_json` / `_escalate_via_records`), but **document its
  rationale first** (it was a quality-aware guard: threaded records always
  replace, flat/JSON replace only when longer, to avoid clobbering good
  prose). The menu replaces "pick the longest" with "feed all, LLM picks."
- **Wire envelope (Ask-First, signed off 2026-06-07):** the default return
  is **unchanged** — `content_md` keeps surfacing a single readable
  candidate (chosen by an explicit *quality* rule, not length). Add a
  **debug-only** `content_candidates[]` to the return (gated like the
  existing `debug` regrouping in `_prune_wire`) so operators and the
  instrument can inspect exactly what Haiku saw. Parsers see zero change on
  the default path.
- **Cost discipline (ADR-0005 forces):** preserve `EXTRACT_*` cache-prefix
  byte-equality (per-page candidate variation must not leak into the cache
  prefix); respect `max_content_chars` with a *priority* trim (don't
  truncate prose and structured equally-blindly); deterministic dedup is
  coarse subset-suppression only — semantic dedup stays the LLM's job.

## Capabilities

### Modified Capabilities
- `extraction`: the extractor input becomes a multi-source menu
  (`fc.content_candidates`) instead of a single volume-gated `content_md`;
  the length-proxy replace rule is retired and replaced by a quality-based
  primary pick + LLM-side selection.
- `fetch-response`: a new **debug-only** `content_candidates[]` field on the
  return surfaces the menu under `debug=True`; the default wire is unchanged.

## Impact

- Code: `fetcher.py` (`_run_extraction_escalation`, `_escalate_via_json`,
  `_escalate_via_records`, `_phase_extract`, `FetchContext`),
  `models.py` (`FetchResponse` debug regrouping in `_prune_wire`,
  `ContentCandidate` surfacing), the extractor prompt assembly in
  `packages/llm_extract/`.
- Wire: default `ask` / `fetch_raw` responses unchanged; `debug=True` gains
  `content_candidates[]`.
- Cost: prompt-cache prefix discipline must be preserved (measured); token
  budget trimmed by priority.
- Instrument: `regression/recipe-nutrition-volume-gate` is the before/after
  gate; the deterministic axis asserts Haiku's input (the menu) contains the
  answer, independent of the wire.
- ADR-0005 moves from *Accepted (provisional)* to *Accepted* on landing +
  substrate validation.
