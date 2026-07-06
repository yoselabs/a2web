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

### Requirement: Paid render escalates on a post-browser js_required SPA shell

The paid last-resort planner SHALL treat a `length_floor` gate verdict whose block-detector subsystem is `js_required` as a wall worth a paid render, dispatching the paid tier (Zyte, default `browserHtml` mode). This fires only after the free/proxied ladder — including the browser rung — is exhausted, and only within the existing single-paid-dispatch budget. The subsystem check is load-bearing: a bare `length_floor` verdict without the `js_required` subsystem (a thin article, an empty result set) MUST NOT trigger paid egress, so paid spend stays scoped to genuine JS-shell SPAs.

#### Scenario: Unrendered SPA shell after the browser rung escalates to paid render

- **WHEN** a fetch's latest gate/regate verdict is `length_floor` with subsystem `js_required`, the browser escalation rung is already spent, and the paid budget is unspent (`paid_dispatches < 1`)
- **THEN** the planner returns `EscalatePaid`
- **AND** the orchestrator dispatches the paid tier in its default browser-render mode

#### Scenario: Bare length_floor does not trigger paid egress

- **WHEN** a fetch's gate verdict is `length_floor` with no `js_required` subsystem (e.g. a genuinely short page or an empty result set)
- **THEN** the paid last-resort rule does not fire, and no paid egress occurs

#### Scenario: Paid budget cap prevents repeat dispatch

- **WHEN** a paid render has already been dispatched for the fetch (`paid_dispatches == 1`)
- **THEN** the js_required-SPA rule does not fire again, and the planner terminates (never spins)

#### Scenario: Un-keyed deployment falls through without cost

- **WHEN** the js_required-SPA condition holds but no paid tier is registered (no key configured)
- **THEN** the paid dispatch is a no-op and the fetch falls through to the never-silently-miss hint, incurring no cost

### Requirement: Paid render escalates on an extractor obstacle

The paid last-resort tier SHALL gain a third trigger, alongside the gate-wall
(`paid_last_resort`) and handler `escalate_to_render` triggers: an `ask`
extractor `obstacle ∈ {empty, blocked}`. When the extractor reports such an
obstacle, no paid render was already spent (`paid_dispatches < 1`), AND there is
evidence a render would add content — the already-extracted content is THIN
(`len(content_md) < _RENDER_CONTENT_CEILING`, so plausibly an unrendered shell
rather than a complete SSR/static page that merely lacks the answer), the
content did NOT come from a JS-executing tier (`jina` / `browser` /
`browser_robust`), AND the raw body shows unrendered-SPA markers
(`block_detector.looks_like_unrendered_spa`) — the orchestrator SHALL dispatch
the paid tier (Zyte, default `browserHtml` mode) on the original URL. All three
triggers share the single one-dispatch-per-fetch budget. `paywalled` / `error`
obstacles SHALL NOT trigger a paid render, and neither SHALL a content-rich page
(SSR or static) that merely lacks the answer.

#### Scenario: Thin SPA shell dispatches the paid render

- **WHEN** an `ask` extractor reports `obstacle` in `{empty, blocked}` over thin content from a non-JS tier bearing unrendered-SPA markers, a paid tier is registered, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches the paid tier in its default browser-render mode on the original URL

#### Scenario: Content-rich SSR page does not dispatch a render

- **WHEN** an `ask` extractor reports `obstacle: "empty"` over an SSR page whose extracted content is at or above the ceiling (complete content, SPA markers present)
- **THEN** the obstacle trigger does not fire, no paid egress occurs, and the surviving obstacle drives `retrieval_incomplete`

#### Scenario: Paid budget is shared across triggers

- **WHEN** a paid render was already dispatched by a gate wall or handler `escalate_to_render` (`paid_dispatches == 1`) and the extractor then reports `obstacle: "empty"`
- **THEN** no second paid render is dispatched (the shared cap holds)

