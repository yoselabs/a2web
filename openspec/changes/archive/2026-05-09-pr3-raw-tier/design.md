## Context

PR1/2 shipped the App + envelope + DI seam. PR3 implements the actual fetch path. The work spans HTTP, extraction, validation, and persistence — four small modules that have to compose without each module knowing the others. We anchor on the Strategy + Registry pattern from `v0.1-patterns.md`: the orchestrator is the only place tier order is encoded; tiers themselves are pure functions of `(url, state) → TierResult`. The cache is a write-through with a non-negotiable invariant (block pages never enter it). All sync extraction libraries are wrapped via `asyncio.to_thread` at exactly one chokepoint per module so `ASYNC100/210/230` lint stays green.

## Goals / Non-Goals

**Goals:**
- `a2web web fetch --url=https://example.com` returns a real `FetchResponse` with non-empty `content_md` extracted from the live response.
- The Tier protocol is locked: PR5 (site handlers), PR7 (Jina/archive/browser) plug in by registering a new tier, no orchestrator edit.
- Cache hits are observable (`cache="hit"`, sub-5ms `total_ms`).
- Block pages produce `status="failed"` with verdict in `diagnostics`, and are NOT cached.
- All sync extraction libs are wrapped exactly once per module; CI green on ASYNC lint.
- `fmt_dur(ms)` is the only place duration strings are produced (lint-checked grep in CI).

**Non-Goals:**
- No proxy support (PR7).
- No browser tier, no Jina, no archive (PR7).
- No site handlers (PR5).
- No `fit_md` pruning filter (PR6).
- No autonomous-action playbook (PR6).
- No streaming progress notifications (PR6 alongside the event bus).
- No NDJSON request log (PR4).
- No retries beyond the per-host purgatory breaker — no proxy retries, no tier-level retries (PR7).
- No coverage of paywall-specific text. Length floor + the regex set + Anubis marker is enough for PR3.

## Decisions

### Decision 1: Tier protocol as a Python `Protocol`, not an ABC

```python
class Tier(Protocol):
    name: str
    async def fetch(self, url: str, *, state: AppState) -> TierResult: ...
```

`TierResult` is a `dataclass(slots=True)` carrying `body: bytes`, `content_type: str`, `status_code: int`, `final_url: str`, `headers: dict[str, str]`, plus a `verdict: Verdict` set by the gate (the tier itself returns `Verdict.ok` or `connection_error`/`timeout`/`rate_limited` — anti-bot detection happens in the gate, post-extraction).

**Alternatives considered:**
- ABC with `@abstractmethod` → forces explicit inheritance; PR5/7 would have to import the base class. Rejected: protocols are duck-typed and play nicely with closures and tests.
- Plain async function (no protocol) → loses the `name` discriminator. Rejected.

### Decision 2: Registry is a `dict[str, Tier]` with explicit ordering

```python
TIER_ORDER = ("raw",)  # PR3
REGISTRY: dict[str, Tier] = {"raw": RawTier()}
```

PR5 prepends `"site_handler"`, PR7 inserts `"jina"`, `"archive"`, `"browser"` in fixed positions. Order is data, not class hierarchy — `fetcher.py` reads `TIER_ORDER` and stops at first `Verdict.ok` after gate.

**Alternatives considered:**
- Priority-based (each tier has a `priority: int`) → drift surface (two tiers with same priority? what now?). Rejected.
- Topological sort over capability tags → over-engineered for ≤6 tiers. Rejected.

### Decision 3: One sync chokepoint per extraction module

`trafilatura`, `htmldate`, `selectolax` are sync libraries. Per `CLAUDE.md`: wrap once, at the boundary. Each `extract/*.py` exposes one async-facing function:

```python
# extract/trafilatura_ext.py
def _extract_sync(html: str, url: str) -> ExtractResult: ...  # private sync impl

async def extract_markdown(html: str, url: str) -> ExtractResult:
    return await asyncio.to_thread(_extract_sync, html, url)
```

The fetcher only calls the async wrappers. Lint catches blocking calls in async paths; the chokepoint discipline keeps it satisfied without per-call `to_thread` noise.

### Decision 4: Cache schema is one table, content-hash dedup, profile-scoped

```sql
CREATE TABLE IF NOT EXISTS cache (
    url            TEXT NOT NULL,
    profile_hash   TEXT NOT NULL,        -- hash of relevant settings (default_ua, stealth, …)
    etag           TEXT,
    last_modified  TEXT,
    fetched_at     INTEGER NOT NULL,     -- unix seconds
    expires_at     INTEGER NOT NULL,     -- unix seconds; freshness window
    status_code    INTEGER NOT NULL,
    content_type   TEXT,
    content_hash   TEXT NOT NULL,        -- sha256 of body
    body           BLOB NOT NULL,        -- gzip'd raw bytes
    PRIMARY KEY (url, profile_hash)
);
CREATE INDEX IF NOT EXISTS cache_content_hash ON cache(content_hash);
```

Profile hash makes the cache safe across stealth toggles (different UA → different fingerprint → different cached body). Content hash dedups across URLs that yield identical bodies (e.g., redirects). TTL comes from `state.settings.cache_ttl_*`. Live-only hosts (`state.settings.live_only_hosts`) bypass cache writes/reads.

