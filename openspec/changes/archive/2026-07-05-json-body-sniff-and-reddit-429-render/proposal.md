## Why

Two residual retrieval-miss holes, both cases where the fetcher takes a
slow-or-wrong path when a correct one is reachable:

1. **JSON served under a non-JSON content-type.** v0.30.0 routes JSON responses
   directly (never through the jina HTML reader) — but detection keys on the
   response content-type. A misconfigured API that returns JSON as `text/html`
   or `text/plain` slips past: trafilatura runs over JSON (garbage) or the body
   escalates to jina (mangled) → a false `length_floor`. The content-type header
   lied; the body is still JSON.
2. **Reddit search/listing `429` takes the slow ladder.** v0.29.0 shortcuts a
   Reddit search/listing `403` straight to a paid site render. A `429`
   (rate-limited) instead returns `rate_limited` and walks the slow ladder — it
   still reaches Zyte eventually (via browser attempts first), just later. A
   rate-limited RSS surface is a wall just like the 403 case.

## What Changes

- **Raw tier body-sniff.** On a 2xx response whose content-type is not
  JSON-family, if the body sniffs as a JSON document (prefix-guarded on `{`/`[`,
  then a real parse), normalize the content-type to `application/json` so the
  existing v0.30.0 synthesis path handles it. HTML never parses as JSON, so the
  sniff only ever upgrades a genuine JSON body; the `{`/`[` prefix guard on a
  bounded window means large HTML bodies are never decoded.
- **Reddit search/listing `429` → escalate-to-render.** A rate-limited (429)
  Reddit search or listing RSS surface now signals `escalate_to_render` (like the
  403 case) instead of returning `rate_limited`. Thread/permalink `429` is
  unchanged (still `rate_limited` — the archive/ladder path handles it).

## Capabilities

### New Capabilities
<!-- none — extends existing capabilities -->

### Modified Capabilities
- `raw-tier`: a 2xx body that parses as JSON under a non-JSON content-type is
  normalized to `application/json` (content-type recovery), so JSON served as
  `text/html` / `text/plain` is synthesized in-place, never mangled.
- `reddit-rss-access`: a rate-limited (`429`) search/listing RSS surface
  escalates to a paid site render (like the `403` wall case), not the slow
  ladder. Thread/permalink `429` still fails loud with `rate_limited`.

## Impact

- **Code**: `src/a2web/packages/json_in_script.py` (+`sniff_json_body`);
  `src/a2web/tiers/raw.py` (2xx sniff + content-type normalization);
  `src/a2web/handlers/reddit.py` (search/listing 429 → `_render_escalation_signal`).
- **APIs / envelope**: none. No wire-shape change, no new tool params.
- **Dependencies**: none.
- **Out of scope** (already in `BACKLOG.md`): requested-vs-actual URL
  transparency (Track 1); obstacle-drives-escalation reorder (Track 3, which
  absorbs generic SPA-search-host coverage / Track 4).
