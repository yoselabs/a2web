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

## 2026-06-26 — Browser backend pluggability (roadmap + Camoufox/Playwright compat)

Surfaced by the Trendyol incident (`surface-browser-internal-errors-as-hints`):
the browser tier is hostage to a single Firefox fork's version-skew, and can't
read Chromium-only SPAs. Plan = a pluggable `BrowserBackend` interface (mirror
of the LLM provider seam) with multiple swappable engines, chosen by a
SPA-read/robustness/speed comparison.

- **🟢 Camoufox ⇄ Playwright version-skew guard (compat note).** The Trendyol
  driver crash was `daijro/camoufox` #635/#617: Playwright **1.60.0**
  (PR microsoft/playwright#39767) added an unguarded `pageError.location.url`
  deref; Camoufox's juggler emitted `Page.uncaughtError` without a location →
  driver crash. Producer-side fix = camoufox **PR #625** (commit `b05563291d`,
  juggler always emits location). **As of 2026-06-26 #625 is MERGED BUT
  UNRELEASED** — it is 3 commits *ahead* of the newest published browser build
  (`v150.0.2-beta.25`, 2026-05-11); latest pip `camoufox==0.4.11` pins an older
  FF135 build. Playwright will NOT fix it (vanilla PW-Firefox always emits
  location → not their bug). **We are immune today ONLY because Playwright is
  pinned 1.59.0 < 1.60.0** — the deref doesn't exist yet; the camoufox build
  version is irrelevant to that. **GUARDRAIL: do NOT bump `playwright` to ≥1.60
  until a Camoufox *release* contains `b05563291d`** (or build the browser from
  source with the patched juggler). Add a pinned-pair compat test. The durable
  fix is a Chromium backend (Change 2), which has no Firefox-juggler coupling.
  Scope: S (pin assertion + compat test); the real exit is `browser-backend-*`.
- **✅ Browser-backend roadmap — SHIPPED (collapsed to 2 changes).**
  (1) `browser-backend-interface` — extracted `BrowserBackend` + `RenderedPage`,
  moved Playwright mechanics into `PlaywrightBackend` (ARCHIVED 2026-06-27).
  (2) `browser-backend-bakeoff` — the originally-planned changes 2-4 collapsed
  into one evaluate-then-commit change: a live render-layer bake-off of
  patchright + rebrowser + zendriver, then **keep two** (patchright fast rung +
  zendriver robust rung — they're complementary, not strictly ranked; the
  Chromium drop-ins fail the Trendyol/Hepsiburada SPAs zendriver reads), pruned
  rebrowser, gated Camoufox, dropped `camoufox`/`playwright`/`<1.60`. Wired as
  two browser tiers on the *existing* gate→playbook escalation (the
  `gate_browser_signal` rule, cap `1→2`), not a new mechanism. The
  pinned-pair compat test idea is moot — `playwright` is no longer a dep.
- **🟡 zendriver robust rung: add a shared-browser pool.** The robust rung
  (`browser_robust`, zendriver) launches a fresh Chromium per render (v1, D3) —
  ~4-5x slower than the pooled fast rung (~6.7s vs ~1.4s in the bake-off). A
  per-host context pool (mirroring `PlaywrightBackend`) would close most of that
  gap. Low urgency: browser is the escalation tier, so the cost only bites when
  the fast rung can't read the page. Scope: M.
- **🟢 Camoufox re-enable when #625 ships.** The Camoufox launcher code is
  retained, gated to `Unavailable` in `_manifests/browser_backends/camoufox.py`.
  When a Camoufox *release* contains juggler `b05563291d` (PR #625), re-enable =
  flip the manifest `_build` back (the commented body is kept inline) + re-add
  `camoufox[geoip]` to `pyproject.toml`. Until then it stays unselectable.

## 2026-06-25 — LLM provider seam leftovers (from `centralize-provider-selection` + `inject-provider-via-di`)

Discovered while centralizing provider selection and injecting the provider via
DI. None block those changes; all are latent cleanups surfaced by the audit.

- **🟡 claude-code's availability gate is vacuous.** `ClaudeCodeProvider.__init__`
  is a no-op — real readiness (OAuth/OS session) is only known at the first
  `complete()`. So `load_surface` always lists `claude-code` as "available", and
  `auto` always picks it first, only discovering an unusable session at call
  time (the error surfaces as a generic fetch failure, not a clean
  "provider unavailable" degrade). Options: a real construction-time probe, or
  fall back to the next provider on the first `complete()` failure. Scope: M.
- **🟢 `provider.name` spelling drift + redundancy.** `providers/base.py`'s
  comment cites `claude_code` while the runtime id / manifest name is
  `claude-code`. Selection keys off the **manifest name** (authoritative);
  `provider.name` is effectively dead for routing. Reconcile the comment and
  consider dropping `provider.name` as a selection input. Scope: S.
- **🟢 `ModelSpec` is now a thin single-field wrapper.** After deleting the dead
  `.provider` field + `.key()`, `ModelSpec` carries only `model: str`. Candidate
  to collapse into a plain model-id string (or keep as a typed nominal if a
  second field ever returns). Low priority — touches every construction site.
  Scope: S.

---

## 2026-06-25 — reliable AliExpress / Alibaba access (from `block-detector-recognize-alibaba-baxia`)

That change shipped only the **best-effort** slice: the gate now recognizes
Alibaba's Baxia "punish" interstitial and escalates raw→browser (or fails
honestly with `subsystem=alibaba_punish`) instead of dying silently at bare
`length_floor`. Live PoCs this session established that *reliable* access is a
much larger, IP-bound problem. Deferred, in dependency order:

