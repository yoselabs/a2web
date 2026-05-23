# Changelog

All notable changes to **a2web** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> First tagged release; entries summarize the full PR1–PR10 build.

## [Unreleased]

## [0.15.0] — 2026-05-23

### Added

- **Handler subsystem unification.** The `handler-subsystem-unification` change resolves three issues surfaced in live evaluation of the just-shipped forum/listing-extraction work: DiscourseHandler failing on Cloudflare-fronted hosts (`linux.do` got an anti-AI banner), HTML entities surfacing raw in Discourse titles (`&rsquo;`), and the generic record renderer flattening the heading the detector had already located.
- **`packages/http_fetch/` — shared `fetch_bytes` primitive.** One async callable — `fetch_bytes(url, *, headers, timeout_s, proxy_url=None, cookies=None, conditional_extras=None, breaker=None) -> FetchOutcome` — owns every HTTP fetch for `RawTier`, `ArchiveTier`, and all nine site handlers. Backed by `curl_cffi.AsyncSession` with Chrome JA3/JA4 impersonation, proxy plumbing, per-host circuit-breaker context, conditional-GET via `If-None-Match` / `If-Modified-Since`, and closed-verdict mapping on the returned `FetchOutcome`. Handlers no longer construct `httpx.AsyncClient`; the test seam now is the transport seam, so monkeypatching cannot hide a transport-layer regression.
- **`packages/html_fragment/` — shared HTML-fragment converter.** `to_markdown(html, *, base_url=None)` and `to_text(html)`, lxml-backed, link-preserving, entity-decoded, nbsp-folded. Replaces four hand-rolled regex strippers (discourse `_cooked_to_md`, habr `_html_to_md` + `_text_of`, v2ex `_html_to_md`, hn `_strip_html`). Fixes the `fancy_title` entity-decode class of bug everywhere at once.
- **Live handler probe — `make handler-probe`.** Async entrypoint walking `_HANDLERS` against a representative URL per handler via real network (no monkeypatching), asserting `verdict == ok` AND non-empty `pre_rendered.content_md`. Loud-failure when a registered handler is missing from the `_PROBE_URLS` map. Deliberately not in `make check` — runs when you change transport, render, or handler routing. `linux.do` PASSES, demonstrating the architectural fix.
- **Structure-aware `Record` rendering.** The record-extract `Record` boundary type gains `heading_text: str | None` and renames `primary_link` → `heading_link`. The renderer leads with `- [heading_text](heading_link)` (or `- heading_text` when no link), then the body (heading text peeled from the smush), then the remaining links. Lobste-style records read as `[title](url)\n  meta` instead of the flat smush; sites without a detected heading fall back to the legacy text-led row.
- **Output benchmark — re-runnable, package-resident.** The `benchmark-harness` change folds the benchmark into the maintained `src/a2web/llm_eval/` harness so it survives envelope changes instead of rotting as dated throwaway scripts. Each (URL, system) cell is scored on four axes: answer quality (judge), token cost (per-field tokens of the response envelope the agent reads), output clarity (judge), and data-contract conformance (deterministic envelope field-presence check). A `next_links_picked_correctly` judge axis is applied to listing URLs. The corpus at `eval/corpus.yaml` emphasizes the tricky cases — Reddit comment threads, Hacker News comment/item pages, index/listing pages — alongside clean/gated/SPA controls. The run produces an `axes.md` report with a per-system table and a vs-WebFetch delta summary.
- **`make bench`** runs the benchmark; `make eval` is kept as an alias. The benchmark prefers the Claude Code OS session (OAuth subscription — no `ANTHROPIC_API_KEY` required); `A2WEB_BENCH_PROVIDER` forces the provider.

### Removed

- Retired the stale `benchmarks/vs-webfetch/2026-05-11/` runnable scripts (`runner.py`, `judge.py`, `aggregate.py`, `multi_model.py`, `phase4_ask.py`, `reliability_runner.py`) — they predated the v0.11/v0.14 envelopes and could no longer run. The `findings_*.md` notes are kept as history.

## [0.14.0] — 2026-05-22

The `envelope-deviation-trim` change: one rule across both tool envelopes — *a field appears on the wire only when it deviates from the default*. A trivial successful `ask` collapses to `{confidence, extracted_answer}`; a trivial `fetch_raw` to `{confidence, content_md}`.

### Changed

