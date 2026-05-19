# a2kit v0.28.0 → v0.29.1 migration

## Why

a2kit shipped four releases between 2026-05-12 and 2026-05-13 (v0.28.1, v0.29.0, v0.29.1) that together close **every** open ergonomic gap from a2web feedback rounds 5 and 6 — plus fix the FastMCP 3.x compatibility break that's currently blocking `a2web serve` as a global Claude Code MCP server.

| Round / item | Shipped in | Adapter code a2web deletes |
|---|---|---|
| **Round 6 blocker — FastMCP 3 break** (`tool.disable()` removed) | v0.28.1 | Currently no workaround; unblocks `a2web serve` |
| **Round 5 gap 1** — async resource boilerplate | v0.29.0 `app.singleton(T, async_factory)` | `SqliteResource`, `BrowserPool`, `LlmExtractorResource` classes (~80 LOC of `_ensure()` + Lock + close idempotency) |
| **Round 5 gap 2** — `ctx` threading | v0.29.0 LDD primitives drop `ctx` (ambient via ContextVar) | `ctx` kwarg on 9 phase functions, `null_context()` import + branch in `fetch()` (~30 LOC) |
| **Round 5 gap 3** — test resource override | v0.29.0 `TestClient.override(T, fake)` | 5 `monkeypatch.setattr(state.…)` sites + `type: ignore[assignment]` |
| **Round 5 gap 4** — `Annotated[T, Param(...)]` verbosity | v0.29.0 Google-style docstring `Args:` auto-pull | 6 `Annotated[…, a2kit.Param(...)]` wrappers in `routers.py` (~50 LOC of prose redistributed to docstring) |
| **Round 6 friction 1** — `_meta` namespace undocumented | v0.28.1 `OPERATIONAL_CONTRACTS` Q7 documents the contract | Documentation only |
| **Round 6 friction 2** — MCP wire payload inspection | v0.29.0 `TestClient.call_wire(tool, **kw)` | Enables 5 new wire-format tests we couldn't write before |

Free wins inherited: CLI cold-start -75% (v0.27.1/2, on the same bump). `a2kit.ldd.log/info/warning/error/debug` primitives (v0.28.0) replace the `ctx.info(msg, k=v)` kwargs form that v0.28.0 narrowed off `StderrToolContext` — a2web doesn't currently use the kwargs form, so this is a forward-compat plus.

Two pieces of original round-3 wishlist remain deferred (streaming response, `timeout=` decorator kwarg) — parked in `docs/history/A2KIT_WISHES_DEFERRED.md` for a future round, neither blocks anything.

## What Changes

### `pyproject.toml`

- Bump `a2kit` pin: `tag = "v0.28.0"` → `tag = "v0.29.1"`.
- No other dependency changes; FastMCP version constraint is now a2kit's responsibility.

### `src/a2web/server.py`

- No structural changes. Verify lifecycle hooks (`@app.on_startup`, `@app.on_shutdown`, `@app.health_check`) still receive `state: AppState` as a DI kwarg — no migration expected, contract is unchanged.

### `src/a2web/state.py`

- `AppState` keeps the three resource fields but **the types change** from wrapper classes to the underlying handles:
  - `sqlite: SqliteResource` → `sqlite: aiosqlite.Connection`
  - `browser_pool: BrowserPool` → `browser_pool: BrowserPool` (keep the wrapper — multi-context acquire semantics are domain logic, not DI plumbing)
  - `llm_extractor: LlmExtractorResource` → `llm_extractor: Extractor | None`
- `build_state(settings)` shrinks to constructing the literal struct; async opens move to the factory functions registered with `app.singleton`.
- Per-resource factory functions (e.g. `open_sqlite_with_schema(settings)`) stay where they live today; they become the async factories passed to `app.singleton`.

Design note on the BrowserPool exception is in `design.md`.

### `src/a2web/fetcher.py`

- Drop `ctx` kwarg from 9 phase / helper functions:
  - `_phase_cache_check`, `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate`, `_phase_cache_write`, `_escalate_browser`, `_dispatch_archive`, `_emit_tier_started`, `_emit_tier_ended`
- Drop the `ctx is None: ctx = null_context()` branch in `fetch()` entrypoint.
- All `a2kit.ldd.event(ctx, payload)` call sites → `a2kit.ldd.event(payload)` (16 sites per grep, all `fetcher.py`).
- Remove unused `from a2kit.testing import null_context` import.
- `FetchContext` keeps its fields; `ctx` field (if present) drops.

### `src/a2web/events/`

