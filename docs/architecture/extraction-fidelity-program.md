# Extraction Fidelity Program

A sequenced program of changes executing ADR-0002 (real surface is ground truth;
upstream extraction is an optimization ladder) and ADR-0003 (the deterministic
coarse-select / LLM-interpret seam). Born from the 2026-06-06 explore session that
started with the `listing-offer-lift` bug and generalized it to a class.

## Status

- **Change 1 `eval-substrate` — instrument LANDED (2026-06-07).** The
  egress-boundary replay harness is built, tested, and gates `make check`
  (`eval/_capture/`, `tests/eval_replay/`). The motivating bug is frozen as
  the first `regression` case, `eval/corpus/regression/hepsiburada-listing-price`:
  a Hepsiburada listing renders discounted items as `890 TL%21700 TL`, the
  record renderer's value-blind text projection fuses the −21% badge into the
  price digits, and the extractor confidently answers with the **list** price
  as the selling price (and fabricates a list price). This is the class —
  *lossy projection gated by a value-blind proxy* — not just one site. The
  deterministic shape gates `make check` today; answer correctness is the
  judged axis that the fidelity program must flip. (Note: a prior JSON-LD
  `ItemList` symptom-patch — see CHANGELOG — fixed the LD path only; this
  case is the residual class bug on the record-extractor path.)
