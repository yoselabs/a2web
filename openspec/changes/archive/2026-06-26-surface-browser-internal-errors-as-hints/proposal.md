## Why

The browser tier (Camoufox / Firefox) leaks raw Node.js stack traces to the operator's terminal when Playwright's Firefox driver hits an internal error — e.g. on JS-heavy SPAs (Trendyol) the driver's `FFPage._onUncaughtError` dereferences an undefined `pageError.location.url` and Node prints the trace to stderr. The fetch then reports a useless `tier=raw verdict=length_floor` while the *actual* cause (the browser tier producing nothing) is discarded: `browser.py:191` catches the navigation exception and does `del exc`, emitting **no** operator hint.

The `browser-tier` spec already requires this stderr to be captured (the "Subprocess stderr from camoufox/playwright lands in LDD diagnostics" requirement, written for the same TechCrunch TypeError) — but `browser_subprocess_stderr` appears nowhere in the code. It was specced and never implemented. Every browser test is stubbed (no real Camoufox ever launches; `conftest.py` globally swaps in an `_UnavailableBrowserTier`), so a "browser tier is broken" regression is structurally invisible to `make check`.

## What Changes

- **Capture the Camoufox/Playwright driver subprocess stderr** so raw Node.js traces never reach the operator's terminal. Route captured lines through the current logging substrate (`await a2kit.log.info(...)`), not the retired LDD path the old requirement names.
- **Convert swallowed browser-tier internal errors into a structured `OperatorHint`.** The navigation/launch exception path that currently does `del exc` SHALL attach an `OperatorHint` with a stable `code` (e.g. `browser_internal_error`), the exception summary as `message`, and an actionable `fix`. The principle: an internal failure becomes a useful hint, never silent loss or terminal noise.
- **Establish a small reusable helper** for turning a caught internal exception into an `OperatorHint`, applied at the browser tier's catch sites (browser-tier scope only this change — no pipeline-wide sweep).
- **Add one opt-in real-browser smoke test** behind a registered marker (e.g. `@pytest.mark.browser`) that launches real Camoufox against a known JS-heavy URL and asserts non-empty rendered content. NOT in `make check`; run by hand / nightly. Closes the "do we have real checks?" gap.
- **Non-goal (explicitly excluded):** no Chromium fallback browser. If a second engine is ever needed it will be a separate tier, not a fallback bolted onto this one.

## Capabilities

### New Capabilities
<!-- none — behavior lands on the existing browser-tier capability -->

### Modified Capabilities
- `browser-tier`: (1) the subprocess-stderr-capture requirement is rewritten to the current `a2kit.log.info` logging substrate and made actually-enforced; (2) a new requirement that internal driver/navigation exceptions surface as a structured `OperatorHint` instead of being swallowed; (3) a new requirement for an opt-in real-browser smoke check that keeps "browser tier broken" observable.

## Impact

- `src/a2web/tiers/browser.py` — replace `del exc` swallow with hint construction; thread captured stderr into log events.
- `src/a2web/packages/browser_pool.py` — launch Camoufox with the driver subprocess stderr captured (not inherited from the Python parent).
- `src/a2web/events/types.py` — event payload for captured subprocess stderr (replacing the LDD-era `browser_subprocess_stderr` naming).
- `src/a2web/models.py` — possible new stable `OperatorHint.code` value (`browser_internal_error`); no envelope-shape change.
- `tests/` — register the `browser` marker (pyproject), add the opt-in real-Camoufox smoke test, and a stub-level test asserting the internal-error → hint conversion.
- No tool-signature or response-envelope change; no new top-level dependency.
