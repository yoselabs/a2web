## 1. Tier protocol — `src/a2web/tiers/__init__.py`

- [x] 1.1 Define `Tier(Protocol)` with `name: str` and `async def fetch(self, url: str, *, state: AppState) -> TierResult`
- [x] 1.2 Define `TierResult` as `@dataclass(slots=True)` with body/content_type/status_code/final_url/headers/tier_extras/verdict fields
- [x] 1.3 Declare `TIER_ORDER: tuple[str, ...] = ("raw",)` and `REGISTRY: dict[str, Tier] = {"raw": RawTier()}`
- [x] 1.4 Module exposes `Tier`, `TierResult`, `TIER_ORDER`, `REGISTRY` at top level

## 2. Raw tier — `src/a2web/tiers/raw.py`

- [x] 2.1 Implement `RawTier` with `name = "raw"`
- [x] 2.2 Use `curl_cffi.requests.AsyncSession(impersonate="chrome120")` (or current default)
- [x] 2.3 GET with `User-Agent` from `state.settings.default_ua`, default 10s timeout
- [x] 2.4 Map curl_cffi exceptions and HTTP statuses to closed `Verdict` enum (connection_error, timeout, not_found, rate_limited, content_type_mismatch, ok)
- [x] 2.5 Honor conditional GET: when `state.sqlite` has a row for `(url, profile_hash)`, send `If-None-Match` / `If-Modified-Since`. On 304 return `tier_extras["conditional_hit"] = True` with body from cache
- [x] 2.6 Use the per-host breaker from `state.breakers.get(host)` — open breaker → `Verdict.connection_error` without issuing the request

## 3. Extraction modules

- [x] 3.1 `src/a2web/extract/__init__.py` (empty re-export module)
- [x] 3.2 `src/a2web/extract/trafilatura_ext.py` — `_extract_sync(html, url) -> ExtractResult` private; `async extract_markdown(html, url)` wraps via `asyncio.to_thread`. Define `ExtractResult` as `@dataclass(slots=True)` with content_md/title/byline/headings/links/score
- [x] 3.3 `src/a2web/extract/htmldate_ext.py` — `_find_published_sync` / `_find_updated_sync` privates; async wrappers via `asyncio.to_thread`
- [x] 3.4 `src/a2web/extract/metadata.py` — pure sync `parse_metadata(html: str) -> dict[str, str]` using selectolax for HTML parsing. Flatten OG/Twitter/JSON-LD with dot-keys. Skip None/missing values

## 4. Quality gate

- [x] 4.1 `src/a2web/gate/__init__.py` (empty re-export)
- [x] 4.2 `src/a2web/gate/block_detector.py` — `evaluate(extract: ExtractResult, headers: dict, content_type: str) -> Verdict`. Pure function, no I/O
- [x] 4.3 Length floor: `len(extract.content_md) < 500` → `Verdict.length_floor`
- [x] 4.4 Block regex set: `Just a moment`, `cf-chl-bypass`, `Attention Required`, `Enable JavaScript`, `Access denied`, `Are you a robot`, `_Incapsula_`, `px-captcha`, `You've been blocked`, `network security` → `Verdict.block_page_detected`
- [x] 4.5 Anubis script-src marker → `Verdict.anti_bot` with subsystem hint
- [x] 4.6 Content-type mismatch (HTML expected, got JSON / non-HTML) → `Verdict.content_type_mismatch`
- [x] 4.7 All else → `Verdict.ok`

## 5. Cache — `src/a2web/cache/sqlite_cache.py`

- [x] 5.1 Define `cache` table DDL with `(url, profile_hash, etag, last_modified, fetched_at, expires_at, status_code, content_type, content_hash, body)` and PK + content_hash index
- [x] 5.2 `_open_sqlite_with_schema(settings) -> aiosqlite.Connection` opens DB at `~/.a2web/cache.sqlite` (override via `A2WEB_CACHE_DIR`), enables WAL, creates table+index if missing
- [x] 5.3 `compute_profile_hash(settings) -> str` — stable hash of `default_ua` + `stealth` (PR7 will fold proxy ids in)
- [x] 5.4 `async cache_get(conn, url, profile_hash) -> CacheRow | None` — returns row only when `expires_at > now`; gunzips body
- [x] 5.5 `async cache_put(conn, url, profile_hash, *, etag, last_modified, status_code, content_type, body, ttl_s)` — inserts/replaces, gzips body, computes content_hash
- [x] 5.6 Live-only hosts (`state.settings.live_only_hosts`) bypass both read and write — orchestrator checks the host before calling

## 6. Time helper — `src/a2web/utils/time.py`

- [x] 6.1 Add `src/a2web/utils/__init__.py` (empty)
- [x] 6.2 Implement `fmt_dur(ms: int) -> str` per the four-tier rule
- [x] 6.3 Use `fmt_dur` for every duration string in fetcher narrative + Diagnostic.dur_ms display + total_ms display

## 7. Orchestrator — `src/a2web/fetcher.py`

