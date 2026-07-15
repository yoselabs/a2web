## ADDED Requirements

### Requirement: thin_content is attached on a thin_unverified failure

`AskResponse` SHALL carry a conditional `thin_content: str | None` field, populated ONLY when the fetch terminates on the `thin_unverified` outcome (a retrieved HTTP 200 that rendered thin with no hard-wall evidence). It holds the retrieved sub-floor body verbatim (wrapped per the existing untrusted-content rule). It SHALL be absent from the wire on every other outcome (omit-empty), and its presence SHALL NOT depend on `include_content` — the index-rule (ADR-0015) forces the body onto the wire on this failure even though `query` withholds content by default. The attached body is wire-only and never enters the cache.

#### Scenario: thin_unverified failure attaches the body

- **WHEN** a `query` fetch terminates on `thin_unverified` (an empty-result thin 200)
- **THEN** the wire payload contains `thin_content` with the retrieved sub-floor body and a `content_thin` warning hint, without requiring `include_content=True`

#### Scenario: thin_content is absent on success and on other failures

- **WHEN** a `query` fetch ends `ok`, or fails on any outcome other than `thin_unverified` (e.g. `wall`, `gone_confirmed`)
- **THEN** the wire payload contains no `thin_content` key
