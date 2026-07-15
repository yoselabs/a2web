## MODIFIED Requirements

### Requirement: thin_content is attached on a thin_unverified failure

`AskResponse` SHALL carry a conditional `thin_content: str | None` field, populated when the fetch terminates on the `thin_unverified` OR `empty_unverified` outcome (a retrieved HTTP 200 that rendered thin with no hard-wall evidence), AND when a corroborated empty is promoted to `ok` (see "Corroborated empty answer is synthetic and honest"). It holds the retrieved sub-floor body verbatim (wrapped per the existing untrusted-content rule). It SHALL be absent from the wire on every other outcome (omit-empty), and its presence SHALL NOT depend on `include_content` — the index-rule (ADR-0015) forces the body onto the wire on these outcomes even though `query` withholds content by default. The attached body is wire-only and never enters the cache.

#### Scenario: thin_unverified failure attaches the body

- **WHEN** a `query` fetch terminates on `thin_unverified` (an ambiguous thin 200)
- **THEN** the wire payload contains `thin_content` with the retrieved sub-floor body and a `content_thin` warning hint, without requiring `include_content=True`

#### Scenario: empty_unverified failure attaches the body

- **WHEN** a `query` fetch terminates on `empty_unverified` (a thin 200 with an empty-result marker but incomplete corroboration)
- **THEN** the wire payload contains `thin_content` with the retrieved body and a `content_thin` warning hint

#### Scenario: promoted-ok empty attaches the body

- **WHEN** a `query` fetch is promoted to `ok` as a corroborated empty
- **THEN** the wire payload contains `thin_content` with the retrieved body alongside the synthetic answer

#### Scenario: thin_content is absent on success and on other failures

- **WHEN** a `query` fetch ends `ok` with real content, or fails on `wall`/`gone_confirmed`
- **THEN** the wire payload contains no `thin_content` key

## ADDED Requirements

### Requirement: Corroborated empty answer is synthetic and honest

When a fetch is promoted to `ok` as a corroborated empty (`is_confirmed_empty` held), the `query` `AskResponse` SHALL carry a synthetic `answer` stating that the page reports no results for the request (never fabricated result content), at `confidence: low`, with a `content_empty` operator hint at `severity: info` and the retrieved body attached as `thin_content`. The response SHALL NOT set `retrieval_incomplete` and SHALL NOT carry `try_user_browser`. The answer's honesty is bounded: it asserts only "the page shows no results", disclosing that this is a distilled reading of a thin page the caller can verify via the attached body.

#### Scenario: A promoted empty answers "no results" at low confidence

- **WHEN** a search-shaped `query` is promoted to `ok` as a corroborated empty
- **THEN** `answer` states the page reports no results, `confidence == low`, a `content_empty` info hint is present, `thin_content` carries the body, and `retrieval_incomplete` is absent

#### Scenario: A promoted empty never fabricates results

- **WHEN** a corroborated empty is promoted
- **THEN** the `answer` does NOT invent items, counts, or listing options — it only reports the absence
