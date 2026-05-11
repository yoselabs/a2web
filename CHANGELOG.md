# Changelog

All notable changes to **a2web** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> First tagged release; entries summarize the full PR1–PR10 build.

## [Unreleased]

### v0.5 step 3 — micro-cleanups bundle (2026-05-12)

- **Three `*_hint` fields collapsed to `fc.operator_hints` accumulator.**
  Anywhere in the pipeline can append; `_build_response` consumes the list
  uniformly. Removes the pattern-duplication smell across `llm_unavailable_hint`
  / `browser_unavailable_hint` / any future "X unavailable" field.
- **`del settings` / `del ms` reserved-for-future stubs deleted.** Three
  parameters removed across `playbook.next_action_after_gate`,
  `playbook.next_action_after_tier`, and `ProxyPool.report`. YAGNI code
  gone.
- **`@runtime_checkable` dropped on `Tier` and `Handler` protocols** (kept
  on `Provider` and `EvalSystem` where contract tests rely on isinstance
  against the Protocol). Less decorator noise; static typing covers the
  rest.
- **`_resolve_env` moved into `ProxyEntry.url` pydantic validator.** Env
  interpolation (`${VAR}` → `os.environ[VAR]`) happens once at settings
  load instead of repeatedly at proxy-resolution time. `proxy/policy.py`
  and `proxy/pool.py` both gain trivial code (read `entry.url` directly).
  Kills a private-import `# type: ignore[attr-defined]` in `pool.py`.
- **`record_from_response` alias replaced** by `FetchResponse.to_log_record()`
  method. Lives next to the model it converts from. Caller goes from
  `await state.log_writer.write_record(record_from_response(response, input_url=url))`
  to `await state.log_writer.write_record(response.to_log_record(input_url=url))`.

### v0.5 step 2 — `packages/` scaffold (2026-05-12)

- **New `src/a2web/packages/` directory** with the microsofware contract:
  modules under `packages/` MUST NOT import from `a2web.<domain>`. Boundary
  types are owned by the package itself. Lives next to a `README.md` that
  documents the rule.
- **`tests/test_packages_independence.py`** — load-bearing invariant test
  that walks every `.py` under `packages/` and asserts zero domain imports.
  Catches drift in CI.
- **`browser_pool.py` relocated** from `src/a2web/browser/pool.py` to
  `src/a2web/packages/browser_pool.py`. First in-tree microsofware,
  validates the scaffold contract.

### v0.5 step 1 — a2kit v0.27.2 migration (2026-05-12)

**Resource pattern adopted (a2kit v0.27 canonical).** Every long-lived async
resource is now a class with sync `__init__`, internal `asyncio.Lock`, lazy
`_ensure()`, and idempotent `close()`. AppState fields are all non-Optional;
locks no longer leak to state.

- **New `SqliteResource`** wrapping `aiosqlite.Connection` + schema bootstrap.
  Replaces the previous Optional `state.sqlite` + startup-hook-opens dance.
- **New `LlmExtractorResource`** wrapping the Extractor + provider auto/anthropic
  fallback + ExtractionCache wiring. Returns `None` on permanent unavailability;
  caller branches and populates an operator hint without retrying construction.
- **`BrowserPool._ensure()`** — idempotent under internal lock with
  double-check. `start()` retained as deprecated alias.
- **DI-aware lifecycle hooks.** `@app.on_startup` / `@app.on_shutdown` take
  typed kwargs (`state: AppState`) — no `container.resolve(...)` ceremony,
  no `connection=None`, no `_app: a2kit.App` parameter.
- **Typed-event direct emit** via `await a2kit.ldd.event(ctx, EventInstance(...))`
  (a2kit 0.26.1). The `_emit` + `_event_payload` adapter shim is gone (~30 LOC).
- **`a2kit.testing.null_context()`** swapped in for direct `fetch(ctx=None)`
  callers; phase functions take non-Optional `ctx: a2kit.ToolContext`.
- **`Param("desc")` positional shorthand** on the URL parameter.

Closes all four gaps + both soft notes from `docs/history/A2KIT_FEEDBACK_v0.26.md`.
Net ~-95 LOC across `state.py` + `server.py` + `fetcher.py` (state.py alone
drops from 136 → 63 LOC).

### Added

