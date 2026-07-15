## REMOVED Requirements

### Requirement: Jina stub recognized as paywall

**Reason**: Decoding jina's reader-wrapper stub is a tier-protocol concern, not a content-gate concern — it moves to the `jina` tier (see `tier-pipeline`: "A retrieved error page surfaces its upstream status"). The gate SHALL NOT branch on `tier == "jina"` or match reader-stub body strings; the `_JINA_PAYWALL_STUB_RE` special-case and its constants are deleted from `evaluate()`. The wrapped-401/403 → `paywall` → archive routing is preserved by the jina tier mapping those statuses to `Verdict.paywall`, and a wrapped 404 now correctly surfaces as `not_found` (previously it fell through to `length_floor` and fired a false anti-bot wall). Block-page and length-floor detection over genuinely-retrieved content is unchanged.

**Migration**: the two prior scenarios (403/401 jina stub → `paywall`) are re-expressed at the tier layer in `tier-pipeline`; the gate no longer has jina-specific behavior to test.

#### Scenario: Gate no longer special-cases jina stubs

- **WHEN** the quality gate evaluates any content
- **THEN** it applies no `tier == "jina"` branch and no reader-stub body regex — jina-wrapper decoding has moved to the tier layer