- **🔴 Browser tier honors `proxy_url` (the keystone).** `tiers/browser.py`
  currently does `del proxy_url` (line ~135) — Camoufox always exits the raw
  host IP. So today you can *render* (browser, no proxy) OR *route through a
  clean IP* (raw, no rendering), never both. AliExpress needs both at once.
  Until this lands, no proxy spend helps the browser tier. The user has
  residential proxies (non-KZ) ready to prototype against once this exists.
  Scope: M.
- **🔴 Per-IP behavioral pacing / rotation.** PoC root cause: AliExpress's
  Baxia is driven by per-IP behavioral reputation, not fingerprint — even a
  real Chrome on a real residential IP hit the slider once the IP was flagged
  by a request burst. Reliable access needs rate-limiting + rotation across a
  residential pool so no single IP trips the "punish" state. Scope: M.
- **🟡 KZ residential proxy provisioning.** The KZ AliExpress *locale* needs a
  KZ-geo residential IP (the user's Istanbul IP geo-redirects to
  tr.aliexpress / aliexpress.ru). Procurement, not code. Scope: S (config).
- **🟡 AliExpress product-JSON handler.** Even once a browser renders the page,
  trafilatura extracts ~nothing from the product grid; the data lives in an
  embedded `_init_data_` / `runParams` blob. A tier-0 handler (reddit/hn/arxiv
  shape) that parses it would be far more robust than prose extraction.
  Scope: M.
- **⛔ Out of scope, permanently:** CAPTCHA-solving (the Baxia slider /
  image-select). Strategy is *avoidance* (clean IP + pacing + real
  fingerprint), never solving. This means reliable access is **probabilistic**
  against an adaptive anti-bot — never guaranteed.

Note: this is purely an anti-bot + IP-reputation problem. The earlier
"simulate an AI agent" idea is irrelevant here (AliExpress is not a UA
allowlist site). Contrast akakçe.com, which is the inverse: it *blocks*
declared AI-agent UAs via Cloudflare while serving plain scrapers fine.

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

## 2026-05-25 — bench follow-ups (v0.24+)