- **`ClaudeCodeProvider`** — runs prompts through the user's Claude Code
  OS session via `claude-agent-sdk`. No `ANTHROPIC_API_KEY` required:
  inherits whatever the local `claude` CLI is logged into (OAuth
  subscription or API key). Implements the same `Provider` Protocol as
  `AnthropicProvider`, so the Extractor and Judge accept it
  transparently. Tools are disabled and `max_turns=1` so the model
  produces a single text completion — no file edits or MCP calls.

- **`llm_provider="auto"` default** — `AppState.ensure_llm_extractor`
  now tries `ClaudeCodeProvider` first and falls back to
  `AnthropicProvider` when the SDK or CLI is missing. Set
  `A2WEB_LLM_PROVIDER=anthropic` to skip the OS-session path and use
  the API key directly, or `A2WEB_LLM_PROVIDER=claude-code` to require
  it.

- **`claude-agent-sdk` added to the `[llm]` extra.** Installing
  `a2web[llm]` now ships both `anthropic` (for the API-key path) and
  `claude-agent-sdk` (for the OS-session path).

- **`benchmarks/.../judge.py`** prefers `ClaudeCodeProvider` by default;
  set `A2WEB_BENCH_PROVIDER=anthropic` to force the API-key path.

## [0.4.0] - 2026-05-11

The `a2web.llm` module — optional server-side LLM extraction +
LLM-as-judge primitive + matrix eval suite. Gated by the `[llm]` install
extra; bare `pip install a2web` is unchanged.

The headline trick (research/123): Claude Code's WebFetch runs Haiku
over the fetched markdown server-side and returns only the answer.
v0.4 makes a2web do the same — caller passes `ask=...` to the `fetch`
tool, gets back a tiny `extracted_answer` envelope. Calling agent's
context stays tiny.

### Added

