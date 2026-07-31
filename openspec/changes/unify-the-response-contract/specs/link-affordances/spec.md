## ADDED Requirements

### Requirement: A link's kind is the kind its producer assigned

Where a producer classifies a link — a handler marking an entry as a drilldown, a
related page, or a discussion — that classification SHALL be carried to the wire.
A projection SHALL NOT relabel it to a fixed value.

Relabelling every entry to a single kind asserts something false about most of
them. A value meaning "deterministic continuation — pagination, page-order" is
wrong for a post drilldown, and it is wrong for every row a handler produced,
because no handler produces a continuation-shaped link at all.

Where the target vocabulary cannot express a producer's classification, the
vocabulary SHALL be extended or the projection SHALL carry the producer's value —
it SHALL NOT substitute the nearest available label.

A producer-supplied anchor label SHALL be carried rather than discarded. Anchor
text is attacker-controlled and SHALL be treated as untrusted, which is a reason
to mark it, not a reason to drop it.

#### Scenario: A handler-classified link keeps its kind

- **WHEN** a handler emits a link classified as a drilldown
- **THEN** the wire reports it as a drilldown

#### Scenario: The anchor survives the projection

- **WHEN** a producer supplies an anchor label for a link
- **THEN** the label is present on the wire

### Requirement: Producer-supplied candidates are not discarded unseen

Where the projection prefers a model-supplied link list over a producer-supplied
one on the grounds that the model re-ranked the producer's candidates, it SHALL
verify that the model was actually given them. When the producer's candidates
were never passed to the model, they SHALL NOT be dropped in favour of the
model's list.

Dropping a set because a downstream stage "already considered it", when that
stage never received it, loses the affordances the withheld-body index exists to
provide.

#### Scenario: Candidates the model never saw are retained

- **WHEN** producer-supplied link candidates were not passed to the extraction
  step
- **THEN** they are retained in the composed result
