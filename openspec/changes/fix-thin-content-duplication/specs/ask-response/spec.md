## MODIFIED Requirements

### Requirement: thin_content is attached on a thin_unverified failure

`AskResponse` SHALL carry a conditional `thin_content: str | None` field, populated when the fetch terminates on the `thin_unverified` OR `empty_unverified` outcome (a retrieved HTTP 200 that rendered thin with no hard-wall evidence), AND when a corroborated empty is promoted to `ok` (see "Corroborated empty answer is synthetic and honest"). It holds the retrieved sub-floor body verbatim (wrapped per the existing untrusted-content rule). It SHALL be absent from the wire on every other outcome (omit-empty). `thin_content` is a **fallback**, not an independent guarantee: it SHALL be populated only when `content_md` is absent from the wire for the same response (i.e. `include_content=False`, the default). When the caller passed `include_content=True`, `content_md` already carries the identical body, so `thin_content` SHALL be omitted regardless of the `thin_unverified` / `empty_unverified` / promoted-empty outcome. The attached body is wire-only and never enters the cache.

#### Scenario: thin_unverified failure attaches the body when content is withheld

- **WHEN** a `query` fetch terminates on `thin_unverified` (an ambiguous thin 200) and `include_content` is `False` (the default)
- **THEN** the wire payload contains `thin_content` with the retrieved sub-floor body and a `content_thin` warning hint, without requiring `include_content=True`

#### Scenario: empty_unverified failure attaches the body when content is withheld

- **WHEN** a `query` fetch terminates on `empty_unverified` (a thin 200 with an empty-result marker but incomplete corroboration) and `include_content` is `False`
- **THEN** the wire payload contains `thin_content` with the retrieved body and a `content_thin` warning hint

#### Scenario: promoted-ok empty attaches the body when content is withheld

- **WHEN** a `query` fetch is promoted to `ok` as a corroborated empty and `include_content` is `False`
- **THEN** the wire payload contains `thin_content` with the retrieved body alongside the synthetic answer

#### Scenario: thin_content is omitted when content_md already carries the body

- **WHEN** a `query` fetch terminates on `thin_unverified`, `empty_unverified`, or a promoted-empty `ok` outcome, and the caller passed `include_content=True`
- **THEN** the wire payload contains `content_md` with the body and no `thin_content` key — the body appears exactly once

#### Scenario: thin_content is absent on success and on other failures

- **WHEN** a `query` fetch ends `ok` with real content, or fails on `wall`/`gone_confirmed`
- **THEN** the wire payload contains no `thin_content` key

### Requirement: Corroborated empty answer is synthetic and honest

When a fetch is promoted to `ok` as a corroborated empty (`is_confirmed_empty` held), the `query` `AskResponse` SHALL carry a synthetic `answer` stating that the page reports no results for the request (never fabricated result content), at `confidence: low`, with a `content_empty` operator hint at `severity: info`, and the retrieved body attached as `thin_content` when `content_md` is not already on the wire (per "thin_content is attached on a thin_unverified failure"). The response SHALL NOT set `retrieval_incomplete` and SHALL NOT carry `try_user_browser`. The answer's honesty is bounded: it asserts only "the page shows no results", disclosing that this is a distilled reading of a thin page the caller can verify via the attached body (`thin_content` when withheld, `content_md` directly when opted in).

#### Scenario: A promoted empty answers "no results" at low confidence

- **WHEN** a search-shaped `query` is promoted to `ok` as a corroborated empty with `include_content=False`
- **THEN** `answer` states the page reports no results, `confidence == low`, a `content_empty` info hint is present, `thin_content` carries the body, and `retrieval_incomplete` is absent

#### Scenario: A promoted empty with include_content=True carries the body once

- **WHEN** a search-shaped `query` is promoted to `ok` as a corroborated empty with `include_content=True`
- **THEN** `answer` states the page reports no results, `confidence == low`, a `content_empty` info hint is present, `content_md` carries the body, and no `thin_content` key is present

#### Scenario: A promoted empty never fabricates results

- **WHEN** a corroborated empty is promoted
- **THEN** the `answer` does NOT invent items, counts, or listing options — it only reports the absence
