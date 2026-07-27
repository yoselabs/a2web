## ADDED Requirements

### Requirement: A genuinely lost index is surfaced as a warning, never silently

ADR-0015 requires that `query`, which withholds the page body by default, never withhold it *silently* — the caller is itself an agent that never sees the body and cannot tell an absent index from an empty one.

When the routing outcome is `unparsable` or `unclassified` AND the response would otherwise carry no index at all (no `also_here`, no `other_pages`, no `options`), the response SHALL carry exactly one `OperatorHint` with severity `warning` recording that the index was lost rather than empty.

`refinement_axes` is deliberately NOT part of the gate. It is gated on the LLM classifying the page as a listing, which by construction cannot hold on either arm this hint fires for — `unparsable` has no payload and `unclassified` has no classification — so including it would read as a fourth source while being unreachable. A guard condition that can never contribute is indistinguishable from one that works.

The hint message SHALL name the concrete recovery. Re-fetching the same URL is served from the HTTP cache within TTL, so recovering the withheld body via `fetch_raw` on the same URL costs no new proxy fetch — the scarce resource. A hint that reports a problem without naming its cheap remedy pushes the caller toward the expensive one.

The hint SHALL NOT be emitted when:

- the routing outcome is `provider_error` — already reported via the `ask_unanswered` path, and reporting it twice describes one failure as two; or
- an index was in fact delivered from any source. The wire index is fed by THREE independent sources — the LLM routing payload, DOM-mined `next_links` folded into `other_pages`, and the DOM-mined `options` shelf — so a lost routing payload frequently costs the caller nothing. The hint is gated on the DELIVERED index being empty, not on routing having been lost.

Severity SHALL be `warning`, never `critical`. `critical` is reserved for the anti-bot klaxon (`try_user_browser`); a degraded index on a successfully fetched page is not a wall, and the false-positive asymmetry runs the other way here — over-warning on a page the caller can still use is cheap, while the `critical` channel loses meaning if it fires for metadata.

This requirement SHALL NOT change `status` or `retrieval_incomplete`.

#### Scenario: Lost index with no other source emits the hint

- **WHEN** `query` runs with the body withheld, the router envelope is unrecoverable, and no `next_links` or `options` were mined
- **THEN** the response carries exactly one `warning` operator hint naming the lost index and the same-URL `fetch_raw` recovery, and `status` is unchanged

#### Scenario: Lost routing with a mined index emits no hint

- **WHEN** the router envelope is unrecoverable but DOM-mined `next_links` populated `other_pages`
- **THEN** no index-loss hint is emitted, because the caller was in fact left an index

#### Scenario: A provider error does not double-report

- **WHEN** the provider raised, so no response text existed to parse
- **THEN** no index-loss hint is emitted and the existing provider-error reporting is unchanged

#### Scenario: The hint never escalates to critical

- **WHEN** any index-loss condition holds
- **THEN** the emitted hint severity is `warning` and no `try_user_browser` hint is emitted by this condition
