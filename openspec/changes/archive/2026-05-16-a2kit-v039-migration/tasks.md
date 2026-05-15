# Tasks — a2kit v0.38 → v0.39 migration

Step ordering is load-bearing. See `design.md` "Migration order recap".

---

## Step 0 — Pin bump + v0.39 surface verification

- [x] 0a. **Confirm `a2kit.testing` surface** — read `/tmp/a2kit-v039/src/a2kit/testing.py` (already cloned) and `a2kit/packages/testing/__init__.py`. Note exact shapes:
  - `a2kit.testing.lazy(value)` — signature and return type.
  - `a2kit.testing.ambient_for_tests` — pytest fixture vs context manager vs both? Record in design D5.
  - `a2kit.testing.resolve(app, T)` — confirm async, confirm scope requirement.

- [x] 0b. **Identity-check grep** — `rg "fastmcp\.Context|ToolContext\s*is\s|isinstance\(.*ToolContext" src/ tests/`. Expected: zero hits. (If any, D6 changes.)

- [x] 0c. **Health-framework wrap-check** — `_run_one_check` does NOT wrap DI resolution. v0.39 changelog says drop `_ensure()` (accepts resolver crash as correct behaviour for sqlite-open failure). Drop both `_ensure()` AND try/except. — read `a2kit/packages/health/__init__.py` (or wherever `@app.health_check` is implemented in v0.39). Confirm whether DI-construction failures are caught and surfaced as `fail()` automatically. Record in design D3 decision (keep or drop the try/except in `_check_sqlite`).

- [x] 0d. **Bump pin** — `pyproject.toml`:
  - `[tool.uv.sources] a2kit.tag` from `v0.38.0` to `v0.39.0`
  - Spec line: `a2kit>=0.38,<1` → `a2kit>=0.39,<1`

- [x] 0e. `uv sync --all-extras`. Confirm install clean.

- [x] 0f. **Red baseline** — actually green: 414 passing, 89% coverage. v0.39 is fully back-compat on a2web's surface. — `make check`. Expected: green (v0.39 is back-compat; nothing forces a rename). If red, capture failure surface before proceeding.

---

## Step 1 — Drop `ctx` from `WebRouter.fetch`

