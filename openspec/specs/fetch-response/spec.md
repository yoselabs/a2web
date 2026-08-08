# fetch-response Specification

## Purpose
TBD - created by archiving change fetch-response-diet. Update Purpose after archive.
## Requirements
### Requirement: FetchResponse omits empty optional fields from the wire

The `FetchResponse` serializer SHALL omit optional fields whose value is `None`, an empty list, an empty dict, or an empty string. The optional fields subject to omission are `title`, `byline`, `published`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, and `extracted_answer`. `FetchResponse` SHALL NOT declare `original_url`. The field `confidence` SHALL always be present; `tier` and `url` each appear only when they deviate from their default and are governed by their own requirements.

#### Scenario: null and empty optionals do not reach the wire

- **WHEN** `fetch_raw` completes successfully against a page with no byline, no metadata, no links, and no LLM extraction
- **THEN** the wire payload contains no `byline`, `published`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, `extracted_answer`, or `original_url` key

#### Scenario: confidence is always present

- **WHEN** any `fetch_raw` invocation completes
- **THEN** the wire payload contains `confidence`

#### Scenario: populated optionals are present

- **WHEN** `fetch_raw` completes against a page that yields a title and metadata
- **THEN** the wire payload contains `title` and `meta` with their non-empty contents

### Requirement: status is failure-only on FetchResponse

`FetchResponse` SHALL include `status` on the wire only when its value is not `ok` — i.e. on a `failed` or `partial` fetch. On a successful `fetch_raw`, `status` SHALL be absent; consumers SHALL interpret its absence as success.

#### Scenario: successful fetch_raw omits status

- **WHEN** `fetch_raw` completes with a successful fetch
- **THEN** the wire payload contains no `status` key

#### Scenario: failed fetch_raw carries status

- **WHEN** `fetch_raw` completes with a failed fetch
- **THEN** the wire payload contains `status` with the value `failed`

### Requirement: narrative is failure-only on FetchResponse

`FetchResponse` SHALL include `narrative` only when `status != ok`. On a successful `fetch_raw` it SHALL be absent from the wire payload.

#### Scenario: successful fetch_raw omits narrative

- **WHEN** `fetch_raw` completes successfully
- **THEN** the wire payload contains no `narrative` key

#### Scenario: failed fetch_raw carries the failure explanation

- **WHEN** `fetch_raw` completes with a failed fetch
- **THEN** the wire payload contains `narrative` describing the failure

### Requirement: timing, cache, diagnostics, tokens, and diagnostics_summary are debug-only on FetchResponse

`FetchResponse` SHALL expose all debug-tier observability through a single `debug` sub-object, not as scattered top-level keys. The `debug` object SHALL carry `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, `content_candidates`, and — only on a failed fetch — `diagnostics_summary`. The `content_candidates` entry SHALL be the list of extraction-input candidates the page produced — each rendered as `{source, content_md}` — exposing exactly the menu the server-side extractor was fed. The `debug` key SHALL appear on the wire only when `fetch_raw` (or `ask`) is called with `debug=True`; with `debug=False` it SHALL be absent. No `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, `content_candidates`, or `diagnostics_summary` key SHALL appear at the top level of the envelope. `content_candidates` SHALL remain a flat attribute on the model for internal callers; only the wire serializer regroups it under `debug`.

`diagnostics_summary` is stricter than its debug-only siblings: it SHALL be present in the `debug` object only when the fetch ALSO failed (`status != ok`) — never on a successful fetch, regardless of `debug`. It is a redundant key=value re-serialization of `narrative`'s exact same inputs (tier, verdict, gate subsystem, total_ms), built for log/grep tooling rather than an agent-facing channel; joining the debug group removes it from the default (non-debug) wire entirely (a2web-7bj.12, ADR-0019). The model attribute (`FetchResponse.diagnostics_summary`) SHALL remain always-populated for internal callers regardless of `debug` or `status` — only the wire serializer applies this gate.

#### Scenario: a failed fetch without debug omits diagnostics_summary

- **WHEN** `fetch_raw` completes with a failed fetch and `debug=False`
- **THEN** the wire payload contains no `diagnostics_summary` key, at the top level or under `debug`

#### Scenario: a failed fetch with debug carries diagnostics_summary under debug

- **WHEN** `fetch_raw` completes with a failed fetch and `debug=True`
- **THEN** the `debug` object contains `diagnostics_summary` describing the failure

