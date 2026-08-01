## Why

**`_phase_extract`'s pre-rendered early return skips the structured-extraction
ladder, not just the trafilatura pass it was written to skip.** The ladder is
two entirely different parsers — `json_in_html`'s embedded-JSON scan and
`record_mine.extract_records`' structural record detection — and neither has
anything to do with the trafilatura content extraction the `pre_rendered`
optimisation exists to avoid. Skipping them costs four things on every browser,
archive, jina, zyte, firecrawl and site-handler fetch:

| lost on the pre-rendered path | consequence |
|---|---|
| `fc.content_candidates` | the extractor sees prose only — the ADR-0005 menu is a single item, and the "collect every rung" contract is silently void |
| `json_synth` / `record_synth` sources | `_build_link_digest`'s gate (`fetcher.py:2329`) can never pass → `other_pages` remains impossible |
| `fc.record_count` → `_phase_listing_completeness` | **no `listing_partial` / `listing_more` signal is emitted on a browser-served listing, ever** — ADR-0009's sufficiency axis is off across the whole hard-fetch population |
| `fc.record_set`, `fc.next_links_handler` | the rank-don't-skip option shelf is empty; `FetchResponse.next_links` loses its handler source |

Three of those four are independent of the link index, which is why this is not
a re-run of the previous diagnosis. `restore-links-on-pre-rendered-tiers` fixed
`fc.links` at this same early return and **measurably did not make `other_pages`
reachable** (`eval/runs/post-link-fix`, 2026-07-28: both target cases still
`unscored`). It was necessary and not sufficient — the second gate is here.

The spec already says this should not be happening. `extraction`'s
"Multi-source extraction escalation ladder" states the ladder runs
**unconditionally** — "there is no recall trigger gating entry to the ladder."
That was written about recall triggers and is true of them; the pre-rendered
bypass carves out most of the tier population without contradicting a word of
it, because no requirement ever says which tiers reach the ladder.

## What Changes

- **The pre-rendered branch runs the structured ladder** over the `raw_html` it
  already has decoded, then `_phase_listing_completeness`. It continues to skip
  `extract_markdown`, `parse_metadata`, and the date finders — those are the
  optimisation, and they stay skipped.
- **`fc.content_candidates` is seeded with the pre-rendered markdown** as the
  `trafilatura`-source baseline candidate, so the menu on this path has the same
  shape as on the raw path and `_wire_content_md`'s pick is unchanged when no
  structured rung fires.
- **The two stale spec requirements are corrected.** `tier-pipeline`'s
  "Pre-rendered handler results bypass extraction" still describes
  `tier_result.tier_extras["pre_rendered"]`, a `dict[str, Any]` bag deleted when
  `TierResult` became typed — the requirement has been describing a field that
  does not exist. It gains the scope boundary it never had: *which* extraction
  is bypassed.
- **A guard pins the boundary**, asserting a pre-rendered fetch of
  listing-shaped HTML produces a `record_synth` candidate and a non-`None`
  digest, and that it still emits no `extract` diagnostic row. Both halves — the
  skip that must survive and the ladder that must not be skipped — in one test,
  because they are one decision.
- **NOT** a change to `_DIGEST_GATE_SOURCES`. The gate is a sound pre-LLM proxy
  for product/listing shape and prose-only articles should keep paying nothing
  for a digest. It was never the defect; it was the second thing standing behind
  it.
- **NOT** a fix for jina. Its `body` is markdown bytes, not HTML, so both rungs
  find nothing and return cleanly — correct behaviour, zero benefit. Recovering
  jina's structure means parsing its markdown, which is the deferred question
  from the previous change and stays deferred.
- **NOT** a change to the prompt, `RouterPayload`, handle rehydration, or the
  meaning of `other_pages`. Unchanged and correct throughout.

## Capabilities

### Modified Capabilities

- `tier-pipeline`: "Pre-rendered handler results bypass extraction" asserts a
  bypass with no stated scope, and names a deleted `tier_extras` field. Gains an
  explicit boundary — content extraction and metadata are bypassed; the
  structured ladder and listing-completeness are not — and drops the dead field.
- `extraction`: "Multi-source extraction escalation ladder" says the ladder runs
  unconditionally but never says on which retrieval paths, which is how a whole
  tier population fell outside it without violating the text. Gains a
  requirement that ladder entry is a property of having HTML, not of which tier
  won.
- `listing-completeness`: its sufficiency guarantee is unreachable on every
  pre-rendered tier — including the browser, the tier most likely to be serving
  an infinite-scroll listing in the first place. Gains a requirement that the
  completeness check is retrieval-path independent.
- `link-affordances`: the digest gate is satisfiable on the pre-rendered path
  for the first time. The requirement's substance is unchanged; it gains the
  scenario that was impossible to satisfy.

## Impact

- `src/a2web/fetcher.py`: `_phase_extract`'s pre-rendered branch
  (1270-1285) — the early return, narrowed. This is the same six lines the
  previous change touched; the fix is completed here, not revised.
- `tests/capabilities/`: the new boundary guard.
- **Behaviour change for callers**: pages served by browser/archive/handlers
  begin emitting `other_pages`, `listing_partial`/`listing_more`, and
  handler-sourced `next_links` where they previously emitted none. All three are
  documented contracts being met on those paths for the first time, not new
  features — but they change bytes on the wire and prompt tokens, so `make
  bench` is required and its result gates the change.
- **Latency cost, unmeasured and the thing to gate on**: two extra parses per
  pre-rendered fetch (selectolax record detection + a JSON script scan) on the
  slowest tier population. Neither is trafilatura and neither is the
  `asyncio.to_thread` chokepoint the `pre_rendered` skip was protecting, but
  "not the expensive one" is an argument, not a measurement.
- **No shelf change required.** Both parsers are already adopted and already
  called on the raw path.
