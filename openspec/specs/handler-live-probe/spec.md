# Handler Live Probe

## Purpose

Live-network handler-probe target that exercises every registered handler against a real representative URL with no monkeypatching. Catches transport-layer regressions that unit tests miss; not part of `make check`.

## Requirements

### Requirement: make handler-probe runs a live end-to-end check per handler

The project SHALL provide a `make handler-probe` target that, for every handler
in `_HANDLERS`, performs real network fetches against representative URLs and
asserts each case's DECLARED YIELD (see "Every probe case declares the yield it
expects"). The target SHALL NOT be included in `make check`. The target SHALL
NOT spend LLM quota — `fetch_raw`-equivalent only, no `ask=`.

A `verdict == Verdict.ok` plus non-empty `content_md` check is NOT sufficient
and SHALL NOT be the probe's assertion: a handler rendering `## Papers (0)`
satisfies both while parsing nothing, which is the exact failure the probe
exists to catch.

#### Scenario: Probe asserts handler end-to-end against the real host

- **WHEN** `make handler-probe` is invoked
- **THEN** for every registered handler, a real network fetch occurs for each of
  its declared cases, and the probe exits non-zero if any case falls short of
  the yield that case declares

#### Scenario: Probe is not part of make check

- **WHEN** `make check` is invoked
- **THEN** the handler-probe target does NOT execute, and `make check` remains offline and deterministic

#### Scenario: Adding a handler adds a probe case

- **WHEN** a new handler is registered in `_HANDLERS`
- **THEN** the probe case table MUST include at least one case for it; a missing
  entry SHALL fail loudly (not silently skip), and this SHALL be enforced
  offline so the omission is caught without a network run

### Requirement: Probe findings record the transport method

A probe finding recorded in design / proposal docs (or in a handler module comment) SHALL name the transport method that produced the result — `curl_cffi-impersonated`, `httpx-anonymous`, `with-cookies`, `with-auth`, etc. — not only the HTTP outcome ("200 JSON"). A handler implementation SHALL invoke a transport at least as strong as the one the probe used; it SHALL NOT silently substitute a weaker stack.

#### Scenario: Probe finding without method is incomplete

- **WHEN** a design or proposal records only "the API returns 200 JSON anonymously" without naming the transport method
- **THEN** the finding is incomplete; reviewers SHALL request the method before accepting the handler

#### Scenario: Handler implementation matches the probed transport

- **WHEN** a probe finding records `curl_cffi-impersonated, 200 JSON`
- **THEN** the handler implementation SHALL invoke the shared `handler-transport` primitive (which provides that transport) and SHALL NOT construct a weaker client

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

#### Scenario: A zero-unit parse is not health

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

### Requirement: Selector rot is distinguishable from an empty page

A schema-driven extraction SHALL report a rotted selector distinctly from a page
that legitimately contains nothing.

Where the schema's container selector always matches — a universal element such
as the document body — every failure is reported as EMPTY, and the failure mode
the schema layer exists to detect is exactly the one it cannot report. **The
container selector SHALL therefore be specific enough that its absence is itself
a signal.** A universal container is a forfeit of the distinction, not a
constraint the page imposed: the discriminating selector is usually present and
unlooked-for.

**The two halves are not equally separable, and a requirement that ignores this
cannot be met.** A rotted CONTAINER selector is always distinguishable — its
absence is a fact about the schema. A rotted ITEM selector generally is NOT: for
a page class where "contains nothing" is a legitimate state (an article that
links nowhere, a thread with no replies), zero rows is the same observation
either way, and no verdict can separate them. Requiring a rot verdict there
would be requiring a distinction that does not exist.

Where the item half is inseparable, the extraction SHALL carry a declared
non-zero yield expectation instead — a floor asserted against captured markup —
and that floor SHALL NOT be zeroed, since it is then the only detector. Each
extraction SHALL state which half its verdict covers; a docstring implying
coverage of both is the defect this requirement exists to prevent.

A live network probe SHALL NOT be the only rot detector, for either half: it
makes rot detection depend on the network, which means it is skipped where it is
needed most.

#### Scenario: A universal container is replaced by a discriminating one

- **WHEN** a schema's container selector matches every document
- **THEN** it is replaced by one whose absence signals that the document is not
  the shape the schema was written for, and that absence reports rot

#### Scenario: An inseparable item half declares a yield floor

- **WHEN** zero items is a legitimate state for the page class, so item rot
  cannot produce a verdict
- **THEN** the extraction declares a non-zero yield floor asserted against
  captured markup, and states that its verdict covers the container half only

#### Scenario: Rot is detectable offline

- **WHEN** rot detection runs without network access
- **THEN** a rotted selector is still detectable against captured markup