- **BREAKING — debug observability is a single `debug` sub-object.** `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, and `extraction` no longer appear as scattered top-level keys; they regroup into one `debug` object present only when the tool is called with `debug=True`. Applies to both `ask` and `fetch_raw`.
- **BREAKING — `tier` is deviation-only.** Omitted from the wire when its value is `raw` (the plain-HTTP default); present for `site_handler:*` / `jina` / `archive` / `browser`. Absence means a plain raw fetch.
- **BREAKING — `url` is redirect-only.** Omitted when the fetched URL equals the requested URL; present (carrying the final URL) only after an HTTP redirect or captcha-host rewrite.

### Removed

- **BREAKING — `original_url` deleted from both envelopes.** The caller already holds the requested URL; the surviving `url` (when present) is the deviation. The internal `FetchContext.original_url` field is gone too — a new `FetchContext.requested_url` captures the caller's input for the `url` deviation comparison.

## [0.13.0] — 2026-05-22

The `fetch-response-diet` change: `fetch_raw` / `FetchResponse` get the same lean wire treatment `ask` already received. A typical `fetch_raw` payload drops from ~22 keys (most of them `null` / `[]` / `{}`) to the handful that carry signal. The omit-empty + TSV serialization logic is now shared with `AskResponse` via a common helper.

### Changed

- **BREAKING — `fetch_raw` omits empty/null optional fields from the wire.** `title`, `byline`, `published`, `original_url`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, and `extracted_answer` are absent when empty rather than serialized as `null` / `[]` / `{}`. On `fetch_raw` the LLM fields (`extraction`, `extracted_answer`) are always empty and simply disappear.
- **BREAKING — `status` is failure-only on `fetch_raw`.** Omitted when the fetch succeeds; present on `failed` / `partial`. Absence of `status` means success.
- **BREAKING — `narrative` / `diagnostics_summary` are failure-only on `fetch_raw`**; `started_at`, `total_ms`, `cache`, `tokens`, and `diagnostics` are `debug`-only. `tokens` joined the `debug` tier — the agent already holds `content_md` and can measure it.
- **BREAKING — `fetch_raw` `links` and `next_links` render as TSV blocks** (header row + one tab-separated row per entry) instead of JSON arrays of objects. `links` columns are `anchor` / `href` / `role`; `next_links` drops its `kind` column when every row is `drilldown`.

`ask` / `AskResponse` are unaffected — the wire shape was already lean; only its serializer implementation is refactored onto the shared `_prune_wire` helper.

## [0.12.0] — 2026-05-22

Follow-up to `ask-response-diet` (`ask-response-trim`): three further trims to the `ask` wire envelope.

### Changed

- **BREAKING — `extraction` is `debug`-only on `ask`.** The `extraction` object no longer appears on the default wire (it was `{"truncated": false}` — zero information — on nearly every response). When the extractor truncated an over-cap page, that now surfaces as an `operator_hint` with `code: "answer_truncated"`. Full extraction metadata still appears under `debug=True` and on LDD events.
- **BREAKING — `status` is failure-only on `ask`.** Omitted when the fetch succeeds; present on `failed` / `partial`. Absence of `status` means success. Joins `narrative` / `diagnostics_summary` in the failure-only tier.
- **BREAKING — `ask` `next_links` renders as a TSV block** (header row + one tab-separated row per link) instead of a JSON array of objects. The `kind` column is dropped when every link is `drilldown` and kept when the list mixes kinds.

`fetch_raw` / `FetchResponse` are unaffected by all three.

## [0.11.0] — 2026-05-22

The `ask-response-diet` change: the `ask` tool returns a lean answer-shaped
envelope instead of the page-shaped `FetchResponse`. Cuts ~70% of the wire
payload on a typical fetch — `ask` carries the extracted answer, not the page.

### Changed

- **BREAKING — `ask` returns the new `AskResponse` envelope.** `content_md`, `headings`, `tokens`, and `is_user_authored` are no longer on the `ask` surface. `content_md` (with the `headings` index) returns only when the caller passes the new `include_content=True` parameter. The page-shaped `FetchResponse` is unchanged and still returned by `fetch_raw`.
- **`ask` omits empty/null optional fields from the wire.** `byline`, `published`, `operator_hints`, `next_links`, `original_url`, and `meta` are absent when empty rather than serialized as `null` / `[]` / `{}`.
- **`ask` `narrative` / `diagnostics_summary` are failure-only**; `started_at`, `total_ms`, `cache`, and `diagnostics` are `debug`-only.
- **`ask` `extraction` metadata is slimmed to `truncated`** on the default wire path; full metadata (`model`, token counts, cost, latency, cache) is `debug`-only and stays on LDD events.
- **HN front page renders both URLs.** External-link stories now expose the article URL *and* the `news.ycombinator.com/item?id=` discussion URL in `content_md`.
- **`Heading` serializes as a compact `[level, text]` tuple** on the wire.

### Removed

- **BREAKING — `FetchResponse.fit_md` deleted.** Unconditionally `None` since v0.3; the pruning filter it reserved space for never shipped (superseded by JSON-synth and the LLM extractor). `TokenCounts.fit` removed with it.
- **`FetchResponse.is_user_authored` deleted** — a constant-`False` flag carrying no information.

### Added

- **Golden API-contract tests** (`tests/test_contracts.py` + `tests/contracts/`). Scenario goldens for the `ask` / `fetch_raw` wire envelopes, invoked through the in-process MCP client; `make bless-contracts` re-blesses after an intentional envelope change.

## [0.10.0] — 2026-05-19

Cycle bundles the harsh-test-session-fixes change + carry-over work that
accumulated on the branch (v0.39 a2kit migration, v0.7 link-discovery,
v0.8 cookie jar). All shipped together because they touched overlapping
files. v0.11 follow-up + post-release docs landed same day; see
sub-sections.

### Added (v0.10 harsh-test-session-fixes, 2026-05-19)

- **JSON-in-script extractor** (`src/a2web/packages/json_in_script.py`). Detects `__NEXT_DATA__`, `__NUXT_DATA__`, `application/ld+json`, and generic `application/json` script blobs; ranks LD-JSON `Product` / `Article` / `ItemList` (with >=3 populated fields) above framework app-state. Boundary type `JsonPayload`; package-independent. Synthesizes a markdown table at the a2web seam (`domain.py::json_to_markdown_rows`) — only known shapes are converted, do-no-harm on unknown JSON. JSON path runs only when trafilatura output is thin (<2KB OR <3 sentences) and replaces only when synthetic is >=2x original. Emits `json_synth` LDD events.
- **Paywall classifier — jina stub recognition.** Gate now recognizes jina-tier responses carrying `Target URL returned error 40[13]` stubs (NYT, WSJ shape) as `Verdict.paywall` instead of `Verdict.length_floor`. Archive escalation playbook now fires on these (previously a silent failure).
- **Thin-browser-response heuristic.** When the browser tier returns 200 OK with <1KB content from a host in the `JS_HEAVY_HOSTS` set (x.com, twitter.com, instagram.com, tiktok.com, trendyol.com, aliexpress.com — operator-extensible via `A2WEB_JS_HEAVY_HOSTS_EXTRA`), the gate downgrades to `length_floor` so escalation continues instead of returning a thin success.
- **Browser tier: scroll-on-thin retry.** After `wait_until="networkidle"`, if the first DOM capture is <4KB and the host is JS-heavy, scroll to bottom + wait 2s + re-snapshot. Keeps the larger capture. Never raises — page-eval errors fall back to the original. Emits `browser_scroll_retry` LDD events with outcome (larger / smaller / timeout).
- **`--max-content-chars` CLI flag + MCP kwarg on `ask`.** Caps content sent to the extractor LLM per-fetch. `None` (default) preserves the 100,000-char default. Reduces cost on pages dumping JSON app state — verified Hepsiburada drop 53,842 -> 11,964 prompt tokens (-78%) on a real benchmark.

### Changed (v0.10 — same cycle)

- **`camoufox` moved to baseline dependencies.** Previously `[browser]` extra; an uninstalled browser dep produced uncaught `ImportError` on the first browser-tier escalation. Install size grows ~150MB; first browser use still requires `python -m camoufox fetch` (runtime asset, not a wheel dep).
- **`playwright` dropped as explicit dep.** Transitive via camoufox, was a redundant pin.
- **`claude-agent-sdk` provider always passes explicit `system_prompt` (even empty).** SDK treats `None` as "load the claude_code preset" (~23k tokens of agentic system prompt). Explicit empty string opts out → drops ~12k tokens / ~50-77% per Haiku call. Verified on arXiv re-fetch ($0.0132 -> $0.0032).

### Added (v0.11, 2026-05-19 — small follow-up)

- **JSON synth now runs against browser-tier rendered DOM.** `_escalate_browser` previously installed browser output directly and re-gated without calling the JSON-in-script path. Now the synth runs against the rendered HTML (`browser_result.body`) before the re-gate, so sites that expose `__NEXT_DATA__` / LD-JSON only post-hydration get the same treatment as raw-tier SSR. Closes the v0.10 known limitation.

### Known Limitations (post-v0.11)

- **Camoufox subprocess stderr leak unfixed.** Spike (`docs/history/spike-camoufox-stderr-2026-05-19.md`) confirmed no supported knob in camoufox / playwright to redirect the Node child process's stderr without monkey-patching internals or `os.dup2`. Operators can redirect at shell level: `a2web ... 2>/tmp/a2web.stderr.log`.
- **Trendyol is a fingerprint-blocked target, not a CSR-architecture issue.** Diagnostic probe (camoufox headless against `/sr?q=...`): DOM contains zero products, no `__NEXT_DATA__`, no `__APOLLO_STATE__`, no state globals. Only analytics stubs and a custom "Mergen" loader. Trendyol detects headless via TLS/canvas/WebGL fingerprinting and serves an empty React shell intentionally. Same bucket as X.com / Instagram — out of scope without authenticated cookies or a non-headless approach. Building a site handler doesn't help (handler still needs a browser, browser still gets the empty shell).

### Added (v0.7 link-discovery — `next_links`, 2026-05-18)

- **New response field `FetchResponse.next_links: list[NextLink]`.** Up to 10 curated "what to fetch next" links per response. Each entry carries `anchor`, `url`, `reason` (one phrase, ≤80 chars), and `kind` (`drilldown` / `related` / `source`). Empty when no drilldown layer exists. Replaces the agent's "scan `links[]` and guess" pattern on listing-style pages.
- **Tier 1 — site handlers populate candidates from structured upstream payloads.**
  - **Reddit:** subreddit listings (`/r/<sub>/`, `/r/<sub>/hot/`, etc.) emit up to 10 permalinks with `reason="<score> score, <num_comments> comments"`. NSFW posts filtered when the subreddit's own `over18` flag is False.
  - **HN:** front page (`news.ycombinator.com/` and `/news`) — now matched (previously unmatched) — emits up to 10 stories; external-URL stories drill to the external link, text-only stories drill to the discussion page.
  - **arXiv:** category listings (`/list/<cat>/<window>`) — newly matched — emit up to 10 abs URLs with authors as `reason`.
  - **GitHub:** repo URLs emit up to 5 top open issues + 5 top open PRs as `kind="related"`. Issue/PR URLs return empty (terminal).
  - **Wikipedia:** up to 10 deduped outbound wikilinks parsed from Parsoid HTML as `kind="related"`. `File:`/`Category:` namespace links filtered. Same source-language host invariant.
- **Tier 2 — LLM curation in the `ask=` extraction call.** When `ask=` is set, the extraction prompt asks the LLM to also return up to 10 candidates inside a fenced JSON block (`` ```next_links ``` ``). Same provider call, no second round-trip. Boundary type `LlmNextLink` lives in `packages/llm_extract`; conversion to the domain `NextLink` happens at the a2web seam.
- **Hallucination defense.** LLM-supplied URLs are validated against the markdown content the LLM was given; absent URLs are dropped with an `extraction_drift` diagnostic. Handler-supplied URLs (Tier 1+2 re-rank) are exempt.
- **Tier 1+2 composition.** When both fire, the handler's candidate list is passed into the `ask=` prompt as context and the LLM re-ranks, filters, and rewrites each `reason` against the user's question. The LLM-returned list replaces (not unions with) the handler's list.
- **New tool parameter `next_links: bool = True`** on both `fetch` (ask=) and `fetch_raw` tools. Default-on; pass `False` on terminal fetches to suppress the field.
- **Out of scope (deferred):** alias-addressed URLs (`alias=` parameter for short-ID drilldown — only worth it once we measure full-URL pass-through as the actual bottleneck), server-side recursive drilldown (`follow_depth=N`).

### Added (v0.8 browser cookies, 2026-05-18)

- **Opt-in browser cookie source.** New settings `cookie_source: Literal["none","chrome","firefox"]` (default `none`), `cookie_profile: str` (default `Default`), `cookie_stale_after_hours: int` (default `24`). When enabled, a2web reads cookies from the user's local Chrome (macOS) or Firefox profile and threads them through the raw (curl_cffi) and browser (Playwright) tiers. Jina tier intentionally skips (third-party reader — would leak the session). Default `none` keeps the subsystem inert with zero observable change.
- **New tool + CLI: `a2web cookies refresh`.** Reads the configured browser profile, decrypts any encrypted values (macOS Keychain via `security` CLI + AES-GCM via `cryptography`), and atomically replaces the mirror inside the existing `SqliteResource` (new tables `a2web_cookies`, `cookies_meta`). The macOS Keychain prompt only appears here, not per fetch — Chrome can keep running.
- **Staleness signal as `OperatorHint(code="cookies_stale", ...)`.** Every fetch where the mirror is older than `cookie_stale_after_hours` (or has never been refreshed) gets one operator hint with the age + threshold + fix command. Agents can branch on `code == "cookies_stale"`. An `a2kit.ldd.event(CookiesStale(...))` is emitted in parallel for operator-facing observability.
- **`OperatorHint` docstring updated.** The `code` field is now explicitly an agent-readable branch point. Existing codes (`llm_unavailable`, `browser_unavailable`, `captcha_redirect`) already served both audiences; the prior "agents never read these" claim was descriptive of original intent, not a constraint. Schema unchanged.
- **`cryptography` promoted to direct dependency** (already transitive via curl_cffi). Used only for PBKDF2-HMAC-SHA1 and AES-GCM decrypt in the Chrome reader.
- **Hand-written cookie readers under `packages/cookie_store/`.** No third-party cookie-extraction library — `rookiepy` and `browser-cookie3` both audited YELLOW (dormant single-maintainer projects, no PyPI Trusted Publishing). Our macOS Chrome path is ~120 LOC; Firefox is plaintext sqlite. Less third-party trust surface, fewer moving parts on Chrome encryption changes.
- **Redaction discipline.** Cookie values never appear in LDD event payloads, structlog records, or diagnostic rows. Helper `redact_cookie_for_event(cookie)` returns `{name, host_key, path, value_length}`. The `CookiesAttached` event carries cookie *names* only.
- **Out of scope (v0.8):** LDD severity levels (upstream a2kit ask — emit at single level today, swap to `warn` when supported); Camoufox `user_data_dir=` profile inheritance; Linux/Windows Chrome; multi-profile merge; automatic background refresh; Safari / Edge / Brave / Arc.

### Changed (a2kit v0.38 → v0.39 migration, 2026-05-16)

- **a2kit pin: v0.38.0 → v0.39.0.** Adopts round-10 friction fixes shipped upstream on 2026-05-16. No wire-surface change; all 414 tests green at 89% coverage.
- **Drop `ctx: a2kit.ToolContext` from `WebRouter.fetch`.** v0.39 binds ambient ctx unconditionally inside any framework dispatch — the `ctx` parameter is no longer needed in tools that don't read ctx in the body. `del ctx` is gone.
- **Drop `await sqlite._ensure()` from `_check_sqlite`.** v0.39 `OPERATIONAL_CONTRACTS Q-HealthChecks` pins the contract: kwarg resolution enters the resource. The health probe receiving `sqlite` is the readiness assertion; no internal probe call needed. The surrounding try/except is gone too — sqlite open-time failures are catastrophic and should crash the probe loudly, not soften to a "degraded" check.
- **`conftest.py` helpers swapped to `a2kit.testing.*`:**
  - `lazy_of(value)` → `a2kit.testing.lazy(value)` (deleted from conftest; tests import directly).
  - Local `_ambient_ldd` autouse fixture → re-export `a2kit.testing.ambient_for_tests` under `pytest.fixture(autouse=True)` using the documented `__wrapped__` unwrap pattern.
  - `make_default_state(...)` kept as-is — it's the deliberate "AppState without an app" test seam (not boilerplate; `a2kit.testing.resolve` is for the orthogonal "AppState inside an app scope" use case, which a2web does not currently use).
- **Round-10 Friction E retracted.** v0.39 shipped `Lazy[T]` recognition in factory parameters (closes a real spec drift), enabling `AppState` to absorb `Lazy[BrowserPool]` / `Lazy[LlmExtractorResource]` as fields. a2web reviewed and **did not adopt** — the architectural split (`AppState` for always-on data, separate `Lazy[T]` DI kwargs at the tool seam for orthogonal services) is correct design, not friction. Mixing services into the data bundle would blur the seam and force tests to fake services they don't exercise. Tool signature stays at three injectables (`state`, `browser_pool`, `llm_extractor`).
- **CLAUDE.md updated** to reflect v0.39 invariants: unconditional ambient ctx; no `_ensure()` in health bodies; canonical `a2kit.testing.*` import path; `ToolContext` is now a `@runtime_checkable typing.Protocol`.

### Added (v0.7 MCP feature wave, 2026-05-15)

- **Reddit search URL handler.** `RedditHandler` now claims `/r/<sub>/search/?q=...` and unscoped `/search/?q=...`. Rewrites to `.json`, renders a terse markdown list (`# Search: <q>` + `## Results (N)` + per-result `**title** (r/sub · u/author, score N, M comments, age) <permalink>`). Caps at 25 entries. Closes the highest-value research gap from v0.6 feedback (search was 100% fail across raw/jina/archive previously).
- **Captcha-host pre-routing.** Google/Bing `/search?q=...` URLs are rewritten to `https://duckduckgo.com/html/?q=<urlencoded-q>` before tier dispatch. New pure function `a2web.domain.rewrite_captcha_host(url)` is the single source of truth. `FetchResponse.original_url` preserves the URL the caller originally asked for so diagnostics stay honest. Non-search paths on captcha hosts (Maps, Drive, Images) pass through unchanged.
- **`FetchResponse.original_url` field** — set when an upfront URL rewrite occurred (e.g. captcha → DDG); `None` when no rewrite. `response.url` always reflects the URL actually fetched.

