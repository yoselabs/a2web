## ADDED Requirements

### Requirement: Browser backend counts subresource challenge responses

During `render`, a `BrowserBackend` SHALL best-effort count page subresource responses that returned a challenge status (401, 403, or 429) for XHR/fetch request types, and surface the total as `RenderedPage.subresource_blocks: int` (default 0). The count SHALL be gathered without raising — a listener or driver error SHALL leave the count at its accumulated value and never fail the render. This is the only signal that distinguishes the walled-API fake-empty (an SPA whose data API was blocked but whose shell rendered an authentic "0 results") from a genuine empty; it is non-text and adversary-hard.

`RenderedPage` stays domain-free (the `packages/` boundary): `subresource_blocks` is a plain int carrying no `Verdict`/`OperatorHint`. The browser tier maps it onto its domain `TierResult` as a typed field (never a `tier_extras` bag), and the fetcher records it on the browser `tier_outcome` observation for the pure classifier.

#### Scenario: A blocked data API is counted

- **WHEN** a backend renders a page whose XHR to a product-search endpoint returns HTTP 403
- **THEN** the returned `RenderedPage.subresource_blocks` is ≥ 1

#### Scenario: A clean render counts zero

- **WHEN** a backend renders a page whose subresources all return non-challenge statuses
- **THEN** `RenderedPage.subresource_blocks == 0`

#### Scenario: Subresource counting never fails a render

- **WHEN** the subresource listener errors or the driver does not expose response metadata
- **THEN** `render` still returns its `RenderedPage` (outcome unaffected) with `subresource_blocks` at whatever it accumulated (0 if nothing was observed)
