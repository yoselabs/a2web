## ADDED Requirements

### Requirement: Router extraction prompt instructs token-efficient, fact-lossless framing

`EXTRACT_ROUTER_V1.system` SHALL include an explicit instruction directing the model to frame its `answer` tersely — minimizing filler prose and hedging language — while never omitting a factual value, identifier, name, number, or unit present in the source content. The instruction SHALL direct a preference for ASCII punctuation (straight quotes, hyphens, `...`) over Unicode look-alikes (curly quotes, em dashes, ellipsis character) in the model's own prose framing, where meaning is unaffected; this preference SHALL NOT apply to verbatim quoted material, which remains governed by the existing 125-character quote rule. This instruction SHALL be added to `system`, not to `cache_prefix_template` or the `{content}`-bearing portion of any template, preserving the v0.19 byte-stable cache-prefix invariant.

#### Scenario: Terseness instruction present without touching the cache prefix

- **WHEN** `EXTRACT_ROUTER_V1.render(content, ask)` is called
- **THEN** the resulting `cache_prefix` is byte-identical to `EXTRACT_CACHEABLE_V1.render(content, ask).cache_prefix`, and the `system` text contains the token-efficiency instruction

#### Scenario: Terse framing does not drop a cited number

- **WHEN** the extractor answers a question whose source content contains a specific figure (e.g. a version number, a count, a price)
- **THEN** the answer preserves that figure verbatim, even when the surrounding prose is compressed

### Requirement: Router extraction prompt instructs partial-signal honesty

`EXTRACT_ROUTER_V1.system` SHALL include an explicit instruction directing the model: when the fetched content mentions the topic asked about but lacks the specific level of detail requested, the `answer` SHALL report what IS present (e.g. "the page lists X as a category but gives no further detail") rather than asserting the page does not address the topic at all. This instruction supersedes any implicit binary answer/no-answer framing for the router template; `TERSE_V1`'s existing binary framing is unaffected (it is a separate, non-router template).

#### Scenario: Partial signal is reported, not denied

- **WHEN** the extractor is asked a detailed question about a topic that the source content mentions only in passing (e.g. named as one item in a list, with no elaboration)
- **THEN** the `answer` states what the content does say about the topic, and does not claim the content "does not address" the topic

#### Scenario: Genuinely absent topic is still reported as absent

- **WHEN** the extractor is asked about a topic entirely absent from the source content
- **THEN** the `answer` states the content does not address the topic — this scenario is unaffected by the partial-signal instruction, which only changes behavior when partial signal genuinely exists
