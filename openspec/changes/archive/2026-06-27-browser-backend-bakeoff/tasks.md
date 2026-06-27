## 1. Candidate backends — Chromium drop-ins

- [x] 1.1 **(ask-first dep)** Add `patchright` + `rebrowser-playwright` as bake-off extras in `pyproject.toml` (transient — pruned in §5); confirm the dep additions before installing. *(user-approved; all three added as `[project.optional-dependencies] bakeoff`)*
- [x] 1.2 Add `packages/browser_backends/patchright.py`: a `patchright_launcher()` returning patchright's `async_playwright`-shaped launch CM; reuse `PlaywrightBackend` verbatim (no new pool/stderr/scroll code). *(shared `chromium_launch` helper flattens the two-step launch)*
- [x] 1.3 Add `packages/browser_backends/rebrowser.py`: a `rebrowser_launcher()` likewise.
- [x] 1.4 Export both launchers from `packages/browser_backends/__init__.py`.
- [x] 1.5 Add `_manifests/browser_backends/patchright.py` + `rebrowser.py` manifests (`PluginManifest(name, protocol=BrowserBackend, factory=_build, requires=...)`, factory builds `PlaywrightBackend(launcher, name=..., stderr_sink=_emit_browser_stderr)`); surface `Unavailable` when the extra is absent. *(import-presence check via `importlib.util.find_spec`)*

## 2. Candidate backend — CDP zendriver adapter

