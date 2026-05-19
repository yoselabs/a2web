# Design — a2kit v0.32 → v0.38 migration

Five decisions need explicit framing. Everything else is grep-and-replace driven by `tasks.md`.

---

## Decision 1 — Each resource is its own provider; AppState slims

a2kit v0.36+ replaced eager-entry-on-`async with app` with lazy-first-use-on-resolution. This redrew the boundary between "what belongs in AppState" and "what's a discrete DI singleton". The answer for a2web:

```
APPSTATE (kept — always-on resources)        DISCRETE PROVIDERS (slim AppState)
  settings: AppSettings                        BrowserPool       ← Lazy[T] at tool
  breakers: AsyncCircuitBreakerFactory         LlmExtractorResource ← Lazy[T] at tool
  proxy_pool: ProxyPool
  sqlite: SqliteResource
```

Why this split:
- Every fetch needs settings + breakers + proxy_pool + sqlite. They enter together via AppState's factory anyway — no benefit to surfacing them as Lazy on the tool signature.
- BrowserPool only enters when the orchestrator escalates to the browser tier (rare path — handler hits + raw curl_cffi cover the vast majority of URLs).
- LlmExtractorResource only enters when `ask=...` is passed. The default `fetch` call doesn't touch it. Today every fetch eagerly constructs the Extractor (provider lookup, API key check, claude-agent-sdk import); migrating to `Lazy[LlmExtractorResource]` removes this from the hot path.

Tool signature shape:
```python
async def fetch(
    self, *,
    url: str,
    ...,
    state: AppState,
    browser_pool: Lazy[BrowserPool],
    llm_extractor: Lazy[LlmExtractorResource],
    ctx: a2kit.ToolContext,
) -> FetchResponse: ...
```

Phase signatures inside `fetcher.py` stay as today — they receive `FetchContext` from the orchestrator, which holds the resolved (non-Lazy) `BrowserPool` / `LlmExtractorResource` instances when the orchestrator needs them. Lazy unwrap happens **once** at the orchestrator seam; downstream code is Lazy-unaware.

### Why not put Lazy[T] inside AppState?

Considered shape: AppState carries `browser_pool: Lazy[BrowserPool]` and `llm_extractor: Lazy[LlmExtractorResource]` fields. Tools see only `state: AppState` and call `await state.llm_extractor()` when needed.

Rejected because:
- Lazy resolution happens against the **call scope's container**, not against a frozen-at-build-time closure. Stashing Lazy callables in a dataclass field built at `AppState`-resolution time may bind to the wrong scope when the dataclass is reused across calls (AppState is a singleton; calls are scoped). v0.36 explicitly designed `Lazy[T]` as a tool-parameter mechanism for this reason.
- Tool signatures are the explicit contract for "what this tool can resolve". Hiding Lazy resources inside AppState makes that contract opaque.
- The framework's `wire_input_params` already filters `Lazy[T]` annotations out of the wire surface — it's the supported declaration site.

### Why not eliminate AppState entirely?

Considered shape: every tool / phase / tier / handler declares the specific resources it needs as DI params. AppState as a concept goes away.

Rejected because:
- Every phase function in `fetcher.py`, every tier in `tiers/`, every handler in `handlers/` would gain 4 kwargs (`settings`, `breakers`, `proxy_pool`, `sqlite`). That's 30+ signatures touched.
- Phases aren't DI-managed — they're called manually by the orchestrator. DI ends at the tool boundary. So replacing AppState with per-resource injection ONLY at the tool level wouldn't propagate; phases would still need a bundle to receive. Re-creating "AppState by another name" is unproductive churn.
- AppState's value as a domain bundle (always-on resources for the fetch pipeline) is independent of how DI used to work. v0.38 doesn't make the bundle wrong; it makes specific resources Lazy-able.

If we want to revisit AppState elimination later as a follow-up "v0.38-fully-native" change, that's clean — but bundling it with the v0.32→v0.38 migration is wrong scope.

---

## Decision 2 — Resources expose `__aenter__`/`__aexit__` as thin wrappers; keep `_ensure()`/`close()` internal

v0.36 removed `aclose`/`close` auto-detection. Resources must expose `__aenter__`/`__aexit__` for the framework to lifecycle them.

Cleanest shape — keep both surfaces:

```python
class SqliteResource:
    # ─── existing internal surface (unchanged) ───
    async def _ensure(self) -> aiosqlite.Connection: ...
    async def close(self) -> None: ...

    # ─── new framework-facing CM protocol ───
    async def __aenter__(self) -> "SqliteResource":
        await self._ensure()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
```

Why both surfaces:
- Lazy callers inside the resource (e.g. internal methods that defensively call `self._ensure()` before using the connection) keep working unchanged. `_ensure()` is documented in `state.py` as the canonical pattern; we don't invalidate that doc.
- Tests that construct a resource directly and exercise `_ensure()` / `close()` keep working.
- Two callers (framework via CM protocol, internal via named method) read clean — each has a named-for-purpose entry point.
- Framework calls `__aenter__` **exactly once** per resolution (singleton-cached after first call). Internal callers can call `_ensure()` defensively N times; it's idempotent. No conflict.

