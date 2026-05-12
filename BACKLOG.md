# Backlog

Deferred items from the v0.1 build, grouped by target milestone. Each entry
records its source (PR id or engineering doc section), a one-line
description, why it was deferred, and a rough scope tier (S / M / L).

> **Lifecycle.** Items are removed in the change that ships them, and added
> by any future OpenSpec change whose proposal carries an "Out of Scope"
> deferral. Keep this file current — every change that defers adds, every
> change that ships removes.
>
> **Single source of truth.** This file consolidates every known
> deferral. Upstream context: `~/Documents/Knowledge/Projects/120-a2web/v0.1-engineering.md`
> §10 (original v0.2/v0.3 deferrals); §9 (build order) is fully shipped
> and lives in `openspec/changes/archive/`. New deferrals land here, not
> in design docs.

---

## v0.5 simplification stages (shipped / deferred)

- ✅ **Stage 1 — a2kit v0.27.2 migration (DONE in v0.5 step 1).** Delivered:
  Resource pattern (SqliteResource, BrowserPool, LlmExtractorResource);
  non-Optional AppState; DI-aware lifecycle hooks; typed-event direct emit
  (no `_emit`/`_event_payload` shim). PR5 "lazy state cleanup" from the
  earlier punch list is folded into this — the Resource pattern delivered
  it.
- ✅ **Stage 2a — `packages/` scaffold + browser_pool moved.** Created
  `src/a2web/packages/` with the contract README, the
  `test_packages_independence` invariant (load-bearing — fails CI if any
  module under `packages/` imports from `a2web.<domain>`), and moved
  `BrowserPool` over as the first proof-of-concept package.
- ✅ **Stage 2b–2g — seven packages promoted (DONE in v0.5 step 9).**
  All seven in-tree microsofware modules now live under `src/a2web/packages/`:
  `browser_pool`, `block_detector`, `http_cache`, `proxy_routing`,
  `llm_extract` (folder), `content_extract`. Five are flat `.py` files;
  `llm_extract/` stays a folder for its multi-author surface
  (extractor, judge, cache, prompts, errors, providers/).
  *NDJSON log package deleted post-v0.5.0 — see Stage 2j.* The
  `test_packages_independence` invariant guards the no-domain-import
  contract for all of them.
- ✅ **Stage 2h — seam-shim layer nuked (DONE in v0.5 step 11).** The
  per-domain seam directories (`cache/`, `gate/`, `proxy/`, `log/`,
  `extract/`, `llm/`) — ~580 LOC of one-line re-exports — were deleted.
  Surviving domain-coupled glue (`compute_profile_hash`, `is_live_only`,
  `log_from_response`) lives in `domain.py`. The AppSettings-aware
  `LlmExtractorResource` lives in `llm_resource.py`. `llm_eval/`
  promoted to top level. Packages now imported directly; no shim hop.
- ✅ **Stage 2i — provider trim (DONE in v0.5 step 12).** Deleted
  `llm_extract/providers/ollama.py` and `openrouter.py` (261 LOC, 0%
  covered, never registered in the auto-select). `anthropic` + `claude_code`
  are the real surface. Add back when a concrete consumer needs them.
- ✅ **Stage 4b — Tier protocol unified (DONE in v0.5 step 11).** The
  `fetch(url, state, proxy_url=..., conditional_extras=...)` signature
  is uniform across raw/jina/archive/browser/site_handler. Killed the
  isinstance ladder in the orchestrator. Test stubs accept `**kwargs`.
- ✅ **Stage 4c — fetcher.py response builders extracted
  (DONE in v0.5 step 13).** `_confidence_for`, `_build_narrative`,
  `_build_diagnostics_summary`, `_wrap_content_md`, and `build_response`
  live in `fetcher_response.py` (169 LOC); `fetcher.py` shrunk
  1010 → 921 LOC. `FetchContext` shared via `TYPE_CHECKING`.
- ✅ **Stage 5 — Link role classification + untrusted-content envelope
  (DONE in v0.5 step 12).** `ExtractedLink.role` (primary/nav/meta/
  footer) via DOM-ancestor walk + ARIA; new `link_roles` tool param
  filters at the wire boundary (default `['primary']`, drops 60-80%
  of link bloat on real pages). `content_md` now wrapped with HTML-
  comment markers carrying source URL + fetched_at + "treat as
  untrusted" warning; `wrap_content` tool param toggles. Defensive
  cue for downstream agents, invisible to rendered HTML/markdown.
