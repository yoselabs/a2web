## Why

The 2026-05-19 harsh-test session (Trendyol, X, NYT, TechCrunch, Yandex Market, Amazon.com.tr, Hepsiburada) exposed six concrete gaps in a2web's fetch pipeline. Three are architectural (modern e-commerce ships product data as embedded JSON, not server-rendered cards), three are operational (paywall stub misclassification, thin browser snapshots, leaking subprocess stderr). Today, "buy a backpack in Türkiye" works on Hepsiburada/Amazon.com.tr (SSR) but fails on Trendyol (CSR) and is 3× more expensive than it needs to be on Yandex Market because the orchestrator can't see it's processing JSON noise.

## What Changes

- Add a **JSON-in-script extractor** that runs before trafilatura when the page carries `<script type="application/json">`, `<script id="__NEXT_DATA__">`, `<script id="__NUXT_DATA__">`, or `window.__INITIAL_STATE__`-shape blobs. Extracted product/list data is converted to a synthetic markdown table the existing extraction model already understands.
- Upgrade the **paywall classifier** so jina's `Warning: Target URL returned error 401: Unauthorized` and `... error 403: Forbidden` stubs map to `Verdict.paywall` (not `Verdict.length_floor`). This makes the existing archive-escalation logic actually fire on NYT / WSJ / FT.
- Add a **thin-browser-response heuristic** to the quality gate: when a browser-tier response is 200 OK but body is <1024 chars *and* host is in the known-JS-heavy set, downgrade verdict to `length_floor` and let escalation continue.
- Browser tier: after `wait_until="networkidle"`, perform a **scroll-to-bottom + 2s idle wait** before snapshotting the DOM. Unlocks lazy-loaded product grids (Trendyol pattern).
- Pipe camoufox/playwright **subprocess stderr to LDD diagnostics** instead of letting Node.js stack traces leak to the user terminal.
- Expose **`--max-content-chars`** as a CLI flag on `ask` / `fetch_raw` (today only a constructor default). Lets callers cap per-fetch when they know the page is dumping JSON state they won't use.

## Capabilities

### New Capabilities
- `json-extract`: detect and parse JSON-in-script payloads (Next.js `__NEXT_DATA__`, Nuxt, generic `application/json`) into structured product/list data, convert to synthetic markdown rows so the existing extraction template can consume it.

### Modified Capabilities
- `quality-gate`: paywall classifier recognizes jina error-stub patterns; thin-browser-response heuristic added for known-JS-heavy hosts.
- `browser-tier`: scroll-to-bottom + idle wait after `networkidle`; subprocess stderr routed to LDD diagnostics instead of inherited stderr.
- `extraction`: `max_content_chars` plumbed end-to-end so CLI / MCP callers can override the default.

## Impact

- **Code**: `src/a2web/packages/content_extract/` (new JSON pathway), `src/a2web/tiers/raw.py` + `src/a2web/tiers/browser.py` (JSON detection, scroll, stderr), `src/a2web/packages/quality_gate/` or wherever the classifier lives (paywall + thin-browser rules), `src/a2web/routers.py` (new CLI flag), `src/a2web/llm_resource.py` (plumb `max_content_chars` override).
- **Deps**: none. JSON parsing uses stdlib `json` + existing `selectolax` for `<script>` tag selection.
- **MCP / CLI surface**: `--max-content-chars` is a new optional Annotated kwarg on both tools — purely additive, not breaking.
- **Tests**: new fixtures for Trendyol-shape `__NEXT_DATA__`, NYT-paywall jina stub, Yandex Market-shape JSON blob, lazy-loaded scroll case. `tests/test_packages_independence.py` must still pass — the JSON extractor lives in `packages/` and stays domain-free.
- **Risk**: scroll-on-every-browser-fetch adds ~2s latency to browser-tier calls. Acceptable since browser tier is already the slow path. Mitigated by only scrolling when first-snapshot is thin.