Apply identically to `BrowserPool` and `LlmExtractorResource`. `ProxyPool` and `AsyncCircuitBreakerFactory` have no lifecycle — no `__aenter__`/`__aexit__` required, framework gracefully skips them.

---

## Decision 3 — Accept lazy first-use; no manual startup warm

v0.36 removed eager singleton entry. The framework's behavior:

```
async with app:           ─── enters NOTHING
   tool call arrives      ─── triggers AppState resolution
                              → cascades through factory deps
                              → enters every resource AppState declares
                                (settings, breakers, proxy, sqlite)
                              → resolves Lazy[BrowserPool] / Lazy[LlmExtractor]
                                only when await heavy() is called
```

Today's startup behavior — `await state.sqlite._ensure()` pre-yield in the explicit lifespan — fail-fast on sqlite misconfiguration at boot. v0.38 makes this lazy: sqlite errors surface on first fetch instead of startup.

Accept this. Rationale:
- The MCP error envelope is now structured (round-8 fix). A sqlite-on-first-fetch failure produces `ToolError({"class": "...", "message": "..."})` over the wire — observably the same as a startup failure for the agent calling us.
- `@app.health_check` is preserved and probes sqlite explicitly when called. Operators wanting an eager check have it via `a2web health`.
- Cold start is faster by ~50-200ms (sqlite open isn't on the boot path).
- Manual warm via `await app.container().get(SqliteResource)` before `a2kit.run(app)` would require `async def main()` and entering the app twice (once for warm, once for run). Awkward and not idiomatic.

This is a behavior change worth flagging in CHANGELOG.md and CLAUDE.md.

---

## Decision 4 — `AppSettings` registered explicitly despite "auto-resolve" changelog claim

v0.36 changelog: *"a tool parameter typed as a `BaseSettings` subclass auto-resolves without explicit `provide()` registration"*.

POC-verified that this is **partial**:
- Inside a factory body — `def build_proxy_pool(settings: AppSettings) -> ProxyPool: ...` — the container auto-resolves `settings` via `_looks_like_basesettings` in `_construct`. Works.
- As a direct tool parameter — `async def fetch(*, settings: AppSettings, ...)` — `wire_input_params` checks `container.has_provider(ann)` only, NOT `_looks_like_basesettings`. So `settings` is treated as a wire kwarg, and FastMCP rejects the call: `"Missing required keyword only argument: settings"`.

Workaround: `app.provide(get_settings)`. Single line. Same registration we'd write anyway.

This is an a2kit bug worth filing as round-10 feedback (see `docs/history/A2KIT_FEEDBACK.md` after this migration archives) — `wire_input_params` should `or _looks_like_basesettings(ann)` alongside the `has_provider` check. But it's not blocking; the workaround is one line and the explicit registration is more discoverable anyway.

---

## Decision 5 — Tests need no changes from the migration

POC-verified by grepping the test suite:

| Concern | Reality |
|---|---|
| `client.call → client.invoke` rename | Zero `.call(` occurrences in `tests/`. Current tests call `orchestrate()` directly, bypassing TestClient. |
| TestClient returns dicts instead of pydantic models | Same — only matters if tests go through TestClient. They don't. `result.field` access in `tests/test_fetcher.py` works against real `FetchResponse` instances returned from `orchestrate()`. |
| Tool exceptions wrap as `fastmcp.exceptions.ToolError` | No current `pytest.raises` test asserts cross-tool-boundary exception classes. Subcomponent tests of `JudgeParseError`, `ExtractionCorpusError`, etc. still pass through unchanged. |
| AppState construction shape change | `tests/test_app_state.py` constructs `AppState(...)` directly — would break if we change field count. Update test to match new field set. |

So the test sweep is ONE file: `tests/test_app_state.py`. Add the migration's own integration test (or defer to the sibling feature-wave change) as a separate decision.

---

## Migration order recap

1. **Step 0** — verification spike against v0.38 + pin bump (red baseline)
2. **Step 1** — drop forced-error sites: `@a2kit.read(idempotent=True)`, `App(lifespan=...)`, `App(health_tool=True)`, `asynccontextmanager` lifespan body
3. **Step 2** — resource `__aenter__`/`__aexit__` wrappers (purely additive on each resource class)
4. **Step 3** — AppState slim (drop browser_pool, llm_extractor fields; rebuild build_state factory)
5. **Step 4** — server.py provider registration (named factories, deps-first order)
6. **Step 5** — routers.py / fetcher.py Lazy resource adoption (signatures gain `Lazy[T]`; orchestrator threads resolved values)
7. **Step 6** — `tests/test_app_state.py` field-set update
8. **Step 7** — docs: CLAUDE.md + BACKLOG.md + CHANGELOG.md
9. **Step 8** — full verification: `make check` green; MCP stdio repro returns structured result; LDD events visible on wire

Order is load-bearing only at steps 3-5: AppState must be slimmed before server.py registers it (build_state factory signature change), and server.py providers must be in place before routers.py declares `Lazy[T]` (otherwise the container can't resolve them).
