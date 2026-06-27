## MODIFIED Requirements

### Requirement: Browser backend is selected from settings via a plugin manifest

The system SHALL select the active backend from `settings.browser_backend` via a `select_backend(settings)` function resolving over manifests in `_manifests/browser_backends/`, each declaring `MANIFEST = PluginManifest(name, protocol=BrowserBackend, factory=..., requires=...)`. An unknown or unavailable backend SHALL degrade through the existing `ResourceUnavailable` seam (the same path the LLM provider uses), never crash the app. Backends requiring an optional dependency SHALL surface as `Unavailable` when the extra is absent.

The registry SHALL retain **two** engines after the bake-off — a fast Chromium engine (`patchright`) selected by `settings.browser_backend` and a robust CDP engine (`zendriver`) selected by `settings.browser_backend_robust` — resolved by a shared `select_backend_named(settings, name)`. The default `settings.browser_backend` SHALL be `"patchright"`, NOT `"camoufox"`. The Camoufox manifest SHALL be gated to surface `Unavailable` — its code is retained behind the gate (it is the one known fingerprint-strong engine) but it is unselectable until a Camoufox build ships juggler commit `b05563291d` (PR #625), at which point the gate is lifted. Both retained engines SHALL be installed out-of-the-box (their dependencies are non-optional) so a fresh install renders both rungs without extra setup.

#### Scenario: default selects the fast engine, not camoufox

- **WHEN** `settings.browser_backend` is unset
- **THEN** `select_backend` resolves `patchright`, and that backend is available (its dependency is installed by default)

#### Scenario: robust engine resolves from its own setting

- **WHEN** `settings.browser_backend_robust` is unset
- **THEN** `select_backend_named` resolves `zendriver`, available out-of-the-box

#### Scenario: camoufox is gated until #625 ships

- **WHEN** `settings.browser_backend` names `"camoufox"`
- **THEN** resolution surfaces `Unavailable` carrying the #625-unreleased reason, and the app does not crash

#### Scenario: unavailable backend degrades, not crashes

- **WHEN** `settings.browser_backend` names a backend whose optional dependency is not installed
- **THEN** resolution surfaces `ResourceUnavailable` at the tool seam and the app does not crash

## ADDED Requirements

### Requirement: The retained engines are the recorded outcome of a live three-candidate bake-off

The system's rendering engines SHALL be selected by a live bake-off — not by assumption — across three candidates wired behind the `BrowserBackend` interface: `patchright` and `rebrowser-playwright` (Chromium drop-ins realized as `PlaywrightBackend(launch_fn)`), and `zendriver` (a CDP engine realized as a dedicated adapter). The candidates SHALL be scored on **SPA-read success, robustness, and speed** (stealth as a secondary tiebreaker) against a browser-stress URL set (the eval corpus does not exercise the browser tier). The outcome SHALL be recorded to a dated findings file (`eval/findings_<date>.md`) as the audit trail. The bake-off MAY conclude that the candidates are complementary rather than strictly ranked; in that case the system SHALL retain the fast Chromium engine (`patchright`) and the robust CDP engine (`zendriver`) as a fast→robust pair and prune only the strict loser (`rebrowser`). After selection, no non-retained candidate's backend, manifest, or dependency extra SHALL remain in the tree.

#### Scenario: retained engines are chosen on recorded numbers

- **WHEN** the bake-off completes
- **THEN** the retained engines and the prune decision match the recorded SPA-read + robustness + speed profile in `eval/findings_<date>.md`

#### Scenario: pruned candidate leaves no residue

- **WHEN** the change is archived
- **THEN** the tree contains exactly the two retained non-Camoufox backends (`patchright`, `zendriver`) plus the gated Camoufox — no `rebrowser` backend module, manifest, or dependency extra remains

### Requirement: The interface is proven engine-family-agnostic by a CDP adapter

The `BrowserBackend` contract SHALL be demonstrated to span engine families, not just the Playwright API: the `zendriver` candidate SHALL be realized as a `ZendriverBackend` adapter that shapes CDP navigation, content capture, and cookie seeding into the same `render(url, *, cookies, budget_s, js_heavy) -> RenderedPage` method the Playwright-family backends satisfy. The adapter SHALL emit the same domain-free `RenderedPage` value object (carrying no Playwright `Page`/CDP session/domain type) so the tier's `RenderOutcome` → `Verdict`/`OperatorHint` mapping is identical regardless of engine family. This proof SHALL hold for the bake-off even if `zendriver` does not win and its adapter is subsequently removed.

#### Scenario: a CDP backend satisfies the same render contract

- **WHEN** `ZendriverBackend.render(...)` completes during the bake-off
- **THEN** it returns a `RenderedPage` carrying no Playwright/CDP/domain object, and the tier maps its `RenderOutcome` to `Verdict`/`OperatorHint` with no engine-family-specific branch