### Breaking (v0.7 LLM extras → core, 2026-05-15)

- **`[llm]` install extra REMOVED.** `pip install a2web[llm]` now errors loudly. `anthropic` + `claude-agent-sdk` are baseline deps. `--ask` works out of the box. Install size jumps from ~30MB to ~240MB (claude-agent-sdk bundles ~210MB Claude Code binary in `_bundled/`) — the bundling is intentional: most a2web callers run inside Claude Code and rely on the OAuth piggyback. Migration: drop `[llm]` from your install command.
- `LLMNotAvailable` only fires now for "no API key AND no Claude Code OAuth session" — the "SDK not installed" branch is dead. Operator hints updated.

### Changed (a2kit v0.32 → v0.38 migration, 2026-05-15)

- **a2kit pin: v0.32.0 → v0.38.0.** Six upstream releases on 2026-05-13 → 2026-05-15 closed feedback rounds 7, 8, and 9 — most importantly, the round-8 MCP `ctx`-binding bug that 100%-broke `mcp__a2web__fetch` in a2web v0.6.0. POC-verified: tool returns structured `FetchResponse` over MCP stdio, LDD events stream as `notifications/message` on the wire, no `TypeError`.
- **DI re-architected for v0.36+ native shape.** Each long-lived resource is now its own provider via `app.provide(...)`. Per-resource singletons enter lazily on first resolution (lazy first-use, replaces eager `async with app:` entry). Resources expose `__aenter__`/`__aexit__` as thin wrappers around existing idempotent `_ensure()` / `close()` methods — both surfaces kept; framework drives the CM protocol while internal lazy callers keep using `_ensure()`.
- **`AppState` slimmed to always-on resources** (settings, breakers, proxy_pool, sqlite). `browser_pool` and `llm_extractor` moved off `AppState` — they're independently provided and surfaced at the tool seam via `Lazy[T]`. The orchestrator awaits the Lazy callable only at the consuming phase (`_escalate_browser` for browser, `_phase_extract_answer` for LLM). Browser pool never enters on the happy path; LLM resource never enters when `ask=` is not passed.
- **`server.py` rewritten** for v0.38: no `@asynccontextmanager` lifespan, no `lifespan=` kwarg, no `health_tool=`. Imperative per-resource `app.provide(...)` registrations in deps-first order (Settings → Breakers → ProxyPool → SqliteResource → BrowserPool → LlmExtractor → AppState). Named factory functions; no lambdas.
- **`@a2kit.read(idempotent=True)`** dropped from `routers.py` per v0.33 — reads are spec-idempotent.
- **`Router.slug`** declaration switched from `ClassVar[str] = "web"` to plain `slug = "web"` per v0.36's `slug: str` instance-variable annotation.
- **BrowserTier signature** gains `pool: BrowserPool | None = None`. The orchestrator's `_escalate_browser` resolves `Lazy[BrowserPool]` and threads it.
- **`Tier` protocol** gains `**kwargs: Any` for protocol-uniform dispatch.
- **`@app.health_check`** signature changed from `(state: AppState)` to `(sqlite: SqliteResource)` — DI resolves the resource directly, the framework enters it for the probe.

