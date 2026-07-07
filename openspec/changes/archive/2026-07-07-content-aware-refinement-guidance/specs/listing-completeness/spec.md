## ADDED Requirements

### Requirement: LLM-side partialness detection supplements the regex oracle

On the `ask` path, partialness detection SHALL NOT be gated solely on the regex item-count
oracle. Because the anchored visible-count nouns cover only a subset of languages (a page in a
language outside the noun list yields no numeric oracle), the extractor SHALL additionally judge
partialness from the content it holds — a repeated item structure together with a visible total
it can read even when the regex noun list cannot match it. A listing SHALL be treated as partial
when *either* the regex oracle *or* the LLM-side judgment indicates a shortfall. The regex oracle
remains the deterministic fast-path and its authority is unchanged; the LLM-side path is a
superset that only ever adds a partial signal, never suppresses an existing one. This closes the
language-coverage gap for a tool distributed across regions.

#### Scenario: Non-covered-language total is caught LLM-side

- **WHEN** an `ask` fetch parses a repeated record set from a page whose visible total uses a noun outside the regex list (e.g. a Russian `товаров` or Japanese `件` count), so the regex oracle yields `None`
- **THEN** the extractor's LLM-side judgment flags the listing partial and the honest partial signal is emitted with the counts it could read

#### Scenario: Regex fast-path still fires on its own

- **WHEN** the regex oracle extracts a numeric total that exceeds the parsed record count
- **THEN** the listing is flagged partial without requiring the LLM-side judgment

#### Scenario: LLM-side detection never suppresses an existing signal

- **WHEN** the regex oracle indicates a complete listing but the LLM-side path is uncertain
- **THEN** the regex oracle's completeness verdict stands — the LLM-side path can only add a partial signal, not remove one