- `events/sinks.py` — unchanged; the sink consumes `LddEmission`, which is unaffected by the dispatcher-side `ctx` ambient change.
- `events/__init__.py` docstring updated to drop the `(ctx, name, **payload)` shape reference.

### `src/a2web/routers.py`

- Strip `Annotated[T, a2kit.Param(...)]` from all 6 user-facing kw-only params on `WebRouter.fetch`.
- Move per-param descriptions into a Google-style `Args:` section in the docstring. Preserve the existing top-level prose verbatim.
- Drop `ctx: a2kit.ToolContext` kwarg from the tool signature (a2kit dispatcher binds it ambient; the tool body doesn't reference it after fetcher.py migration).

### `tests/`

- Replace 5 `monkeypatch.setattr(state.<resource>, ...)` sites with `async with client.override(<T>, <fake>):` blocks. Drop attendant `type: ignore[assignment]`.
- Any test that uses `ldd_state_for_call(...)` directly: add required `ctx=` keyword.
- Existing `test_fetcher.py::test_no_ctx_no_events` (line 283) — semantics change; without an active dispatch, `a2kit.ldd.event` raises `AmbientContextMissing`. Rewrite to assert the raise, or delete (the assertion no longer maps to a real failure mode).
- **New test: param-description completeness** using `TestClient.call_wire` to introspect the MCP schema and assert every user-facing kw-only param has a description ≥20 chars. Belt-and-braces guard against silent docstring drift.

### `pyproject.toml` (Ruff config)

- Add `[tool.ruff.lint.pydocstyle] convention = "google"`. Locks the docstring style for the auto-pull to function correctly across contributors.

### `CLAUDE.md`

- One-line addition under conventions: `Args:` prose in tool docstrings is **agent-facing tool guidance** — include heuristics (when to pass, when not, payload cost, default rationale), not just type restatement.

### `docs/history/`

- `A2KIT_FEEDBACK.md` (round-6 outgoing) → renamed to `A2KIT_FEEDBACK_v0.28.md` with a one-line "shipped in v0.28.1 + v0.29.0 + v0.29.1" prefix.
- `A2KIT_WISHES_DEFERRED.md` already created — preserves the remaining round-3 wishes.

## Non-goals

- **No new tools.** The MCP surface (`WebRouter.fetch`) is unchanged; tool args, return type, and behavior are identical from a caller's POV.
- **No fetcher logic changes.** Tier order, escalation rules, gate logic, cache semantics — all unchanged.
- **No streaming response work.** Parked as a future a2kit wish.
- **No `timeout=` decorator work.** Parked.
- **No openspec spec-file updates** unless a spec contradicts the new shape. AppState's spec (`specs/app-state/`) may need a one-line touch; if so it's captured in `tasks.md`.

## Acceptance

1. `make check` passes (lint + ty + 374-test suite, ≥85% coverage gate holds).
2. `a2web serve` starts cleanly against `a2kit v0.29.1` (no FastMCP `NotImplementedError`).
3. `a2web serve` registers successfully as a global Claude Code MCP server and `mcp__a2web__fetch` shows up in the agent's tool list — this was the original blocker that triggered the migration.
4. CLI smoke (`a2web web fetch --url=<known-hard-URL>`) returns a populated `FetchResponse` with diagnostics.
5. Param-description completeness test (the new wire-format test) passes — every user-facing param has a substantive description in the MCP schema.

## Risks

- **Ambient `ctx` migration is many-site mechanical.** 16 `a2kit.ldd.event` call sites. Easy to miss one. Mitigation: grep-driven sweep + the now-loud `AmbientContextMissing` exception will surface any missed site at runtime.
- **Docstring pull is silent on missing entries.** Adding a new param to `fetch` without updating `Args:` → empty description in MCP schema, no error. Mitigation: the new `call_wire`-based completeness test fails CI if any param's description is missing or under 20 chars.
- **Test override semantics for `BrowserPool`.** If we keep `BrowserPool` as a wrapper class, the override target type matters — we override `BrowserPool` (the wrapper), not the underlying Camoufox launch. Design covers this.
- **Cosmic-ray-style: docstring style drift.** Contributors writing `:param url: ...` (reST style) silently fail to populate. Mitigation: Ruff's `convention=google` lint rule.

## Out-of-scope items captured elsewhere

See `docs/history/A2KIT_WISHES_DEFERRED.md` for the remaining round-3 wishes (streaming response API, `timeout=` decorator kwarg) and the a2kit-internal openspec follow-ups worth watching (`align-context-method-signatures`, `rebuild-test-client-on-real-context`).
