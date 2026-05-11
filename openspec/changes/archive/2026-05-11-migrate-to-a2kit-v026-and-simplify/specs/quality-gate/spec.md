## ADDED Requirements

### Requirement: block-detector is a uv workspace package

The block-page detection logic (`evaluate(content_md, raw_html, content_type) -> GateResult`, the regex patterns, the signal table, the closed-enum verdict + `suggested_tier` hint) SHALL live in `packages/block-detector/` as an internal workspace package. The package SHALL:

- Declare its own `pyproject.toml` with no dependencies (pure-Python, stdlib only).
- Define its own narrow types (`BlockVerdict`, `GateResult`, `SuggestedTier` enum) and expose them via `__init__.py`.
- NOT import any symbol from the `a2web` namespace.
- Pass `make lint`, `make ty`, `make test` independently when run from inside the package directory.
- Carry the detection patterns for the v0.1 signal table (Anubis, Turnstile, Akamai BMP, Cloudflare interstitial, generic JS-required, paywall, length-floor).

#### Scenario: Package isolation

- **WHEN** lint runs over `packages/block-detector/src/`
- **THEN** zero `from a2web` or `import a2web` matches are found

#### Scenario: Package tests run independently

- **WHEN** `cd packages/block-detector && uv run pytest` runs
- **THEN** the test suite passes without requiring a2web to be installed

#### Scenario: No transitive deps

- **WHEN** an operator inspects `packages/block-detector/pyproject.toml`
- **THEN** the `[project.dependencies]` table is empty or contains only stdlib-equivalent helpers

### Requirement: a2web adapter for block-detector

`src/a2web/gate/__init__.py` SHALL be a thin adapter that imports `block_detector` and translates package-native types to a2web's `Verdict` enum where needed. The adapter SHALL be the seam where package-native verdicts cross into a2web's domain types.

The orchestrator SHALL call `from a2web.gate import evaluate` (a re-export through the adapter) — it SHALL NOT import directly from `block_detector`.

#### Scenario: Adapter exists and is the only seam

- **WHEN** `grep -r "from block_detector" src/a2web/` runs
- **THEN** only `src/a2web/gate/__init__.py` matches (the adapter module)

## MODIFIED Requirements

### Requirement: Gate result carries optional suggested_tier

`GateResult` SHALL carry a `suggested_tier: SuggestedTier | None = None` field. The type is package-defined (`block_detector.SuggestedTier` enum with values `browser`, `tls_impersonate`). Behavior preserved from v0.1.0 — the v0.1 signal table is unchanged.

#### Scenario: Anubis page yields suggested_tier = browser

- **WHEN** the gate evaluates a response containing the Anubis marker with body length below the floor
- **THEN** `GateResult.verdict == Verdict.anti_bot`, `subsystem == "anubis"`, `suggested_tier == SuggestedTier.browser`

#### Scenario: Cloudflare interstitial yields suggested_tier = tls_impersonate

- **WHEN** the gate sees a "Just a moment" interstitial with `cf-chl-bypass` markers
- **THEN** `suggested_tier == SuggestedTier.tls_impersonate`

#### Scenario: Clean article has no suggested_tier

- **WHEN** the gate evaluates a normal article that passes all checks
- **THEN** `verdict == Verdict.ok` and `suggested_tier is None`
