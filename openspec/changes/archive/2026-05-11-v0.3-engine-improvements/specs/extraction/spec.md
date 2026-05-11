# extraction (delta)

## MODIFIED Requirements

### Requirement: fit_md is None when no pruning filter ran

`FetchResponse.fit_md` SHALL be `None` when the response did not pass through a populated pruning filter. The current behavior of populating `fit_md` as a byte-for-byte copy of `content_md` SHALL be removed.

The field stays on the model as `fit_md: str | None = None` for forward-compatibility with a future pruning-filter implementation (per CLAUDE.md "Architecture" note). What changes is the *population behavior* of the orchestrator, not the schema.

#### Scenario: ok fetch with no pruning filter returns fit_md=None

- **WHEN** a fetch completes via raw / jina / handler / browser tier without any pruning-filter phase
- **THEN** `FetchResponse.fit_md is None`
- **AND** `FetchResponse.content_md` carries the extracted markdown as today

#### Scenario: failed fetch with empty content returns fit_md=None

- **WHEN** a fetch fails (e.g. `length_floor`, `blockpagedetected`) and `content_md == ""`
- **THEN** `FetchResponse.fit_md is None` (NOT `""`, NOT a copy)