- **Change 2 `typed-extraction-boundary` — `record_extract` half LANDED
  (2026-06-07).** The value-blind no-separator projection in
  `record_extract._own_text` is eliminated: distinct DOM text nodes are
  separated at element boundaries (and strikethrough tags marked as markdown
  `~~…~~`). Validated against the frozen regression: the judged answer flipped
  from the list price (890, fabricated 1,700, fake 48%) to the correct
  discounted price (700, 21% off). Empirical finding recorded in ADR-0004 —
  **node-separation alone sufficed** to flip the case; Hepsiburada's
  CSS-`line-through` struck price (not a `<del>` tag) is handed to ADR-0007.
  The `json-extract` typed-schema.org half of ADR-0004 is deferred to its own
  instrument-gated change (no captured regression yet — don't fix blind).
- **Change 3 `multi-source-extraction-input` — LANDED (2026-06-07).** The
  extractor is fed the full menu (prose + all renderable JSON payloads +
  records) via `fetcher.assemble_menu`; the value-blind length proxy is retired
  from the input path (it survives only as the byte-identical wire `content_md`
  display heuristic). The JSON rung now emits all renderable payloads, not just
  the top-ranked one. Debug-only `content_candidates[]` surfaces the menu.
  Confirms ADR-0005, proven by the menu unit + arch fitness tests. **Instrument
  finding:** the motivating `recipe-nutrition-volume-gate` case is NOT
  menu-fixable alone — `json_to_markdown_rows` can't render
  `Recipe`/`NutritionInformation`, so the answer never reaches the menu. That
  rendering-coverage gap is ADR-0004's json half, routed to **change 4**, where
  the recipe case becomes the captured regression that confirms it. (A live
  menu-only corpus regression remains as optional substrate enrichment.)
- **Change 4 `answer-bearing-json-rendering` — LANDED (2026-06-07).** Confirms
  ADR-0004's json half. `json_to_markdown_rows` renders the `Recipe` /
  `NutritionInformation` answer-bearing subset, and single-entity rendering is
  default-keep (not an `interesting_keys` allowlist) — eliminating the
  value-blind structural-filter projection on the JSON-LD path.
  `regression/recipe-nutrition-volume-gate` is now FIXED: `input_menu_includes:
  ["268 calories"]` green, and the live judged answer flipped to "268 calories,
  24 grams sugar". The motivating Hepsiburada→recipe class is closed across
  changes 2-4. (Remaining structural-filter siblings — `_rows_to_md_table`
  column skip, `_framework_state_to_markdown` scalar flatten — await their own
  captured regression.)
- **Changes 5–6 — UNBLOCKED.** Each measured before/after against the
  substrate; provisional ADRs (0006–0007) confirm only once proven against a
  replayed regression delta. ADR-0007 now also owns CSS-styled-strikethrough
  list/sale grounding (surfaced by change 2).

## Governing ADRs (Accepted)

- **ADR-0002** — Real surface is ground truth; optimization ladder with a fidelity debt.
- **ADR-0003** — The extraction seam: deterministic coarse-select, LLM interprets.

## Provisional-ADR lifecycle (convention established here)

Per-change ADRs carry `Status: Accepted (provisional) · Confirm-by: <change>`. They
record the agreed *direction* but are not settled. Each owning change's `tasks.md`
includes an explicit **"reconfirm / update this ADR"** task; the ADR is moved to
plain `Accepted` (or `Revised` / `Superseded`) only when the change lands AND is
validated against the eval substrate. Rationale: implementation routinely shifts
decisions; crystallizing the ADR before its change proves it would cement a guess.

## Change sequence

```
  1. eval-substrate ───────────────┐  the INSTRUMENT — built first; everything below is
                                    │  validated against it (don't cement architecture blind)
  2. typed-extraction-boundary ◀────┤  confirms ADR-0004 — structural elimination of lossy projection
  3. multi-source-extraction-input ◀┤  confirms ADR-0005 — the "menu"; retire the volume gate
  4. answerability-escalation ◀─────┤  confirms ADR-0006 — two-stage escalation; answerability signal
  5. real-surface-grounding ◀───────┘  confirms ADR-0007 — rendered DOM first-class; reconciliation
```

Dependencies: 2 depends on 1 (measure before/after). 3 depends on 2 (the typed
boundary is what the menu feeds). 4 is the overarching orchestrator change (phase
model); it depends on 1 for the necessity check. 5 depends on 4 (real-surface tier
first-class). Each step re-runs against the eval substrate.

## Per-change constraints (from the 2026-06-06 five-agent adversarial review)

| Change | Must satisfy (agent finding) |
|--------|------------------------------|
| eval-substrate | live-truth-vs-frozen paradox → three-layer fixtures (raw HTML + rendered DOM + answer); LLM-judged axes stay informational (`make bench`), only deterministic contract/token axes gate `make check`; multiple corpuses (happy-pass regression + breaking A/B/C/JS) with sync; judge-model pinned/tracked. |
| typed-extraction-boundary | package-owned boundary types, no domain imports; reuse `Wobbled`-style funnel; type the answer-bearing schema.org subset, default-keep the tail; arch fitness fn bans the structural-filter projection. |
| multi-source-extraction-input | preserve cache-prefix byte-equality; budget-aware trim vs `max_content_chars`; dedup is LLM-side (coarse subset-suppression only deterministically); `fc.content_candidates` list, not a mutated slot; document+retire the volume gate. |
| answerability-escalation | resolve the phase-inversion (post-extraction descent + decision-log re-projection, browser-≤1 cap, Verdict-as-projection); boolean+reason NOT a 4-value enum; FIRST establish (via substrate) whether behavioral `ask_here`/`try_url` already suffice; Ask-First envelope sign-off. |
| real-surface-grounding | surface conflicts via `OperatorHint(price_mismatch)` before LLM reconciliation; scope to commerce/price; depends on rendered-DOM grounding; token-budget aware. |

## Ask-First gates (CLAUDE.md)

Changes 3 and 4 touch the response-envelope shape / extractor seam → explicit
envelope sign-off required before implementation. The provisional-ADR Confirm-by
process forces that conversation.

## Backlog (noted, out of program scope)

- WebMCP (top-of-ladder surface) · full cross-source atomization · price
  provenance + locale/currency exposure.

## Status

- ADR-0002, ADR-0003: Accepted.
- ADR-0004–0007: Accepted (provisional), confirm-by their changes.
- Changes: `eval-substrate` next (proposal in progress).
