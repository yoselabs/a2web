# paid-fetch-tiers Specification

## Purpose
TBD - created by archiving change reddit-reachability-never-silent-miss. Update Purpose after archive.
## Requirements
### Requirement: Env-gated paid fetch tiers (Zyte + Firecrawl)
a2web SHALL expose Zyte and Firecrawl as **out-of-band** fetch tiers (`priority=-1`, not in `TIER_ORDER`) registered via `_manifests/tiers/` plugins, keyed by `A2WEB_ZYTE_KEY` and `A2WEB_FIRECRAWL_KEY` (env-only secrets). An un-keyed tier's factory SHALL return `Unavailable` so it never enters the registry. Keyed tiers SHALL be dispatched only on a terminal block/paywall/anti_bot signal (via an `EscalatePaid` planner rule), never on every fetch.

#### Scenario: Un-keyed tier is skipped
- **WHEN** neither `A2WEB_ZYTE_API_KEY` nor `A2WEB_FIRECRAWL_KEY` is set
- **THEN** the paid tiers are not attempted and escalation proceeds to the terminal browser hint

#### Scenario: Keyed tier participates in escalation
- **WHEN** a service key is configured and a fetch is walled
- **THEN** the keyed paid tier is attempted before the terminal hint

#### Scenario: Paid is the cost-incurring last resort, after proxied free attempts
- **WHEN** a fetch is walled
- **THEN** the free tiers (raw via the proxy pool, and browser where applicable) are exhausted first, and the paid tier is dispatched only afterward, before the terminal `try_user_browser` hint

### Requirement: Fail loud on service/key failure — no silent downgrade
When a paid tier is keyed but the call fails (bad key, quota, auth/billing error), the tier SHALL return the authoritative `Verdict.paid_auth_error`, which SHALL STOP escalation so the failure surfaces as the reported result. a2web SHALL NOT silently fall back to a lower-quality path.

#### Scenario: Bad key reports rather than degrades
- **WHEN** a keyed paid tier returns an authentication/billing error
- **THEN** the tier returns `paid_auth_error` (authoritative), escalation stops, and the response reports the failure loudly rather than silently substituting a lower-quality result

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