### Removed (a2kit v0.32 → v0.38 migration)

- **`@asynccontextmanager` lifespan** in `server.py`. `App(lifespan=cm)` was removed in a2kit v0.35; resource lifecycle now flows through each resource's `__aenter__`/`__aexit__`.
- **`app.singleton(...)`** — replaced by `app.provide(...)` in v0.36.
- **Eager-warm-on-startup pattern** — v0.36 made all resource entry lazy. Sqlite misconfig now surfaces as a structured `ToolError` envelope on the first fetch instead of crashing at server boot. `a2web health` still warms sqlite eagerly via the health-check path.
- **`browser_pool: BrowserPool`** and **`llm_extractor: LlmExtractorResource`** fields from `AppState`. They live as independent providers, surfaced via `Lazy[T]` at the tool seam.

---

### Previously changed (a2kit v0.28.0 → v0.32.0 migration, 2026-05-13)

- **a2kit pin: v0.28.0 → v0.32.0.** Six upstream releases on 2026-05-12 → 2026-05-13 closed every open ergonomic gap from a2web feedback rounds 5 + 6 plus fixed the FastMCP 3.x compatibility break that was blocking `a2web serve` as a global Claude Code MCP server.
- **Lifespan over lifecycle hooks.** `@app.on_startup` / `@app.on_shutdown` (removed in a2kit v0.31) replaced by a single `lifespan=` async context manager in `server.py`. Pre-`yield` warms sqlite (fail-fast); `finally` block closes resources LIFO with each close error-isolated.
- **Explicit Router contract.** `WebRouter` declares `slug = "web"` and `tools = (fetch,)` ClassVars per a2kit v0.31's removal of `_derive_slug` and the `dir(self)` walk.
- **`a2kit.Param` → `pydantic.Field`.** Six call sites in `routers.py` migrated. The `Param` wrapper was removed in a2kit v0.31 (was a one-line forwarder); explicit `Annotated[T, pydantic.Field(description="...")]` is now the canonical form.
- **Ambient `ctx` for LDD primitives.** Per a2kit v0.29.0+, `a2kit.ldd.event(...)` reads ctx from a `ContextVar` set by the dispatcher. Stripped `ctx` kwarg from 9 phase / helper signatures in `fetcher.py` and 16 `a2kit.ldd.event(ctx, ...)` call sites. The tool body still declares `ctx: a2kit.ToolContext` for the dispatcher to bind ambient (per OPERATIONAL_CONTRACTS Q8).
- **`null_context()` import + branch removed** from `fetcher.py::fetch()`.
- **LDD import path** in `events/sinks.py`: `from a2kit.ldd import LddEmission` → `from a2kit.packages.ldd import LddEmission` (v0.32 namespace trim).

