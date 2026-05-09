## Why

Two PRs in, a2web still doesn't fetch anything. PR3 makes one URL work end-to-end: a generic blog post comes back as readable markdown with title/byline/published date, and the result is cached so the second call is sub-millisecond. Every later PR (Jina, archive, browser, site handlers) plugs into the same pipeline shape; getting it right once here means PR5/7 become drop-ins instead of refactors. PR3 also establishes the Tier protocol, the quality gate, and the cache-write invariant — three pieces every later tier depends on.

## What Changes

- Add `src/a2web/tiers/__init__.py` with a `Tier` protocol (`async fetch(url, *, state) -> TierResult`) and a `TierRegistry` exposing ordered iteration. PR3 registers exactly one tier (`raw`); PR5+ append.
- Add `src/a2web/tiers/raw.py` — `RawTier` using `curl_cffi` with Chrome JA3/JA4 TLS impersonation, sane timeout (default 10s), respect `state.settings.default_ua`. Returns body bytes + response metadata; no extraction here.
- Add `src/a2web/extract/trafilatura_ext.py` — sync `extract_markdown(html: str, url: str) -> ExtractResult` wrapped via `asyncio.to_thread` at the call site. Uses trafilatura's `extract` with markdown output + JSON metadata.
- Add `src/a2web/extract/htmldate_ext.py` — sync `find_published(html: str, url: str) -> date | None` and `find_updated`, wrapped via `asyncio.to_thread`.
- Add `src/a2web/extract/metadata.py` — pure parser for OpenGraph + Twitter cards + JSON-LD; returns the `meta: dict[str, str]` slice of the envelope. Sync, pure function.
- Add `src/a2web/gate/__init__.py` and `src/a2web/gate/block_detector.py` — pure functions returning a closed-enum `Verdict`. Implements: length floor (<500 chars after extraction), block-page regex set (`Just a moment`, `cf-chl-bypass`, `Attention Required`, `Enable JavaScript`, `Access denied`, `Are you a robot`, `_Incapsula_`, `px-captcha`, `You've been blocked`, `network security`), Anubis script-src marker, content-type mismatch.
- Add `src/a2web/cache/__init__.py` and `src/a2web/cache/sqlite_cache.py` — `aiosqlite` connection + DDL, conditional-GET (etag, last-modified, freshness), content-hash dedup, TTL per host class. Cache key = `(url, profile_hash)`. **Block pages NEVER enter the cache** (gate runs before write).
- Add `src/a2web/fetcher.py` — orchestrator (≤200 lines for PR3): cache lookup → tier loop → extraction → metadata → gate → cache write. Emits `Diagnostic` rows as it goes. Single retry layer at HTTP level with `purgatory` per-host breaker (PR7 adds proxy/global).
- Add `src/a2web/utils/time.py` — `fmt_dur(ms: int) -> str` adaptive formatter (`<1s→Xms`, `1-7s→X.Xs`, `7-60s→Xs`, `≥60s→MmSs`). Used everywhere a duration prints.
- Wire into `AppState`: PR3 fills `sqlite: aiosqlite.Connection`. The connection is opened on first use and closed via a teardown hook in `register_state` (we add a minimal lifespan helper here, not the full TaskGroup PR4 will ship).
- Replace the `WebRouter.fetch` stub: now does real work via `fetcher.fetch(url, state=state)`. Returns the populated `FetchResponse` envelope (real `content_md`, `title`, `byline`, `published`, `meta`, `links`, `headings`, `diagnostics`).
- Tests: unit tests for each module (gate verdicts, metadata parsing, fmt_dur), integration test against a fixed local HTML fixture (no network in CI), one network-marked test against example.com (skipped by default; runs locally with `pytest -m network`).

## Capabilities

### New Capabilities

- `tier-pipeline`: Tier protocol + registry, gate verdicts, cache-write invariants, Diagnostic emission contract.
- `raw-tier`: curl_cffi-backed HTTP fetch with TLS impersonation.
- `extraction`: trafilatura + htmldate + OG/JSON-LD pipeline (sync, `asyncio.to_thread` at call site).
- `cache`: sqlite conditional-GET cache with quality-gate write protection.

### Modified Capabilities

- `app-composition`: `WebRouter.fetch` now invokes the real pipeline; the response includes populated content/diagnostics. Stub fields (`tier="stub"`, placeholder narrative) are gone.
- `app-state`: `AppState.sqlite` is no longer `None` — it carries a live `aiosqlite.Connection`. Lifecycle: opened lazily on first `register_state`, closed via the same module's teardown hook on process exit.

## Impact

- **Code**: 8 new files, 3 modified. ~600–800 LOC total (driven by the Strategy protocol + small modules).
- **Public surface**: `FetchResponse` payload becomes meaningful — clients see real `content_md`, real `tier="raw"`, real diagnostics. Tool *signature* doesn't change.
- **Dependencies**: `curl_cffi`, `trafilatura`, `htmldate`, `selectolax`, `aiosqlite`, `purgatory` are already in `pyproject.toml`. No new top-level deps.
- **Performance**: cold-start cache miss on a 50KB blog ≈ 200–600ms (network-dominated); warm cache hit <5ms. We don't optimize further until profiling reveals a bottleneck.
- **Network in tests**: by default, no network in CI — unit tests use canned HTML fixtures. The single network test is `@pytest.mark.network` and skipped unless explicitly requested.
- **Lifespan**: PR3 adds a *minimal* teardown for the sqlite connection (atexit-style). Full anyio TaskGroup + FastMCP lifespan still ship in PR4 with the NDJSON log writer; PR3's teardown is a stop-gap and will fold into PR4's hook.
- **Cache invariant**: block pages never enter the cache. This is enforced in `fetcher.py` (gate verdict gates the write) and asserted in tests. Future PRs MUST preserve this.
