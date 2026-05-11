# quality-gate (delta)

## ADDED Requirements

### Requirement: length_floor + JS-shell pattern produces suggested_tier="browser"

When the gate evaluates a tier response and the verdict would be `length_floor`, the gate SHALL additionally inspect the first 8192 bytes of the raw response body (lowercased) for JS-framework root markers. If any of the following are present:

- `id="__next"` (Next.js root element)
- `id="root"` (React root element)
- `id="app"` (Vue / generic SPA root element)
- `window.__data__` (Ember-style hydration marker)
- `<noscript>` (progressive-enhancement marker indicating JS-required content)

AND the body also contains `<script`, THEN the gate SHALL set `GateResult.suggested_tier = "browser"`. The verdict remains `length_floor`. The orchestrator SHALL dispatch the browser tier as per the existing `browser-tier` spec.

#### Scenario: thin Next.js shell triggers browser escalation

- **WHEN** raw tier returns 200 with body containing `<div id="__next">` and `<script>` but trafilatura extracts < 500 chars
- **THEN** `GateResult.verdict == length_floor` AND `GateResult.suggested_tier == "browser"`
- **AND** the orchestrator dispatches the browser tier once

#### Scenario: thin plain-HTML page (not a JS shell) does NOT trigger browser

- **WHEN** raw tier returns 200 with truly empty body (no JS markers) and trafilatura extracts < 500 chars
- **THEN** `GateResult.verdict == length_floor` AND `GateResult.suggested_tier is None`
- **AND** the orchestrator does NOT dispatch browser

## MODIFIED Requirements

### Requirement: block_detector length threshold tuned for compact-SPA landing pages

The existing length-floor threshold in `block_detector.py` SHALL be re-tuned so that compact-SPA marketing pages with real content (≥ 200 chars of substantive `content_md` after extraction) are NOT classified as `length_floor`. The exact threshold is a code-level tuning choice; the spec requires the regression scenario below to pass.

#### Scenario: Linear-style compact landing page is classified as ok

- **WHEN** the gate evaluates a page where trafilatura extracted ≥ 200 chars of body text and the gate's prior signals (anubis, turnstile, etc.) are absent
- **THEN** `GateResult.verdict == ok` and `status` propagates as `ok` in `FetchResponse`
