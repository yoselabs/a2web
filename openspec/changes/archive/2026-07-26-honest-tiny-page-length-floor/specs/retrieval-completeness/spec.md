## ADDED Requirements

### Requirement: A corroborated complete small page answers, not fails

A thin page (extracted content below `LENGTH_FLOOR`) SHALL be promoted to
`verdict: ok` — so extraction runs and the caller receives an honest answer from
the retrieved body — when ALL of the following hold (the `is_complete_small_page`
conjunction, a strict sibling of `is_confirmed_empty`):

- an independent BROWSER render returned a non-empty body substantially matching
  the small HTTP body (corroboration that the page is small, not walled-thin);
- an HTTP tier returned a body;
- NO 4xx or challenge status was observed;
- NO `subresource_blocks` observation exists;
- NO hard-wall evidence exists anywhere in the fetch.

Unlike `is_confirmed_empty`, this promotion SHALL NOT require a search-shaped URL,
and SHALL NOT synthesize a "no results" answer — the extractor runs on the real
body. The promotion preserves the empty-vs-wall false-positive asymmetry: any wall
evidence forbids it, so an ambiguous case errs toward `failed`.

#### Scenario: A tiny complete unwalled page is answered

- **WHEN** a fetch of a non-search URL returns ~230 chars over HTTP, an independent
  browser render returns substantially the same ~230 chars, and no 4xx/challenge/
  subresource-block/hard-wall evidence exists
- **THEN** the verdict is promoted to `ok`, extraction runs on the body, and the
  response carries a populated `answer` with `status: ok` (not `failed`, not
  `retrieval_incomplete`)

#### Scenario: A thin page with wall evidence is not promoted

- **WHEN** a fetch returns a thin body but a `subresource_blocks` observation or a
  hard-wall marker is present
- **THEN** the page is NOT promoted; it stays `status: failed` with an agnostic
  `content_thin` WARNING and the body attached as `thin_content`

### Requirement: A bare length-floor page is not re-rendered redundantly

A `length_floor` verdict produced by the no-evidence fallthrough (no anti-bot
marker, not `js_required`, not `blank_page` — the page is simply short) SHALL be
escalated to the browser at most once. The single render serves as the
corroborating second witness for the complete-small-page promotion; a second
render only re-confirms the page's small size and SHALL NOT be dispatched. A
`length_floor` that carries wall/subresource suspicion keeps its existing
escalation budget.

#### Scenario: A short marker-free page burns at most one browser render

- **WHEN** a short, marker-free page produces a bare-fallthrough `length_floor`
- **THEN** at most one browser render is dispatched for it (the corroborating
  witness), not two
