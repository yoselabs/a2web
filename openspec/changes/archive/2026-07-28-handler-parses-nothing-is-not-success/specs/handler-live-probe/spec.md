## ADDED Requirements

### Requirement: The probe checks yield, not just reachability

The handler probe SHALL assert that each handler produces UNITS — entries,
records, items — and not merely that it returned without error. A handler
returning `Verdict.ok` with a zero-unit parse is indistinguishable from a
working one under a reachability check, which is precisely the failure the probe
exists to catch.

Where a handler's success is not defined by a unit count, the probe SHALL assert
whatever yield that handler does have (a non-trivial body, a resolved title) and
SHALL record which property it checked, so a later reader can tell a deliberate
weaker assertion from an overlooked one.

#### Scenario: A handler with stale selectors is caught

- **WHEN** a handler's site changes its markup so the parse yields nothing, while
  the site still returns HTTP 200
- **THEN** the probe reports that handler as failing

#### Scenario: Reachability alone does not pass

- **WHEN** a handler returns without error and with zero parsed units
- **THEN** the probe does not report it as healthy

### Requirement: Offline handler fixtures are captured, never hand-written

A fixture standing in for a real page in a handler parse test SHALL be captured
from that site. A hand-written approximation SHALL NOT be used as the oracle for
whether a parser matches the site.

A hand-written fixture encodes the same assumptions as the parser it tests,
authored by the same person at the same moment, so it cannot fail when those
assumptions are wrong about the site — it can only confirm that the parser
agrees with itself. This is not hypothetical: the arXiv listing parse test was
green against a hand-written fixture while the handler returned zero entries on
the live page (2026-07-28).

Where a captured fixture is impractical, the test SHALL state what it is
therefore NOT evidence of.

#### Scenario: A fixture cannot witness the parser it was written from

- **WHEN** a parser and its fixture encode the same assumption about a site's
  markup, and that assumption is wrong
- **THEN** the test passing is not evidence that the parser works

#### Scenario: Captured fixture detects rot

- **WHEN** a site changes its markup and a fresh capture is taken
- **THEN** the parse test fails, rather than continuing to pass against the old
  hand-written shape
