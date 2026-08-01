## Why

a2web is a network fetcher whose every input is hostile by definition — remote
pages, remote APIs, and an LLM. Three of its paths have no bound at all, verified
2026-07-31:

1. **The LLM call has no timeout.** The string `timeout` does not appear
   anywhere in `packages/llm_extract/` or `llm_resource.py`. It is not an
   oversight in a2web alone: `anyllm.LLMProvider.complete()` **has no timeout
   parameter**, so the substrate cannot currently express one. A hung provider
   hangs the tool call indefinitely.
2. **There is no per-fetch deadline.** 34 timeout sites exist across `src/`,
   each bounding one hop. Nothing bounds their sum. A walled fetch walking the
   full ladder is roughly 329 s of composed hops *plus* an unbounded extraction,
   and no caller-visible or operator-visible ceiling exists.
3. **`hn.py:233` recurses on untrusted API input with no depth cap**, where both
   sibling tree-renderers cap at 20 (`habr.py:48`, `discourse.py:41`). The
   deleted-comment branch at `hn.py:240` is worse than uncapped: it recurses with
   `depth=depth`, *unchanged*, so a chain of deleted comments would defeat a
   naive depth cap too. Each level also prepends `">" * depth`, so output grows
   quadratically before the interpreter's recursion limit turns it into a crash.

Exactly one timeout in the whole system is operator-tunable
(`browser_idle_timeout_s`), and it governs browser idleness rather than any
request bound.

Why now: independent of the T1/T2 refactors, small, and #3 is reachable from
attacker-influenced input today.

## What Changes

- **A per-fetch deadline**, operator-configurable, enforced at the orchestrator
  so it bounds the whole pipeline rather than any one hop. Exceeding it is a
  normal ADR-0009 failure — `status: failed`, `retrieval_incomplete: true`, an
  operator hint naming the deadline — never a silent truncation.
- **A timeout on every LLM call.** a2web wraps `complete()` at its own seam,
  because `anyllm` cannot express it today. **The matching shelf promotion —
  giving `anyllm` a real per-request timeout — is filed as follow-up, not done
  here**; a2web's wrapper cancels the coroutine but cannot abort an HTTP request
  the adapter owns.
- **`hn.py`'s comment renderer gains the depth and count bounds its two
  siblings already have**, including on the deleted-comment path, which must
  increment depth like any other level.
- **The request bounds become settings**, so an operator can shorten them
  without a code change. Today they are 34 literals.

Not breaking: every new bound is a ceiling above current observed behaviour, and
crossing one produces the failure envelope ADR-0009 already specifies.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `extraction`: an LLM call SHALL be bounded, and exceeding the bound SHALL
  surface as a declared failure rather than a hang.
- `tier-pipeline`: a fetch SHALL carry a total deadline that bounds the sum of
  its hops, not merely each hop.
- `site-handlers`: a handler rendering a tree from upstream data SHALL bound
  recursion depth and node count, on every recursive path.

## Impact

- `src/a2web/fetcher.py` — deadline threading through `FetchContext`
- `src/a2web/packages/llm_extract/extractor.py`, `judge.py`,
  `src/a2web/llm_resource.py` — the LLM timeout seam
- `src/a2web/handlers/hn.py` — `_render_kid`
- `src/a2web/settings.py` — the new knobs
- `src/a2web/models.py` — a deadline-exceeded operator hint
- **Shelf follow-up (not in this change):** `anyllm` has no per-request timeout.
  Filed against the shelf; a2web's wrapper is the interim.
- No new dependencies. `asyncio.timeout` is stdlib.
