## Why

`ask-response-diet` + `fetch-response-diet` made the envelopes lean by dropping *empty* fields. Two classes of clutter survive: (1) the debug-tier fields (`started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, `extraction`) are scattered as conditionally-present top-level keys — the envelope's two-tier nature is implicit and a consumer must strip six keys instead of one; (2) `tier` and `url` are *always* present but carry signal only when they deviate from the boring default — `tier` is `raw` on most fetches, and `url` just echoes back the URL the caller already passed. `original_url` exists purely to tell the caller "what you originally asked for," which the caller already holds.

The unifying rule, already proven by failure-only `status`: **a field appears on the wire only when it deviates from the default.** Applied here it collapses a trivial successful `ask` to `{confidence, extracted_answer}` and a trivial `fetch_raw` to `{confidence, content_md}`.

## What Changes

- **BREAKING** — the debug-tier fields move off the top level into a single `debug` sub-object (`DebugInfo` model) carrying `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, and (for `ask`) `extraction`. The `debug` key appears only when the tool is called with `debug=True`; absent otherwise.
- **BREAKING** — `tier` is deviation-only: omitted from the wire when its value is `raw` (the plain-HTTP default); present for `site_handler:*`, `jina`, `archive`, `browser`. Absence means a plain raw fetch.
- **BREAKING** — `url` is redirect-only: omitted when the fetched URL equals the URL the caller requested; present (carrying the final URL) only when the fetch landed somewhere else (HTTP redirect or captcha-host rewrite).
- **BREAKING** — `original_url` is deleted from both envelopes. The caller already holds the requested URL; the surviving `url` (when present) *is* the deviation.
- The `_prune_wire` helper gains value-based deviation rules (`tier == "raw"`, `url` absent) alongside the existing `status == ok` rule.

## Capabilities

### Modified Capabilities
- `ask-response`: debug fields packed into a `debug` sub-object; `tier` deviation-only; `url` redirect-only; `original_url` removed.
- `fetch-response`: same four changes applied to the `fetch_raw` / `FetchResponse` envelope.

## Impact

- `src/a2web/models.py` — new `DebugInfo` model; `AskResponse` / `FetchResponse` lose the six scattered debug fields and `original_url`, gain `debug: DebugInfo | None`; `_prune_wire` gains the `tier` / `url` deviation rules.
- `src/a2web/fetcher_response.py` — `build_response` / `build_ask_response` assemble the `DebugInfo` sub-object and apply the `tier` / `url` deviation logic.
- `tests/` — contract goldens re-blessed; `ask` / `fetch_raw` wire assertions updated.
- BREAKING for any MCP consumer reading `started_at` / `total_ms` / `cache` / `diagnostics` / `tokens` / `extraction` at the top level, or relying on `tier` / `url` / `original_url` being always present.
