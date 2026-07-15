## ADDED Requirements

### Requirement: A retrieved error page surfaces its upstream status

A tier that retrieves an upstream ERROR page (an HTTP 4xx/5xx the origin returned, however the tier transports it) SHALL surface the real upstream status on its `TierResult` and map it through the tier's status→verdict function — it SHALL NOT report `ok` merely because bytes were returned. The decision log therefore records the truthful `(status_code, verdict)` per tier, so downstream classification reasons on real evidence.

Specifically:

- The `jina` reader wraps an upstream error as its OWN HTTP 200 with a body stub (`Target URL returned error <status>`). The `jina` tier SHALL decode that stub — capturing the status generically (`(\d{3})`, not a fixed enumeration), routing it through the existing status→verdict mapping, setting the real `status_code`, and NOT installing a `pre_rendered` payload — so a wrapped upstream error does not falsely win the tier loop. A body-length guard SHALL prevent a long document that merely quotes the stub string from being misread as a wrapper. A wrapped `401`/`403` SHALL map to `Verdict.paywall` to preserve archive-escalation routing; a wrapped `404` SHALL map to `not_found`.
- The `browser` tier, when it renders an upstream error page, SHALL surface that upstream status on its `TierResult` (so a browser-confirmed 404 is an observation, not a buried diagnostic). Its success path is unchanged.

The gate SHALL NOT contain tier-specific body-string special-cases for reader wrappers — decoding a tier's own transport protocol is tier work.

#### Scenario: jina-wrapped 404 does not win the loop

- **WHEN** `jina` returns HTTP 200 whose body is `Warning: Target URL returned error 404: Not Found`
- **THEN** the `jina` tier reports `verdict=not_found, status_code=404` with no `pre_rendered` payload, and does not win the tier loop

#### Scenario: jina-wrapped 403 preserves archive routing

- **WHEN** `jina` wraps an upstream `403`
- **THEN** the tier maps it to `Verdict.paywall`, and the archive escalation still fires (routing behaviour-neutral versus today)

#### Scenario: A quoted stub string is not a false wrapper

- **WHEN** a long retrieved article merely contains the text `Target URL returned error 404` in its body
- **THEN** the body-length guard prevents misclassification and the content is treated as real

#### Scenario: A browser-rendered error page is an observation

- **WHEN** the browser tier renders a page the origin served as HTTP 404
- **THEN** the tier surfaces a 404 upstream status on its `TierResult`, observable in the decision log

### Requirement: Incoming reader-prefix URLs are normalized to the target

When the caller passes an already-wrapped reader URL of the form `https://r.jina.ai/<real-url>` (including the `http://` and scheme-less variants), the `fetch()` entrypoint SHALL strip the reader prefix and fetch `<real-url>` with the full tier ladder, sibling to the existing captcha-host rewrite. A pre-wrapped URL otherwise pins a2web to the jina tier alone — treating `r.jina.ai` as the origin — with no raw/browser/paid fallback, defeating recovery. The real target SHALL be surfaced as `requested_url` so the wire `url` reflects the true target, never the wrapper. A bare `r.jina.ai/` with no inner URL SHALL be left unmodified.

#### Scenario: A pre-wrapped URL is unwrapped and gets full fallback

- **WHEN** the caller passes `https://r.jina.ai/https://example.com/x`
- **THEN** a2web fetches `https://example.com/x` through the full ladder (raw → jina → browser → paid), and the wire `url` is `https://example.com/x`, never the `r.jina.ai` wrapper

#### Scenario: A bare reader host is untouched

- **WHEN** the caller passes `https://r.jina.ai/` with no inner URL
- **THEN** the input is left unmodified