- ✅ **Stage 2j — NDJSON log nuked (post-v0.5.0).** The fetch log
  existed primarily to support replay-from-cache (PR10b). With the
  cache covering hit-keyed lookup and the structured `diagnostics`
  trace already in the response envelope, the NDJSON layer was pure
  duplication. Deleted: `packages/ndjson_log.py` (118 LOC),
  `LogWriter`/`LogRecord`/`dominant_verdict` + 3 test files, plus
  `state.log_writer`, `FetchResponse.to_log_record()`,
  `domain.log_from_response()`, the `log_enabled` /
  `log_retention_days` settings, and the README "Inspecting the log"
  section. Supersedes deferred Stage 3a (logging swap) and PR10b
  (replay) — both items removed.
- ⏳ **Stage 3b — proxy → purgatory.** *Why deferred:* purgatory's API is
  context-manager-flavored (`async with brk: ...`), not report-flavored.
  Swapping cleanly requires either making `ProxyPool.acquire/report` async
  and wrapping every tier call in `async with breaker:`, or hooking into
  purgatory's internal messagebus directly. Larger surface than planned.
  Current `_ProxyHealth` (~30 LOC, well-tested, no bugs) stays — defer to
  its own design PR.
- ✅ **Stage 3c — PR1 micro-cleanups (DONE in v0.5 step 3).** Delivered:
  three `*_hint` fields collapsed to `fc.operator_hints` accumulator;
  `del settings` / `del ms` reserved-for-future stubs deleted (3 params
  removed across `playbook.next_action_*` + `ProxyPool.report`);
  `@runtime_checkable` dropped on `Tier` and `Handler` protocols (kept
  on `Provider` + `EvalSystem` where contract-tests rely on isinstance);
  `_resolve_env` moved from `proxy/policy.py` into a pydantic
  `field_validator` on `ProxyEntry.url` in `settings.py`;
  `record_from_response` alias replaced by `FetchResponse.to_log_record()`
  method.
- ✅ **Stage 4 — fetcher decomposition (DONE in v0.5 step 10).** Delivered:
  `_phase_tier_loop` body split into `_install_won_tier`,
  `_install_archive_payload`, `_apply_after_tier_action` (returning the
  `_AfterTier` enum); shared `_emit_tier_started` / `_emit_tier_ended`
  helpers used by tier loop + both escalators; shared
  `_regate_after_escalation` helper. `_phase_extract_answer` stays at
  the a2web seam by design (intrinsically domain-coupled — uses
  FetchContext, FetchResponse, OperatorHint).

---

## v0.2 workspace-packaging deferral (from `migrate-to-a2kit-v026-and-simplify`)

- **Phase D — extract as uv workspace packages.** Source:
  `migrate-to-a2kit-v026-and-simplify` Phase D (tasks 4.1–4.6).
  *Superseded by v0.5's in-tree `packages/` migration.* All six
  remaining candidate microsofware modules (`browser_pool`,
  `block_detector`, `http_cache`, `proxy_routing`, `llm_extract`,
  `content_extract`) now live under `src/a2web/packages/` with the
  contract enforced by `test_packages_independence`. Promoting one
  to a separate uv workspace package is a mechanical move from there
  — wait for an actual second consumer before paying that mechanical
  cost. Scope: M per module.

## v0.2 OSS-adoption deferrals (from `migrate-to-a2kit-v026-and-simplify`)

Four OSS swaps the research recommended that turned out to be wrong fits on closer inspection. Documented here so a future change can revisit if circumstances shift.

- **hishel for HTTP cache.** Source: `migrate-to-a2kit-v026-and-simplify` Phase B 2.1+2.2. *Why deferred:* hishel v1.2's `AsyncCacheProxy` requires owning the HTTP transport via a `request_sender` callback. a2web's cache is an orchestrator-level before/after wrapper around the tier loop — it doesn't own transport. Adopting hishel would mean restructuring every tier to delegate raw HTTP to hishel, which is a fundamental architectural shift, not a shim. Reconsider if v0.3 collapses tiers to a single curl_cffi-backed transport. Scope: L.
- **aiometer for hedged archive requests.** Source: 2.7. *Why deferred:* `aiometer.run_any` returns the FIRST result regardless of value (first finisher wins, losers cancelled). Our archive tier wants "first SUCCESS" semantics — if Wayback returns None, we want to keep waiting for archive.ph. aiometer cancels and returns None instead. Custom 30 LOC of anyio task-group + capacity-1 stream stays. Scope: S.
- **purgatory for proxy quarantine.** Source: 2.6. *Why deferred:* ProxyPool's API is sync (`.acquire()`, `.report()`); purgatory's breakers are async (`.get_breaker()`, `breaker.context()`). Swap would force ProxyPool async, propagating through the orchestrator's tier loop. Net: more code, not less. Custom 30 LOC health state machine stays. Purgatory's redis-persistence value-add is the PR7e win; defer until PR7e actually needs redis. Scope: S.
Pattern: hand-rolled async code (cache wrapper, hedged race, proxy health) is hard to beat with sync libraries even when the library "covers" the use case. Trafilatura's bundled metadata (which DID land — drops htmldate) was the one clean OSS swap because the API shape genuinely matched. (RotatingFileHandler-for-NDJSON entry deleted: the NDJSON layer itself was removed post-v0.5.0 — the cache covers replay.)

