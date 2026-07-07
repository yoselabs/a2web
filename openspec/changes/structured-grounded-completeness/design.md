## Context

`structured-data-answers` promotes a thin page whose answer is in
answer-bearing structured data to `ok` so `ask` can answer from it. That fix
succeeds — but exposes a pre-existing contradiction in the extractor's routing:
the LLM reads the short structured menu, classifies the *page* as an empty
shell (`obstacle: "empty"`), and `build_ask_response` turns that into
`retrieval_incomplete: true` + a critical "do not answer as if it does" hint —
alongside the correct answer it just returned.

The obstacle→incomplete rule lives in the `retrieval-completeness` capability
(`_INCOMPLETE_OBSTACLES = {empty, blocked}`, `fetcher_response.py:404`). It is a
real safety net (ADR-0009): a fluent-but-unfounded answer with a surviving
obstacle must not read as complete. The rule is right in general; it is wrong
only for the narrow case this change targets.

## Goals / Non-Goals

**Goals:**
- Stop flagging a structured-grounded, non-empty answer as
  `retrieval_incomplete` on an `empty` obstacle.
- Keep an honest hedge (`confidence: low`) so the caller still verifies.
- Preserve the never-silently-miss floor for every other case.

**Non-Goals:**
- Changing the `extraction_empty` hard-fail (a truly empty answer still fails).
- Touching `blocked` / `paywalled` / `error` obstacle handling.
- Changing the paid-render-before-incomplete ladder.
- Trying to make the LLM stop emitting `obstacle: empty` on thin pages — we
  correct the *envelope* rule deterministically, not the model.

## Decisions

### D1: Key the carve-out on the structured-answer *promotion*, not on "an answer-bearing candidate exists"

The tempting signal — "suppress when `any(c.answer_bearing)` and the answer is
non-empty" — is too loose. A page can carry a strong `Product` (price) while the
user asked about warranty; the LLM may confabulate a warranty answer and
correctly set `obstacle: empty`. Suppressing there would hide a real miss.

Instead, key on the **narrow** fact that the `ok` verdict came from the
`structured-data-answers` length-floor exemption — i.e. the page was thin and its
**only** answer source was the structured candidate. In that case a non-empty
answer is structured-grounded *by construction* (there was no prose to answer
from). This is the exact population where `obstacle: empty` is a false positive.

Mechanically: `_phase_gate_and_escalate` sets `fc.structured_grounded = True`
when (and only when) the `structured_answer` exemption is what flipped the
verdict to `ok`. Carry it to `FetchResponse` as an internal (wire-invisible)
signal.

*Alternative considered:* substring-match the answer against the structured
candidate's text at extraction time. Rejected — fuzzy, and the LLM legitimately
paraphrases ("General phone: 444 3 061" vs the raw `telephone` field).

### D2: Drop `retrieval_incomplete` + the critical hint, KEEP `confidence: low`

The carve-out removes only the two contradictory signals: the
`retrieval_incomplete` flag and the critical `retrieval_incomplete` operator
hint. It does **not** promote confidence — a structured-exemption answer keeps
`confidence: low` (it bypassed the prose-quality signal). So the envelope still
says "verify me," just via a low-confidence answer rather than a klaxon that
contradicts the answer. This retains the honest hedge while removing the
self-contradiction.

### D3: Empty answer still fails hard

The carve-out is scoped to a **non-empty** answer. If the extractor returns an
empty answer on a promoted page, the existing `extraction_empty` guard fires
(`status: failed` + `retrieval_incomplete`), untouched. So "the structured menu
had nothing usable" still surfaces loudly.

## Risks / Trade-offs

- **[Confabulation on a thin structured page slips through]** → Residual, bounded:
  the answer keeps `confidence: low` (never presented as confident/complete), and
  the population is narrow (thin page, sole source = structured data). The
  general obstacle→incomplete net still covers every prose-source page.
- **[Threading a new internal flag through FetchContext→FetchResponse]** → Small,
  typed, wire-invisible; no envelope-shape change. Mirrors existing internal
  signals like `retrieval_incomplete`.

## Open Questions

- Should the carve-out also apply when the page had above-floor prose *and* the
  LLM chose to answer from the structured candidate? (Deferred — D1 deliberately
  scopes to the promotion case only; widening needs the grounding signal D1
  rejected.)