### Added

- **`tests/conftest.py::_ambient_ldd` autouse fixture.** Wraps every test in `ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)` so direct `fetch()` calls from tests don't raise `AmbientContextMissing` (a2kit v0.29+ requires LDD primitives to run inside an active dispatch scope).

### Removed

- **`SqliteResource` / `BrowserPool` / `LlmExtractorResource` close-from-`@on_shutdown` ceremony.** Cleanup now lives inside the App lifespan's `finally` block.

### Notes

- Free wins inherited on the bump: CLI cold-start −75% (v0.27.1/2), WARN_ONCE on five framework-internal silent-swallow sites (v0.31.0), `@a2kit.list_` parameter parity (v0.32.0).
- The docstring `Args:` auto-pull shipped in a2kit v0.29.0 was reverted in v0.30.0 — our round-5 caution about silent description-loss drift was vindicated by upstream removal within 24 hours of release. Param descriptions stay in `Annotated[T, pydantic.Field(description=...)]`.
- Two original round-3 wishes (streaming response API, `@a2kit.read(timeout="60s")` decorator kwarg) remain deferred — see `docs/history/A2KIT_WISHES_DEFERRED.md` along with three new round-7 candidates surfaced during the migration (singleton teardown kwarg, `tools` tuple completeness lint, sharper `AmbientContextMissing` message for no-ctx tools).
- Acceptance: `make check` green (387 tests, 89.45% coverage); `claude mcp list` shows `a2web: ✓ Connected`; CLI smokes (example.com, news.ycombinator.com, arxiv.org) return populated `FetchResponse` with diagnostics.