---

## PR7e — Proxy polish

- **Browser-tier proxy plumbing.** Source: PR7d / PR7c. Camoufox is
  context-level (proxy lives on the persistent context, not the page);
  the v0.1 pool resolves and reports but does not configure browser
  contexts. *Why deferred:* per-host context coupling needs rework and
  is a separate scope from the orchestrator's proxy contract. Scope: M.
- **Archive-tier proxy plumbing.** Source: PR7d. Wayback / archive.ph
  hedge requests bypass the proxy pool today. *Why deferred:* the
  hedged-request task group needs proxy-aware retry semantics. Scope: M.
- **Persistent `~/.a2web/proxy-health.json`.** Source: PR7d. Health is
  in-memory only at v0.1. *Why deferred:* survives a single process;
  multi-process / restart-friendly health is a v0.2 concern. Scope: S.
- **Background health-check loop.** Source: PR7d. Quarantine is
  reactive (3 failures → 600s). *Why deferred:* proactive probes are
  observability work; in-memory reactive policy is sufficient for v0.1.
  Scope: M.
- **`a2web profile` CLI commands.** Source: PR7d. *Why deferred:* the
  multi-profile system itself is post-v0.1; CLI follows the model.
  Scope: M.
- **Global circuit breaker alarming.** Source: PR7d. Hooks exist;
  alerting does not. *Why deferred:* alerting is observability work,
  out of scope for the cascade. Scope: S.

## PR7c follow-ups

- **Anubis PoW solver / Turnstile auto-solve / cookie-consent dismissal.**
  Source: PR7c. *Why deferred:* Camoufox + realistic timing handles
  most observed cases; explicit solvers wait for v0.2 evidence. Scope: L.
- **Profile-keyed browser contexts.** Source: PR7c. *Why deferred:* the
  profile system itself is post-v0.1. Scope: M.

## PR8b — Site handlers

- **`youtube` handler.** Source: PR8. *Why deferred:* needs the browser
  tier or a `yt-dlp` opt-in dependency; both are non-trivial. Scope: M.
- **`substack` handler.** Source: PR8. *Why deferred:* trafilatura
  already handles articles; per-domain auto-detection complexity is not
  worth it without signal. Scope: S.
- ✅ **`twitter` / X handler — SHIPPED (v0.3, commit 519c011).** Nitter
  rotation with per-instance circuit breakers. 87% coverage. Was
  previously listed as deferred (auth-gated, no clean v0.1 path) —
  Nitter unblocked it.
- **Per-handler proxy plumbing.** Source: PR8. *Why deferred:* mostly
  mechanical — bundle with PR7e proxy work. Scope: S.

## v0.2 candidates

- 🟢 **Reader-LM v2 fallback.** Source: engineering.md §10. *Status:*
  greenlit post-v0.5.0 — Denis OK with running benchmarks + deep
  research. Trip condition: corpus run shows trafilatura + readability
  miss ≥10% of content on a representative set. Scope: L (corpus
  selection + extraction harness + Reader-LM v2 wrapping + threshold
  picker). Next step: pick benchmark corpus (~50-100 URLs across
  article / docs / forum / aggregator / SPA classes).
- **Multimodal fetch (screenshot + DOM as response).** Source:
  engineering.md §10. *Why deferred:* requires the browser tier to
  emit screenshots and a response-shape change; v0.2 contract decision.
  Scope: L.
## v0.3+

- **Browser-as-a-service remote CDP.** Source: engineering.md §10. *Why
  deferred:* removes the local Camoufox dep at the cost of a network
  hop and a service to operate. Scope: L.
- **VLM image captioning.** Source: engineering.md §10. *Why deferred:*
  vision pipeline. Scope: L.
