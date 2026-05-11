# tier-pipeline (delta)

## ADDED Requirements

### Requirement: `fetch` tool accepts `include_links` and `debug` params

The `WebRouter.fetch` tool SHALL accept two new optional parameters with the following defaults and semantics:

- `include_links: bool = False` — when `False`, `FetchResponse.links` MUST be an empty list regardless of what tiers/handlers produced. When `True`, links are populated as per the existing extraction rules.
- `debug: bool = False` — when `False`, the full `FetchResponse.diagnostics` list MUST be omitted from MCP/CLI serialization (the field stays on the in-process Python object for internal callers). When `True`, the full diagnostics trace is serialized as today.

#### Scenario: default fetch omits links and diagnostics from wire output

- **WHEN** `fetch(url=...)` is invoked with no extra params
- **THEN** the JSON response MUST NOT contain a populated `links` array (empty list or omitted)
- **AND** the JSON response MUST NOT contain a `diagnostics` key
- **AND** the JSON response MUST contain a `diagnostics_summary` string

#### Scenario: opt-in includes links

- **WHEN** `fetch(url=..., include_links=True)` is invoked
- **THEN** `FetchResponse.links` SHALL be populated with all extracted links as per pre-v0.3 behavior

#### Scenario: opt-in includes full diagnostics

- **WHEN** `fetch(url=..., debug=True)` is invoked
- **THEN** the JSON response SHALL contain both `diagnostics` (full list) and `diagnostics_summary`

### Requirement: `FetchResponse.diagnostics_summary` is always populated

`FetchResponse` SHALL gain a `diagnostics_summary: str` field, always populated, with the shape:

```
tier=<tier_name> verdict=<verdict_value> total_ms=<int>[ extras=<k=v,...>]
```

Where `extras` is omitted unless the response is `status=failed`, in which case it includes the failure code from the gate or the last tier (e.g. `extras=length_floor`, `extras=blockpagedetected`).

#### Scenario: ok response has a clean one-line summary

- **WHEN** a fetch completes with `status=ok` via the raw tier in 708 ms
- **THEN** `diagnostics_summary == "tier=raw verdict=ok total_ms=708"`

#### Scenario: failed response surfaces the failure code

- **WHEN** a fetch completes with `status=failed` and the gate emitted `length_floor`
- **THEN** `diagnostics_summary` SHALL contain `extras=length_floor`
