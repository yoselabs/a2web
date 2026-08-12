# interaction-gated-sections

## ADDED Requirements

### Requirement: A page section withheld behind an in-page interaction SHALL be reported as unretrieved, never as absent at source

When the fetched page's own content asserts that a section exists — a tab
label, a disclosure control, or a section heading — and that section's body was
not retrieved because it loads only after an in-page interaction a2web cannot
perform, a2web SHALL NOT report the section's content as absent from the source.
The envelope SHALL state that the section was not retrieved and SHALL instruct
the caller to treat its content as unknown.

Where the page states a count for the section, that source-stated count SHALL be
relayed verbatim and SHALL NOT be reinterpreted, rounded, or replaced by a count
a2web derived itself.

#### Scenario: A gated section the query targets is reported as unretrieved

- **GIVEN** a page carrying a section whose body loads only after an in-page interaction, with no separate URL for that section
- **WHEN** `query` is called with a question that section would answer
- **THEN** the `answer` states that the section was not retrieved and that its content is unknown rather than absent
- **AND** `operator_hints` includes an `interaction_required` entry naming the section

#### Scenario: A source-stated count is relayed, not discarded

- **GIVEN** a gated section whose page text states a count of entries
- **WHEN** the gate blocks the answer to the caller's question
- **THEN** the `interaction_required` hint relays that source-stated count
- **AND** the `answer` does not claim the section holds zero entries

#### Scenario: An absence claim contradicting the page is never emitted

- **GIVEN** a page whose content asserts a section exists and holds at least one entry
- **WHEN** that section's body was not retrieved
- **THEN** the envelope does not assert that the source has no such content

### Requirement: The `interaction_required` hint SHALL state that no alternative URL exists and that re-querying is futile

The hint SHALL name the gated section using the label as it appears on the page,
SHALL state that the section has no separate URL, SHALL state that re-querying
the same URL returns the same result, and SHALL direct the caller to open the
URL in a real-browser tool and expand the section, or to report the gap to the
user. Its `severity` SHALL be `warning`.

The hint SHALL NOT be `section_unretrieved`: that code's remediation advises
retrying and setting a credential, which is false guidance for a gate no retry
passes.

#### Scenario: The hint forecloses the futile retry

- **WHEN** an `interaction_required` hint is emitted
- **THEN** its message states that re-querying the same URL will return the same result
- **AND** its `fix` names opening the URL in a real-browser tool and expanding the section, or reporting the gap to the user
- **AND** its `severity` is `warning`

#### Scenario: A gated section does not borrow the retry-and-credential remediation

- **WHEN** a section is withheld behind an in-page interaction
- **THEN** `operator_hints` does not include a `section_unretrieved` entry for that section

### Requirement: A gate that does not block the caller's question SHALL be silent

Detection SHALL NOT by itself produce a hint or alter `confidence`. A gated
section reports only when it withholds content the caller's question needs. On a
page carrying gated sections irrelevant to the question asked, the envelope SHALL
be indistinguishable from one produced for a page with no gated sections at all.

#### Scenario: An irrelevant gate produces no signal

- **GIVEN** a page carrying a gated Q&A section
- **WHEN** `query` is called with a question the retrieved body fully answers
- **THEN** `operator_hints` contains no `interaction_required` entry
- **AND** `confidence` is unaffected by the presence of the gate

### Requirement: A section reachable at its own URL SHALL be surfaced as a link, not as a gate

When the withheld content is reachable at a distinct URL present among the
page's links, a2web SHALL surface that link through the existing link-affordance
mechanism and SHALL NOT emit `interaction_required`. a2web SHALL NOT fetch that
URL of its own accord in place of the requested one, and SHALL NOT construct a
URL for a gated section by pattern.

#### Scenario: A linked section takes the link path

- **GIVEN** a page whose withheld section is reachable at a distinct URL present among the page's links
- **WHEN** the caller's question targets that section
- **THEN** the response surfaces that link as a drilldown affordance
- **AND** `operator_hints` contains no `interaction_required` entry

#### Scenario: No URL is invented for a gated section

- **GIVEN** a gated section with no corresponding link on the page
- **WHEN** an `interaction_required` hint is emitted
- **THEN** no URL for that section appears anywhere in the response

### Requirement: Gate detection SHALL read the retrieved markup and SHALL declare its coverage limit

Detection SHALL operate on the retrieved page markup rather than on the
converted markdown body, because markdown conversion removes the structural
attributes that distinguish a collapsed section from ordinary text.

On a tier whose retrieved body is already markdown and carries no markup, a2web
SHALL NOT claim a gate it cannot evidence; reduced recall on those tiers is
accepted rather than compensated by a looser textual heuristic.

#### Scenario: Detection survives markdown conversion loss

- **GIVEN** a page whose gated tab strip is removed by markdown conversion
- **WHEN** the tier retained the page markup
- **THEN** the gate is still detected

#### Scenario: A markdown-only tier does not manufacture a gate

- **GIVEN** a tier whose retrieved body is markdown with no markup retained
- **WHEN** no gate can be evidenced from that body
- **THEN** no `interaction_required` hint is emitted

### Requirement: Gate relevance SHALL be judged from grounded candidates, never invented

The set of gates a2web may report SHALL be limited to gates detected on the
fetched page. Any component selecting which gate blocks the answer SHALL choose
from that detected set and SHALL NOT introduce a section label absent from it.
Relevance SHALL NOT be decided by term overlap between the question and the
label, which fails when the page and the question are in different languages.

#### Scenario: A cross-language gate is matched to the question

- **GIVEN** a page whose gated section label is in a different language from the caller's question
- **WHEN** the question targets that section
- **THEN** the gate is reported

#### Scenario: No gate label is reported that was not detected on the page

- **WHEN** an `interaction_required` hint names a section
- **THEN** that section label was detected on the fetched page
