# a2kit v0.38 → v0.39 migration

## Why

a2kit v0.39 shipped on 2026-05-16 and addresses four of the six frictions we filed in round 10 (`docs/history/A2KIT_FEEDBACK_v0.38.md`). This change adopts the **mechanical surface fixes only** — pin bump + the ceremony + boilerplate removals that v0.39 directly enables. No architectural restructuring.

Specifically: **we are NOT folding `Lazy[BrowserPool]` + `Lazy[LlmExtractorResource]` into `AppState`**, even though v0.39's `Lazy[T]`-in-factory-params shipping makes it possible. The current split — `AppState` for always-on data, separate Lazy DI kwargs for orthogonal services — is the *correct* idiomatic shape:

- `AppState` is a **data bundle**, not a service locator. Lifecycles, lazy resolution, and conditional resolution are service concerns; they don't belong on a `@dataclass(slots=True)`.
- **Tools declare exactly the services they use**. The tool signature *is* the contract. Funneling everything through AppState hides which tool needs the browser vs the LLM.
- Every test that constructs `AppState` would otherwise have to fake all six fields (including ones it doesn't exercise). Keeping AppState narrow keeps the test seam narrow.

Round 10 Friction E was a mis-diagnosis — the architectural split it called out is correct design, not friction. We retract it. v0.39's `Lazy[T]`-in-factory-params is still a real fix (closes a spec drift); it just doesn't change a2web.

| Friction | Action |
|---|---|
| **B — `ctx` ceremony** | Drop `ctx: a2kit.ToolContext` + `del ctx` from `WebRouter.fetch` (v0.39: ambient ctx is non-None inside any framework dispatch) |
| **A1 — `lazy_of` helper** | Swap callsites to `a2kit.testing.lazy`; delete `conftest.py:lazy_of` |
| **A2 — autouse LDD fixture** | Replace local `_ambient_ldd` with `a2kit.testing.ambient_for_tests` (preserve autouse semantics in our own conftest) |
| **A3 — `make_default_state`** | **Keep as-is** — deliberate "AppState without an app" test seam (see design D4) |
| **~~E — AppState fold~~** | **Retracted** — split is correct design |
| **F — health probe `_ensure()`** | Drop `await sqlite._ensure()` from `_check_sqlite` |
| (new) **ToolContext is a Protocol** | No code change; verification only (no `is fastmcp.Context` identity checks in a2web) |
| C — canonical `a2kit.Lazy` | NOT shipped in v0.39; stays deferred |
| D — `pydantic.Field` description sugar | NOT shipped in v0.39; stays deferred |

## What changes

### Tool seam — `routers.py`

```diff
 @a2kit.read(open_world=True, title="Fetch Web Page")
 async def fetch(
     self,
     *,
     url: ...,
     state: AppState,
     browser_pool: Lazy[BrowserPool],
     llm_extractor: Lazy[LlmExtractorResource],
-    ctx: a2kit.ToolContext,
 ) -> FetchResponse:
-    del ctx
     ...
```

`browser_pool` + `llm_extractor` stay as Lazy DI kwargs. Architectural split preserved.

### `server.py` — drop `_ensure()` call

```diff
 @app.health_check
 async def _check_sqlite(sqlite: SqliteResource) -> a2kit.HealthResult:
-    try:
-        await sqlite._ensure()
-    except Exception as exc:
-        return a2kit.HealthResult.fail(f"sqlite open failed: {exc}")
+    """Framework enters `sqlite` via __aenter__ on kwarg resolution
+    (OPERATIONAL_CONTRACTS Q-HealthChecks). DI-time failures surface
+    via the health framework's own wrapping.
+    """
+    _ = sqlite
     return a2kit.HealthResult.ok()
```

### `tests/conftest.py` — delete two helpers, keep `make_default_state`

- `lazy_of(value)` → `a2kit.testing.lazy(value)` at every callsite; delete the local helper.
- `_ambient_ldd` autouse fixture → use `a2kit.testing.ambient_for_tests` (exact shape — fixture vs context manager — confirmed in Step 0).
- `make_default_state(...)` unchanged.

### `events/__init__.py` — stale docstring fix

```diff
-Emissions go through a2kit.ldd (`await a2kit.ldd.event(ctx, name, **payload)`)
+Emissions go through a2kit.ldd (`await a2kit.ldd.event(EventInstance(...))`)
```

### CLAUDE.md — minor tweaks

- Strengthen the ctx rule: "Don't declare `ctx: a2kit.ToolContext` on a tool that doesn't read ctx in its body" (v0.39 ambient ctx works without it).
- The "Lazy[T] at the tool seam" guidance stays — that's the idiom, unchanged.

### `docs/history/` — friction history

- Append "shipped in v0.39 — Friction E retracted by a2web" footer to `A2KIT_FEEDBACK_v0.38.md`.
- Refresh `A2KIT_WISHES_DEFERRED.md` with Friction C + D as parked entries.

## Non-goals

- Folding lazy resources into `AppState` (architectural drift; explicitly retracted from round 10).
- Promoting `a2kit.Lazy` / `a2kit.LddEmission` to top-level (not in v0.39).
- Description-sugar wrapper for `pydantic.Field` (not in v0.39).
- Touching `fetcher.py` phase decomposition, tier registry, handlers, events, sinks.
- Changing the wire surface (tool name, response envelope, event payloads — all unchanged).

## Risks

- **Test ambient fixture shape** — `a2kit.testing.ambient_for_tests` may be a fixture-factory, a pytest plugin, or a context manager. Confirm in Step 0 and adapt the conftest re-export.
- **Health check body without try/except** — if `a2kit.packages.health` doesn't wrap DI-construction failures, the loud failure path disappears. Mitigation: read v0.39 source; keep try/except as belt-and-suspenders if needed.
- **`lazy_of` callsite count** — likely many tests. Grep + mechanical swap.

## Migration order

1. Pin bump + v0.39 surface verification (Step 0).
2. Drop `ctx` from `WebRouter.fetch` (Step 1).
3. Drop `_ensure()` from health check (Step 2).
4. `conftest.py` helpers swap (Step 3).
5. Stale docstring fix + grep audits (Step 4).
6. Docs + history (Step 5).
7. Final `make check` + smokes (Step 6).
