## 1. Spike: confirm the stderr capture point

- [x] 1.1 Reproduce the driver stderr leak with real Camoufox against a JS-heavy SPA (Trendyol or a local JS fixture that throws a locationless uncaught error); confirm the raw trace lands on the parent's fd 2.
- [x] 1.2 Confirm whether Camoufox/Playwright (installed version) exposes a clean driver-stderr launch hook; if it does, prefer it over the fd-2 redirect and note the decision in design.md Open Questions.
- [x] 1.3 Verify the chosen capture mechanism actually swallows the reproduced trace before building on it.

## 2. Capture driver subprocess stderr

- [x] 2.1 Add a typed event payload (e.g. `BrowserSubprocessStderr`) to `src/a2web/events/types.py` carrying the trimmed line.
- [x] 2.2 In `src/a2web/packages/browser_pool.py`, capture the driver subprocess stderr at `_ensure()` (fd-2 redirect scoped to the browser lifetime, preserving the real fd via `os.dup`; or the clean launch hook from 1.2); restore fd 2 in `close()`/`__aexit__` under the existing lock.
- [x] 2.3 Drain captured lines on a daemon thread and forward each via `await a2kit.log.info(BrowserSubprocessStderr(...))`, routing real output back through the preserved fd so legitimate stderr still reaches the terminal.
- [x] 2.4 Join the drain thread with a timeout on `close()`; ensure no thread leak (mirror the aiosqlite-daemon discipline; add a teardown/arch assertion if cheap).

## 3. Internal exception → OperatorHint

- [x] 3.1 Add a small helper (e.g. `_internal_error_hint(exc, *, code, fix) -> OperatorHint`) that produces a single-line `message` from the exception type + text.
- [x] 3.2 Replace the `del exc` swallow at `src/a2web/tiers/browser.py:191` with a `browser_internal_error` hint on the returned `TierResult.operator_hint`; keep `Verdict.connection_error`.
- [x] 3.3 Register `browser_internal_error` as a documented stable `OperatorHint.code` value (docstring/comment in `models.py` alongside the existing codes).
- [x] 3.4 Confirm `fetcher.py:1471-1472` surfaces the new hint onto `operator_hints` (no orchestrator change expected; add a test if the path is untested).

## 4. Opt-in real-browser smoke check

- [x] 4.1 Register the `browser` marker in `pyproject.toml` `[tool.pytest.ini_options] markers`.
- [x] 4.2 Exclude the marker from the default run: set `-m "not browser"` (or addopts) so `make check` / `make test` never launch Camoufox.
- [x] 4.3 Add a deterministic local JS-rendering fixture server (renders content via JavaScript, offline) under `tests/`.
- [x] 4.4 Add `tests/.../test_browser_smoke.py` marked `@pytest.mark.browser`: opt out of the autouse `_UnavailableBrowserTier` stub, launch a real `BrowserPool`, fetch the local fixture, assert `Verdict.ok` + non-empty `pre_rendered.content_md` + `js_executed == True`; auto-skip when the Camoufox binary is absent.
- [x] 4.5 Add a `make test-browser` target that runs `-m browser`.

## 5. Tests for the captured paths

- [x] 5.1 Stub-level test: feed a synthetic noisy line through the stderr drain and assert exactly one `BrowserSubprocessStderr` log event and no terminal leak; assert zero events on a clean fetch.
- [x] 5.2 Stub-level test: a navigation exception yields `verdict == Verdict.connection_error` with a populated `browser_internal_error` `operator_hint` (single-line message, non-null fix) that reaches the response `operator_hints`.

## 6. Gate and docs

- [x] 6.1 Run `make check` (lint + ty + test + arch, coverage ≥85%) and confirm green with the browser marker excluded.
- [x] 6.2 Run `make test-browser` once locally to confirm the smoke check passes against the local fixture.
- [x] 6.3 Update `CHANGELOG.md` with the stderr-capture + internal-error-hint + smoke-check entry.
