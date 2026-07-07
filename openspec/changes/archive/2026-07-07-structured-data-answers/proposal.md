## Why

Pages that are **thin in prose but rich in structured data** — company contact
pages, organization pages, event pages — currently fail with `status: failed`,
`answer: null` even when the answer is sitting in the page's own JSON-LD. The
motivating case is `veito.com/iletisim-EN.html`: an `ask` for the company's
phone and email returned a failed envelope while the response's own `meta`
block carried `jsonld[0].telephone = "444 3 061"` and
`jsonld[0].email = "destek@veito.com"`.

The pipeline actually *rendered* that JSON-LD into a `json_synth` content
candidate, but the length-floor gate (`content_md < 500` chars) classified the
short page as `Verdict.length_floor` → `failed`, which skips LLM extraction
entirely (`_phase_extract_answer` hard-gates on `verdict == ok`). A
small-but-complete structured answer is deleted for being short — the exact
mistake the existing `is_json` exemption already prevents for whole-body JSON
responses.

## What Changes

- **Answer-bearing structured content exempts a bare `length_floor` from
  failure.** When the collected content menu contains an answer-bearing
  structured candidate (a strong JSON-LD / microdata payload), the gate SHALL
  promote a bare `length_floor` verdict to `ok` — mirroring the existing
  `is_json` small-but-complete promotion. This lets extraction run and answer
  from the structured data. The promotion is scoped to *bare* `length_floor`
  (subsystem `None`); it SHALL NOT fire for SPA-shell (`js_required`),
  thin-browser, anti-bot, or block-page verdicts, so no wall is masked.
- **Contact / org / event schemas become first-class "strong" structured
  data.** `_PREFERRED_LD_TYPES` (and the microdata strong set) widen from
  commerce+editorial only (`Product`, `Article`, `NewsArticle`, `ItemList`,
  `BreadcrumbList`) to also include `LocalBusiness`, `Organization`,
  `ContactPoint`, `Event`, `Recipe`. The `≥3 populated fields` threshold is
  unchanged, so junk payloads still rank weak.
- **The escalation ladder tags each structured candidate as answer-bearing.**
  `ContentCandidate` gains a typed `answer_bearing: bool` field, set by the
  `json_synth` rung from the package's `is_answer_bearing(payload)` verdict —
  so the gate exemption and the display pick can consult it without re-parsing
  and without the gate importing schema knowledge.
- **The display pick prefers an answer-bearing structured candidate over
  sub-floor prose.** When the quality-picked display prose is below the length
  floor and an answer-bearing structured candidate exists, `content_md` SHALL
  surface the structured candidate — so `fetch_raw` (no LLM) also carries the
  answer, not a thin nav/footer fragment.

Not breaking: no tool signature, response envelope shape, or new
dependency changes. Confidence is unchanged — a promoted page follows the
normal `ok` path and the extractor assesses confidence from the data itself.

## Capabilities

### New Capabilities
<!-- none — all changes modify existing capability requirements -->

### Modified Capabilities
- `quality-gate`: add a requirement that a bare `length_floor` is promoted to
  `ok` when an answer-bearing structured candidate is present (mirrors the
  `is_json` exemption); the promotion never fires for SPA-shell / thin-browser
  / anti-bot / block verdicts.
- `json-extract`: widen the strong-payload type set (`_PREFERRED_LD_TYPES` +
  microdata strong) to include `LocalBusiness`, `Organization`, `ContactPoint`,
  `Event`, `Recipe`; expose a pure `is_answer_bearing(payload)` predicate.
- `extraction`: `ContentCandidate` carries `answer_bearing: bool` set by the
  `json_synth` rung; the display-pick rule prefers an answer-bearing structured
  candidate over sub-floor prose.

## Impact

- `src/a2web/packages/block_detector.py` — none directly (the exemption lives in
  the fetcher seam, mirroring `is_json`).
- `src/a2web/fetcher.py` — `evaluate(...)` seam gains a `structured_answer`
  parameter and the mirror promotion block; `_phase_gate_and_escalate` computes
  it from `fc.content_candidates`; `_escalate_via_json` sets
  `ContentCandidate.answer_bearing`; `_pick_display_candidate` prefers
  answer-bearing structured over sub-floor prose.
- `src/a2web/packages/json_in_script.py` — `_PREFERRED_LD_TYPES` widened;
  `_ld_json_strong` / `_microdata_strong` cover the new types; new public
  `is_answer_bearing(payload) -> bool`.
- `ContentCandidate` (a slotted frozen dataclass) gains one typed `bool` field —
  no `dict[str, Any]` bag.
- Motivating fetch `veito.com/iletisim-EN.html` moves from `failed/null` to
  `ok` with the phone + email answered.
- Same win applies to the class: LocalBusiness/Organization contact pages,
  Event pages, and any thin page whose answer lives only in structured data.
