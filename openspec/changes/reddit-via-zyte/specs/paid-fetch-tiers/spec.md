## ADDED Requirements

### Requirement: Zyte raw (httpResponseBody) fetch mode
The Zyte tier SHALL support a raw `httpResponseBody` fetch mode in addition to `browserHtml`. In raw mode it SHALL request `httpResponseBody`, decode the base64 body, and return it as the tier result without browser rendering. This mode is selected for server-rendered targets (e.g. old.reddit) where browser rendering is unnecessary and more expensive. Auth/billing failure mapping to the authoritative `paid_auth_error` fail-loud stop SHALL apply identically in both modes.

#### Scenario: Raw mode returns decoded server-rendered HTML
- **WHEN** the Zyte tier fetches a server-rendered URL in `httpResponseBody` mode
- **THEN** it returns the decoded HTML body without incurring browser-rendering cost

#### Scenario: Bad key still fails loud in raw mode
- **WHEN** a Zyte raw-mode request returns 401/402/403
- **THEN** the tier reports the authoritative `paid_auth_error` and escalation STOPs (no silent downgrade), identical to browserHtml mode

### Requirement: Eager paid dispatch for known-walled hosts
The orchestrator SHALL allow a handler to route a known-walled host directly to the paid tier (eager dispatch), bypassing the free tier ladder, in addition to the existing last-resort escalation. Eager dispatch SHALL remain gated on the paid tier being configured (`Unavailable` when un-keyed), preserving zero-cost behavior for un-keyed deployments.

#### Scenario: Handler routes a walled host straight to paid
- **WHEN** a handler marks a fetch as known-walled and a paid tier is configured
- **THEN** the paid tier is dispatched immediately without first running the free ladder

#### Scenario: Eager dispatch is inert when un-keyed
- **WHEN** a handler requests eager paid dispatch but no paid tier is keyed
- **THEN** no paid request is made and the flow falls back to the remaining available tiers (e.g. RSS)
