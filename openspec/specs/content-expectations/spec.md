# content-expectations Specification

## Purpose
TBD - created by archiving change reddit-via-zyte. Update Purpose after archive.
## Requirements
### Requirement: Oracle-driven content-readiness expectation
The system SHALL support a per-site **content expectation** that declares an authoritative expected quantity (an **oracle**) and a measured **progress** quantity, and resolves a fetched page to `ready`, `partial`, or `fail`. An expectation SHALL NOT treat a page as complete unless progress meets the oracle within a declared tolerance. Reddit is the first instance: the oracle is the thread's authoritative comment total, progress is the number of parsed comments.

#### Scenario: Complete when progress meets the oracle
- **WHEN** a page is fetched and parsed progress meets the oracle within tolerance
- **THEN** the expectation resolves `ready` and the result is returned without a partial signal

#### Scenario: No oracle means default readiness
- **WHEN** a site declares no oracle for a page shape
- **THEN** the default readiness (non-block, non-empty) applies and no partial signal is emitted

### Requirement: Honest partial signal on shortfall
When measured progress is below the oracle target (e.g. a large thread exceeds the per-fetch limit, or nested/deleted items do not render), the system SHALL emit an informational partial signal rather than silently returning the incomplete result. For Reddit this SHALL be `OperatorHint(code="comments_partial", severity="info")` naming the loaded and total counts, plus structured `comments_loaded` and `comments_total` fields on the response. This is the never-silently-miss tenet (ADR-0009) applied at content-item granularity.

#### Scenario: Deep thread returns a labeled top-N sample
- **WHEN** a thread claims 32,346 comments and 458 are loaded
- **THEN** the response carries `comments_loaded=458`, `comments_total=32346`, and a `comments_partial` info hint stating it is the top sample; it never implies all comments were retrieved

#### Scenario: Zero progress against a positive oracle fails loud
- **WHEN** the oracle indicates comments exist but zero are parsed
- **THEN** the fetch is treated as an incomplete retrieval and surfaces the never-silently-miss critical hint, not an empty "success"

### Requirement: Bounded satisfaction effort
For rungs that can act to increase progress (a browser rung scrolling or paginating), the expectation MAY drive a bounded action loop, but SHALL respect a hard time budget and return the best honest result (with the partial signal) when the budget is exhausted rather than hang.

#### Scenario: Action loop respects the time budget
- **WHEN** a browser rung is loading comments and the time budget (≤ 3 minutes) elapses before the oracle is met
- **THEN** the fetch returns the comments loaded so far with the `comments_partial` signal, and does not exceed the budget

### Requirement: The extractor receives the page's real links

The extractor SHALL be given the page's real anchor links — including chrome (nav/footer/tab) anchors that trafilatura removes as boilerplate — so it can return a real sub-resource/continuation URL rather than guess. This SHALL be satisfied by the selectolax `links[]` pass already produced by `content_extract` (flowing to `fc.links`); no shelf change is required.

> **Deferred enhancement (separate shelf EVOLVE, not this change):** enabling trafilatura `include_links=True` so *in-body* anchors additionally survive as inline `[label](url)` markdown (positional grounding). That depends on the shelf-adopted `content_extract`/`convert-md` and SHALL be enabled via a configuration passthrough or shelf contribution — never a local fork. It is additive on top of this requirement.

#### Scenario: Chrome anchor reaches the extractor

- **WHEN** a page links its reviews page only from a footer/tab anchor
- **THEN** that anchor's href is present in the link digest fed to the extractor (via the selectolax pass), even though trafilatura stripped it from the prose

### Requirement: Content concatenates prose and JSON-LD, never replaces

When both trafilatura prose and JSON-LD synthesized content are available, the content SHALL concatenate both rather than selecting one and discarding the other. This applies to the extractor input (already concatenated) and SHALL be extended to the caller-facing `content_md` so page prose is not made invisible when JSON-LD wins a display pick.

#### Scenario: Prose survives alongside JSON-LD

- **WHEN** a product page has both JSON-LD product data and body prose
- **THEN** the caller-facing content includes both, not JSON-LD alone

### Requirement: trafilatura duplicate body is de-duplicated

*(Applies only once the deferred `include_links=True` EVOLVE lands — the duplicate-body behavior was observed under `include_links`. Not a v1 concern.)* When trafilatura with `include_links=True` emits the body content more than once, the system SHALL de-duplicate the repeated block before use.

#### Scenario: Duplicated body collapsed

- **WHEN** trafilatura returns the same body block twice
- **THEN** the content used downstream contains it once

