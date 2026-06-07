## Context

Extraction today is single-source. `_run_extraction_escalation`
(`fetcher.py:1060`) tries `json_synth`, then `record_synth`, keeps the first
whose render *beats the baseline by length* (`len(synthetic) > original_len`,
threaded records exempt), and assigns the winner to `fc.content_md`.
`_phase_extract_answer` then feeds that single `fc.content_md` string to
Haiku (`extractor.extract(content=...)`).

Two consequences, both shown by `regression/recipe-nutrition-volume-gate`:
the extractor only ever sees one source, and the source it sees is chosen by
a value-blind length proxy. On the BBC banana-loaf page the record detector
false-fires on the sidebar widgets, the 2,055-char junk render wins on
length, and Haiku — fed only the sidebar — answers "no nutrition, it's a
listing." The answer (`268 kcal`) lives in the prose, the `Recipe` JSON-LD,
and the `NutritionInformation` JSON-LD — all discarded.

`ContentCandidate` (`fetcher.py:148`, `source / content_md / next_links`)
already exists as the immutable per-rung bid; today it's collapsed to one
winner. The extractor's cache uses `hash(truncated content)` as part of its
key, and — critically — `cache_prefix_template = "{content}"`, so the
**content is the Anthropic prompt-cache prefix** (system + content cached;
`ask` in the variable tail, letting many questions reuse one cached read).

## Goals / Non-Goals

**Goals:**
- Feed Haiku **all** coarsely-selected sources (prose + json_synth +
  record_synth) as one deterministic menu, so it chooses the answer-bearing
  one. Retire the length-proxy replace rule.
- Keep `fc.content_candidates: list[ContentCandidate]` as the immutable
  internal menu; assign the wire `content_md` default by a *quality* rule,
  not length.
- Default wire shape **unchanged**; add a **debug-only**
  `content_candidates[]` to the return.
- Make the fix **deterministically provable** in `make check` by asserting
  the menu fed to Haiku contains the answer — independent of the wire.
- Preserve prompt-cache behavior and `max_content_chars` budget.

**Non-Goals:**
- Fixing the record-detector sidebar false-positive (real-surface precision;
  ADR-0007). The menu makes the system *robust* to it; it does not cure the
  detector.
- The `json-extract` typed schema.org boundary (ADR-0004 deferred half).
- Cross-source atomization / price-provenance / locale (program backlog).
- Changing any MCP tool signature.

## Decisions

### D1 — Menu assembly lives in the domain, passed as one `content` string
`_run_extraction_escalation` stops picking a winner. It collects every
non-empty rung into `fc.content_candidates` — always including a
`trafilatura` candidate for the prose baseline — in a **fixed source
order**: `trafilatura → json_synth → record_synth`. `_phase_extract_answer`
assembles these into a single menu string with **stable, content-free
section labels** (e.g. `## source: prose` / `## source: structured (json)` /
`## source: structured (records)`) and passes it as `extract(content=menu)`.

Rationale: keeps `packages/llm_extract` content-agnostic (no boundary
change, no new extractor params — the package independence invariant holds),
and reuses the existing content-hash cache key unchanged. Menu assembly is
domain glue → it belongs next to the other domain seams (`fetcher` /
`domain.py`).

### D2 — Cache discipline: deterministic, byte-stable assembly
Because `content` *is* the cache prefix, the menu for a given fetched page
must be **byte-identical across repeated asks**. Assembly therefore uses:
fixed source ordering, static labels, no timestamps / counts / object
identity / dict iteration order. Same page → same menu → same
`cache_prefix` → Anthropic prefix-cache and the local extraction cache both
still hit across questions. An architecture fitness test asserts assembly is
a pure function of the candidate list (ADR-0003 rule 3).

### D3 — Budget: priority trim, not blind truncation
When the menu exceeds `max_content_chars`, trim by **source priority**, not
uniformly: prose and `json_synth` are answer-dense and trimmed last;
`record_synth` (the long, often-noisy listing render) is trimmed first. The
existing `_truncate` cap still backstops the total. Priority order is a
static table (no per-page variation → D2 holds).

### D4 — Deterministic dedup is coarse subset-suppression only
If one candidate's normalized text is a strict substring of another's, drop
the subset before assembly (guards the 3–7× duplication when the same
ItemList appears in microdata + og + ld_json + records). Anything finer is
semantic dedup → the LLM's job (ADR-0003). Subset check is pure → D2 holds.

### D5 — Wire default: quality pick (prose-preferred), shape unchanged
`fc.content_md` (the default return) is set to a single candidate chosen by
quality, not length: **prose (trafilatura) when non-empty**, else the first
structured candidate, else the pre-rendered handler/browser payload (which
already bypasses this path via `fc.pre_rendered_payload`). The wire *shape*
is unchanged (still one `content_md` string, no new required field). The
*selection rule* changing from length→quality is inherent to retiring the
volume gate; as a side benefit it stops the sidebar junk reaching the wire
on the BBC case. This is not a breaking parser change (signed off
2026-06-07).

### D6 — Debug-only `content_candidates[]` on the return
Add `content_candidates: list[ContentCandidate]` to `FetchResponse` as a
flat attribute, regrouped by `_prune_wire` into the wire-only `debug` object
(present only under `debug=True`, exactly like `extraction` / `cache` /
`tokens` today). Each wire entry is `{source, content_md}` (chars, not
next_links). Attribute access stays flat for internal callers; the default
wire never carries it. This is the instrument's inspection + extra proof
hook for what Haiku saw.

### D7 — Provability: assert the menu (Haiku's input), not the wire
The deterministic gate for `regression/recipe-nutrition-volume-gate`
asserts the **menu fed to Haiku** contains `268` / `kcal` — surfaced via the
debug `content_candidates[]` (D6) under replay's `debug=True`. This decouples
the fix's proof from the wire-envelope decision. The LLM-judged answer flip
(`make bench` / a live-on-frozen-bytes check, as in change #2) remains the
quality axis.

## Risks / Trade-offs

- **Token cost up** — Haiku reads more per fetch. Mitigated by D3 priority
  trim and D4 dedup; measured on the substrate before ADR-0005 is confirmed.
  Accepted direction (ADR-0005: "start generous, optimize down measured").
- **Prompt-cache regression** if assembly is non-deterministic — the central
  risk, addressed head-on by D2 + a fitness test. Must verify the
  `EXTRACT_*` cache-prefix byte-equality test still passes.
- **LLM confusion from noise** (the junk sidebar source is still in the
  menu) — this is ADR-0005's explicit bet ("dedup/selection is the LLM's
  job"). Validated by the judged answer flip; if it fails to flip, the bet
  is wrong and the ADR is revised, not the gate relaxed.
- **`content_md` content shifts** (prose-preferred, D5) for pages where
  records used to win on length — intended, but re-run the four-axis
  output-benchmark capability tests to catch collateral regressions on
  legitimately record-shaped pages (listings, threaded discussions). Note:
  threaded/handler/pre-rendered pages bypass this path, limiting blast
  radius.
