## Context

a2web v0.1.0 shipped on 2026-05-10 against `a2kit v0.23.0`. Three threads now converge:

1. **a2kit's v0.24–v0.26 deliveries** address rounds 1–3 of our feedback. Every workaround pattern we carried — lifecycle scaffolding, lazy lock fields, in-process test substitutes, duck-typed Protocol for ctx, hand-rolled DI closure — has a first-class replacement.
2. **An OSS-library survey** identified four libraries that replace ~510 LOC of hand-rolled correctness-critical code with maintained alternatives (hishel for HTTP cache, stdlib `RotatingFileHandler` for log rotation, trafilatura bundled metadata, purgatory for proxy quarantine).
3. **Internal magic-smell review** of `fetcher.py` (678 LOC orchestrator) catalogued patterns we keep flagging but never fix — `tier_extras: dict[str, Any]` as a typed hole, two near-duplicate archive dispatch blocks, decimal "Phase 4.25" comments, slippery `tier_used: str` identity.

Bundling the three threads into one tracked change is the right move because they compose: the a2kit migration replaces the lifecycle scaffolding the OSS adoption would otherwise have to re-route around, and the internal cleanup leverages the typed abstractions that both phases unblock. Doing them separately means re-touching the same files three times.

Target outcome: ~4448 LOC → ~3600 LOC (a2web only, before counting workspace packages). One fewer top-level dep (`htmldate` out, `hishel` in is net zero; `aiosqlite` removed if reachable post-hishel). No public tool-surface change — agents see the same `web.fetch` tool with the same `FetchResponse` shape; semantics tighten under the hood (cache becomes RFC 9111 strict; events become typed and subscribable).

