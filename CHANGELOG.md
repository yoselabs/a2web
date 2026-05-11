# Changelog

All notable changes to **a2web** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> First tagged release; entries summarize the full PR1–PR10 build.

## [Unreleased] - v0.3 engine improvements (partial)

Driven by `benchmarks/vs-webfetch/2026-05-11/` findings. Two of the seven
v0.3 sections shipped; remaining sections (gate escalation, Linear gate FP,
Twitter/Nitter, v0.4 prep) tracked in `openspec/changes/v0.3-engine-improvements/`.

### Changed (response envelope — opt-in for prior defaults)

- **`fit_md` no longer duplicates `content_md`.** v0.2 populated `fit_md` as
  a byte-for-byte copy of `content_md` (pruning filter is gone since v0.2;
  field was preserved for forward-compat). Reality: 19% of total payload
  tokens across the benchmark corpus, zero quality benefit. v0.3 returns
  `fit_md=None` until a future pruning filter ships. Field stays on the
  model.
- **`links` is opt-in via new `include_links: bool = False` param.** Was
  the largest line item (49% of total payload), dominated by aggregator/UI
  noise. Pass `include_links=True` for list-extraction tasks. Default-off
  saves ~50% of tokens on link-heavy pages with judge-score parity on
  17/20 benchmark URLs.
- **`diagnostics` is opt-in via new `debug: bool = False` param.** A new
  always-populated `diagnostics_summary: str` field carries a one-line
  `tier=X verdict=Y total_ms=Z` summary. Pass `debug=True` to get the
  full per-tier diagnostic trace. Default-off saves ~3% always-on tokens.
- **Net result on the benchmark corpus: 72% fewer tokens per fetch by
  default** (127k → 35.5k across 20 URLs; gh-trending alone dropped from
  27,167 to 1,011 tokens).

### Fixed

- **Reddit handler now falls back to `old.reddit.com` on `.json` failure.**
  Reddit's `.json` endpoint frequently 404s for threads that remain
  readable on old.reddit (UA gating, removed/quarantined quirks). The
  handler now: (a) attempts the JSON path first as before, (b) on 404 or
  empty thread (no title + no selftext + no comments), retries against
  `old.reddit.com<path>` with trafilatura extraction. Single extra GET
  only when the JSON path is empty/missing.

### Migration notes

Callers that relied on `links` or full `diagnostics` being present without
explicit opt-in must pass the new params. The `fit_md` change is purely a
defect fix — callers that read `fit_md` got the same content as
`content_md` and should switch to `content_md` directly.

## [0.2.0] - 2026-05-11

### Changed (internal architecture; wire surface unchanged)

- Migrated to a2kit v0.26: imperative `App` composition (no fluent
  builder chain), typed `app.singleton(T, factory=...)` DI,
  `@app.on_startup` / `@app.on_shutdown` / `@app.health_check`
  decorators replace the bespoke lazy+`atexit` lifecycle pattern.
- Typed LDD event registry — emit via `a2kit.ldd.event(PayloadType(...))`
  / `a2kit.ldd.report(...)` from anywhere in the pipeline; subscribe
  external consumers (OTel exporter, etc.) via `app.ldd.add_sink(...)`.
  The custom `anyio.MemoryObjectStream` fan-out bus and
  `mcp_progress_sink` helper are removed; `events/sinks.py` shrinks to
  the OTel forwarder.
- `TierResult` is now a typed `dataclass(slots=True)` with named fields
  (`pre_rendered: Rendered`, `from_archive`, `from_browser`,
  `js_executed`, `browser_wall_ms`, `browser_bytes`,
  `snapshot_age_days`, `operator_hint`, `no_match`, `skipped`,
  `handler_name`, `conditional_hit`, `archive_source`). The
  `tier_extras: dict[str, Any]` bag is removed across all call sites.
- Orchestrator (`fetcher.py`) split into a 12-line `_run_pipeline`
  coordinator + six named phase functions (`_phase_cache_check`,
  `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate`,
  `_phase_cache_write`) with a single `FetchContext`
  `dataclass(slots=True)` threading state instead of 20+ locals.
- Tests use a2kit's in-process client (`a2kit.testing.client(app)` +
  `a2kit.testing.peek`) instead of the prior `bootstrap_state_for_test`
  / `teardown_state_for_test` helpers.

### Added

- Architecture retrospective at
  `openspec/changes/archive/2026-05-11-migrate-to-a2kit-v026-and-simplify/retrospective.md`
  capturing the four OSS swaps researched-but-deferred (hishel,
  aiometer, purgatory-for-proxy, stdlib-RotatingFileHandler) and the
  lesson: hand-rolled async tends to beat sync-wrapped stdlib even when
  the library nominally covers the use case.

### Removed

- `htmldate` dependency — `trafilatura.extract_metadata()` now returns
  the published date alongside title/author in one call.