#### Scenario: a successful fetch with debug still omits diagnostics_summary

- **WHEN** `fetch_raw` completes successfully and `debug=True`
- **THEN** the `debug` object contains no `diagnostics_summary` key

#### Scenario: default fetch_raw omits the debug sub-object

- **WHEN** `fetch_raw` is called with `debug=False`
- **THEN** the wire payload contains no `debug` key, and no `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, or `content_candidates` key at the top level

#### Scenario: debug fetch_raw nests the full trace under debug

- **WHEN** `fetch_raw` is called with `debug=True`
- **THEN** the wire payload contains a `debug` object carrying `started_at`, `total_ms`, `cache`, `tokens`, the `diagnostics` trace, and `content_candidates`

#### Scenario: content_candidates surfaces the extractor menu

- **WHEN** `fetch_raw` is called with `debug=True` against a page that produced multiple extraction candidates
- **THEN** the `debug.content_candidates` list carries one `{source, content_md}` entry per candidate fed to the extractor, in the menu's source order

### Requirement: links and next_links render as TSV blocks on FetchResponse

When `FetchResponse.links` or `FetchResponse.next_links` is non-empty, the serializer SHALL render it on the wire as a TSV string — a tab-separated header row followed by one tab-separated row per entry. `links` columns SHALL be `anchor`, `href`, `role`; `next_links` columns SHALL be `anchor`, `url`, `reason`, `kind`, with the `kind` column omitted when every entry's `kind` is `drilldown`. An empty `links` or `next_links` SHALL remain absent from the wire payload.

#### Scenario: populated links render as TSV

- **WHEN** `fetch_raw` is called with `include_links=True` against a page with links
- **THEN** the wire `links` is a TSV string whose header row is `anchor`, `href`, `role`, followed by one row per link

#### Scenario: next_links render as TSV

- **WHEN** `fetch_raw` completes with a non-empty `next_links` list
- **THEN** the wire `next_links` is a TSV string with a header row and one row per candidate

#### Scenario: empty link arrays stay absent

- **WHEN** `fetch_raw` completes with no links and no next-link candidates
- **THEN** the wire payload contains no `links` and no `next_links` key

### Requirement: the empty-omission serializer is shared with AskResponse

The empty-field omission and TSV-rendering logic SHALL be implemented once as a shared helper and reused by both the `AskResponse` and `FetchResponse` serializers, parameterized by each envelope's required-field set and TSV-field set. The two serializers SHALL NOT carry duplicated omission logic.

#### Scenario: both envelopes prune via the same helper

- **WHEN** the `AskResponse` and `FetchResponse` serializers run
- **THEN** both delegate empty-omission and TSV rendering to the same shared helper function

### Requirement: tier is deviation-only on FetchResponse

`FetchResponse` SHALL include `tier` on the wire only when its value is not `raw` — i.e. when the content came from a site handler, the Jina reader, the archive fallback, or the browser tier. On a plain raw HTTP fetch (`tier == "raw"`), `tier` SHALL be absent; consumers SHALL interpret its absence as a plain raw fetch.

#### Scenario: raw-tier fetch omits tier

- **WHEN** `fetch_raw` completes with the content served by the `raw` tier
- **THEN** the wire payload contains no `tier` key

#### Scenario: non-raw tier is carried

- **WHEN** `fetch_raw` completes with the content served by a site handler (e.g. `site_handler:hn`)
- **THEN** the wire payload contains `tier` with that tier identifier

### Requirement: url is redirect-only on FetchResponse

`FetchResponse` SHALL include `url` on the wire only when the fetched URL differs from the URL the caller requested — i.e. when an HTTP redirect or a captcha-host rewrite changed the destination. When the fetch landed exactly on the requested URL, `url` SHALL be absent; consumers SHALL interpret its absence as "the fetch landed on the URL I requested."

#### Scenario: no-redirect fetch omits url

- **WHEN** `fetch_raw` completes and the fetched URL equals the requested URL
- **THEN** the wire payload contains no `url` key

#### Scenario: redirected fetch carries the final url

- **WHEN** `fetch_raw` completes and the fetch was redirected or the host was rewritten
- **THEN** the wire payload contains `url` with the final fetched URL

### Requirement: a cross-domain landing caps confidence and is flagged

`FetchResponse` SHALL compare the requested URL's registrable domain against the final fetched URL's registrable domain. When they differ (a redirect or tier mixup landed on a different site than the one requested), `confidence` SHALL NOT be `high` — a `high` computed confidence SHALL be capped to `medium` — and `operator_hints` SHALL include a `served_url_differs` hint. A same-site redirect (matching registrable domain) SHALL NOT trigger the cap or the hint. The cap SHALL only ever lower confidence, never raise it.

#### Scenario: cross-domain landing caps high confidence

- **WHEN** `fetch_raw` completes on a page whose final URL's registrable domain differs from the requested URL's, with a computed confidence of `high`
- **THEN** the envelope's `confidence` is `medium` and `operator_hints` includes a `served_url_differs` entry

#### Scenario: same-site redirect is not flagged

- **WHEN** `fetch_raw` completes on a page whose final URL shares the requested URL's registrable domain (a canonicalization redirect or captcha-host rewrite back to origin)
- **THEN** `confidence` is unaffected and no `served_url_differs` hint is present

#### Scenario: the cap never raises confidence

- **WHEN** a cross-domain landing's computed confidence is already `medium` or `low`
- **THEN** `confidence` stays at that computed value — the cap only ever lowers `high`

### Requirement: A listing whose served items share no term with the query caps confidence and is flagged

`FetchResponse` SHALL compare the caller's `ask` (query) against the titles of
the items a listing page actually served (`record_set.records[].heading_text`),
scoped to fetches where routing classified the page `structural_form: listing`
AND at least one item record was parsed. The comparison SHALL strip a small,
fixed, English-only set of operator words (price, stock, review, vs, compare,
best, etc.) from the query before comparing; if nothing remains after
stripping, the check SHALL NOT run (no signal, not a flag). Otherwise, when
NONE of the served item titles share a normalized token with the remaining
query terms, `confidence` SHALL NOT be `high` — a `high` computed confidence
SHALL be capped to `medium` — and `operator_hints` SHALL include a
`query_title_mismatch` hint. When at least one served item title shares a
token with the query, the check SHALL NOT trigger. This check is independent
of, and may fire alongside, the cross-domain-landing check; the cap SHALL
only ever lower confidence, never raise it, and SHALL NOT apply twice (a
response already capped to `medium` or lower by another check stays there).

#### Scenario: Zero-overlap listing caps high confidence

- **WHEN** `query` fetches a page classified as a `listing`, the query is `"pindstrup"`, and every parsed item title shares no normalized token with it (e.g. all titled "Gölgelik File", "Kalsiyum Nitrat")
- **THEN** the envelope's `confidence` is `medium` (down from a computed `high`) and `operator_hints` includes a `query_title_mismatch` entry

#### Scenario: Any overlapping item is not flagged

- **WHEN** `query` fetches a listing whose query is `"RTX 4090"` and at least one parsed item title contains "RTX 4090" or "RTX" and "4090" as normalized tokens, even if other items in the same listing don't
- **THEN** `confidence` is unaffected and no `query_title_mismatch` hint is present

#### Scenario: A non-listing fetch is not checked

- **WHEN** `query` fetches a page routing classified as `product` or `article` (not `listing`), regardless of query/title overlap
- **THEN** the check does not run — no `query_title_mismatch` hint, `confidence` unaffected by this check

#### Scenario: A query with no substantive terms is skipped, not flagged

- **WHEN** `query` fetches a listing with the query `"price, stock"` (both terms are in the operator-word set, nothing remains after stripping)
- **THEN** the check does not run — no `query_title_mismatch` hint, `confidence` unaffected by this check

#### Scenario: The cap never raises confidence and does not double-apply

- **WHEN** a zero-overlap listing's computed confidence is already `medium` or `low`, or has already been capped to `medium` by the cross-domain-landing check
- **THEN** `confidence` stays at that value — this check only ever lowers a `high`, and never re-lowers an already-capped value further

### Requirement: A failed browser rung caps confidence

`FetchResponse` SHALL check whether `operator_hints` carries evidence that a browser rung was dispatched on this fetch and failed to run (`browser_internal_error` or `browser_unavailable`). When present, `confidence` SHALL NOT be `high` — a `high` computed confidence SHALL be capped to `medium`, following the same downgrade-only precedent as the cross-domain-landing cap. No new hint is added; the browser-failure hint already on `operator_hints` is the explanation. A fetch whose content was retrieved WITHOUT any browser rung failing SHALL be unaffected (a2web-7bj.7 — a DHL tracking answer shipped `confidence: high` on the negative claim "this page does not provide the current status" in the same envelope as `browser_internal_error` AND `browser_unavailable`; the page may well have had the status behind the render that failed, so a confident absence claim next to a failed retrieval rung is a silent miss wearing a different hat).

#### Scenario: A failed browser rung caps high confidence to medium

- **WHEN** a fetch's `operator_hints` carries a `browser_internal_error` or `browser_unavailable` hint and computed confidence is `high`
- **THEN** the envelope's `confidence` is `medium`

#### Scenario: No browser-rung failure leaves confidence unaffected

- **WHEN** a fetch's `operator_hints` carries no `browser_internal_error` or `browser_unavailable` hint
- **THEN** confidence is the plain `_confidence_for` computation, uncapped by this rule

#### Scenario: The cap never raises confidence

- **WHEN** a failed browser rung's fetch already computed `medium` or `low` confidence
- **THEN** confidence stays at that computed value

### Requirement: retrieval_incomplete envelope field
`FetchResponse` (and the projected `AskResponse`) SHALL carry a `retrieval_incomplete` boolean that is true when the requested URL's content was not retrieved due to a wall. The field SHALL be present on the wire whenever true and MAY be omitted when false (absence means retrieval was complete).

#### Scenario: Field present on walled fetch
- **WHEN** a fetch is walled
- **THEN** the serialized envelope includes `retrieval_incomplete: true`

#### Scenario: Field absent on success
- **WHEN** a fetch succeeds
- **THEN** the envelope omits `retrieval_incomplete` (or sets it false)

### Requirement: OperatorHint severity
`OperatorHint` SHALL gain a `severity` field (at least `info` and `critical`). A `try_user_browser` hint SHALL be `critical`. Existing hints without an explicit severity default to `info` (backward-compatible).

#### Scenario: Browser hint is critical
- **WHEN** a `try_user_browser` hint is emitted
- **THEN** its `severity` is `critical`

#### Scenario: Existing hints stay info
- **WHEN** a pre-existing hint (e.g. `cookies_stale`) is emitted without an explicit severity
- **THEN** its severity defaults to `info` and existing behavior is unchanged

### Requirement: Fetch envelope carries listing item counts

The `FetchResponse` envelope (returned by `fetch_raw`) SHALL carry optional
`items_loaded` and `items_total` fields and a `listing_partial` operator hint on
a partial listing, on the same terms as the `ask` envelope, pruned from the wire
when absent. Because `fetch_raw` runs no LLM and drives no render escalation, the
signal is diagnostic-only on this path — the counts and hint surface, but no
scroll-to-complete is attempted.

#### Scenario: fetch_raw surfaces the partial signal without scrolling

- **WHEN** a `fetch_raw` over a listing parses 31 records against an oracle of 40
- **THEN** the response carries `items_loaded: 31`, `items_total: 40`, and a `listing_partial` info hint, and no scrolling render is attempted

### Requirement: An unavailable resource is not reported as a defect

A failure caused by an unconfigured or unavailable resource — a missing
credential, a disabled provider, an absent optional dependency — SHALL be
reported with a kind that distinguishes it from an internal defect.

Where a typed error taxonomy is adopted but no failure is raised into it, the
taxonomy's dispatch branch is dead and every failure falls through to the
catch-all. A missing credential and a null dereference then render identically as
an internal error. The operator whose configuration is incomplete is told the
software is broken, and cannot act on the message.

A taxonomy's declared kinds SHALL be reachable. A label that no code path can
produce is documentation of an intent, not a behaviour.

#### Scenario: A missing credential reports as unavailable

- **WHEN** a tool fails because a required credential is unconfigured
- **THEN** the error envelope reports an unavailable-resource kind, not an
  internal defect

#### Scenario: Declared kinds are reachable

- **WHEN** the error taxonomy declares a set of kinds
- **THEN** each kind is produced by at least one code path

### Requirement: Emptiness has one definition

The predicate deciding whether a field is empty for wire purposes SHALL have one
implementation.

Several omit-empty implementations in one module — an inline predicate, an
inherited base-class predicate, and an unused adopted helper — are three answers
to one question that nothing compares. Whether a field reaches the caller then
depends on which path serialized it.

#### Scenario: One predicate decides omission

- **WHEN** a field is considered for omission from the wire
- **THEN** a single predicate decides it, regardless of the serialization path