The migration is BREAKING at the framework boundary (a2kit v0.23 → v0.26) and at the cache file-format boundary (hishel's SQLite schema differs from ours). Both are acceptable: no public consumer of the framework boundary exists (a2web is the consumer); cache files are non-authoritative and auto-rebuild.

## Goals / Non-Goals

**Goals:**
- Delete every workaround pattern made unnecessary by a2kit v0.26 (lifecycle, singleton DI, ldd sinks, testing.client, tool annotations, Param descriptions, health probe).
- Adopt the four researched OSS libraries where the cost-to-benefit is clear, drop the corresponding hand-rolled code.
- Refactor `fetcher.py` to remove the four named smells (typed extras, single archive dispatch helper, named phases, unified tier identity).
- Extract `proxy/` and `browser/` as internal uv workspace packages with their own `pyproject.toml`, types, and tests. Enforce a hard import boundary (packages cannot `from a2web import ...`).
- Land as four sequential PRs (Phase A → B → C → D), each independently reviewable, each green on `make check` before the next starts.
- Maintain ≥85% test coverage gate.
- Preserve `web.fetch` tool wire surface — agents see no change.

**Non-Goals:**
- Re-design the response envelope or the tier cascade. `FetchResponse` shape and tier order stay.
- Adopt OSS libraries the research rejected (crawl4ai, newspaper4k, nodriver/AGPL, etc.).
- Build the package boundary for `events/`, `gate/`, `log/`, `extract/`, `cache/` — research determined these don't earn packaging post-OSS-adoption.
- Address backlog items unrelated to the three converging threads (PR7e proxy CLI, PR8b YouTube handler, PR10b replay-from-log).
- Ship chunked `content_md` streaming response. Confirmed with a2kit dev: LLM/CLI consumers buffer anyway; defer until human-UI consumer emerges.
- Add `@a2kit.read(timeout=...)` decorator. Q2 documents nested `anyio.fail_after` patterns; the four patterns fit our tier-budget model better than one number anyway.
- Migrate to a different HTTP client. `curl_cffi` stays — TLS impersonation is a hard requirement.
- Replace `purgatory` with anything (it's already in; usage broadened, not swapped).

## Decisions

### D1. Phase order is A → B → C → D, each a separate PR

**Decision:** Four PRs, sequenced, each landed and green before the next starts.

**Rationale:** The a2kit migration (A) is BREAKING and touches almost every file. Bundling A + B + C means one unreadable diff and a bisect nightmare if a regression surfaces. Phase B's cache replacement is BREAKING for the cache file format; running it alongside A means two breaking changes in one diff. Phase C is pure refactor and benefits from the typed abstractions A introduces. Phase D is layout-only and benefits from the smaller modules B + C produce.

**Alternative considered:** Bundle A + B as one PR since both touch state.py. Rejected — the cognitive load of "is this a2kit migration or hishel adoption?" makes review harder. Worth the slight rework cost.

**Consequence:** Four PRs over (estimate) 1–2 weeks of focused work. Main branch stays shippable throughout.

### D2. Use a2kit's `app.singleton(AppState, factory=build_state)` not `app.provide(AppState)`

**Decision:** Register state as a singleton via factory function, not as class-as-factory.

**Rationale:** a2kit's `provide(T)` reads `__init__` via introspection — implicit container behavior that breaks at runtime if signatures change. We flagged this in feedback item 11; the dev acknowledged the concern. For our top-level `AppState`, an explicit factory function is clearer (we control what gets resolved when), and per-App singleton semantics are exactly what `singleton(...)` provides.

**Alternative considered:** `app.provide(AppState)` class-as-factory. Rejected on principle (see above) and practice (`AppState.__init__` takes 7 fields; the factory has real logic to assemble them).

### D3. OTel sink registered via `app.ldd.add_sink(otel_sink)`, not via internal bus

**Decision:** Delete `events/bus.py` and `events/sinks.py.mcp_progress_sink`. Keep `otel_sink` as a single ~15 LOC async callable; register via `app.ldd.add_sink(otel_sink)`. Orchestrator emissions go to `a2kit.ldd.event(ctx, ...)` directly.

**Rationale:** v0.26's `add_sink` API is exactly what we asked for. Sequential fan-out after wire emit, best-effort under cancellation (matches our Q5 stance "10 of 20 events is fine, prefer truth over completeness"). No more double-emit, no more duck-typed Protocol, no more anyio task group in routers.py.

**Alternative considered:** Keep a small internal channel just for OTel, double-emit from orchestrator. Rejected — `add_sink` solves this cleanly.

**Consequence:** `events/` shrinks from ~200 LOC to ~50 LOC (one sink + the typed event payload types). The typed event registry (`app.ldd.events.register(...)`) is the home for `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded`, and new `TierHeartbeat`.

### D4. Add `TierHeartbeat` events from inside slow tiers

**Decision:** Browser tier emits a heartbeat every 2s during page load; archive tier emits a heartbeat per hedged-request boundary. Payload includes current page state (browser) or current upstream (archive) and elapsed-in-tier ms.

**Rationale:** Today the orchestrator emits `TierStarted` → ... → `TierEnded` with no observability during the tier. Browser tier has a 30s page budget; on failure the symptom is "silence for 30s then timeout." With heartbeats, both OTel and humans see "still alive at 22s, 24s, 26s..." and the abrupt silence tells you where it died. v0.26's `add_sink` makes this nearly free; it's the right time to add the pattern. Confirmed by a2kit dev as the streaming-visibility answer.

**Alternative considered:** Wait until production signal demands it. Rejected — we have the signal demand (30s budget burns are real), and the cost is ~30 LOC tier-internal, no orchestrator change.

### D4b. fit-md deleted entirely; trafilatura native pruning replaces it  ✅ SHIPPED

**Outcome:** Validation gate ran every existing fit-md fixture against `trafilatura.extract(html, url=url, output_format="markdown", include_comments=False, include_tables=False)`. **0 of 4 fixtures regressed by >20%.** `src/a2web/extract/pruning_filter.py` and `tests/test_pruning_filter.py` deleted. `_phase_fit` removed from orchestrator. `FetchResponse.fit_md` preserved as a backward-compat field but now equal to `content_md`.

**Decision:** Delete `src/a2web/extract/pruning_filter.py` and the `fit-md` capability. Replace its role with trafilatura's native `prune_xpath` + `include_comments=False` + `include_tables=False` options at the `bare_extraction(...)` call site. The orchestrator's "Phase 4.5 — fit_md" disappears entirely.

**Rationale:** Research finding — trafilatura's extraction pipeline already performs DOM-based boilerplate stripping (headers, footers, ads, blogrolls, recurring elements) before emitting markdown, producing output documented as ~67% smaller than raw HTML. Our `fit-md` runs a second-pass density filter on already-cleaned text; the marginal value is small. The `fit-md` algorithm was originally crawl4ai's `PruningContentFilter` reimplemented in-tree; the original lives in crawl4ai which we explicitly rejected for dep weight.

**Validation gate:** Before deletion, run all v0.1.0 fit-md fixtures through plain trafilatura with the new options. If >5% of fixtures regress on token count by >20%, demote to "partial-drop": keep a thin ~30 LOC post-filter rather than the full ~130 LOC algorithm. If validation passes, full delete.

**Consequence:** `FetchResponse.fit_md` field remains for backward compatibility but becomes equal to `content_md` (no separate pruning pass). After one minor version we can drop the field.

### D5. hishel adoption gated by a spike PR  ❌ DEFERRED (spike fired)

**Outcome:** Spike performed against hishel v1.2 surface. Two findings:
1. v1.2's primary API is `AsyncCacheProxy(request_sender=..., storage=..., policy=...)` — the cache **owns the HTTP transport**, not the other way around. Our cache sits **outside** the tier loop as a thin before/after wrapper; tiers own the HTTP calls. Adopting hishel would require restructuring every tier to delegate raw HTTP to `proxy.handle_request(...)` — that's a re-architecture, not a shim.
2. The v1.2 `CachePolicy` class only exposes `use_body_key`; the sans-I/O state machine the research described isn't exposed at a level we could plug into our orchestrator.

Per the spike's go/no-go contract, hishel adoption is deferred to v0.3 or later. Custom `sqlite_cache.py` (150 LOC, clean, tested, matches our orchestrator's cache-as-wrapper model) stays. See `BACKLOG.md` for the v0.3 re-evaluation note.

**Decision:** Phase B starts with a hishel-only spike PR (just the curl_cffi response shim, no broader migration). If shim ≤ 80 LOC and tests pass on a smoke fixture, proceed with full adoption. If not, defer hishel to v0.2 and ship only NDJSON + trafilatura + purgatory in Phase B.

**Rationale:** Hishel is the highest-value OSS adoption (RFC 9111 correctness, ~100 LOC out) but also the highest-risk (curl_cffi's response shape differs from httpcore's; the sans-I/O Controller needs an httpcore-compatible interface). Better to verify the seam first than discover halfway through Phase B that the shim is unworkable and have to unwind.

**Alternative considered:** Go in confident, fix the shim as needed. Rejected — the risk asymmetry favors a spike: cheap to confirm, expensive to recover if wrong.

**Consequence:** Phase B is two PRs in practice: B-spike (hishel shim, ~80 LOC, decides go/no-go) and B-main (rest of OSS arc).

### D5b. aiometer adopted for hedged archive requests  ❌ DEFERRED

**Decision:** Replace the hand-rolled hedged-request anyio task group in `tiers/archive.py` (~30 LOC racing Wayback against archive.ph) with `aiometer.run_any([wayback_fn, archiveph_fn])`.

**Rationale:** Research finding — `aiometer.run_any` is precisely the "race concurrent coroutines, return first result, cancel losers" primitive we hand-rolled. The library is anyio-4 native, MIT-licensed, actively maintained, and gives us `max_per_second` rate limiting for free if we ever need it (archive endpoints have soft rate limits we currently ignore).

**Alternative considered:** Keep the 30 LOC hand-rolled. Rejected — replacing well-defined async primitives with library calls is exactly the kind of move "we don't need to maintain this" justifies, even at 30 LOC. Libraries get bug-fixed; our 30 LOC won't.

**Consequence:** `aiometer` becomes a new top-level dep (small, pure-Python, no transitive concerns). `tiers/archive.py` loses ~30 LOC. Future rate-limit needs (paid-tier handlers) inherit the primitive.

**Outcome (post-spike, reversed):** `aiometer.run_any` is **"first result wins"** — first finisher returns its value, losers are cancelled. We need **"first SUCCESS wins"** — if Wayback returns None (no snapshot), we want archive.ph to keep going. Same word "race," different contract. Hand-rolled 30 LOC of anyio task group + capacity-1 stream stays. See `retrospective.md` for the broader pattern (this was 1 of 4 reversed library swaps in Phase B).

### D6. `tier_extras: dict[str, Any]` → typed fields on `TierResult`

**Decision:** Replace the dict bag with explicit fields: `pre_rendered: Rendered | None`, `from_archive: bool`, `snapshot_age_days: int | None`, `from_browser: bool`, `js_executed: bool`, `browser_wall_ms: int | None`, `browser_bytes: int | None`, `operator_hint: OperatorHint | None`, `no_match: bool`, `skipped: bool`, `handler_name: str | None`, `conditional_hit: bool`. Group archive-only and browser-only fields into sub-dataclasses if the field count grows past ~12.

**Rationale:** Eight different string-key reads in `fetcher.py` against `tier_extras` is a contract leak. Typed fields give the compiler something to check; refactors don't silently break consumers.

**Alternative considered:** Keep dict, add `TypedDict`. Rejected — TypedDict is structural, doesn't fail at construction time if a tier produces the wrong shape; we want nominal types.

**Consequence:** Every tier returns a typed `TierResult`. Site handlers populate `pre_rendered=Rendered(...)`; archive tier sets `from_archive=True, snapshot_age_days=...`; browser tier sets `from_browser=True, js_executed=True, browser_wall_ms=...`. Orchestrator reads typed fields.

### D7. Single `_dispatch_archive(...)` helper replaces two near-duplicate blocks

**Decision:** Lift the after-tier and after-gate archive-dispatch blocks (lines 276–315 and 502–558 in current `fetcher.py`) into one async helper:

```
async def _dispatch_archive(
    url: str,
    *,
    state: AppState,
    ctx: a2kit.ToolContext,
    start_perf: float,
    diagnostics: list[Diagnostic],
    re_gate: bool,
) -> ArchiveOutcome:
    ...
```

The two call sites differ only in source URL and whether to re-gate; both feed back into orchestrator state via the returned `ArchiveOutcome` dataclass.

**Rationale:** ~100 LOC of copy-paste is harder to evolve than one helper. The two paths share the same archive dispatch + verdict-replacement logic; they should share code.

**Consequence:** Orchestrator drops ~80 LOC; the helper adds ~50 LOC; net ~-30 LOC and a single point of change for archive dispatch.

### D8. Named phase functions replace decimal phase comments

**Decision:** Replace `# Phase 4.2`, `# Phase 4.25`, etc. with named functions:

```
_phase_cache_check
_phase_tier_loop
_phase_extract
_phase_gate
_phase_escalate_browser
_phase_escalate_archive
_phase_fit
_phase_cache_write
```

Each phase function takes the orchestrator's mutable `FetchContext` dataclass and updates it. The top-level `_run_pipeline` becomes a sequence of phase calls with early-exit on cache hit.

**Rationale:** Decimal phase numbers are decay markers — escalation logic got bolted into a numbered list that wasn't designed to grow. Named functions let you grep for "what does the escalate-browser phase do?" without scanning a 600-line function. Each phase becomes independently testable.

**Alternative considered:** Just rename phase comments to be non-decimal. Rejected — the underlying problem is the monolithic function, not the comment numbering.

**Consequence:** `fetcher.py` reorganizes from "one 600-line function with comments" to "a top-level `_run_pipeline` of ~80 lines + 8 phase functions of 30–60 lines each." Same total LOC, much better navigation.

### D9. `tier_used: str` identity resolved by one function

**Decision:** Single `_resolve_tier_used(tier, tier_result, escalation_path) -> str` function decides what string lands in `FetchResponse.tier`. Rule:
- Site handler match → `tier_result.handler_name` (e.g., `"reddit"`, `"hn"`)
- Otherwise → tier's registry key (`"raw"`, `"jina"`, `"archive"`, `"browser"`)
- Archive/browser escalation overrides → corresponding literal

The string is built once at the end of the pipeline; nowhere else writes to `FetchResponse.tier`.

**Rationale:** Currently four code paths produce the value; the contract is whatever the last writer set. Public field, fuzzy semantics.

### D10. Workspace package boundary: no reverse imports

**Decision:** Three packages — `packages/proxy-pool/`, `packages/browser-pool/`, `packages/block-detector/` — each defines its own types (no `from a2web.models import Verdict`). a2web's `src/a2web/proxy/__init__.py`, `src/a2web/browser/__init__.py`, and `src/a2web/gate/__init__.py` become thin adapter modules that import the package and translate to `a2web` types.

**Why block-detector earns its own package:** Pure function (regex on HTML/markdown → typed verdict + tier hint), no deps, 95 LOC of carefully tuned detection rules for Cloudflare/Anubis/Turnstile/Akamai BMP/paywall. Research confirmed: nothing in the OSS ecosystem returns "this is which anti-bot system" as a typed verdict — every existing library is a *bypass* tool, not a *detector*. The detection rules are the asset; reusable across any web-fetching tool.

**Why fit-md is NOT packaged:** Deleted entirely per D4b. Trafilatura's native pruning replaces it.

**Why hedged-request is NOT packaged:** Replaced by `aiometer.run_any` per D5b. Library exists; we adopt it.

**Why cache-shim is NOT packaged:** Too tightly coupled to curl_cffi + hishel. Only useful to someone who made the same two choices. Stays inline in `src/a2web/cache/`.

**Why ndjson-log is NOT packaged:** Post-Phase-B it's ~20 LOC of stdlib glue (`RotatingFileHandler` + gzip rotator). Not enough to package.

**Why event-bus is NOT packaged:** Replaced by a2kit's ldd subscription chain per D3. No code left to package.

**Rationale:** Real package boundary is enforced at the import graph. If packages can import from a2web, the boundary is decorative. Each package is genuinely portable — could be lifted to PyPI if any of them prove useful elsewhere.

**Alternative considered:** Allow packages to import a2web's leaf types (e.g., `Verdict`) for convenience. Rejected — that's the dependency we'd regret. Type duplication is a small cost; coupling is a much bigger one.

**Consequence:** Each package has ~3–5 enum/dataclass definitions duplicated from a2web. Adapter layer in a2web translates. Hard boundary enforceable by `make lint` (custom check or use ruff's `flake8-tidy-imports`-style banlist).

### D11. `connection=None` stays as-is

**Decision:** No change. a2web doesn't use the connections package, so the kwarg never appears in our code paths post-migration (tests using `a2kit.testing.client(app)` don't need it).

**Rationale:** Item 6 from round 1 was ergonomic, not blocking. With `testing.client` in place, the only place we typed `connection=None` was test_app_state.py contortions — and those get deleted.

### D12. Fluent vs imperative composition style: imperative in `server.py`

**Decision:** Adopt imperative composition for `server.py`:

```python
app = a2kit.App("a2web", health_tool=True).add_router(WebRouter())
app.singleton(AppState, factory=build_state)

@app.on_startup
async def _open(state: AppState) -> None: ...

@app.on_shutdown
async def _close(state: AppState) -> None: ...

@app.health_check
async def _sqlite(state: AppState) -> a2kit.HealthResult: ...

app.ldd.add_sink(otel_sink)
```

**Rationale:** v0.26 ships imperative APIs alongside fluent and the README now leads with imperative. Imperative scales to our composition (singleton + 2 lifecycle hooks + health check + ldd sink) without becoming an unreadable chain. Conditional registration (if we ever need it) drops into normal Python.

## Risks / Trade-offs

**R1. hishel + curl_cffi shim complexity.** Hishel's sans-I/O Controller expects an httpcore-compatible request/response shape; curl_cffi has its own. The shim might exceed our 80-LOC budget or hit edge cases (chunked transfer, HTTP/2 frame handling) we don't yet know about. **Mitigation:** D5 — spike PR first, decide go/no-go before broader Phase B work. **Fallback:** ship Phase B without hishel, defer cache replacement to v0.2; ~100 LOC of cache code stays.

**R2. Cache file-format break.** Hishel's SQLite schema differs from ours. Users post-upgrade get a fresh cache. **Mitigation:** Acceptable — cache is non-authoritative, repopulates on use. Document in CHANGELOG.

**R3. Test rewiring scope.** ~10 integration tests move from direct `fetcher.fetch` calls to `client.invoke`. Each may surface a bug in the adapter layer that was previously untested. **Mitigation:** Migrate tests one at a time in Phase A, fix surfaced bugs before proceeding. Surfaced bugs are a feature, not a regression — that's why we're moving the tests.

**R4. TierHeartbeat event volume.** A 30s browser fetch at 2s heartbeats = 15 events. Multiplied by hot-path traffic, this could be a wire-noise problem. **Mitigation:** Heartbeats only emit while a tier is mid-flight; phase boundaries already emit `TierEnded`. Total event count stays bounded per fetch (≤ ~30 events). Kill-switch via `app.set_ldd(events=False)` if it becomes a problem.

**R5. Workspace packaging boilerplate.** Each package gets its own `pyproject.toml`, `tests/`, optional `README.md`. Real cost ~1 day to set up the two packages + CI rewiring. **Mitigation:** Phase D last, after the rest has settled. Worth the upfront cost for the hard import boundary; if it turns out to be over-engineered for 2 packages, can collapse back to subpackages later (rare path).

**R6. a2kit v0.27 breaking changes.** Round 4 (deprecation of old `add_cli` auto-install) lands in v0.27. We're migrating to v0.26 now, which still supports the old form. If we land Phase A on v0.26 and a2kit ships v0.27 before we're done, we may need a v0.26 → v0.27 mini-migration. **Mitigation:** Use the new `app.add_router(connections(...))` form from the start (even though we don't have connections, we follow the pattern); ride v0.26 for the rest of the work. Treat v0.27 upgrade as a separate, small change.

**R7. Phase scope creep.** Each phase has a clean scope on paper, but "while I'm in there" temptation is real (e.g., "Phase C is touching `fetcher.py`, may as well also fix the `narrative` string formatter"). **Mitigation:** Strict scope per PR; new opportunities go to `BACKLOG.md`, not into the current PR. Reviewer explicitly enforces this.

**R8. Multi-PR coordination cost.** Four sequential PRs means main branch carries partial state for the duration. CI must stay green on every PR; rollback paths must be clear. **Mitigation:** Each phase is independently revertable. Phase A doesn't depend on B/C/D semantically — if hishel falls through, A still ships value. Tag releases between phases (`v0.1.1` after A, `v0.2.0-rc.1` after B given the cache break, etc.).
