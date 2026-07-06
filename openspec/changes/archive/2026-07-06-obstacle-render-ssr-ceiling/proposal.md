## Why

The v0.32.1 marker-based guard is insufficient. Live testing proved it: asking
rfc-editor.org (a **Nuxt SSR** app) an unanswerable question still triggered a
paid render. SSR framework sites (Next / Nuxt — a large fraction of the modern
web) carry the same SPA mount markers (`id="__nuxt"`, `__NUXT_DATA__`) as a CSR
shell, YET already contain their full content in the initial HTML. Markers alone
cannot distinguish "SSR page with content" from "CSR shell without content", so
the guard let content-rich SSR pages render pointlessly.

## What Changes

- **Add a content-length ceiling as the load-bearing guard.** The obstacle-driven
  render now also requires the already-extracted `content_md` to be THIN
  (`< _RENDER_CONTENT_CEILING`, 2000 chars). Substantial extracted content means
  the page is complete (SSR or static) and the answer's absence is real — a
  render can't add it. Only a thin result (in the `(LENGTH_FLOOR, ceiling)`
  window) is plausibly an unrendered shell worth rendering. This is the direct
  measure of "did we already get the content", where markers were only a proxy.
- **Widen SPA mount markers to include Nuxt** (`id="__nuxt"`, `__NUXT_DATA__`,
  `__NEXT_DATA__`) so the marker check is accurate; the ceiling, not the markers,
  now carries the SSR exclusion.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `tier-pipeline`: the obstacle-driven render phase adds a thin-content
  precondition (`len(content_md) < _RENDER_CONTENT_CEILING`) — a content-rich
  page (SSR/static) is never re-rendered even when it carries SPA markers.
- `paid-fetch-tiers`: the extractor-obstacle paid trigger requires thin already-
  extracted content in addition to a non-JS tier + SPA markers.

## Impact

- **Code**: `src/a2web/fetcher.py` (`_RENDER_CONTENT_CEILING` + the ceiling check
  in `_obstacle_wants_render`); `src/a2web/packages/block_detector.py` (Nuxt
  markers in `_SPA_MOUNT_MARKERS`).
- **APIs / envelope**: none. Behavior-narrowing (strictly fewer renders); the
  never-silently-miss floor is unchanged — a surviving obstacle still flags
  `retrieval_incomplete`.
- **Live-verified**: rfc-editor.org (Nuxt) + a Wikipedia off-topic ask no longer
  render (both flag `retrieval_incomplete` without paid egress).
