## Why

A genuinely small but complete page has no path to a successful answer.
`https://example.com` (~230 chars — its entire content is "This domain is for
use in documentation examples") returns `status: failed`, `verdict:
length_floor`, `retrieval_incomplete: true`, and `answer: null` — the extractor
never runs, because the gate runs *before* extraction and only proceeds on
`verdict == ok`. The retrieval was complete; the page is just short. This is the
canonical bad first smoke test (`LESSONS_LEARNED.md` #5), but the real defect is
deeper than a confusing smoke test: the floor conflates two different questions.

`LENGTH_FLOOR = 500` (chars of extracted markdown) exists as a *block-detection*
heuristic — "is this page thin because it is WALLED?" But it is used as a
*content-sufficiency gate* — "is there enough content to bother extracting?" Those
are different. A 230-char page that is complete and unwalled has ample content to
answer "what is this about"; the wall heuristic should not fail it.

Two structural symptoms confirm the conflation:

1. `example.com` hits the bare fallthrough in `block_detector.evaluate`
   (`block_detector.py:325`) — no anti-bot marker, not `js_required`, not
   `blank_page`, just short — returning `length_floor` with `escalation=None`,
   `subsystem=None`. `length_floor` is doing double duty as both "floor violation
   detected" and "no evidence of anything, the page is simply small".

2. The planner (`playbook.py:340`, `_decide_gate_thin_escalate`) escalates *any*
   `length_floor` to the browser, fingerprint-blind, up to twice. So a page that
   is complete at 230 chars burns up to two browser renders — both of which return
   the same 230 chars — before failing anyway.

There is a promotion path for a *confirmed empty search result*
(`is_confirmed_empty`, `empty.py`), but its conjunction ends in
`is_search_shaped(url)`, so it can never rescue a non-search page. There is no
sibling path for a *confirmed complete small page*.

## What Changes

This adds a promotion for a corroborated-complete small page, as a strict sibling
to `is_confirmed_empty` — and it deliberately preserves the empty-vs-wall
false-positive asymmetry (a false wall over-warns, cheap; a false "complete"
under-warns and could hide a wall, so the conjunction must be as strict as the
empty one).

- **A new `is_complete_small_page(observations, url)` conjunction** promotes a
  thin page to `verdict: ok` — so extraction runs and the caller gets the honest
  answer from the small content — ONLY when: an independent BROWSER render
  returned substantially the same small content as an HTTP tier (corroboration
  that the page IS small, not walled-thin) · NO 4xx/challenge status · NO
  `subresource_blocks` / hard-wall evidence anywhere. It does NOT require a
  search-shaped URL (that is precisely the term that distinguishes it from
  `is_confirmed_empty`). Unlike the empty promotion it produces no synthetic "no
  results" answer — the extractor runs on the real body.

- **Split the bare fallthrough from a suspicious floor violation.** The
  no-evidence fallthrough (`block_detector.py:325`) becomes distinguishable from a
  floor violation that carries wall/subresource suspicion, so the planner can stop
  spending a second browser render re-confirming that a 230-char page is 230
  chars. The corroborating browser render (the first) is justified as the second
  witness; the second is waste — cap bare-fallthrough browser escalation at 1.

- **A thin page that is NOT corroborated-complete keeps today's honest-failure
  behavior** unchanged: `content_thin` WARNING worded agnostically, body attached
  as `thin_content`, `status: failed` + `retrieval_incomplete: true`. The floor
  still errs toward the wall side whenever corroboration is absent.

- **Caching:** the promoted complete-small-page IS real content and MAY be cached
  (unlike the promoted empty, which is never cached) — pending the design
  decision below, since a false-positive here would cache a wall.

## Open questions (see design.md)

- Is the promoted complete-small-page cacheable, or wire-only like the empty
  promotion? (false-positive risk vs. re-fetch cost)
- Confidence tier for a promoted small page — `low`, or `medium` when both tiers
  agree?
- Does "substantially the same content" need a similarity threshold, or is
  "both under the floor AND both non-empty" sufficient?

## Impact

- Affected code: `src/a2web/actions/empty.py` (new sibling conjunction),
  `src/a2web/actions/playbook.py` (`_decide_gate_thin_escalate` cap + the
  fallthrough distinction), `src/a2web/packages/block_detector.py` (distinguish
  bare fallthrough), `src/a2web/fetcher_response.py` (promotion → ok wiring),
  `LESSONS_LEARNED.md` #5.
- **Touches the empty-vs-wall-discrimination first-class product invariant** — a
  Constitution-adjacent change requiring human confirmation (Phase A). The design
  is explicitly built to preserve the invariant's false-positive asymmetry.
- Response-envelope shape unchanged (a formerly-`failed` page becomes `ok` with a
  populated `answer`; no new fields). Corpus entry added so `example.com` is a
  regression, not a smoke-test footgun.
