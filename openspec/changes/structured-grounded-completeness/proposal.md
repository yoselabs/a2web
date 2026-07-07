## Why

After `structured-data-answers`, a thin page whose answer lives only in
answer-bearing structured data (a LocalBusiness contact page) now resolves to
`ok` and answers correctly. But the LLM extractor, reading a short structured
menu, still self-reports `obstacle: "empty"` — which drives
`retrieval_incomplete: true` plus a **critical** operator hint (*"Do not answer
as if it does"*). The envelope then carries a correct, structured-grounded
answer **and** a klaxon telling the caller not to trust it. For an agent
consumer, that contradiction can cause it to discard a good answer — half-negating
the fix that produced it.

Live evidence (`veito.com/iletisim-EN.html`): `answer` = phone `444 3 061` +
email `destek@veito.com`, `status` ok, yet `retrieval_incomplete: true` with the
critical hint.

## What Changes

- **A structured-grounded non-empty answer is not flagged retrieval-incomplete.**
  When the `ask` verdict was promoted to `ok` by the `structured-data-answers`
  length-floor exemption (i.e. the page is a thin page whose **only** answer
  source is an answer-bearing structured candidate) AND the extractor returned a
  **non-empty** answer, an `obstacle: "empty"` SHALL NOT set
  `retrieval_incomplete` or emit the critical `retrieval_incomplete` hint.
- **The honest hedge is retained, the false alarm is dropped.** `confidence`
  stays `low` for these answers (they bypassed the usual prose-quality signal),
  so the caller is still told "verify me" — but via a low-confidence answer, not
  a "do not answer as if it does" klaxon that contradicts a delivered answer.
- **The never-silently-miss floor is preserved everywhere else.** A genuinely
  empty answer still fails hard (the `extraction_empty` guard is untouched).
  `blocked` / `paywalled` / `error` obstacles are untouched. A page with a real
  prose answer source (not a structured-exemption promotion) keeps today's
  obstacle-driven incompleteness behavior. The paid-render-before-incomplete
  ladder is unchanged.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `retrieval-completeness`: carve out the structured-grounded case from
  "Obstacle-flagged ask answers surface as retrieval-incomplete" — a non-empty
  answer on a structured-exemption-promoted page is not incomplete on an
  `empty` obstacle (confidence still capped low).

## Impact

- `src/a2web/fetcher.py` — record that the `ok` verdict came from the
  structured-answer exemption (a `structured_grounded` signal on `FetchContext`,
  carried to `FetchResponse`).
- `src/a2web/fetcher_response.py` — `build_ask_response`: gate the
  `obstacle in _INCOMPLETE_OBSTACLES` block so `empty` + non-empty answer +
  `structured_grounded` skips `retrieval_incomplete` (keeps the `low` confidence
  cap).
- `src/a2web/models.py` — possibly one new boolean field on `FetchResponse`
  (wire-invisible on the ask envelope; internal signal only).
- Depends on `structured-data-answers` having shipped (the exemption + the
  `answer_bearing` plumbing).