**Alternatives considered:**
- Separate tables per content class (article/static/live) → premature normalization. One table + TTL column wins.
- Filesystem cache (one file per URL) → harder to query, harder to dedup. Rejected.
- Redis → adds infra. Rejected for v0.1.

### Decision 5: Gate runs after extraction, before cache write

The integration plan says "Quality gate runs after every tier, before cache write." We implement it as: `gate.evaluate(extract_result, headers) -> Verdict`. The gate does NOT see raw bytes — it sees the extracted markdown text and the response headers. This makes block detection deterministic and unit-testable without HTTP.

If the verdict is anything other than `Verdict.ok`, the orchestrator:
1. Marks `FetchResponse.status = FetchStatus.failed` (or `partial` if some content survived but quality is low).
2. Skips the cache write.
3. Adds the verdict to `diagnostics`.
4. PR3: returns failure (no further tiers). PR5/7: escalates to the next tier.

### Decision 6: One retry layer — per-host purgatory breaker only

The integration plan calls out 5 retry layers (connection / HTTP / proxy / tier / handler). PR3 ships **only** the per-host breaker. Connection-level retries are off — `curl_cffi` already handles transient TLS resets. Tier-level escalation is "no, we have one tier." HTTP retries (5xx) are deferred to PR7 alongside proxy retries — they share the same machinery.

The breaker is `purgatory.AsyncCircuitBreaker` keyed by host, threshold 5 failures / 60s, recovery 30s. Configured via `state.breakers` (initialized in `register_state`).

### Decision 7: sqlite connection lives on `AppState`; teardown via atexit

PR3 needs the sqlite connection across calls — opening per-fetch is wrong. Lifecycle:

```python
# state.py update:
def register_state(app, *, settings=None) -> a2kit.App:
    state = AppState(settings=settings or get_settings())
    state.sqlite = await_blocking(_open_sqlite_with_schema(state.settings))
    atexit.register(lambda: _sync_close(state.sqlite))
    app.provide(AppState, lambda: state)
    return app
```

This is the "stop-gap" the proposal mentions. PR4 replaces `atexit` with a proper anyio TaskGroup managed by FastMCP lifespan. The atexit hook is simple, unsurprising, and terminates the connection cleanly on process exit. We accept it for one PR.

`await_blocking` is a small helper that runs an async coroutine to completion at registration time (synchronous context). Implementation: `asyncio.run(coro)` if no loop; else schedule and wait. The setup is one-shot at import — performance is irrelevant.

### Decision 8: Network test uses a marker, default-skipped

```python
# tests/test_e2e.py
@pytest.mark.network
async def test_fetch_example_com() -> None:
    ...
```

Add `markers = ["network: requires network"]` to `pyproject.toml`. Default test run skips it (`addopts = "-m 'not network'"`). Local dev runs `pytest -m network` to exercise it.

The unit-tested path uses canned HTML fixtures in `tests/fixtures/` — one well-formed blog post, one block page (Cloudflare interstitial), one short page that trips the length floor. Three fixtures, one per gate verdict path.

### Decision 9: `fmt_dur` lives in `utils/time.py`, single import in CI

Every duration string in the envelope, diagnostics, and narrative goes through `fmt_dur(ms)`. To enforce: a one-line CI check `grep -rE '"[0-9]+\.?[0-9]*[ms|s]"' src/a2web | grep -v 'fmt_dur'` should return nothing. We don't ship the grep yet (would slow `make check`); for PR3 it's convention + reviewer's eye.

## Risks / Trade-offs

- **[Risk] Tier protocol shape locks early; PR5/7 may want different signatures** → Mitigation: keep `TierResult` minimal — body+headers+status. Anything richer (extracted JSON, transcripts) is a tier-private detail attached via a `tier_extras: dict[str, Any]` field that PR5+ can populate without changing the protocol.
- **[Risk] Cache schema requires migration when PR7 adds proxy column** → Mitigation: schema includes `profile_hash`, which already varies on stealth toggle. Proxy choice will fold into `profile_hash`. Migration in PR7 = drop+recreate is acceptable for v0.1.
- **[Risk] `atexit`-based teardown leaks if process is `kill -9`'d** → Mitigation: aiosqlite uses WAL mode, fsync on commit; data integrity survives. PR4's TaskGroup hook lands within the week.
- **[Risk] curl_cffi TLS impersonation breaks on some hosts** → Mitigation: PR3 uses Chrome120 default; if a host fails, surface the verdict (`anti_bot`) and fail loudly. PR7 adds tier escalation; PR3 doesn't paper over.
- **[Risk] trafilatura miss-extracts well-formed pages** → Mitigation: PR3 uses trafilatura defaults; if extraction returns <100 chars on a 50KB page, the gate trips `length_floor` and we fail the fetch. PR6 adds a readability fallback.
- **[Risk] Quality-gate regex set produces false positives on legitimate content** → Mitigation: regexes are tight (`Just a moment`, `_Incapsula_` are very specific). False positives on a real article would surface in the network test loop; we tune as needed.

## Migration Plan

- No external migration. First fetch landing means clients see a different (richer, real) envelope from the same tool. No version bump on the public schema.
- Rollback: `git revert <PR3 commit>` returns to PR2's stub. The sqlite cache file at `~/.a2web/cache.sqlite` becomes orphaned but causes no harm (a fresh install would create it again).
