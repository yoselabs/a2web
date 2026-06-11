# a2kit v0.41 → v0.43 migration

## Why

a2web is pinned to `a2kit==v0.41.1`. a2kit has since shipped v0.42.0, v0.42.1,
and v0.43.0. Two of those releases carry breaking surface changes that a2web
consumes directly:

- **v0.42.0** — the big one. Two ADRs land together:
  - **ADR-0028 (unified surface):** `App` is now authored by **subclassing**,
    not imperative construction. `a2kit.App("name")` + `App.add_router(...)`
    are removed; routers are a `routers = (...)` ClassVar of Router *classes*.
    Router `tools = (...)` ClassVars are removed (verbs auto-collect from
    `@a2kit.read/write/list_` markers). Canonical tool names are now flat
    `{slug}_{leaf}`.
  - **ADR-0027 (LDD refound):** the bespoke `a2kit.ldd` channel is retired and
    re-founded on stdlib `logging`. `a2kit.ldd` / `a2kit.packages.ldd` are gone;
    `await a2kit.log.info(instance)` replaces `await a2kit.ldd.event(instance)`
    (still **async** — it awaits an optional MCP-wire forward after a synchronous
    `_LOGGER.log` to the `"a2kit"` logger); sinks become `logging.Handler`s
    registered via `app.log.add_handler(...)` (≡ `logging.getLogger("a2kit")`).
- **v0.42.1** — removes `expose=` / `visibility=` outright. **a2web uses
  neither** (only `open_world=`/`title=`), so this is a no-op for us.
- **v0.43.0** — purges all backward-compat machinery (tombstones, aliases,
  hints). A removed name now raises the plain language-default error. This only
  bites if we still reference a removed surface after the v0.42 work — so it is
  a no-op *if v0.42 is migrated correctly*. It is the reason we cannot stop at
  v0.42: there is no graceful shim left to lean on.

This change adopts all three pin steps in one pass and migrates the two surfaces
a2web actually consumes (App composition + LDD). No architectural restructuring
beyond what the framework forces.

## What changes

### Front A — App composition (ADR-0028)

`src/a2web/server.py` flips from imperative to subclass:

```diff
-app = a2kit.App("a2web")
-app.provide(get_settings)
-...seven providers...
-app.add_router(WebRouter())
-app.add_router(CookiesRouter())
+class A2Web(a2kit.App):
+    name = "a2web"
+    routers = (WebRouter, CookiesRouter)
+
+def build_app() -> A2Web:
+    app = A2Web()
+    app.provide(get_settings)   # .provide() instance method survives in v0.43
+    ...seven providers...
+    return app
```

`src/a2web/routers.py`: drop both `tools: ClassVar[...]` tuples (verbs
auto-collect). The `slug` attributes stay.

### Front B — LDD → stdlib logging (ADR-0027)

- 28 `await a2kit.ldd.event(X)` sites → `await a2kit.log.info(X)` — **keep the
  `await`**; `info` is async (it awaits the optional MCP-wire forward). Only the
  channel name changes. Across `fetcher.py`, `tiers/browser.py`,
  `llm_eval/runner.py`. (Earlier draft wrongly said "drop await" — corrected
  after reading `a2kit/packages/log/emission.py`.)
- Delete the `app.ldd.events.register(T)` loop in `server.py` — there is no
  pre-registration step; `a2kit.log.info(instance)` accepts any typed instance.
- `app.ldd.add_sink(otel_sink)` → `app.log.add_handler(OtelHandler())`.
- `otel_sink(emission: LddEmission)` → an `OtelHandler(logging.Handler)` whose
  sync `emit(record)` reads `record.getMessage()` (the type name, was
  `emission.name`) and `record.a2kit_fields` (the payload dict, was
  `emission.payload`).
- `LiveSink` (bench) → a `logging.Handler`: sync `emit(record)` reusing the
  handler's built-in `self.lock` (no `asyncio.Lock`); async `__aenter__/__aexit__`
  retained to own the heartbeat task in the bench event loop. Cells run
  single-threaded on one loop, so this is clean — see design.md D-LiveSink.
- `_ldd_ambient(...)` in `runner.py` collapses to `app.log.add_handler(...)`
  for the suite duration. `ldd_state_for_call` / `events_enabled` /
  `reports_enabled` / `sinks=` knobs are gone.
- Replace all `from a2kit.packages.ldd import LddSink` and
  `from a2kit import LddEmission` with `logging.Handler` / `logging.LogRecord`.

### Front C — Tool-name pin (decision: preserve verbatim)

Under v0.42 flat naming, `ask`/`fetch_raw`/`refresh` would become
`web_ask`/`web_fetch_raw`/`cookies_refresh`. a2web is installed globally and
wired into Claude Code's MCP config under the current bare names. We **pin them
verbatim** with `canonical_name_override="ask"` / `"fetch_raw"` / `"refresh"`
on the three router verbs. This preserves both the MCP wire contract and the
nested CLI surface (`a2web web ask`). Rationale and the rejected
"drop-the-router" alternative are in design.md D-Names.

### Front D — Lint codes

Codes renamed `A2K###`→`AK###`/`AKR###`/`RG###`. A repo grep found **no**
`# noqa: A2K*` suppressions, so nothing to migrate. Verify-only.

### Front E — Docs

`CLAUDE.md` architecture prose is stale (describes v0.39 internals:
`a2kit.ldd.event`, `tools: ClassVar`, `app.provide` insertion order,
`app.ldd.add_sink`). Full rewrite to the v0.43 surface as part of this change.

## Non-goals

- No change to fetch/extraction behavior, tier routing, the response envelope,
  or handler logic. This is a framework-surface migration.
- No `expose=`/`visibility=`/`surfaces=` work — a2web never used the old axis;
  default (all-surfaces) is correct.
- No restructuring of the AppState / Lazy[T] split (settled in the v0.39
  migration; still idiomatic).

## Impact

- Affected: `server.py`, `routers.py`, `fetcher.py`, `tiers/browser.py`,
  `events/{sinks,types,__init__}.py`, `_manifests/sinks/__init__.py`,
  `llm_eval/{runner,live_sink}.py`, plus `tests/` (1 app-construction site,
  otel-sink + live-sink unit tests), `pyproject.toml`, `CLAUDE.md`.
- **Breaking for any MCP client that hardcoded a NON-bare name** — none do;
  bare names are preserved via Front C, so the installed binary's contract is
  unchanged. Still requires `make install-global` + session restart to pick up
  the new code.
- One spec delta (`specs/app-composition/`): an ADDED requirement pinning the
  canonical MCP tool names (`ask`/`fetch_raw`/`refresh`) against v0.42 flat
  naming. This captures the contract Front C actively defends — it is the one
  observable thing the migration guarantees, not a behavior change to fetch/
  extraction. Everything else is framework-surface churn with no spec impact.
