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

