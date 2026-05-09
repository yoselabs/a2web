## MODIFIED Requirements

### Requirement: Tier registry with explicit ordering

The system SHALL expose `TIER_ORDER: tuple[str, ...]` and `REGISTRY: dict[str, Tier]` from `a2web.tiers.__init__`. After PR7a, `TIER_ORDER` SHALL be `("site_handler", "raw", "jina")`. The `"site_handler"` slot SHALL dispatch via `match_handler(url)` from `a2web.handlers`; if no handler matches, the slot SHALL emit a sentinel `TierResult` with `tier_extras["no_match"] = True` that the orchestrator interprets as "skip silently — produce no diagnostic row, fall through to the next tier." The `"jina"` slot SHALL emit a sentinel `TierResult` with `tier_extras["skipped"] = True` when the URL host appears in `settings.jina_deny_hosts`; the orchestrator SHALL treat skipped tiers identically to no-match (no diagnostic row, fall through).

#### Scenario: site_handler precedes raw precedes jina

- **WHEN** the registry is imported in PR7a
- **THEN** `TIER_ORDER == ("site_handler", "raw", "jina")` and `len(REGISTRY) >= 3`

#### Scenario: No-match handler dispatch is silent

- **WHEN** the orchestrator runs against a URL no handler matches
- **THEN** the resulting `FetchResponse.diagnostics` contains no entry with `step == "site_handler"`; the first diagnostic row is from `raw` (or whichever next tier ran)

#### Scenario: Denied jina dispatch is silent

- **WHEN** the orchestrator runs against a URL whose host is in `settings.jina_deny_hosts` after raw fails
- **THEN** `FetchResponse.diagnostics` contains no entry with `step == "jina"`