## [0.6.0] - 2026-05-12

Post-v0.5.0 simplification sweep. The codebase finished v0.5.0 still
carrying a per-domain seam-shim layer (`cache/`, `gate/`, `proxy/`,
`log/`, `extract/`, `llm/`) — one-line re-exports preserving import
paths from before the packages migration. This sweep deletes them
outright; consumer compat is explicitly disclaimed pre-1.0.

### Structural

- **Seam-shim layer nuked.** Six per-domain seam directories (~580 LOC
  of one-line re-exports) deleted. Surviving domain-coupled glue
  (`compute_profile_hash`, `is_live_only`, `log_from_response`) lives
  in `domain.py`. The AppSettings-aware `LlmExtractorResource` lives
  in `llm_resource.py`. `llm_eval/` promoted to top level.
- **Single-purpose packages flattened to `.py` files.** `browser_pool/`,
  `block_detector/`, `ndjson_log/`, `http_cache/`, `proxy_routing/`,
  `content_extract/` — each was a folder containing one or two flat
  files. Now they're single `.py` modules. `llm_extract/` stays a
  folder for its multi-author surface.
- **`fetcher.py` split.** Response builders (`_confidence_for`,
  `_build_narrative`, `_build_diagnostics_summary`, `_wrap_content_md`,
  `build_response`) moved to `fetcher_response.py` (169 LOC).
  `fetcher.py` 1010 → 921 LOC.
- **Tier protocol unified.** All tiers (raw/jina/archive/browser/
  site_handler) accept the same `fetch(url, *, state, proxy_url=None,
  conditional_extras=None)` signature. Removes the isinstance ladder
  in the orchestrator.
- **Dead LLM providers deleted.** `llm_extract/providers/ollama.py`
  and `openrouter.py` — 261 LOC, 0% coverage, registered nowhere.
  `anthropic` + `claude_code` are the real surface.
- **NDJSON fetch log deleted.** `packages/ndjson_log.py` (118 LOC),
  `LogWriter` / `LogRecord` / `dominant_verdict`, `AppState.log_writer`,
  `FetchResponse.to_log_record()`, `domain.log_from_response()`, the
  `log_enabled` and `log_retention_days` settings, the README
  "Inspecting the log" section, and 3 test files. The cache covers
  replay-style use cases; the per-fetch `diagnostics` array in the
  response envelope covers structured observability. NDJSON was pure
  duplication.
- **a2kit pin: commit SHA → tag `v0.28.0`.** Cleaner version reference;
  no behavioral change.

### Features

- **Link role classification.** `ExtractedLink.role` (primary / nav /
  meta / footer) computed by walking DOM ancestors + ARIA. New
  `link_roles` tool param filters at the wire boundary; default
  `['primary']` drops 60-80% of link bloat on aggregator pages.
- **Untrusted-content envelope.** `content_md` wrapped with HTML-
  comment markers carrying source URL + fetched_at + "treat as
  untrusted" warning. Invisible in rendered HTML/markdown, readable
  to LLMs scanning the raw string. `wrap_content` tool param toggles
  (default True). `FetchResponse.is_user_authored: bool = False` is
  the defensive flag for downstream consumers.