- [x] 2.1 **(ask-first dep)** Add `zendriver` as a bake-off extra in `pyproject.toml`; confirm before installing. *(user-approved with §1; `zendriver>=0.15,<1` in the `bakeoff` extra)*
- [x] 2.2 Add `packages/browser_backends/zendriver.py`: `ZendriverBackend` implementing `BrowserBackend` directly (`render` + `__aenter__`/`__aexit__`) — open tab, navigate with `budget_s` cap, seed `BackendCookie`s via CDP `Network.setCookie`, capture outer HTML, map failures to `RenderOutcome.{timeout,error,unavailable}`. Return only `RenderedPage` (no `Tab`/CDP session leak). v1: per-render launch, no host pool (D3). *(tuned `Config.browser_connection_timeout=1.0 ×15` — default 0.25×10 ≈ 2.5s races Chromium's CDP socket on a cold host and spuriously reports `unavailable`)*
- [x] 2.3 If the adapter needs any new boundary value object, make it package-owned + domain-free and add it to `_FROZEN_BOUNDARY_TYPES` in `tests/architecture/test_packages_boundary_frozen.py`. *(N/A — reused `BackendCookie`/`RenderedPage`; no new boundary type)*
- [x] 2.4 Add `_manifests/browser_backends/zendriver.py` manifest (Unavailable when the extra is absent). *(builds `ZendriverBackend`, not `PlaywrightBackend`; no `stderr_sink` — CDP in-process, no Node driver subprocess)*
- [x] 2.5 Confirm `test_packages_independence` + `test_packages_boundary_frozen` stay green with the CDP adapter present. *(tach `✅ All modules validated`; boundary-frozen green)*
- [x] 2.6 Add a unit test for `ZendriverBackend` mapping (fake CDP driver, no real browser) covering ok/timeout/error/unavailable outcomes — mirrors `test_playwright_backend.py`. *(7 tests, all green)*

## 3. Bake-off — score and decide

- [x] 3.1 Add a bake-off script/CLI that sweeps `settings.browser_backend` over `{patchright, rebrowser, zendriver}`. *(`a2web.llm_eval.browser_bakeoff`; corpus barely touches the browser tier (only react.dev), so it drives a dedicated browser-stress URL set instead — user-approved)*
- [x] 3.2 Capture per-candidate: SPA-read success (`block_detector` verdict `ok` + md ≥ floor), robustness (not block/anti-bot), speed (`wall_ms`); render-layer only (~0 LLM quota, user-approved). *(reuses `extract_markdown` + `block_detector.evaluate`)*
- [x] 3.3 Run it (live network) and write `eval/findings_2026-06-27.md`. *(zendriver reads Trendyol+Hepsiburada 4/5, patchright/rebrowser 2/5; rebrowser strict loser; complementary → keep two)*
- [x] 3.4 Confirm the winner with the user before pruning. *(user chose two-engine fast→robust ladder modeled as two tiers/"spheres" reusing the existing escalation)*
- [x] 3.5 Phase B (LLM answer-quality) — DEFERRED (recorded in findings): render-layer was decisive on the incident class (zendriver reads what patchright can't); LLM confirm not needed to commit.

## 4. Commit: prune the loser (rebrowser)

- [x] 4.1 Delete `packages/browser_backends/rebrowser.py` + its `__init__` exports (`rebrowser_launcher`); keep `patchright_launcher` + `chromium_launch`.
- [x] 4.2 Delete `_manifests/browser_backends/rebrowser.py`. Keep `_common.py` only if patchright still uses `playwright_backend_manifest`; otherwise inline the single patchright manifest and delete `_common.py`.
- [x] 4.3 Confirm exactly two non-Camoufox backends remain (`patchright`, `zendriver`) + gated Camoufox; no `rebrowser` residue.

## 5. Two-tier escalation: wire browser (fast) + browser_robust (robust)

- [x] 5.1 `settings.py` — `browser_backend` default `"camoufox"` → `"patchright"`; add `browser_backend_robust: str = "zendriver"`.
- [x] 5.2 `state.py` — add `select_backend_named(settings, name)` (the current `select_backend` becomes `select_backend_named(settings, settings.browser_backend)`); add `build_browser_robust_backend(settings)` resolving `settings.browser_backend_robust`.
- [x] 5.3 `server.py` — `app.provide(build_browser_robust_backend)` alongside the fast one.
- [x] 5.4 `_manifests/tiers/browser_robust.py` — register a `BrowserTier(name="browser_robust")` tier (priority=-1, out-of-band). Confirm `REGISTRY` has both browser rungs and `TIER_ORDER` excludes both. (Add a `name` param to `BrowserTier.__init__`.)
- [x] 5.5 `actions/playbook.py` — **reuse** the existing `EscalateBrowser` action + `gate_browser_signal` rule; only **widen its cap** from `browser_dispatches < 1` to `< 2` (update the `PlannerCaps.browser_dispatches` doc). No new action, no new rule, no new cap field.
- [x] 5.6 `routers.py` / `fetcher.py` — add the `browser_robust_backend: Lazy[RobustBrowserBackend]` tool seam + `FetchContext` field; **parameterize the single `_escalate_browser` handler by rung** (`fc.browser_dispatches`: 0 → tier `browser` + `fc.browser_backend`; 1 → tier `browser_robust` + `fc.browser_robust_backend`). No `_escalate_browser_robust` twin.
- [x] 5.7 Fix the hardcoded `engine="camoufox"` in `_escalate_browser` events + diagnostics → the real tier/engine name (`browser`/`browser_robust`, `patchright`/`zendriver`).

## 6. Gate Camoufox, modernize deps

- [x] 6.1 Gate `_manifests/browser_backends/camoufox.py` to return `Unavailable("camoufox: FF build lacks juggler #625 / b05563291d; re-enable when shipped")`; keep `PlaywrightBackend` + `camoufox_launcher` code in place.
- [x] 6.2 **(ask-first dep)** Promote `patchright` + `zendriver` from the `bakeoff` extra to baseline `dependencies`; drop the `bakeoff` extra (incl. `rebrowser`); drop `camoufox[geoip]` (retires the transitive `playwright` / `<1.60` exposure). Confirm before applying.
- [x] 6.3 `uv sync --all-extras`; verify a clean install resolves with both engines non-optional.

## 7. Tests, gate, finish

- [x] 7.1 Update `select_backend` tests: unset `browser_backend` → `patchright`; `browser_backend_robust` → `zendriver`; camoufox → `Unavailable` with the #625 reason.
- [x] 7.2 Add a playbook test for the new rule: a `browser` thin/blocked gate after a fast dispatch → `EscalateBrowserRobust`; never before the fast rung; caps respected.
- [x] 7.3 Add/adjust a real-browser smoke for both rungs under the `browser` marker (auto-skip when binaries absent).
- [x] 7.4 Run `make check` (lint + ty + test, coverage ≥85%) green; `make arch` green.
- [x] 7.5 `make test-browser` — confirm a real render through both rungs.
- [x] 7.6 Update `CHANGELOG.md` (two-tier browser escalation + engine swap + dep modernization) and `BACKLOG.md` (close the bake-off roadmap; note gated-Camoufox re-enable + the zendriver per-render-launch pooling optimization).
