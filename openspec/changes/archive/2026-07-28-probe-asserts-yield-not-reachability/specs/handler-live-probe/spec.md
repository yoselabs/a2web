## ADDED Requirements

### Requirement: Every probe case declares the yield it expects

Each probe case SHALL declare, for one handler and one URL, the yield that a
working handler produces at that URL: a minimum rendered-content length, a
minimum candidate count, and a prose statement of the property being checked.
The probe SHALL fail a case whose observed yield is below any declared floor,
even when the handler returned `Verdict.ok`.

Declared floors SHALL be set below the observed working value rather than at it.
A floor pinned to the observed value is a golden — it fails when the site's
content rotates, which is not the failure the probe exists to catch.

The prose statement is REQUIRED, including for cases whose only available
assertion is weak. Its purpose is to let a later reader distinguish a
deliberately weak assertion from an overlooked one.

#### Scenario: A rotted parser fails the probe

- **WHEN** a handler's selectors stop matching, and the handler returns
  `Verdict.ok` with a body naming zero units
- **THEN** the probe fails that case, naming the declared floor and the observed
  value

#### Scenario: Reachability alone does not pass

- **WHEN** a handler completes a live fetch and returns non-empty content below
  its declared content floor
- **THEN** the probe reports the case as failing

#### Scenario: Content rotation does not fail the probe

- **WHEN** a listing renders fewer entries than on the day the case was written,
  but above its declared floor
- **THEN** the case passes

### Requirement: Every shape a handler serves is probed

A handler that serves more than one URL shape — a listing and a detail page, an
index and a topic — SHALL carry a probe case for each shape it serves. A shape
that is never probed is not covered by the probe, regardless of how many cases
the handler has.

#### Scenario: A listing-only parser is exercised on a listing

- **WHEN** a handler's index parser is reached only by listing URLs
- **THEN** the probe includes a listing case for that handler, not only a detail
  case

### Requirement: A handler that yields candidates declares a non-zero floor

Where a handler populates `next_links`, at least one of its probe cases SHALL
declare a candidate floor greater than zero. This SHALL be enforced offline, in
the standard test suite, reading which handlers populate candidates from the
handler sources rather than from a maintained list.

The probe itself is live-network and outside `make check`, so nothing otherwise
prevents a floor from being edited to zero to turn a red probe green — which is
the same weakening that let a dead parser pass. The offline guard makes the
number's DELETION visible; it does not and cannot check the number against a
live site.

#### Scenario: A candidate floor cannot be silently removed

- **WHEN** every probe case for a candidate-populating handler declares a
  candidate floor of zero
- **THEN** the offline suite fails, naming that handler

#### Scenario: An article handler needs no candidate floor

- **WHEN** a handler populates no `next_links` at any shape
- **THEN** its cases may declare a candidate floor of zero without failing the
  offline guard

### Requirement: A blocked handler stays declared and stays failing

Where a handler cannot complete a live fetch from the environment the probe runs
in — a blocked host, a dead upstream — its case SHALL remain in the table with
real declared floors, and the probe SHALL report it as failing. The case SHALL
NOT be removed, and its floors SHALL NOT be lowered to produce a passing result.

A removed case converts a known-blocked handler into a silently unprobed one,
which is the condition this capability exists to prevent. An honestly failing
probe carries more information than a green one that stopped asking.

#### Scenario: A blocked host is reported, not omitted

- **WHEN** a handler's representative host blocks the probe's network
- **THEN** the probe names that handler as failing and does not omit it from its
  count