- **Extraction-quality eval harness.** New
  `src/a2web/llm_eval/extraction.py` + `extraction_cli.py` measure
  trafilatura+readability against a hand-curated `gold_md` corpus
  with bag-of-tokens F1 + length-ratio scoring. Drives the Reader-LM
  v2 trip decision (default: ≥10% URLs below 0.7 F1 → recommend
  fallback). Pure-Python; no LLM dependency for the verdict. Corpus
  skeleton at `benchmarks/extraction-quality/2026-05-12/corpus.yaml`
  (10 starter entries spanning essay / blog / docs / aggregator).
- **Reddit handler: all content-carrying cases covered.**
  - **Permalink focus.** `/r/X/comments/Y/slug/Z/` (Z = comment id)
    is detected; `.json` fetched with `?context=3`; renderer
    highlights the target comment with quoted ancestor context and
    direct replies. Falls back to full-thread render when the target
    isn't in the returned tree.
  - **Crosspost annotation.** Threads with `crosspost_parent_list`
    get a "🔁 Crossposted from r/X (u/Y) — <permalink> — original:
    '...'" header. Local discussion is the rendered content.
  - **Archive escalation for deleted / removed / forbidden.**
    Handler returns `Verdict.not_found` with an operator hint when
    `.json` 404 + old.reddit 404, or on `.json` 403 (quarantined /
    NSFW / private). New playbook rule
    (`next_action_after_tier` → `RetryViaArchive` on reddit
    `not_found`) dispatches the Wayback tier — captures from before
    removal are common.
  - **Short-URL HEAD resolution.** `redd.it/<id>` now matches;
    handler does a HEAD with `follow_redirects`, recurses on the
    resolved comments URL, or surfaces `no_match` when the
    resolution points at non-thread content.
  - **`np.reddit.com`** host added.
  - Mod-removed bodies (`selftext == "[removed]"`) rendered as
    `_[post body removed]_` instead of empty selftext.

### Coverage

- Tier suite gaps filled: `raw.py` 20% → 96%, `archive.py` 86% → 100%,
  plus browser/jina/site_handler closeouts.
- Reddit handler coverage: 13 new tests (permalink detection +
  focused render, crosspost annotation, removed-body marker,
  archive-escalation signal on 404 + 403, short-URL HEAD resolution
  + non-thread no_match, playbook escalation rule).
- Test count 320 → 387; coverage 85.90% → 89.71%
  (NDJSON suite removed; extraction-eval + reddit suites added).

### Docs

- `docs/history/A2KIT_FEEDBACK_v0.27.md` — 358-line feedback doc on four
  ergonomic ceilings that would unlock another ~175 LOC of deletion
  upstream (async resources, ambient ctx threading, test resource
  override, Param verbosity).
- `BACKLOG.md` updated to match reality — removed stale references to
  seam shims, marked twitter handler as shipped (v0.3 Nitter).
- `CLAUDE.md` refreshed for the radical clean-up.

## [0.5.0] - 2026-05-12

Simplification + structural cleanup release. Three themes:

1. **a2kit v0.27.2 migration** (step 1). Resource pattern for every
   long-lived async resource — sync `__init__`, internal lock, lazy
   `_ensure()`, idempotent `close()`. Non-Optional AppState. DI-aware
   lifecycle hooks. Typed-event direct emit. ~-95 LOC.
2. **Seven in-tree microsofware packages** (steps 2, 4–9). New
   `src/a2web/packages/` directory with a strict contract: no
   `a2web.<domain>` imports allowed inside. Promoted: `browser_pool`,
   `block_detector`, `ndjson_log`, `http_cache`, `proxy_routing`,
   `llm_extract`, `content_extract`. The `test_packages_independence`
   invariant fails CI on drift.
3. **Fetcher decomposition** (step 10). The 180-LOC tier loop is
   split into a coordinator + three named helpers driven by an
   `_AfterTier` enum. Shared tier-emit and regate-after-escalation
   helpers centralize previously-duplicated boilerplate.

Plus a micro-cleanups bundle (step 3) that collapsed `*_hint` fields
to a single `fc.operator_hints` accumulator, deleted YAGNI parameter
stubs, dropped non-loadbearing `@runtime_checkable` decorators, and
moved `_resolve_env` to a pydantic validator.

320 tests passing at 85.90% coverage on release.

### v0.5 step 10 — fetcher decomposition (2026-05-12)

Plan: `openspec/changes/archive/2026-05-12-v0.5-fetcher-decomposition/`.

- **Step 10a — `_emit_tier_started` / `_emit_tier_ended` helpers.** The
  TierStarted/TierEnded emission pattern was duplicated at three sites
  (tier loop, archive escalation, browser escalation). Centralized
  into two small async helpers above the archive section. Removes a
  stale in-band `tier_dur_ms` calc — TierEnded.dur_ms and Diagnostic
  share exactly one source now.
- **Step 10b — split `_phase_tier_loop` into named helpers.** The
  180-LOC tier loop now coordinates over three named helpers with an
  `_AfterTier` enum driving control flow: `_install_won_tier`,
  `_install_archive_payload`, `_apply_after_tier_action`. Outer loop
  body drops from ~150 to ~85 LOC and reads top-to-bottom without
  flag variables (`restart_loop`, `archive_break_payload`).
- **Step 10c — `_regate_after_escalation` helper.** Browser and
  gate-path archive escalators both ran the same 7-line regate block
  after installing pre-rendered content; now one helper, one source
  of truth.

### v0.5 step 9 — content_extract promoted to packages/ (2026-05-12)

Closes Stage 2b — the original deferred-with-reason item that needed
boundary types before it could move.

- **`packages/content_extract/`** — seventh in-tree microsofware. Owns
  the trafilatura wrapper (`extract_markdown`) + OG/Twitter/JSON-LD
  metadata parser (`parse_metadata`). Boundary types `ExtractedHeading`
  / `ExtractedLink` / `ExtractedContent` are frozen `dataclass(slots=True)`,
  package-owned. Zero `a2web.<domain>` imports.