- [x] 1a. `src/a2web/routers.py`:
  - Remove `ctx: a2kit.ToolContext` from the `fetch` signature (currently at line ~95).
  - Remove `del ctx` from the body (currently at line ~116).
  - Update the docstring line that references "bound ambient by the dispatcher" if needed (it's now unconditional).

- [x] 1b. Verify imports — `a2kit` import stays (still used for `@a2kit.read`, `a2kit.Router`).

- [x] 1c. `make check` — 414 passing, 89% coverage. v0.39 MCP wrapper synthesizes ctx for the tool transparently.. End-to-end tool dispatch should pass; MCP transport tests should pass (v0.39's MCP wrapper synthesizes `_a2kit_ctx` for tools that don't declare it).

---

## Step 2 — Drop `_ensure()` from `_check_sqlite`

- [x] 2a. `src/a2web/server.py:111-122`:
  - Drop `await sqlite._ensure()` call.
  - Decide on try/except retention based on Step 0c finding:
    - If health framework wraps DI failures → body becomes `_ = sqlite; return a2kit.HealthResult.ok()`.
    - If not → keep try/except, but the catch now wraps the (no-op) probe body — likely defensive against `__aexit__`-time effects.
  - Update docstring to reference `OPERATIONAL_CONTRACTS Q-HealthChecks`.

- [x] 2b. `make check` — 414 passing.. Health-check tests (if any) pass; `uv run a2web health` smoke returns OK.

---

## Step 3 — `conftest.py` migrates to `a2kit.testing.*`

- [x] 3a. **`lazy_of` swap** — replaced in `test_fetcher_ask.py` (4 callsites), deleted from conftest.
  - `rg "lazy_of" tests/` — find every callsite.
  - At each callsite, replace `lazy_of(value)` with `lazy(value)`. Either import `from a2kit.testing import lazy` at each callsite, OR re-export from `conftest.py` for the existing import shape — pick whichever creates the smaller diff.
  - Delete `lazy_of` definition from `tests/conftest.py:34-45`.

- [x] 3b. **Autouse LDD fixture swap** — used the docstring-recommended pattern: `_ambient_ldd = pytest.fixture(autouse=True)(_ambient_inner.__wrapped__)`. Removed `ldd_state_for_call` + `null_context` imports.
  - Per Step 0a finding, adopt the right shape from design D5.
  - Replace the local `_ambient_ldd` autouse fixture body (`tests/conftest.py:71-79`).
  - Remove unused imports: `ldd_state_for_call`, `null_context` (unless still used elsewhere — check).

- [x] 3c. `make check` — 414 passing, lint clean (one I001 auto-fixed).

---

## Step 4 — Stale docstring + grep audits

- [x] 4a. `src/a2web/events/__init__.py:3` — fix stale docstring:
  ```diff
  -Emissions go through a2kit.ldd (`await a2kit.ldd.event(ctx, name, **payload)`)
  +Emissions go through a2kit.ldd (`await a2kit.ldd.event(EventInstance(...))`)
  ```

- [x] 4b. **Grep audits** — all clean (ctx/del ctx/_ensure() calls/lazy_of: zero hits in code; remaining `_ensure()` refs are docstrings).
  - `rg "ctx: a2kit\.ToolContext|ctx: ToolContext" src/` → expected: zero hits in tool bodies (a future tool can re-add).
  - `rg "del ctx" src/` → expected: zero hits.
  - `rg "_ensure\(\)" src/a2web/server.py` → expected: zero hits.
  - `rg "lazy_of" src/ tests/` → expected: zero hits.

- [x] 4c. **Lazy[T] location check** — all hits are tool sigs, factory sigs, docstrings, or imports. No leaks. — `rg "Lazy\[" src/ tests/`. Every hit should be one of: tool signature kwarg, factory signature kwarg, `a2kit.testing.lazy(...)` test callsite, or `from a2kit.packages.di import Lazy` import. Anything else is a smell.

---

## Step 5 — Docs + history

- [x] 5a. `CLAUDE.md`:
  - Find the "Never" rule about `ctx`. Strengthen to: "Don't declare `ctx: a2kit.ToolContext` on a tool that doesn't read ctx in its body (v0.39: ambient ctx is bound unconditionally inside framework dispatch)."
  - Find the "Never" rule about `_ensure()` in health checks — if present, drop. If absent, add a conventions note: "Health-check bodies don't probe internals — kwarg resolution enters the resource (OPERATIONAL_CONTRACTS Q-HealthChecks)."
  - "Heavy/conditional resources surface as `Lazy[T]` at the tool seam" — leave as-is (still the idiom; round-10 Friction E retracted).

- [x] 5b. `docs/history/A2KIT_FEEDBACK_v0.38.md` — appended "Status — shipped in v0.39" footer with per-friction adoption + retract notes. — append the "Status — shipped in v0.39" footer from design D7 verbatim.

- [x] 5c. `docs/history/A2KIT_WISHES_DEFERRED.md` — added entries 7 (Friction C canonical-surface) and 8 (Friction D description sugar). — refresh:
  - Add or update entry for Friction C (canonical-surface promotion: `a2kit.Lazy`, `a2kit.LddEmission` still buried).
  - Add or update entry for Friction D (`pydantic.Field` description sugar).

- [x] 5d. `CHANGELOG.md` — added "Changed (a2kit v0.38 → v0.39 migration, 2026-05-16)" section under Unreleased. (a2web) — add entry under Unreleased or next-version section:
  > **a2kit v0.39 migration** — pin bump; drop `ctx: ToolContext` declaration from `WebRouter.fetch` (v0.39 ambient ctx unconditional); drop `_ensure()` from health probe; conftest `lazy_of` + `_ambient_ldd` helpers replaced with `a2kit.testing.{lazy, ambient_for_tests}`. Behaviour unchanged on the wire. Round-10 Friction E retracted (AppState/Lazy split is correct design).

---

## Step 6 — Final gate

- [x] 6a. `make check` — 414 passing, lint clean, 89.29% coverage. (lint + ty + test, coverage ≥85%).
- [~] 6b. **MCP smoke** — deferred (requires `claude mcp` interactive session). Tool dispatch covered by in-process TestClient (414 tests green); v0.39 wrapper synthesizes `_a2kit_ctx` correctly for the ctx-less tool. Wire-level smoke can run manually after merge. — `claude mcp list` shows a2web ✓; one real `mcp__a2web__fetch` against a known-good URL returns expected `FetchResponse`; events fire on the wire.
- [x] 6c. **CLI smoke** — `uv run a2web web fetch --url=https://example.com` returned structured JSON; LDD events streamed (TierStarted/TierEnded/StageStarted/StageEnded — ambient ctx bound despite no `ctx` param). returns expected output.
- [x] 6d. **CLI smoke** — `uv run a2web health` returns `{"status": "ok", ..., "checks": [{"name": "_check_sqlite", "status": "ok"}]}`. Resource entry happens at kwarg resolution; body is the readiness assertion. reports OK without `_ensure()` private probe.

---

## Step 7 — Archive

- [x] 7a. Archived to `openspec/changes/archive/2026-05-16-a2kit-v039-migration/`.
