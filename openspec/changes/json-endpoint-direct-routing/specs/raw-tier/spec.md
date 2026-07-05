## MODIFIED Requirements

### Requirement: HTTP failures map to closed-enum verdicts

The system SHALL map curl_cffi exceptions and HTTP status codes to the closed `Verdict` enum:

- Connection refused / DNS / TLS handshake errors → `Verdict.connection_error`
- Timeout → `Verdict.timeout`
- 404 → `Verdict.not_found`
- 429 → `Verdict.rate_limited`
- 5xx → `Verdict.connection_error`
- 2xx with a JSON content-type (`application/json`, `application/<x>+json`, `text/json`) → `Verdict.ok` (a JSON response is first-class content, not a mismatch — it is synthesized to markdown downstream, never escalated to the jina HTML reader)
- 2xx with a non-HTML, non-JSON content type when HTML expected → `Verdict.content_type_mismatch`
- 2xx HTML otherwise → `Verdict.ok`

The JSON carve-out SHALL be evaluated BEFORE the non-HTML mismatch check, so a JSON response never maps to `content_type_mismatch`. Detection SHALL use a shared `_is_json_content_type` predicate (also consulted by the extract phase) so the raw tier and the orchestrator agree on what counts as JSON.

#### Scenario: 404 maps to not_found

- **WHEN** the tier receives an HTTP 404 response
- **THEN** the returned `TierResult.verdict == Verdict.not_found` and `status_code == 404`

#### Scenario: Timeout does not raise

- **WHEN** the upstream host fails to respond within the timeout
- **THEN** the tier returns a `TierResult` with `verdict == Verdict.timeout`, NOT a raised `TimeoutError` propagating through the orchestrator

#### Scenario: 2xx JSON response maps to ok

- **WHEN** the tier receives an HTTP 200 with `content-type: application/json`
- **THEN** `TierResult.verdict == Verdict.ok` and `TierResult.content_type` carries the JSON content-type through to extraction

#### Scenario: 2xx JSON-family content-type maps to ok

- **WHEN** the tier receives an HTTP 200 with `content-type: application/vnd.api+json` (a `+json` suffix type)
- **THEN** `TierResult.verdict == Verdict.ok`

#### Scenario: 2xx non-JSON non-HTML still mismatches

- **WHEN** the tier receives an HTTP 200 with `content-type: application/pdf`
- **THEN** `TierResult.verdict == Verdict.content_type_mismatch` (unchanged — only JSON is carved out)