- [x] 7.1 Define `async fetch(url: str, *, state: AppState) -> FetchResponse`
- [x] 7.2 Phase 1 — cache check: live-only host? → bypass. Else `cache_get` and short-circuit on hit (set `cache="hit"`, populate `tier_extras["from_cache"]`, run extraction on cached body)
- [x] 7.3 Phase 2 — tier loop over `TIER_ORDER`: invoke each tier, build `Diagnostic` row with `t_ms` offset and `dur_ms`. Stop at first `Verdict.ok` post-gate
- [x] 7.4 Phase 3 — extraction: `extract_markdown` + `find_published` + `find_updated` + `parse_metadata`. Skip extraction on conditional 304 (reuse cached body's prior extraction — for PR3 simplicity, re-extract from cached body)
- [x] 7.5 Phase 4 — gate: `evaluate(extract, headers, content_type)`. If verdict != ok, mark response failed/partial, append diagnostic, skip cache write
- [x] 7.6 Phase 5 — cache write: gate-passed only; `cache_put` with TTL from `state.settings.cache_ttl_*` based on content_type heuristic (article vs static)
- [x] 7.7 Build `FetchResponse` with all fields populated; narrative summarizes via `fmt_dur(total_ms)` + tier name + cache state + verdict
- [x] 7.8 Keep this file ≤200 LOC; if it grows past, split into `_pipeline.py` helpers

## 8. State updates — `src/a2web/state.py`

- [x] 8.1 Update `AppState`: `sqlite` field type tightens from `Optional[aiosqlite.Connection]` to `aiosqlite.Connection | None` (no signature change at the dataclass level; lifecycle changes)
- [x] 8.2 Add `BreakerRegistry` (lightweight wrapper holding `dict[str, AsyncCircuitBreaker]` + `get(host)` method that lazy-creates breakers)
- [x] 8.3 Update `register_state` to: open sqlite via `_open_sqlite_with_schema`, build breaker registry, register `atexit` close hook
- [x] 8.4 `await_blocking` helper that runs an async coroutine to completion at registration time (synchronous context). Use `asyncio.run` if no loop; else create a one-shot loop. Document why this is the stop-gap before PR4's TaskGroup hook

## 9. Router wire-up — `src/a2web/routers.py`

- [x] 9.1 Replace stub body with `from a2web.fetcher import fetch as orchestrate`; tool body becomes `return await orchestrate(url, state=state)`
- [x] 9.2 Remove the placeholder `narrative` constant (now produced by orchestrator)

## 10. Tests — fixtures

- [x] 10.1 `tests/fixtures/blog.html` — well-formed blog post with title, byline, OG tags, article body, JSON-LD (~5KB)
- [x] 10.2 `tests/fixtures/cloudflare_block.html` — Cloudflare interstitial trigger (`Just a moment`, `cf-chl-bypass`)
- [x] 10.3 `tests/fixtures/short_page.html` — <500 chars after extraction (length-floor case)
- [x] 10.4 `tests/fixtures/anubis.html` — Anubis script-src marker

## 11. Tests — unit

- [x] 11.1 `tests/test_fmt_dur.py` — five cases (sub-second, 1.0–7.0s, 7–60s, ≥60s, zero)
- [x] 11.2 `tests/test_metadata.py` — OG-only, JSON-LD-only, both, neither
- [x] 11.3 `tests/test_gate.py` — each `Verdict` path against the appropriate fixture
- [x] 11.4 `tests/test_extract.py` — trafilatura on blog fixture; htmldate on blog fixture (date present and absent cases)
- [x] 11.5 `tests/test_cache.py` — schema creation, put/get round-trip, profile_hash isolation, live-only bypass, expiry

## 12. Tests — integration

- [x] 12.1 `tests/test_fetcher.py` — using a mock Tier returning the blog fixture, fetcher produces a populated `FetchResponse` with `tier="mock"`, `status=ok`, non-empty `content_md`, populated `meta` and `headings`
- [x] 12.2 `tests/test_fetcher.py` — block-page fixture → `status=failed`, `verdict=block_page_detected`, no cache row written
- [x] 12.3 `tests/test_fetcher.py` — cache-hit path: first call writes; second call reads cache and returns `cache="hit"` with no tier invocation
- [x] 12.4 `tests/test_fetcher.py` — live-only host bypasses cache fully

## 13. Tests — network (default-skipped)

- [x] 13.1 Add `markers = ["network: requires network"]` to `[tool.pytest.ini_options]`; default `addopts` includes `-m 'not network'`
- [x] 13.2 `@pytest.mark.network async def test_e2e_example_com()` — fetches `https://example.com`, asserts `status=ok`, `tier=raw`, `len(content_md) > 100`

## 14. Quality gate

- [x] 14.1 `make lint` clean (especially ASYNC100/210/230 — sync chokepoint discipline)
- [x] 14.2 `make ty` clean
- [x] 14.3 `make test` green, coverage ≥85%
- [x] 14.4 `make check` clean

## 15. Smoke

- [x] 15.1 `uv run a2web web fetch --url=https://example.com` returns a JSON envelope with non-empty `content_md`
- [x] 15.2 Second invocation hits the cache (`cache=hit`, `total_ms<50`)
- [x] 15.3 `uv run a2web serve --transport=stdio` `tools/list` still shows `fetch` with `url` only

## 16. Docs + commit

- [x] 16.1 Update `CLAUDE.md`: flip `(PR3)` markers off for `tiers/raw.py`, `extract/`, `gate/`, `cache/`, `fetcher.py`. Document the sync-chokepoint pattern + cache invariant
- [x] 16.2 Update README quick-start with example output of a real fetch
- [x] 16.3 Single commit "PR3: raw tier end-to-end — first real fetch lands"
- [x] 16.4 Hand off to PR4 (NDJSON log + `a2web logs` CLI + lifespan hook replacing atexit)
