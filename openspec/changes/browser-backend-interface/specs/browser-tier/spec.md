## MODIFIED Requirements

### Requirement: Browser tier executes JS via Camoufox pool

The system SHALL define `BrowserTier` in `src/a2web/tiers/browser.py` implementing the `Tier` protocol with `name = "browser"`. `BrowserTier.fetch` SHALL delegate rendering to the **selected `BrowserBackend`** (`backend.render(url, cookies=..., budget_s=..., js_heavy=...)`) rather than driving a Playwright `Page` directly. The tier SHALL own only the engine-agnostic tail: run trafilatura over the returned `RenderedPage.html`, populate `pre_rendered` (typed `Rendered`: `content_md`, `title`, `byline`, `headings`), set `from_browser = True` and `js_executed = RenderedPage.js_executed`, run the quality gate, and assemble the `TierResult`. The `TierResult` shape and every field it carries SHALL be unchanged from the pre-refactor tier (the response envelope is frozen).

The Playwright-specific mechanics the tier previously performed inline — per-host context pool, cookie seeding, navigation + network-idle budget, scroll-on-thin re-capture, driver-stderr capture, and the `browser_internal_error` hint — are realized by `PlaywrightBackend` behind the `BrowserBackend` interface (see the `browser-backend` capability). The tier no longer references `BrowserPool` or any Playwright type.

#### Scenario: Anubis-gated page renders post-PoW

- **WHEN** the URL serves an Anubis interstitial that resolves to real content after JS PoW
- **THEN** the selected backend's `render` returns the post-PoW HTML and the tier returns `verdict == Verdict.ok` with the content in `pre_rendered.content_md`

#### Scenario: Network-idle wait exceeds page budget

- **WHEN** rendering does not reach network-idle within `budget_s`
- **THEN** the backend returns a timed-out result and the tier returns `verdict == Verdict.timeout` with `browser_wall_ms >= budget_s * 1000`

#### Scenario: Tier holds no Playwright reference

- **WHEN** `tiers/browser.py` is imported
- **THEN** it imports no Playwright/Camoufox symbol and references no `BrowserPool` — it depends only on the `BrowserBackend` interface and `RenderedPage`
