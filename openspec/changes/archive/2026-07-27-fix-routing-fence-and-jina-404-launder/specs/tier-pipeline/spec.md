## MODIFIED Requirements

### Requirement: A retrieved error page surfaces its upstream status

A tier that retrieves an upstream ERROR page (an HTTP 4xx/5xx the origin returned, however the tier transports it) SHALL surface the real upstream status on its `TierResult` and map it through the tier's status→verdict function — it SHALL NOT report `ok` merely because bytes were returned. The decision log therefore records the truthful `(status_code, verdict)` per tier, so downstream classification reasons on real evidence.

Specifically:

- The `jina` reader wraps an upstream error as its OWN HTTP 200 with a body stub (`Target URL returned error <status>`). The `jina` tier SHALL decode that stub — capturing the status generically (`(\d{3})`, not a fixed enumeration), routing it through the existing status→verdict mapping, setting the real `status_code`, and NOT installing a `pre_rendered` payload — so a wrapped upstream error does not falsely win the tier loop. A wrapped `401`/`403` SHALL map to `Verdict.paywall` to preserve archive-escalation routing; a wrapped `404` SHALL map to `not_found`.
- **The guard against a false wrapper SHALL be positional, not length-based.** jina emits its wrapper metadata (`Title:`, `URL Source:`, `Published Time:`, `Warning: Target URL returned error <status>`) in a header block that precedes the `Markdown Content:` separator introducing the retrieved body. The tier SHALL search for the stub ONLY within that header region, and SHALL NOT match occurrences at or after the separator. A body-length ceiling SHALL NOT be used: total response length does not discriminate a wrapper from a quotation, and a2web's own `X-Return-Format: markdown` request header inflates the wrapper body past any fixed ceiling, which silently disarmed the decode and laundered a real upstream 404 into `ok` with `confidence: high`. When no `Markdown Content:` separator is present, the tier SHALL treat the response as header-only and search it in full.
- The `browser` tier, when it renders an upstream error page, SHALL surface that upstream status on its `TierResult` (so a browser-confirmed 404 is an observation, not a buried diagnostic). Its success path is unchanged.

The gate SHALL NOT contain tier-specific body-string special-cases for reader wrappers — decoding a tier's own transport protocol is tier work.

#### Scenario: jina-wrapped 404 does not win the loop

- **WHEN** `jina` returns HTTP 200 whose body is `Warning: Target URL returned error 404: Not Found`
- **THEN** the `jina` tier reports `verdict=not_found, status_code=404` with no `pre_rendered` payload, and does not win the tier loop

#### Scenario: A verbose wrapped error is still decoded

- **WHEN** `jina` wraps an upstream `404` and the response body exceeds 2048 bytes — the shape a2web's own `X-Return-Format: markdown` header produces, measured at 3030 bytes for a real fat 404 page
- **THEN** the stub is still decoded from the header block and the tier reports `verdict=not_found, status_code=404`, NOT `ok`

#### Scenario: jina-wrapped 403 preserves archive routing

- **WHEN** `jina` wraps an upstream `403`
- **THEN** the tier maps it to `Verdict.paywall`, and the archive escalation still fires (routing behaviour-neutral versus today)

#### Scenario: A quoted stub string is not a false wrapper

- **WHEN** a retrieved article's body — the region at or after the `Markdown Content:` separator — contains the text `Target URL returned error 404`, and jina's own header block carries no `Warning:` stub
- **THEN** the positional guard prevents misclassification and the content is treated as real, at any body length

#### Scenario: A browser-rendered error page is an observation

- **WHEN** the browser tier renders a page the origin served as HTTP 404
- **THEN** the tier surfaces a 404 upstream status on its `TierResult`, observable in the decision log