- 🟢 **`bench-shutdown-thread-leak`** — operator pain RESOLVED 2026-06-11.
  Source: 2026-05-25 v0.23 bench run. After the final cell ends and
  `write_all(report)` completes, the Python process hung in `Py_FinalizeEx →
  wait_for_thread_shutdown` on a non-daemon background thread parked in
  `_queue_SimpleQueue_get` (a curl_cffi / SDK worker on `queue.SimpleQueue.get`).
  Output was fully written; only the exit blocked, requiring a manual SIGKILL —
  and the lazily-launched Camoufox subprocess lingered while the parent hung.
  **Landed:** `llm_eval/__main__.py::main()` now flushes stdout/stderr and
  calls `os._exit(rc)` after `asyncio.run` returns — skips interpreter finalize
  (so no thread-join hang) and the parent dies immediately (so Camoufox reaps
  itself via its parent-death pipe). Mechanism proven deterministically (a
  non-daemon SimpleQueue thread hangs normal return; `os._exit` exits clean).
  **Still OPEN (low pri):** upstream root-cause attribution — *which* dep leaks
  the non-daemon thread. **Not a2kit** — the bench never starts the MCP server
  or `a2kit.run`, and refound LDD is threadless stdlib logging; a2kit has no
  non-daemon thread on this path. `SimpleQueue.get` rules out `anyio` (uses
  `queue.Queue`) and aiosqlite (daemon, joined). Prime suspects: `curl_cffi`
  (libcurl multi-handle) or the playwright/camoufox pipe transport (Camoufox is
  what visibly lingered). Cheap probe to attribute without a full bench: in a
  subprocess, run one minimal `fetcher.fetch` over the raw (curl) path and one
  over the browser tier, then `threading.enumerate()` the surviving non-daemon
  threads after `asyncio.run` returns — names the culprit module without LLM
  spend. (Heavier fallback: arm `faulthandler.dump_traceback_later` in a live
  bench and grep the parked thread's filename.) Scope: S.

---

## 2026-05-26 — structural-refactor follow-ups (ADR-0001 deferrals)

From the 2026-05-26 explore session that produced ADR-0001 + three openspec
changes (`wobble-typed-funnel`, `arch-fitness-functions-bootstrap`,
`unify-plugin-manifests`). Three audit findings were deliberately NOT folded
into the change set — each earns its own pass when its trip condition fires.

- 🟢 **`reddit-policy-to-planner`.** Source: 2026-05-26 explore audit
  (Cluster D). `handlers/reddit.py:155-160` carries shape-aware escalation
  policy inline (`if shape in ("search", "listing"): RetryViaArchive`).
  Correct behaviour, wrong layer — escalation policy belongs in
  `actions/playbook.py`, not inside the handler. Cost of moving today: low
  but unclear value (only Reddit needs it). Trip condition: a second handler
  wants shape-aware escalation. Until then, the inline check is acceptable.
  Scope: S.

- 🟢 **`askresponse-composite-fields`.** Source: 2026-05-26 explore audit
  (Cluster E). `AskResponse` exposes 7 router-shape fields flat
  (`structural_form` + `shape` + `genre` + `obstacle` + `ask_here` +
  `try_url` + implicit grouping). Natural sub-models are
  `PageClassification(structural_form, shape, genre)` and
  `NextSteps(obstacle, ask_here, try_url)`. Consumers today must reason
  about which fields belong together. Cosmetic until consumer count > 2;
  serializer keeps wire flat for back-compat. Trip condition: a third
  external consumer of `AskResponse` ships, or we hit a real bug from
  flat-field reasoning. Scope: S.

- 🟢 **`tier-loop-state-machine`.** Source: 2026-05-26 explore audit
  (Cluster B). `fetcher._phase_tier_loop` is 141 LoC mixing proxy
  acquisition + conditional-request header building + after-tier action
  dispatch + observation logging + loop control. Refactoring into an
  explicit `TierIteration` state with Command-typed actions would flatten
  the phase function. The current shape works; the risk is future tiers
  expanding it further. Trip condition: a new tier needs bespoke
  rate-limit-backoff or auth-retry policy, OR the function crosses
  ~200 LoC. Scope: M.

- 🟢 **`cross-package-coupling-cleanup`.** Source: 2026-05-26 Tach spike.
  `packages/block_detector.py:23` imports `a2web.packages.escalation` —
  one `packages/X` reaching into another `packages/Y` instead of through
  domain glue. Grandfathered into `tach.toml`'s ignore list by
  `arch-fitness-functions-bootstrap`; this entry tracks the actual
  refactor (likely: move `EscalationSignal` to a shared location, or
  invert the dependency). Scope: S.

- 🟢 **`wobble-to-a2kit`.** Source: 2026-05-26 ADR-0001 "Negative /
  accepted cost". If `wobble.parse_with_policy` graduates into `a2kit`
  as a public library primitive, the funnel must defend itself against
  library consumers (who can't depend on a2web's pytest-archon CI).
  That's the moment to add phantom-types + beartype runtime enforcement
  (Recipe B from the explore session). Today: in-tree, AST-test backstop
  is sufficient. Trip condition: a second project (a2kit-internal or
  otherwise) needs the wobble shape. Scope: M.

---

## 2026-05-25 — fetcher-orchestrator-refactor-v1 follow-ups (v0.23+)

Shipped `fetcher-orchestrator-refactor-v1` (v0.23). Closed TIER-1 audit smells
#1 (dual-semantics state slots), #2 (three construction paths drift),
#3 (escalation contract scattered), plus TIER-2 #5 (boundary freeze). Four
follow-up items surfaced during the audit that we deliberately deferred —
none are blocking, each earns its own design pass.

- 🟢 **`unify-resource-protocol`.** Source: 132-a2kit-structural-audit
  (TIER-2, Smell #4). Resources today split into "crash on unavailable"
  (Sqlite required) and "graceful unavailable" (BrowserPool, LlmExtractor
  via `unavailable_lazy`). Pattern works but is implicit — a future reader
  has to read `bootstrap_state` and `unavailable_lazy` to learn which is
  which. Worth promoting to a typed Protocol (`OptionalResource` vs
  `RequiredResource`) once a third resource needs the choice. Trip
  condition: third resource arrives. Scope: S.
- 🟢 **`url-shape-router-helper`.** Source: 132-a2kit-structural-audit
  (TIER-2 DX). Each handler reimplements URL-pattern matching
  (`matches(url)`) and there's a per-handler skip-on-no-match
  bookkeeping convention via `TierResult(no_match=True)`. A shared
  URL-router helper (host + path-shape declared once per handler) would
  drop ~50 LOC across 9 handlers and make adding a new handler a
  three-line registration. Scope: S.
- 🟢 **`package-folder-vs-flat-convention`.** Source: 132-a2kit-structural-audit
  (TIER-2 DX). `packages/` currently mixes flat `.py` (browser_pool,
  block_detector, http_cache, proxy_routing, content_extract, escalation)
  and folders (`llm_extract/`, `cookie_store/`). Convention: folder when
  multi-author surface, flat otherwise. Document this in
  `src/a2web/packages/README.md` and add a one-line test that asserts
  any folder package exports its public surface from `__init__.py`.
  Scope: S.
- 🟢 **`handler-failure-visibility-in-response`.** Source:
  132-a2kit-structural-audit (TIER-2 operator UX). When a site handler
  short-circuits with a non-ok FetchVerdict (rate limit, timeout,
  404 from an API endpoint), the response carries
  `status=failed` + `narrative` but the operator can't tell from the
  envelope which tier failed — they have to read `debug.diagnostics`.
  Worth surfacing `failed_at_tier: "site_handler:reddit"` (or similar)
  as a top-level failure-only field. Scope: S.

---

## 2026-05-23 — prompt cache + affordances followups (v0.19+)

Shipped `make-llm-prompts-cache-compliant` (v0.19): `EXTRACT_CACHEABLE_V1`
template with byte-stable prefix, `cache_control` markers on Anthropic-direct,
byte-stable concat on claude-agent-sdk (no marker API), OpenAI auto-cache
for free. Spike + capability work follows.

### LLM caching — operational follow-ups

- 🟡 **Verify Claude Code SDK auto-cache fires in production.** The probe
  confirmed the SDK has no `cache_control` API and that we rely on the CLI
  binary to apply caching given a stable prefix. We have not verified the
  CLI actually does so for one-shot `query()` calls (it definitely does for
  multi-turn conversations). Spike: write a small script that runs the
  production Extractor twice with the same `content` and different `ask`
  values, inspects `ResultMessage.usage` for non-zero `cache_read_input_tokens`
  on the second call. Scope: S (~40 LoC + a notes file in `eval/findings/`).
- 🟡 **Telemetry: cache hit/miss ratio in production.** Add a
  `tokens.cache_read` / `tokens.cache_creation` rollup on the LDD bus.
  Today the values flow into `ProviderResponse.prompt_tokens` (aggregated)
  but the breakdown is not surfaced anywhere observable. Trip condition: we
  want to know whether the 5-minute TTL is enough or extended cache (1-hour)
  is justified.
- 🟢 **Extended cache (1-hour TTL) plumbing.** Anthropic supports `cache_control:
  {type:"ephemeral", ttl: "1h"}` for higher write cost but longer hits.
  Defer until telemetry shows enough cache misses that would have hit a
  1-hour window. Scope: S (one kwarg + a settings toggle).

### Affordances — "what else this page can answer"

- ✅ **Affordances spike v1 (2026-05-24).** 5-URL probe with generic prompt.
  Findings: `eval/findings_2026-05-24-affordances-v1.md`. Follow-ups + shapes
  hit quality bar on 4/5 URLs; `missed_sections` is hallucination-prone (arXiv
  abstract case); standalone Haiku call is $0.013/URL but fold-in marginal cost
  is ~$0.002/URL (~18% on top of `ask`). Design: fold into
  `EXTRACT_CACHEABLE_V1` under `include_affordances=True`, drop
  `missed_sections`, keep `shapes` closed-enum.
- ✅ **Affordances spikes v2 + v3 (2026-05-24).** 30-URL corpus across content
  extremes × 3 prompt variants (V_GEN, V_CTX, V_LEAN). Findings:
  `eval/findings_2026-05-24-affordances-v2-v3.md`. Key results: 100% fetch
  success, 100% JSON parse success across 90 calls; closed shape vocabulary
  holds at scale; V_CTX classification 63% literal / ~80% semantic accuracy
  (model often more right than my declared labels); V_LEAN as standalone 2nd
  call only ~5% cheaper than V_GEN (page content dominates cost — fold-in is
  the only economic shape); V_CTX wins on edge cases (paywalled / 404 / unusual
  pages) at zero cost penalty over V_GEN.
- ✅ **Affordances spikes v4 + v5 (2026-05-24).** Two-axis rubric calibration.
  v4 found `page_kind_confidence` was conflating epistemic uncertainty about
  the label with content usefulness — model returned `high` on everything
  because it WAS confident, even when wrong. v5 split into two orthogonal
  axes (`page_kind_confidence` + `content_value`) following RAG-eval
  literature (Braintrust/Deepchecks/ResearchRubrics). Added hard cluster
  trigger forcing confidence ≤ medium when label falls in a confusable
  cluster. Findings: `eval/findings_2026-05-24-affordances-v5-two-axes.md`.
  Result on full 30: 0 envelope violations, 0 parse failures, 5/30 medium
  confidence (vs 30 high), content_value well-distributed (18 high / 5 med
  / 3 low / 4 omitted on obstacles). **Design LOCKED for production.**
- ✅ **Affordances production wiring (v0.20, 2026-05-24)** — superseded by
  router-shape v0.21 (2026-05-25). The single `affordances` payload was
  replaced wholesale by seven router-shape fields (`answer`, `structural_form`,
  `shape`, `genre`, `obstacle`, `ask_here`, `try_url`) per
  `openspec/changes/refactor-ask-to-router-shape/`. v0.20 lived one release.
- ✅ **Router-shape production wiring (v0.21, 2026-05-25).** Shipped under
  `openspec/changes/refactor-ask-to-router-shape/`. Three exploration spikes
  (`router_shape_v1`, `router_shape_v2_stress`, `surface_eval_v1`/`v2`)
  refined the affordances design into a router-shape envelope. `RouterPayload`
  boundary type + pydantic mirror with closed `Literal` enums on all 4 typed
  fields. `EXTRACT_ROUTER_V1` template extends `EXTRACT_CACHEABLE_V1`
  byte-for-byte on the cache prefix. Default ON; opt-out via
  `ask(include_routing=False)`. Omit-empty discipline on all 4 conditionals via
  `_prune_wire`. Includes `mcp_servers={}` + `strict_mcp_config=True` +
  `agents={}` Claude Code provider isolation (closes the personal-context
  memory leak observed in surface_eval_v1). All gates green. Remaining:
  output-benchmark A/B (`make bench` — live-network) before declaring quality
  parity vs v0.20.

### Router-shape — deferred follow-ups (v0.21+)

- 🟢 **Structured-answer mode.** When the user asks for an enumeration ("top
  N stories", "all bags reviewed with verdict"), let them supply a JSON schema
  for the `answer` field. Likely separate `extract` tool with consumer-supplied
  schema; needs schema-discovery design. Out of scope for v0.21 — surface the
  list IN the answer string for now.
- 🟢 **page_kind_confidence resurrection.** v0.21 dropped the
  confidence/content_value fields on the theory that behavioral signal
  (presence of `ask_here` / `try_url` arrays) paraphrases them well enough.
  If a real consumer wants the explicit confidence rating back, add it as a
  debug-only field — don't bloat the default wire.
- 🟢 **Genre prompt tightening for HN-front.** Pre-impl eval found `news` was
  emitted instead of `community` on HN front-page (defensible; both apply).
  Worth one prompt sentence pushing aggregator-of-tech-discussion pages to
  `community` instead of `news`.
- 🟢 **Corpus refresh**: 3 URLs in the v2-v5 corpus are stale 404s
  (`news-bbc`, `comments-lobste`, `blog-jvns/2024/01/05/2023-in-review`).
  Replace before next eval pass.
- 🟢 **Content-value second-order signal**: `content_value=low` paired with
  a content-kind page_kind could auto-trigger browser-tier escalation.
  Telemetry first to confirm the signal is reliable at production scale.

### Reddit `old.reddit.com` raw-tier fetch failure (2026-05-24)

- ✅ **Fixed via `expand-js-shell-markers` (v0.22, 2026-05-25).** Root
  cause was upstream of the handler: the block detector's marker list
  was React/Vue/Next-centric and missed Reddit's actual response shape
  (a JS-challenge anti-bot interstitial, not a content shell). Probes
  also disproved option (a): `old.reddit.com` is also 403'd to unauth
  curl_cffi. Option (c) implemented via marker detection — the existing
  `EscalateBrowser` planner rule already routes `suggested_tier="browser"`
  to Camoufox. No handler change needed.

### 403 → browser planner escalation (2026-05-25)

- 🟢 **Investigate** whether a planner rule "raw or site_handler returned
  status=403 → EscalateBrowser" earns its complexity. `eval/spikes/
  cloudflare_bypass_probe.py` (2026-05-25) showed `curl_cffi
  impersonate=chrome` already bypasses Cloudflare, and no live case has
  been found where `raw=403 ∧ browser=200`. Defer until a probe finds
  one. Open question raised during `expand-js-shell-markers` exploration.

## 2026-05-23 — post-trio followups (v0.18+)

Added after shipping `replace-cookie-store-with-browser-cookie3` (v0.16),
`replace-github-handler-with-gidgethub` (v0.17), and `add-microdata-rdfa-extraction`
(v0.18). The mission-driven-library exploration surfaced Tier-2 swaps and
two new capability ideas; recording them here so they don't slip.

### Library swaps (Tier 2 — defer until a concrete win signal)

- 🟢 **arxiv handler → `arxiv-py`.** Source: 2026-05-23 exploration. Current
  `handlers/arxiv.py` is ~290 LOC of stdlib `xml.etree.ElementTree` against
  the arXiv API. `arxiv-py` is a maintained client with sane pagination,
  retry, and typed results. Sans-IO-adjacent (uses `urllib`/`feedparser`
  internally — would need a transport adapter similar to gidgethub's
  `_CurlCffiGitHubAPI` to keep our curl_cffi tier + breakers). Trip
  condition: bug or maintenance burden on arxiv.py warrants the swap.
  Scope: M (~150 LOC out, +arxiv-py direct, +feedparser transitive).
- 🟢 **URL canonicalization → `courlan`.** Source: 2026-05-23 exploration.
  Multiple sites in domain.py (Google/Bing → DDG rewrite,
  reddit `.json` API munging, host-normalisation for breakers) reinvent
  pieces of URL canonicalization. `courlan` (the trafilatura sibling)
  centralises tracking-param stripping, host normalisation, ccTLD-aware
  language detection. Small, sans-IO, no transport opinions. Trip
  condition: a real bug class (e.g. cache-key drift from tracking-param
  duplication) surfaces. Scope: S.
- 🔴 **HN handler — NO swap warranted.** Source: 2026-05-23 exploration.
  Current `handlers/hn.py` already uses `hn.algolia.com/api/v1` and is
  cleanly structured (~230 LoC). The python-firebase / hn-py libraries
  do not improve on what we have. Recorded as a "do not pursue" entry.
- 🔴 **Reddit handler — NO clean swap.** Source: 2026-05-23 exploration.
  `praw` is async-unfriendly and owns its transport; `asyncpraw` exists
  but bundles `aiohttp`. Neither composes with our curl_cffi tier +
  breakers + proxies. The 799-LOC hand-rolled handler stays. Reconsider
  only if a Reddit-side API contract change forces a rewrite.

### Capability ideas (new — 2026-05-23)

- 🟡 **`llms.txt` / `llm.txt` discovery.** Source: 2026-05-23. Adopt the
  emerging convention (Mintlify et al. — `/llms.txt` at site root, with
  optional `/llms-full.txt` for the full corpus) as a tier-0 detector.
  *Why interesting:* on sites that publish it, `llms.txt` is a curated
  text surface that already represents what the operator wants an LLM
  to see — strictly higher signal-to-noise than trafilatura against the
  HTML chrome. The probe is cheap (one HTTP HEAD/GET to `/llms.txt`)
  and short-circuits the entire tier cascade when present. Caveats:
  (a) convention is young — coverage is small but growing fast; need
  to confirm with a corpus probe before sinking design effort. (b) the
  spec allows it to be a markdown index pointing at *other* URLs — we'd
  want to expand referenced URLs only if the prompt asks the agent to
  drill down, not eagerly. (c) hostile `llms.txt` is a real prompt-
  injection surface (operator-controlled instructions disguised as
  content); needs the same untrusted-content envelope as page content.
  Scope: S (detector + cache hit), M (drill-down expansion + injection
  defence). Cross-ref: spec/SIG at https://llmstxt.org. Trip condition:
  corpus probe shows ≥5% of frequently-fetched hosts ship one.
- 🟡 **Agent-identity stealth (look like a human, not a bot).** Source:
  2026-05-23. Audit and minimise the signals that mark our requests as
  "AI agent". Today the default `User-Agent` is a static Safari string
  (good) but other tells leak: (a) the LLM extractor sometimes
  fingerprints with referer-less navigation patterns; (b) some handlers
  set `X-GitHub-Api-Version` (acceptable on api.github.com but a generic
  fingerprint elsewhere); (c) browser tier may carry telltale headless
  Camoufox fingerprints under certain configurations; (d) we have no
  per-host UA pinning to match the canonical browser the host expects
  (e.g. Reddit serves different content to mobile UA vs desktop).
  *Concrete pieces of work:*
  1. **UA rotation strategy** — small pool of real recent Safari/Chrome/
     Firefox UAs, pinned per-host for the session so requests look
     coherent.
  2. **Referer chains** — set realistic `Referer` headers on follow-up
     requests so we don't look like a fresh-tab fetcher on every URL.
  3. **`Sec-Fetch-*` header trio** — the modern fingerprint-via-omission
     signal; we currently omit these, real browsers send them.
  4. **AcceptedLanguage / Accept jitter** — small per-session variation
     to break the "exact same fingerprint across 1000s of requests"
     tell.
  5. **Tier-0 handler audit** — ensure no handler leaks `a2web` in any
     outgoing header. GitHub's `_REQUESTER = "a2web"` shows up in
     `User-Agent` per gidgethub — change to a generic project string.
  6. **Cookie carry-through** — when we have a `CookieJarResource`
     mirror for a host, our requests should look like the operator's
     browser session (same UA + same cookies + same Accept headers).
     Today the UA isn't pinned to match the cookie profile.
  *Why important:* Cloudflare / Akamai / DataDome are increasingly
  scoring requests as "agent vs human" not just "browser vs curl";
  even a perfect TLS fingerprint loses if the header set is
  inconsistent. The cumulative cost of looking obvious is silent quality
  loss — sites return banner-mode content instead of full content. The
  point is NOT to evade rate limits or impersonate users illegally; it
  is to avoid the increasingly-common "served degraded content because
  you look like a bot" failure mode that doesn't even surface in our
  block detector. Cross-ref: existing `cookie_jar.py` (already steps
  toward this); `tiers/raw.py` (JA3/JA4 already correct). Scope: M
  (audit + pinning), L (full Sec-Fetch-* + referer-chain semantics).
  Trip condition: any benchmark URL that returns degraded content under
  a2web but full content under a real browser session.

### Speculative — only if signal surfaces

- **Re-adopt `extruct` for RDFa.** Source: 2026-05-23 — extruct was
  added then removed mid-implementation (see `openspec/changes/archive/
  2026-05-23-add-microdata-rdfa-extraction/design.md` D1). The
  rdflib weight is only justified by RDFa coverage; eval corpus
  shows zero RDFa hit rate today. Reversible — add back if a real
  RDFa-shaped failure surfaces in a future `make bench` run
  (academic-publishing URL that ships RDFa but no microdata / LD-JSON).
  Scope: S.
- **PDF tier (`pymupdf` or `marker`).** Source: 2026-05-23 — was raised
  in the mission-driven-library exploration but not pursued in the
  trio. Tier 4. Many high-value agent destinations (regulatory
  filings, academic papers, manuals) are PDF-first; the cascade
  currently 404s or content-type-mismatches them. Choice between
  `pymupdf` (fast, lightweight, classic) and `marker` (LLM-aware,
  better tables / figure handling, much heavier). Decide via a
  small spike on a representative corpus. Scope: M (pymupdf) / L
  (marker).

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

## Hard-access forums (Tieba / Zhihu / Discuz!)

- **Tieba / Zhihu / Discuz!-engine forums — access-blocked, needs an
  access spike.** Source: `structural-record-detection` CN-forum probing
  campaign (2026-05-22). *Finding:* for these targets the blocker is
  **access, not extraction**. A probe with curl_cffi Chrome-impersonation
  (a2web's raw-tier engine) got: Tieba → HTTP 403; Zhihu → SPA shell + 403
  on every content page; Discuz! forums (hostloc, right.com.cn) →
  login-walls / pages stripped to anonymous fetch. The structural record
  detector cannot be validated against them because there is no clean HTML
  to run it on. *Why deferred:* needs its own spike first — does a2web's
  browser tier (Camoufox) + stealth + `cookie_jar` punch through these
  anti-bot walls? Until that is known the handling cannot be specified.
  Discuz! additionally has no API (an engine-specific HTML parser would be
  needed) and its post wrappers use empty-class `<div id="post_X">` that
  the structural detector's non-empty-class guard rejects. V2EX, Discourse,
  and Habr — the accessible CN/RU targets — are covered by their own
  handler changes (`v2ex-handler`, `discourse-handler`, `habr-handler`);
  this entry is the residual hard tier. Scope: L (access spike + per-engine
  handling).

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

### v0.4+ (link addressing / aliases)

- **🟡 Alias-addressed links for drilldown flows.** Source: 2026-05-18
  discovery design chat. *Problem:* multi-step research (Reddit thread →
  linked page; AliExpress listing → product detail; HN front page →
  comments) currently round-trips full URLs through the agent, which is
  expensive on listing-style pages where 50+ candidate URLs may each be
  100+ chars. *Idea:* return short alias IDs (e.g. 6-char) alongside
  `next_links`; store alias → URL in sqlite with short TTL scoped
  per agent session; agent passes `alias=` to the next `fetch` call.
  *Why deferred:* prerequisite (curated `next_links` field) shipped in
  v0.7 link-discovery (2026-05-18) — see CHANGELOG. Aliasing earns its
  keep only once we measure full-URL pass-through as the actual bottleneck
  on real agent traces; today's benchmark corpus doesn't yet show it.
  Adds a stateful layer that breaks the current stateless fetch contract.
  Scope: M.

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

### Reddit self-hosted stealth-browser rung (deferred from `reddit-via-zyte`, 2026-07-04)

- **🟡 Self-hosted Camoufox/zendriver browser tier + residential egress as
  Reddit ladder rung 1.** `reddit-via-zyte` shipped the Zyte-primary public
  path and *designed* the arbitration ladder with an `Unavailable`-gated
  self-hosted rung ahead of Zyte, but did not build it. It would give a
  **free, private, logged-in** Reddit read (Zyte is paid, third-party,
  public-only).
  *Why deferred:* the blocker is not the engine — Camoufox (stealth Firefox)
  and zendriver (stealth Chromium/CDP) both pass Reddit headless — it is the
  **IP**. Both are blocked through shen/Contabo datacenter egress
  (`38.242.156.243`); the passing recipe needs a **residential IP** (or the
  operator's own node) plus headful-under-virtual-display (Xvfb/neko/Kasm) for
  the logged-in variant. That is an infra project (egress + display), not a
  code change. Spike scripts: `docs/history/spikes/browser_headful_poc.py`,
  `browser_headful_confirm.py`. Evidence: ADR-0011 (both the headful POC and
  the `reddit-via-zyte` update). Once residential egress exists, the rung slots
  in under `reddit_tier_policy` with zero ladder rewrite (it self-gates via the
  plugin `Unavailable` pattern). Scope: L (infra) + M (tier).
- **🟡 content-expectations action loop for a scrolling browser rung.** The
  `content_expectations.assess` seam resolves `ready|partial|fail`; the Zyte/
  old.reddit path uses it as a pure one-shot post-fetch assertion. A browser
  rung could instead *drive* a bounded scroll/paginate loop off the same
  verdict under a ≤3-min budget to push `loaded` toward the oracle. Designed
  into the seam + design.md, not built (no browser rung yet). Scope: M.

**Smaller `reddit-via-zyte` leftovers (deferred as out-of-scope):**

- **🟢 Caller-selectable comment sort.** The eager Zyte path hardcodes
  `sort=top` (best answers for a Q&A agent). A future tool arg could let the
  caller pick `top | new | controversial | best` (old.reddit supports all).
  Noted in `design.md` §1. Scope: S.
- **🟢 Route Reddit listings/search through Zyte too.** Only *threads* go
  eager-Zyte today; listings/search stay on keyless RSS (which works and is
  cheaper). If richer listing data is ever needed, Zyte `browserHtml` on the
  new-reddit canonical would serve it — the normalizer already emits that
  canonical. Scope: S–M.
- **🟢 old.reddit parser structural-probe test.** The selectolax parser keys on
  `div.thing.comment` / `a.comments`. If old.reddit changes shape the parser
  returns `None` and falls through to RSS (safe), but silently. A periodic live
  probe (behind a marker, not in `make check`) that fails loudly when the
  anchors vanish would catch drift before users see degraded reads. Mitigation
  noted in `design.md` risks. Scope: S.
- **🟢 Live `ask` (LLM-extraction) validation over the scored-comment render.**
  Task 6.2 live-validated the `fetch_raw` path (Zyte → parse → counts/hint). The
  `ask` path (LLM extraction over the nested comment markdown) was not run live —
  worth a one-off check that extraction quality holds on the denser, scored input
  before leaning on it in the benchmark. Scope: S.
- **🟡 Firecrawl has no old.reddit raw-mode equivalent.** The eager Reddit path
  requires Zyte specifically (`httpResponseBody` on server-rendered old.reddit).
  A deployment keyed with *only* Firecrawl falls back to RSS for Reddit. If that
  combination matters, add a Firecrawl raw-fetch shape. Scope: M.
