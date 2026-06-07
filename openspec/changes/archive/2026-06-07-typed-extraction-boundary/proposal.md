## Why

The frozen regression case `eval/corpus/regression/hepsiburada-listing-price`
proves the lossy-projection *class* (ADR-0003) is still live — and on a path
ADR-0004 did not name. The `record_extract` DOM projection `_own_text`
(`detector.py:87-99`) concatenates a record's descendant text nodes with **no
separator** and discards answer-bearing markup, so a discounted product card
(`<del>890 TL</del> <span>%21</span> <span>700 TL</span>`) flattens to
`890 TL%21700 TL`. The extractor cannot recover list-vs-sale, confidently
answers with the **list** price as the price the customer pays, and fabricates
a list price out of the fused `%21700` digits — at `confidence: high`. This is
the structural elimination ADR-0003 demands and ADR-0004 records as direction.
Now is the time: the eval substrate (change 1) can referee the fix, and ADR-0004
cannot be confirmed until its owning change lands and is validated.

## What Changes

- **`record_extract` projection preserves structure (regression-gated core).**
  `_own_text` stops fusing distinct DOM text nodes — distinct nodes are
  separated so adjacent-but-semantically-distinct values (`%21`, `700 TL`)
  never merge. Answer-bearing markup is preserved across the boundary, at
  minimum strikethrough (`<del>`/`<s>`/`<strike>`/line-through) so the
  extractor can tell a struck-through list price from the live sale price.
  This is a *general* fix to a value-blind projection — no site-specific or
  price-specific special-casing (that would be the symptom-patch ADR-0003
  forbids).
- **Fitness function (ADR-0003 rule 3).** A pytest-archon / AST architecture
  test that bans the value-blind no-separator descendant-flatten projection in
  `record_extract`, so this defect re-lands as a red test, not a silent
  quality drop.
- **Out of scope (deliberately): the `json-extract` typed schema.org
  boundary.** ADR-0004's *original* framing — typing `Product`/`Offer`/etc. and
  retiring the `domain.py` dict-filter siblings — is the **same class on a
  different projection site**, but it has **no captured regression yet**.
  Fixing it now would be fixing blind, which is exactly what building the eval
  substrate first was meant to prevent. It becomes its own instrument-gated
  change once a `json-extract` regression case (e.g. a JSON-LD `ItemList`
  pricing page) is captured. This change reconciles ADR-0004 to that reality
  (see below) rather than expanding to cover it unproven.
- **Proof via the eval substrate.** `make eval-refresh CASE=regression/hepsiburada-listing-price`
  re-captures and the LLM-judged answer flips from the list price to the
  discounted price. If it does not flip, the fix is incomplete — the
  instrument says so before the ADR is confirmed.
- **Reconfirm / revise ADR-0004.** Record that the class has two projection
  sites — `record_extract` (DOM) and `json-extract` (structured payload). This
  change confirms the principle and lands the `record_extract` half (proven
  against the frozen case); ADR-0004's confirm-by is re-pointed so the
  `json-extract` typed-subset half is confirmed by its own future change.

## Capabilities

### New Capabilities

(none — this is structural elimination within existing extraction capabilities)

### Modified Capabilities

- `record-extraction`: the DOM record projection SHALL preserve text-node
  boundaries and answer-bearing markup (strikethrough) across the
  record→extractor boundary, so distinct values cannot fuse and list-vs-sale
  is recoverable.

## Impact

- **Code:** `src/a2web/packages/record_extract/{detector.py,render.py,models.py}`
  (text-node separation + markup preservation). New `tests/architecture/`
  fitness test. No public tool-signature or response-envelope change.
- **Behavior:** discounted-listing answers gain fidelity; token cost may rise
  slightly (more structure reaches the extractor) — bounded and measured
  against the eval substrate.
- **ADRs:** lands the `record_extract` half of ADR-0004 and executes ADR-0003;
  re-points ADR-0004's `json-extract` half to its own future change.
- **Proof:** the frozen Hepsiburada regression case is the acceptance gate
  (`make eval-refresh` must flip the judged answer from list to sale price).
