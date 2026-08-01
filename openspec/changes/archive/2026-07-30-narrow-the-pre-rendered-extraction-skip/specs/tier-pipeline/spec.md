## MODIFIED Requirements

### Requirement: Pre-rendered handler results bypass extraction

The orchestrator SHALL check `tier_result.pre_rendered` for a `Rendered`
payload. When present, the orchestrator SHALL use its `content_md`, `title`,
`byline`, `headings`, and `links` directly and SHALL NOT invoke
`extract_markdown`, `find_published`/`find_updated`, or `parse_metadata`.

**The bypass is scoped to content extraction and metadata parsing only.** It
SHALL NOT extend to the structured-extraction ladder or to the
listing-completeness check, which are different parsers over the same bytes and
which a tier that produced markdown has not already performed. A pre-rendered
result SHALL reach both.

The quality gate SHALL still run on the rendered markdown; the cache write
proceeds with the original `body`.

> The prior wording named `tier_result.tier_extras["pre_rendered"]`, a
> `dict[str, Any]` bag removed when `TierResult` became typed, and asserted a
> bypass with no stated scope. Both are corrected here: the field is the typed
> one, and the boundary is explicit. The unstated scope is not a documentation
> defect — it is how the ladder, the digest gate, the listing sufficiency check
> and the option shelf all came to be unreachable on every pre-rendering tier
> without any requirement being violated.

#### Scenario: Pre-rendered result skips trafilatura

- **WHEN** a tier returns a `TierResult` carrying a `Rendered` pre-rendered payload
- **THEN** the resulting `FetchResponse.content_md` equals the pre-rendered value
- **AND** the diagnostics list contains no `extract` row

#### Scenario: Pre-rendered result does NOT skip the structured ladder

- **WHEN** a tier returns a pre-rendered payload and the retrieved body is HTML
  carrying a detectable record region
- **THEN** the structured-extraction ladder runs over that body and contributes
  its candidate to `fc.content_candidates`
- **AND** the diagnostics list still contains no `extract` row

#### Scenario: Gate still runs on pre-rendered markdown

- **WHEN** the pre-rendered `content_md` is shorter than the length floor (<500 chars)
- **THEN** the gate emits `Verdict.length_floor` and the orchestrator marks the response as failed
