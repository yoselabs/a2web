## ADDED Requirements

### Requirement: The partial-listing signal is reachable on every listing path

Where a2web renders a listing and the page advertises a total larger than what
was rendered, the shortfall SHALL surface as a `listing_partial` operator hint.
This SHALL hold on every path that produces a listing, not only the path where
the DOM record-miner ran.

The sufficiency phase currently gates on `record_count`, which has exactly one
writer. A listing rendered by a site handler therefore never reaches the
assessment, and the shortfall is invisible to any machine consumer.

Carrying the shortfall in the rendered prose is NOT sufficient. Prose serves the
model reading the answer; the hint serves the caller reading the envelope. The
2026-07-28 fix supplied the former and left the latter unreachable, and this
requirement exists to close that half.

#### Scenario: A handler-rendered listing signals its shortfall

- **WHEN** a site handler renders N items of an advertised M, with M > N
- **THEN** the envelope carries a `listing_partial` hint quantifying N and M

#### Scenario: The signal does not depend on the record-miner

- **WHEN** a listing is produced without the DOM record-miner running
- **THEN** the sufficiency assessment still runs

#### Scenario: A complete listing signals nothing

- **WHEN** the rendered count meets the advertised total within tolerance
- **THEN** no partial-listing hint is emitted

#### Scenario: Prose and hint agree

- **WHEN** a rendered listing states a shortfall in its markdown
- **THEN** the envelope carries the corresponding hint, and the two counts match