- **`ask=` parameter on the `fetch` tool.** When set, a2web invokes an
  LLM extractor server-side after the existing content extract phase
  and populates `FetchResponse.extracted_answer` + `extraction`
  metadata. Default model is `claude-haiku-4-5-20251001` (matches
  Claude Code's WebFetch sub-call per research/123). Graceful when
  the `[llm]` extra is missing or `ANTHROPIC_API_KEY` is unset — the
  fetch still succeeds, `extracted_answer` stays None, and an operator
  hint with code `llm_unavailable` surfaces the actionable reason.

- **`src/a2web/llm/` module** — Extractor, Judge, prompts, providers,
  cache. Public surface:
  - `Extractor(provider, model, template, cache?)` — wraps a Provider
    with a frozen prompt template; returns `ExtractionResult`.
  - `Judge(provider, model)` — LLM-as-judge over (task, criteria,
    answer) tuples; returns `JudgeVerdict` (scores, overall, reached,
    reasoning, cost). Robust JSON parsing tolerates markdown fences
    and prose wrappers; `JudgeParseError` carries raw text on failure.
  - `Provider` Protocol + `AnthropicProvider` reference implementation
    with hardcoded pricing table for Haiku 4.5 / Sonnet 4.6 / Opus 4.7
    (populates `cost_usd`). Empty system content + thinking_disabled
    are first-class for WebFetch behavioral parity.
  - `PromptTemplate` frozen dataclasses: `WEBFETCH_DEFAULT_V1`
    (byte-for-byte the `Rb9` template from Claude Code's binary),
    `TERSE_V1` (compact variant), `JUDGE_V1` (strict-JSON judge).
  - `ExtractionCache` — sqlite-backed (content_hash, ask_hash,
    model_id, template_name) → answer LRU. Mirrors WebFetch's 15-min
    TTL (`sg5 = 900000ms`). Lives in the same sqlite file as the HTTP
    cache; schema created lazily so the no-extra install is unaffected.

- **`src/a2web/llm/eval/` module + `make eval`** — deterministic eval
  harness. EvalSuite runs (corpus × systems × judge) with bounded
  concurrency, writes dated `eval/runs/<timestamp>/` directories
  containing `results.tsv`, `manifest.json`, `leaderboard.md`,
  `cost.md`, `findings.md`, `corpus.frozen.yaml`, and per-cell trace
  dirs. Three systems out of the box:
  - `WebFetchBaseline` — faithful local reproduction of Claude Code
    WebFetch using the binary-extracted constants. Runs offline (no
    Claude Code session needed). Documented divergences: no domain
    preflight, no cross-host redirect break, no preapproved-host fast
    path, markdownify ≠ Turndown.
  - `A2WebDetail` — a2web `fetch(url)` without `ask=`; measures the
    "agent reads envelope, extracts in its own context" path.
  - `A2WebExtract` — a2web `fetch(url, ask=...)`; matches WebFetch's
    answer-only shape via server-side extraction.

- **`[llm]` install extra** — adds `anthropic`, `openai` (reserved for
  v0.5 OpenRouter), and `markdownify` (Turndown neighbor for
  WebFetchBaseline). `pip install a2web[llm]` enables `ask=` and the
  eval suite.

- **New Makefile targets**: `make eval` (full matrix), `make
  eval-baseline` (WebFetchBaseline only, drift detection), `make
  eval-detail` (a2web systems only, engine-only validation).

- **New settings on `AppSettings`**: `llm_provider` ("anthropic" in
  v0.4), `llm_model` (default `claude-haiku-4-5-20251001`),
  `llm_api_key_env`, `extraction_max_chars` (default 100,000 — matches
  WebFetch's `BD_`), `extraction_cache_ttl_s` (default 900 — matches
  WebFetch's `sg5`).

- **New models**: `ExtractionMeta` carrying per-fetch LLM metadata
  (model, template_name, tokens, cost, latency, cache_hit, truncated).
  `FetchResponse.extracted_answer: str | None` and `extraction:
  ExtractionMeta | None` (both default None — no schema change for
  callers not using `ask=`).

### Tests

- 50+ new scenarios across `test_llm_module.py`, `test_llm_judge.py`,
  `test_llm_eval_systems.py`, `test_llm_eval_suite.py`,
  `test_llm_cache.py`, `test_fetcher_ask.py`. All isolated via mock
  providers + in-memory sqlite + httpx MockTransport — no real API
  calls in the test suite.

### Migration notes

- Bare `pip install a2web` keeps working unchanged; `ask=` simply
  surfaces an `llm_unavailable` operator hint without the extra.
- Callers wanting `ask=` should `pip install a2web[llm]` and set
  `ANTHROPIC_API_KEY` (or whatever `llm_api_key_env` points at).

## [0.3.0] - 2026-05-11

Engine improvements driven by `benchmarks/vs-webfetch/2026-05-11/`.
Five of seven planned sections shipped (envelope diet + reach
reliability + Twitter handler); the last two (v0.4 benchmark code
migration, verification re-run) deferred. Remaining tracker:
`openspec/changes/v0.3-engine-improvements/`.

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

### Added

- **Twitter / X handler via Nitter rotation.** New site handler matching
  `x.com` / `twitter.com` status URLs. Reads `nitter_instances` from
  `AppSettings` (env `A2WEB_NITTER_INSTANCES`, comma-separated; also from
  YAML). Empty list = handler effectively disabled (matches the URL but
  `fetch` returns `no_match=True` so the orchestrator falls through to
  raw + browser tiers without errors). When configured, the handler
  shuffles the instance list per fetch and probes in order, with per-
  instance circuit breakers reusing the existing `purgatory` infra.
  First HTTP 200 with extractable content wins; all-fail → returns the
  last verdict (typically `connection_error`) for the orchestrator to
  escalate. Closes the X auth-wall gap that the gate fix exposed — the
  browser tier now dispatches on X status URLs but hits the login wall;
  Nitter sidesteps both problems.

### Fixed

- **Gate: block-page markers no longer false-positive on pages with substantive
  extracted content.** Real interstitial / block pages by definition return
  empty bodies; previously a "cf-chl-bypass" or "Just a moment" string anywhere
  in the HTML (security pages, cookie banners, compliance copy) was enough to
  flag the page. v0.3 requires `content_md < LENGTH_FLOOR` for any block-marker
  verdict to fire — the same length-gated rule Anubis already used. Surfaces on
  the benchmark as the Linear false-positive (1,152 chars extracted, marked
  `status=failed`).
- **Gate: broader JS-shell escalation to browser tier.** Previously the
  length_floor → browser path required the narrow `<noscript>enable JavaScript</noscript>`
  marker plus three `<script>` tags. v0.3 also escalates on any of: `id="__next"`
  (Next.js), `id="root"` (React), `id="app"` (Vue / generic), `id="react-root"`
  (Twitter / X), `window.__data__`, `window.__INITIAL_STATE__`, or any
  `<noscript>` tag — provided extracted content is below the floor and at
  least one `<script>` tag is present. Closes the "browser tier fires 0/20
  times" benchmark finding for the SPA-shell case.
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
