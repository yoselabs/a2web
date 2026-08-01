## ADDED Requirements

### Requirement: Ladder entry is a property of holding HTML, not of which tier won

Entry to the multi-source extraction escalation ladder SHALL depend only on the
fetch having retrieved a body, never on which tier retrieved it. Every retrieval
path — the raw tier, the browser, archive, the paid tiers, and every site
handler — SHALL reach the ladder. A path that installs pre-rendered markdown
SHALL skip the trafilatura content pass and still enter the ladder.

The existing "Multi-source extraction escalation ladder" requirement states that
the ladder runs **unconditionally**, with each rung self-gating on its own
preconditions. That is a statement about recall triggers and remains true of
them. It never said which retrieval paths reach the ladder at all, and for the
whole pre-rendered population none did — a gap that violated no requirement
because no requirement covered it. This requirement covers it.

A non-HTML body — a markdown reader's output, a JSON API payload — SHALL be
handled by the rungs' own preconditions producing no output, NOT by a
content-type gate outside the ladder. Duplicating that judgement outside the
rung is how the outer copy drifts out of agreement with the inner one.

#### Scenario: Browser-served listing reaches record extraction

- **WHEN** a listing page is retrieved by the browser tier, which installs
  pre-rendered markdown, and the rendered DOM carries a detectable record region
- **THEN** the ladder runs over that DOM and the `record_synth` rung contributes
  a candidate
- **AND** `fc.content_candidates` also carries the baseline candidate seeded from
  the pre-rendered markdown

#### Scenario: Client-rendered listing is structurally parsed for the first time

- **WHEN** a listing renders its items only after JavaScript execution, forcing a
  browser fetch
- **THEN** record detection runs over the post-JavaScript DOM
- **AND** the records it finds are the ones the raw tier could never have seen

#### Scenario: Non-HTML pre-rendered body self-gates to no output

- **WHEN** a tier installs pre-rendered markdown and its retrieved body is a JSON
  API payload or a markdown reader's output
- **THEN** the ladder still runs, both structured rungs produce no output, and
  `fc.content_candidates` carries only the baseline candidate
- **AND** no content-type precondition outside the rungs is consulted

#### Scenario: The trafilatura pass stays skipped

- **WHEN** the ladder runs on a pre-rendered path
- **THEN** `extract_markdown` and `parse_metadata` are still not invoked, and the
  baseline candidate is seeded from the pre-rendered markdown rather than
  re-derived
