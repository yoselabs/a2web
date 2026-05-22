# link-discovery Specification

## Purpose

A curated, ranked set of "links worth following next" returned alongside the answer, so a research agent can act on intent rather than scanning a flat `links` dump and guessing from anchor text. Owns the `NextLink` model, the response-envelope contract, the `next_links` tool parameter, the Tier 2 LLM-curation extension of the `ask=` extraction call, and the Tier 1 + Tier 2 composition rule. Handler-specific candidate population is owned by `site-handlers`.

## Requirements

### Requirement: NextLink model

The system SHALL define a `NextLink` pydantic model at module scope in `src/a2web/models.py` with exactly four fields:

- `anchor: str` — visible link text, ≤120 characters
- `url: str` — absolute URL (no aliasing)
- `reason: str` — one phrase, ≤80 characters, explaining why the link matters for the current fetch
- `kind: Literal["drilldown", "related", "source"]`

The model SHALL be importable as `from a2web.models import NextLink`. Both `anchor` and `reason` SHALL be validated against their character caps via pydantic `Field(max_length=...)`; values exceeding the cap SHALL be truncated (not rejected) so a misbehaving provider response does not fail the whole fetch.

#### Scenario: Module-scope import

- **WHEN** `from a2web.models import NextLink` is executed
- **THEN** the import succeeds and `NextLink(anchor="x", url="https://e.com", reason="y", kind="drilldown")` constructs without error

#### Scenario: Over-cap anchor truncates

- **WHEN** `NextLink(anchor="x" * 200, url="https://e.com", reason="y", kind="drilldown")` is constructed
- **THEN** the resulting `anchor` has length ≤120 (truncated, not raised)

#### Scenario: Invalid kind rejects

- **WHEN** `NextLink(anchor="x", url="https://e.com", reason="y", kind="other")` is constructed
- **THEN** pydantic raises `ValidationError`

### Requirement: FetchResponse exposes next_links

The system SHALL add an optional `next_links: list[NextLink]` field to `FetchResponse` with default `[]`. The field SHALL serialize to JSON as an empty list when no candidates apply (never `null`, never omitted). The list SHALL be capped at 10 entries — any source producing more SHALL be trimmed to the top 10 (preserving order).

#### Scenario: Default empty list on terminal fetch

- **WHEN** a fetch returns from an arbitrary page without `ask=` set
- **THEN** the response has `next_links == []` (empty list, not `None`)

#### Scenario: Cap enforced at 10

- **WHEN** a handler or LLM provider supplies 15 candidates
- **THEN** the wire response contains exactly 10 entries, preserving the original order's top 10

### Requirement: next_links tool parameter

The `fetch` MCP tool SHALL accept a `next_links: bool = True` parameter via `Annotated[bool, pydantic.Field(description=...)]`. When `True`, the response SHALL populate `next_links` per the rules in the other requirements of this capability. When `False`, the response SHALL force `next_links == []` regardless of what handlers or the LLM produced.

#### Scenario: Default True populates candidates

- **WHEN** the agent calls `fetch(url=<reddit listing>)` without passing `next_links`
- **THEN** the response contains Tier 1 candidates from the Reddit handler

#### Scenario: Explicit False suppresses candidates

- **WHEN** the agent calls `fetch(url=<reddit listing>, next_links=False)`
- **THEN** the response has `next_links == []` even though the Reddit handler produced candidates internally

### Requirement: Tier 2 LLM curation extends the ask= extraction call

When `ask=` is set on a fetch AND the page has no handler-supplied candidates, the system SHALL extend the existing `ask=` LLM extraction prompt with instructions to return up to 10 `next_links` selected from inline markdown links present in the page content. The Tier 2 candidates SHALL be returned in the SAME provider call as `answer` — no second LLM round-trip.

The provider response schema SHALL gain an optional `next_links: list[NextLink]` field; absence of the field SHALL be interpreted as an empty list. Every returned `url` SHALL be validated to appear in the markdown the LLM was given; URLs that fail this validation SHALL be dropped with a `Diagnostic(verdict=extraction_drift, ...)` appended to the response's diagnostics chain.

#### Scenario: Single LLM call produces both fields

- **WHEN** `fetch(url=<arbitrary blog post>, ask="what GPUs are mentioned?")` is called
- **THEN** exactly one LLM provider call is issued and the response contains both `answer` and `next_links` populated from that call

#### Scenario: URL not present in markdown is dropped

- **WHEN** the LLM returns a `next_links[i].url` that does not appear in the markdown content the LLM received
- **THEN** that candidate is dropped from the response and a `Diagnostic` with `verdict=extraction_drift` and a message naming the offending URL is appended to `diagnostics`

#### Scenario: ask= absent on arbitrary page yields empty list

- **WHEN** `fetch(url=<arbitrary blog post>)` is called without `ask=`
- **THEN** the response has `next_links == []` (no signal — no question, no handler structure)

### Requirement: Tier 1 + Tier 2 composition — LLM re-ranks handler candidates against the question

When both a handler produced `TierResult.next_links` AND the user passed `ask=`, the system SHALL pass the handler's candidate list into the `ask=` extraction prompt as a system message and instruct the LLM to re-rank, filter, and rewrite each `reason` against the user's question. The LLM's returned list SHALL REPLACE (not union with) the handler's list. The LLM MAY drop handler-supplied candidates that don't match the question; the LLM MAY add candidates from the markdown if the handler missed an obvious one (subject to the URL-must-appear-in-markdown validation from the Tier 2 requirement).

#### Scenario: Reddit listing + ask= re-ranks by question relevance

- **WHEN** `fetch(url=<r/LocalLLaMA listing>, ask="find posts about RTX 5090 inference benchmarks")` is called and the handler supplies 10 permalinks ordered by score
- **THEN** the final `next_links` is the LLM-returned list (which may be ordered differently than score), and each entry's `reason` mentions question-relevance (e.g. "5090 benchmark thread, 412 comments") rather than only score

#### Scenario: Handler candidates pass through unchanged when ask= absent

- **WHEN** `fetch(url=<r/LocalLLaMA listing>)` is called without `ask=`
- **THEN** the response's `next_links` is exactly the handler's list (no LLM call, no re-ranking)

### Requirement: link-discovery does not import from packages

The `link-discovery` capability SHALL be implemented entirely under `src/a2web/` domain modules (`models.py`, `fetcher.py`, `routers.py`, and the LLM extractor's existing wiring at `llm_resource.py`). It SHALL NOT introduce any new imports from `src/a2web/packages/` into domain modules beyond those already present, and SHALL NOT introduce any imports from `src/a2web/<domain>` into `src/a2web/packages/`. The `test_packages_independence` invariant SHALL remain green.

#### Scenario: Independence test stays green

- **WHEN** the `test_packages_independence` invariant runs after the change is merged
- **THEN** the test passes (no `packages/` module imports anything under `a2web.<domain>`)
