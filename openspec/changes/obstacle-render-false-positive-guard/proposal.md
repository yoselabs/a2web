## Why

Live testing of v0.32.0 (obstacle-driven render) surfaced a real false-positive
cost. `obstacle: empty` conflates two cases the trigger can't distinguish:

1. **The page is a shell / didn't load** — un-executed JS is hiding content. A
   render *helps*.
2. **The page loaded fully but doesn't contain the answer** — a complete static
   document (a spec, a book) that simply lacks what was asked. A render is *pure
   waste* (rendering returns the same content).

Confirmed live: asking "what is the cookie recipe?" against RFC 2616
(`raw → extract → gate → zyte`) rendered pointlessly — the RFC was fully fetched;
no render could add a cookie recipe. An agent asking many unanswerable questions
would accumulate wasted Zyte spend + a second Haiku call each time.

## What Changes

- **Gate the obstacle render on evidence a render would add content.** The
  obstacle-driven render fires only when BOTH hold, in addition to the existing
  guards: (a) the content did NOT come from a JS-executing tier (`jina` /
  `browser` / `browser_robust` already ran JS, so re-rendering is redundant), and
  (b) the raw body shows unrendered-SPA markers (a root mount like `id="root"` /
  `id="__next"` plus `<script>` tags). A complete static page with no such markers
  no longer triggers a render on `obstacle: empty`.
- **New length-independent SPA detector.** `block_detector.looks_like_unrendered_spa(raw_html)`
  reuses the existing SPA-shell markers but drops the length gate, so a FAT shell
  that passed the length floor is still recognized as unrendered. (The existing
  `js_required` gate branch stays length-gated and unchanged.)

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `tier-pipeline`: the obstacle-driven render phase gains a false-positive guard —
  it fires only when the content came from a non-JS-executing tier AND shows
  unrendered-SPA markers.
- `paid-fetch-tiers`: the extractor-obstacle paid trigger requires evidence a
  render would add content (non-JS tier + SPA markers), so a complete static page
  that merely lacks the answer does not incur paid egress.

## Impact

- **Code**: `src/a2web/packages/block_detector.py` (+`looks_like_unrendered_spa`);
  `src/a2web/fetcher.py` (`_obstacle_wants_render` guard + `_JS_EXECUTED_TIERS`).
- **APIs / envelope**: none. Behavior-narrowing only (fewer renders); the
  never-silently-miss floor is unaffected — a surviving obstacle still flags
  `retrieval_incomplete`.
- **Cost**: strictly reduces paid egress (removes the wasted-render case).
- **Dependencies**: none.
