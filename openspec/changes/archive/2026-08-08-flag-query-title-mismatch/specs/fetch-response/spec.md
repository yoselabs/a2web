## ADDED Requirements

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
