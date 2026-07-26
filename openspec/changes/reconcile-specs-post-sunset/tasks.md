# Tasks

Spec-only reconciliation. The witness for every rewritten requirement is the
existing passing suite / live server, NOT the spec text. Cite the current source
module in each requirement body.

## 1. Anchor: app-composition (the worst offender, 20 hits)
- [x] 1.1 Copy the archived sunset delta's `## ADDED Requirements`
      (`archive/2026-07-26-sunset-a2kit-dependency/specs/app-composition/spec.md`)
      as the new baseline; move the mislabelled "Typed events…" from `MODIFIED` to
      `ADDED`. — done: `specs/app-composition/spec.md` seeded; verified the base
      spec has no "Typed events" requirement, so `ADDED` is correct.
- [x] 1.2 Author `## REMOVED Requirements` for the a2kit-era ones the new set
      replaces: "Public fetch tool envelope" (`fit_md`/`tokens`/`EventBus`),
      "Server composition entrypoint" (`a2kit.App`/`a2kit.run`), "CookieJarResource
      is registered via app.provide", "Canonical MCP tool names pinned under flat
      naming", "MCP wire contract survives a2kit substrate upgrades". — done: all
      five verified present in the base `app-composition` spec before removal.
- [x] 1.3 Reconcile framework-neutral survivors so bodies stop naming a2kit. —
      done: audited every base requirement for residue; the only survivors that
      described retired a2kit machinery were the two router requirements ("Router
      registration under `web`" and "CookiesRouter exposes the refresh tool"),
      both now REMOVED (covered by the ADDED "tools registered directly" + the
      `browser-cookies` spec). "Closed-enum verdicts/status", "Configuration via
      single YAML file plus env", and "OperatorHint docstring" carry no a2kit
      residue — left framework-neutral, untouched.
- [x] 1.4 `openspec validate --change reconcile-specs-post-sunset` on the
      app-composition delta before moving on. — passed ("is valid").

## 2. Sweep the remaining 10 specs
- [x] 2.1 `streaming-progress` — done: `Event types` MODIFIED (payload types
      survive in `events/types.py`, reframed as stdlib-logging payloads); `EventBus`,
      `Orchestrator publishes phase boundaries`, `MCP progress sink`, `Router builds
      the bus` all REMOVED (retired, migration → app-composition synchronous typed
      events + app-logging).
- [x] 2.2 `app-logging` — done: 6 requirements MODIFIED (`a2kit` logger/`LogConfig`
      → single `a2web` logger, `src/a2web/log.py`, `propagate=False` + NullHandler);
      Purpose stub replaced in the base spec (non-requirement prose, edited in place).
- [x] 2.3 `browser-cookies` (3 MODIFIED: app.provide→Lazy in build_components;
      `@a2kit.write`/CookiesRouter→`@mcp.tool` via register_cookies_tools;
      `a2kit.ldd.event`→`a2web.log`), `ask-response` (1 MODIFIED:
      `canonical_name_override`→literal `@mcp.tool(name="query")`), `endpoint-auth`
      (3 MODIFIED: GoogleAuth AuthSpec + `a2kit.run(app)` → serve_http_main() →
      mcp.run(transport="http")), `browser-tier` (1: a2kit.log→a2web.log),
      `tier-pipeline` (2 MODIFIED + 1 REMOVED: the retired `bootstrap_state`/
      `Resources` factory), `extraction` (1: a2kit.log→a2web.log), `output-benchmark`
      (1: "a2kit LDD event bus"→a2web logging path). All headers verified verbatim
      against base so archive applies cleanly.
- [x] 2.4 `openspec validate reconcile-specs-post-sunset` → "is valid" (10 deltas).

## 2b. DISCOVERED remainder (2026-07-27) — a SECOND staleness layer the proposal did not scope
The a2kit-LITERAL thesis (`a2kit`/`app.provide`/`EventBus`/`ToolContext`) is now
clean across the 10 in-scope specs. The full audit found more, NOT in the original
11-spec framing — decide whether to widen this change or file a follow-up:
- [x] 2b.1 `app-state` — done (owner: "widen to the clear lies", 2026-07-27):
      MODIFIED "AppState is a dataclass holding shared resources" to the current
      always-on shape (`settings`/`breakers`/`proxy_pool`/`sqlite`; heavy resources
      are `Lazy[T]` on `Components`); REMOVED the three PR-stub/a2kit-concept
      requirements ("Per-App singleton registration", "fetch tool resolves AppState
      via DI", "Server composition registers AppState") — covered by
      `app-composition`. Purpose stub replaced in the base spec.
- [x] 2b.2 `container-image` — done: dropped `A2KIT_*` from the env list, kept
      `A2WEB_*` + provider/secret env.
- [x] 2b.3 `request-log` — done: "route a WARNING through `structlog`" → "emit a
      WARNING via `a2web.log`" (ban on `structlog` elsewhere left intact).
- [ ] 2b.4 DEFERRED (cosmetic, owner-marked optional): "LDD"-branding references
      (a2web's own retired term, not a2kit) in `browser-cookies`/`browser-tier`/
      `extraction`/`output-benchmark` bodies + scenario titles + the
      `output-benchmark` requirement NAME ("…on the LDD bus"). Not a mechanism lie;
      renaming a requirement needs REMOVE+ADD, so batch it if/when touched.
- [ ] 2b.5 DEFERRED (deeper than this change): domain-rename drift the a2kit sweep
      did not chase — `BrowserPool` → `browser_backend`/`any_browser`, the gone
      `Resources` bundle, residual `ask`→`query`. A characterization pass, not a
      grep; file as a follow-up if a clean-baseline audit wants it.

## 3. Residue guard (non-vacuous)
- [ ] 3.1 Add `tests/architecture/test_no_a2kit_in_specs.py` (CODE — needs exit from
      explore). **Denylist decision, informed by 2b.1:** a2kit-literal alone
      (`a2kit`/`app.provide`/`EventBus`/`ToolContext`) is INSUFFICIENT — it passes
      `app-state`, a pure-a2kit spec. Widen to the concept terms that actually mark
      the dead framework: `WebRouter`/`register_state`/`bootstrap_state`/`add_router`/
      `has_provider`/`ToolContext`/`canonical_name_override`, with an explicit
      historical-note allowlist (the `app-logging` factual `a2kit.ldd` migration
      reference is the known exemption). Do NOT denylist `structlog` (a live ban
      term) — this is the "golden proves change, not correctness" hazard applied to
      the guard's own denylist.
- [ ] 3.2 Assert the walk is non-vacuous (`minimum=` file floor, per
      `_walk.walked_files`) — a guard over zero files reads as coverage.

## 4. Close
- [ ] 4.1 `make check` green (the guard is the only new test; specs don't run).
      (CODE/gate — needs exit from explore.)
- [ ] 4.2 `openspec archive reconcile-specs-post-sunset` — applies the 10 deltas
      to `openspec/specs/`. NOTE: resolve §2b first (or explicitly defer it) so the
      archived baseline isn't left half-reconciled.
