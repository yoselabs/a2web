## Why

`a2web-axb` shipped the cross-domain half of the "requested identity vs served
content" check (registrable-domain comparison, downgrade-only confidence cap,
`served_url_differs` hint). The audit (§4a2/§4b) documents a second, harder
shape the domain check cannot see: the served page is real and on the RIGHT
site, but is the wrong product/entity relative to the caller's query — a
marketplace search returning a different product family entirely
(hepsiburada `pindstrup` → shade cloth; `kekkila` → calcium nitrate; kaspi
`AMT M-1` → unrelated computer/auto parts across 387k results), all shipped at
`confidence: high` with nothing telling the caller the results don't match
what they asked for.

There is no deterministic URL-level signal for this — the fix needs
query-term overlap between the caller's `ask` and the served title.

## What Changes

- `build_response` gains a second, independent same-domain check, following
  the exact downgrade-only cap precedent `served_url_differs` established:
  when a fetch is a LISTING (routing classified `structural_form: listing`
  AND `fc.record_set` parsed rows) with a non-empty `ask`, and NONE of the
  served item titles (`record_set.records[].heading_text`) share a
  substantive token with the query, `confidence` is capped `high` → `medium`
  and a new `query_title_mismatch` operator hint is appended.
- Compares against served ITEM titles, not the page's own `<title>` — a
  search-results page's `<title>` typically echoes the query term regardless
  of whether the results are relevant ("pindstrup arama sonuçları" says
  "pindstrup" even when every result is shade cloth), which would show zero
  mismatch exactly in the audit's failure cases. See design.md D1.
- Token overlap is a plain-stdlib, locale-agnostic normalize-and-split (no new
  dependency): casefold, Unicode NFKD + strip combining marks, split on
  non-alphanumeric, drop tokens below a length floor. No stemming. A small,
  fixed, English-only operator-word list (price/stock/review/vs/...) is
  stripped from the QUERY side only — a2web's own tool description shows the
  caller-facing query convention is English regardless of the served page's
  language, so this is not a locale-maintenance burden. See design.md D3.
- Scoped to LISTING pages with zero-overlap only. The harder confusable-variant
  shape on a SINGLE product page (Lenovo 15AKP10 vs 15IRX10 — partial overlap,
  differs only in a model-number suffix, no listing item titles to check
  against) is an explicit Non-Goal — see design.md.
- No tool signature change, no envelope field change — this reuses the
  existing `operator_hints` + `confidence` mechanism the domain check already
  established; only a new hint CODE is added, same shape as
  `served_url_differs`.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `fetch-response`: extends the confidence-cap requirements alongside
  "a cross-domain landing caps confidence and is flagged" with a sibling
  same-domain, query-term-mismatch requirement.

## Impact

- `src/a2web/fetcher_response.py` — new check inside `build_response`,
  adjacent to the existing `served_url_differs` block; a new pure token-overlap
  helper function.
- `src/a2web/hints.py` — new `query_title_mismatch_hint()`.
- `openspec/specs/fetch-response/spec.md` — new Requirement.
- No wire contract change expected (new hint CODE only fires on a real
  mismatch; existing golden fixtures aren't expected to trigger it, same as
  `served_url_differs` needed no re-bless).