- **Distributed cache (remote backend).** Source: engineering.md §10.
  *Why deferred:* sqlite is sufficient for single-operator use. Scope: L.
- **Webhook callbacks for slow fetches.** Source: engineering.md §10
  (vision). *Why deferred:* event-sink pattern, not yet needed. Scope: M.
- **LLM-emitted hints.** Source: engineering.md §10 (vision). *Why
  deferred:* needs an evaluation harness first. Scope: L.

## v1.0 / vision

- **Search aggregation as primary surface.** Source: engineering.md §10
  (v1.0). *Why deferred:* a separate product surface, not a tier in
  the cascade. Scope: L.

---

## Findings from `benchmarks/vs-webfetch/2026-05-11/` (a2web vs Claude Code WebFetch)

20-URL benchmark, blind LLM judge, three a2web response variants. Full
write-up at `benchmarks/vs-webfetch/2026-05-11/findings.md`. Headline:
**a2web's content tier wins on quality (mean 3.40 vs WebFetch 2.95) but
the default response envelope leaks ~80% of its token budget for ~0%
quality gain on most tasks** — `links` is 49% of payload, `fit_md` is
19% of payload as a pure duplicate of `content_md`.

### v0.3 (response-envelope diet) — SHIPPED ✓ (v0.3.0)

Three items merged. Benchmark re-run on 2026-05-11 against the same
20-URL corpus shows **72% token reduction across the default response
shape**, judged equivalent quality on 17/20 URLs.

- ~~**Stop populating `fit_md` with `content_md`**~~ ✓ SHIPPED — fit_md
  stays None until a real pruning filter ships.
- ~~**Default `include_links=false` (param-gated)**~~ ✓ SHIPPED — new
  `include_links: bool = False` param on the `fetch` tool.
- ~~**Move `diagnostics` behind `debug=true`**~~ ✓ SHIPPED — new
  `debug: bool = False` param; one-line `diagnostics_summary` always
  populated.

Still deferred:

- **🟡 Classify links at extraction time** (`role:
  primary|nav|meta|footer`) and filter by default. Source: H2.
  Eyeballed HN/PyPI/gh-trending payloads — 60-80% of link entries are
  UI/nav/redundant. Even when links stay, returning only `role=primary`
  shrinks them ~5×. Scope: M.

### v0.3 (browser tier reliability) — SHIPPED ✓ (v0.3.0)

- ~~**Investigate why browser tier fires 0/20 times**~~ ✓ SHIPPED — gate
  now produces `suggested_tier="browser"` on the broader JS-shell pattern
  (Next.js / React / Vue / Twitter / Ember / noscript). Orchestrator
  already routed on the hint; the gate side was the bottleneck.
- ~~**Gate false-positive on Linear**~~ ✓ SHIPPED — all interstitial /
  block-page markers are now length-gated; substantive extracted content
  (>= LENGTH_FLOOR) keeps `status=ok` regardless of marker matches.

### v0.3 (handler coverage)

- **🟢 Add site handlers for PyPI, npm, GitHub Trending.** Source:
  benchmark finding. Current envelope/value ratios:
  - PyPI: 13,312 tokens A_full, 287 links → 1,011 tokens C_content (13×
    bloat for the same answer)
  - gh-trending: 27,167 tokens A_full, 1,142 links → 379 tokens
    C_content (71× bloat, AND only A had the data to answer the task)
  - npm: 1,874 tokens A_full → 228 tokens C_content (8× bloat)
  Handlers would return structured tier-0 output with the right
  fields, killing both the bloat and the list-extraction failure mode.
  Scope: M per handler.

### v0.3+ (untrusted-content envelope) — security posture

- **🟡 Wrap fetched content in a structural envelope** (e.g.
  `<a2web:content>...</a2web:content>` or explicit
  `is_user_authored: bool` flag) so downstream agents can syntactically
  distinguish page content from system signals / harness messages.
  Source: false-positive incident during the benchmark — even a careful
  reader misclassified a Claude Code harness reminder as page content
  when it appeared inside a tool-result envelope. If a single LLM
  judge could be confused, so can downstream agents consuming
  `content_md`. Scope: S (envelope) + M (taxonomy).

### Process / measurement

- **🟢 Make this benchmark a recurring eval.** Source: benchmark
  itself. Re-run on each v0.3+ release; track judge scores + token
  sums as regression metrics. Adds the harness, corpus, and judge
  prompts already in `benchmarks/vs-webfetch/`. Scope: S.