- `src/a2web/extract/pruning_filter.py` (in-tree block-density `fit_md`
  builder) — the `FetchResponse.fit_md` field remains for forward-compat
  but is now always `None` until a replacement ships in v0.3.
- `src/a2web/events/bus.py`, the `mcp_progress_sink` helper, and the
  `bootstrap_state_for_test` / `teardown_state_for_test` test helpers —
  all superseded by a2kit v0.26 surface.

### Deferred (see `BACKLOG.md`)

- Phase D workspace packaging (proxy-pool, browser-pool, block-detector).
  All three are sensible extraction candidates but no external reuse
  signal yet justifies the mechanical cost.
- Four OSS swaps (above) — each documented with the specific
  API/semantic mismatch that killed it.

## [0.1.0] - 2026-05-10

### Added

- Single-tool MCP/CLI surface `WebRouter.fetch(url)` returning a typed
  `FetchResponse` (envelope + LDD diagnostics + operator hints) (PR1, PR2).
- Tier cascade orchestrator with closed-enum verdicts, per-fetch action
  caps, and pluggable Strategy + Registry tiers (PR3, PR4).
- `raw` tier (curl_cffi TLS impersonation) and `jina` tier (r.jina.ai
  reader, bearer-optional, deny-list short-circuit) (PR3, PR7a).
- Site handlers as tier-0: `reddit` (`.json?limit=500`), `hn` (Algolia)
  (PR5); `arxiv` (export.arxiv.org Atom), `wikipedia` (REST page/html),
  `github` (REST API, optional `A2WEB_GITHUB_TOKEN`) (PR8).
- Quality gate with closed-enum verdicts and `suggested_tier` hints
  (`browser`, `tls_impersonate`) covering paywall / block-page /
  anti-bot / length-floor / content-type / cf_iuam / anubis / turnstile
  / akamai_bmp / js_required signals (PR3, PR7c).
- `archive` tier dispatched out-of-band on playbook `RetryViaArchive`:
  Wayback CDX + archive.ph hedged via anyio task group; Wayback chrome
  stripped before trafilatura; results carry `from_archive=True` and
  `snapshot_age_days` (PR7b).
- `browser` tier dispatched out-of-band on gate `suggested_tier="browser"`:
  Camoufox via lazy `BrowserPool`, page-per-fetch, persistent per-host
  context, LRU + idle eviction, 30s page budget; missing dep group
  surfaces as a graceful `connection_error` rather than a crash (PR7c).
- Trafilatura + htmldate extraction with OG/JSON-LD metadata and an
  in-tree block-density `fit_md` pruning filter; sync work wrapped in a
  single `asyncio.to_thread` chokepoint (PR3, PR6).
- Conditional-GET sqlite cache (etag / last-modified / content-hash
  dedup); cache writes gated on quality verdict; archive results never
  cached (PR4, PR7b).
- Proxy pool with first-match-wins route policy, host-glob + tier match,
  AND-composition, `${ENV_VAR}` resolution, alive/quarantined/dead
  health states, and per-tier retry walks (PR7d).
- Autonomous-action playbook (paywall→archive, block→archive,
  cf-403→archive, arxiv-pdf→abs, `RewriteUrl` capped at 1) with the
  after-tier no-op closed (PR7b, PR7d).
- Diagnostic event bus (`anyio.MemoryObjectStream` fan-out): MCP
  progress sink (`ctx.event` + `ctx.report_progress`) and an OTel sink
  emitting one span per `*Ended` event (no-op when SDK absent) (PR6,
  PR7a).
- Lazy + `atexit` lifecycle pattern for sqlite, browser pool, and proxy
  pool — required because a2kit v0.23 exposes no lifespan hook (PR7a,
  PR7c, PR7d).
- NDJSON request log with size-based rotation and gzip on rollover; one
  record per fetch; lazy-open writer; best-effort writes that surface
  failures via `operator_hints[code=log_write_failed]` (PR9).
- Settings layer: `AppSettings(BaseSettings)` from `A2WEB_*` env + optional
  YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml`; secrets are env-only
  (PR1, PR7a, PR7d).
- Optional `[browser]` extras for Camoufox / Playwright; bootstrap via
  `make bootstrap` (`uv sync --all-extras`) (PR7c).
- `CHANGELOG.md` and `BACKLOG.md` at repo root; `BACKLOG.md` consolidates
  every known deferred item across PR7e / PR8b / PR10b / v0.2 / v0.3+.

### Removed

- The pre-release `LogsRouter` MCP/CLI surface (`replay` / `tail` / `grep`)
  and its supporting `log/reader.py` + duration parser. The on-disk
  NDJSON log itself is unchanged; operators inspect it directly with
  `tail` / `grep` / `jq`. Replay-from-cache is deferred to PR10b — see
  `BACKLOG.md`.

[0.1.0]: https://github.com/yoselabs/a2web/releases/tag/v0.1.0