- **`extract/trafilatura_ext.py` reduced to seam.** Calls the package
  and maps `ExtractedHeading` → `models.Heading`, `ExtractedLink` →
  `models.Link`. Preserves the existing `ExtractResult` shape so
  `fetcher.py` and tests need zero changes.
- **`extract/metadata.py` reduced to one-line re-export.**
- `test_packages_independence` auto-validates the new module.

### v0.5 step 8 — llm_extract promoted to packages/ (2026-05-12)

- **`packages/llm_extract/`** — sixth in-tree microsofware. Owns the
  whole LLM extraction + judge surface: `Extractor`, `ModelSpec`,
  `ExtractionResult`, `ExtractionCache` + `hash_text`, `Judge` +
  `JudgeVerdict` + `JudgeParseError`, `PromptTemplate` + the
  WEBFETCH/TERSE/JUDGE prompts, `LLMNotAvailable`, plus the four
  providers (`anthropic`, `claude_code`, `openrouter`, `ollama`) and
  `Provider` Protocol. Zero `a2web.<domain>` imports.
- **`llm/*.py` reduced to seam shims.** `llm/__init__.py` re-exports
  the package's public surface. `llm/{cache,errors,extractor,judge,prompts}.py`
  and `llm/providers/*.py` are one-line re-exports each. Existing test
  imports (`from a2web.llm.extractor import Extractor, ModelSpec`,
  `from a2web.llm.providers.claude_code import ClaudeCodeProvider`, etc.)
  keep working unmodified.
- **`llm/resource.py` stays at the seam.** `LlmExtractorResource`
  remains the domain-coupled wiring — it pulls provider selection from
  `AppSettings.llm_provider`, plumbs `SqliteResource` into
  `ExtractionCache`, and gates construction on the optional `[llm]`
  install extra.
- **`llm/eval/` stays at the seam.** The eval harness imports
  `AppSettings`, `FetchResponse`, `build_state` — domain-coupled by
  definition.
- `test_packages_independence` auto-validates all new modules.

### v0.5 step 7 — proxy_routing promoted to packages/ (2026-05-12)

- **`packages/proxy_routing/`** — fifth in-tree microsofware. Owns
  `ResolvedRoute`, `ProxyHandle`, `ProxyPool`, `resolve_route`, plus
  Protocol-shaped boundary types `ProxyEntryShape` / `RouteRuleShape`.
  Zero `a2web.<domain>` imports — the package reads route/proxy data
  via the Protocols, so any duck-typed source (pydantic, dataclass)
  works without conversion.
- **`proxy/policy.py` + `proxy/pool.py` reduced to seams.**
  `resolve_route(host, tier, AppSettings)` forwards `settings.routes` /
  `settings.proxies` into the package. `ProxyPool(settings=...)` is a
  subclass shim with a back-compat `.settings` property. Existing test
  and consumer imports (`from a2web.proxy.policy import resolve_route`,
  `from a2web.proxy.pool import ProxyPool, ProxyHandle`) unchanged.
- `test_packages_independence` auto-validates the new module.

### v0.5 step 6 — http_cache promoted to packages/ (2026-05-12)

- **`packages/http_cache/`** — fourth in-tree microsofware. Owns
  `CacheRow` (boundary type), `SqliteResource` (lazy aiosqlite + schema
  bootstrap), `cache_get`/`cache_put` primitives, `open_sqlite_with_schema`,
  `cache_dir`. Zero `a2web.<domain>` imports — the package takes a
  `db_path: Path | None` instead of `AppSettings`.
- **`cache/sqlite_cache.py` reduced to seam.** Keeps the domain-coupled
  bits: `compute_profile_hash(AppSettings)`, `is_live_only(url,
  AppSettings)`, and a `SqliteResource(settings)` subclass shim that
  forwards to the package. Re-exports the package primitives so
  existing imports (`from a2web.cache.sqlite_cache import …`) keep
  working unmodified.
- `test_packages_independence` auto-validates the new module.

### v0.5 step 5 — ndjson_log promoted to packages/ (2026-05-12)

- **`packages/ndjson_log/`** — third in-tree microsofware. Owns
  `LogRecord` (boundary type), `LogWriter` (lazy-open + size-based
  rotation + gzip on rollover), `paths.py`, `rotation.py`. Zero
  `a2web.<domain>` imports.
- **`log/*.py` reduced to seam shims.** `log/record.py` keeps the
  domain-coupled `from_response(FetchResponse) -> LogRecord` adapter;
  `log/paths.py` / `log/writer.py` / `log/rotation.py` are one-line
  re-exports from the package. Test imports (`from a2web.log.record
  import LogRecord, from_response`, etc.) keep working unmodified.
- `test_packages_independence` auto-validates the new module.

### v0.5 step 4 — block_detector promoted to packages/ (2026-05-12)

- **`packages/block_detector.py`** — second in-tree microsofware after
  `browser_pool`. Defines package-local `BlockVerdict` enum + `BlockResult`
  dataclass; no `a2web.<domain>` imports. Values intentionally match
  `a2web.models.Verdict` strings so the seam adapter is a one-liner.
- **`gate/block_detector.py` → thin seam adapter** (~52 LOC). Imports the
  package, calls it, maps `BlockVerdict → Verdict`, returns `GateResult`
  for the pipeline. Public signature (`evaluate(...) -> GateResult`,
  `LENGTH_FLOOR` re-export) unchanged — fetcher and gate tests pass
  unmodified.
- `test_packages_independence` invariant validates the new module
  automatically.

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
