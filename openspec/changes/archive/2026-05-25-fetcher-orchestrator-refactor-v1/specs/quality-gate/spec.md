## ADDED Requirements

### Requirement: BlockResult carries a typed EscalationSignal instead of a string suggested_tier

`BlockResult` in `src/a2web/packages/block_detector.py` SHALL replace its `suggested_tier: str | None = None` field with `escalation: EscalationSignal | None = None`. `EscalationSignal` lives in `src/a2web/packages/escalation.py` — package-owned so block_detector can import it without crossing the packages-independence boundary.

Detector branches that previously set `suggested_tier="browser"` SHALL set `escalation=EscalationSignal(next_tier="browser", reason="<subsystem>")` where `<subsystem>` is the matching marker family name (`js_required`, `anubis`, `turnstile`, `akamai_bmp`, etc.).

Detector branches that previously set `suggested_tier="tls_impersonate"` SHALL set `escalation=EscalationSignal(next_tier="tls_impersonate", reason="cf_iuam")`.

The block detector remains policy-free — it emits typed evidence; the planner decides whether to act. Behavior visible to callers is unchanged; only the field type changes.

#### Scenario: JS-required marker yields typed escalation

- **WHEN** the gate evaluates a thin response containing web-component or React markers + `<script>`
- **THEN** `BlockResult.escalation == EscalationSignal(next_tier="browser", reason="js_required")` and downstream the planner reads the typed signal

#### Scenario: Cloudflare interstitial yields typed escalation

- **WHEN** the gate sees a "Just a moment..." interstitial with `cf-chl-bypass` markers
- **THEN** `BlockResult.escalation == EscalationSignal(next_tier="tls_impersonate", reason="cf_iuam")`

#### Scenario: Healthy page emits no escalation

- **WHEN** the gate evaluates a normal article that passes all checks
- **THEN** `BlockResult.escalation is None` (semantically identical to the previous `suggested_tier is None`)

## REMOVED Requirements

### Requirement: Gate result carries optional suggested_tier
**Reason**: Superseded by typed `EscalationSignal`. The string field encoded a Literal-shaped value as text, required string compares in the planner, and offered no compile-time safety. The typed payload also adds an explicit `reason` field that aligns with the gate's `subsystem` annotation.
**Migration**: Code reading `block_result.suggested_tier` MUST switch to `block_result.escalation.next_tier if block_result.escalation else None`. The matching subsystem string remains available on `block_result.subsystem` (unchanged) for diagnostics.
