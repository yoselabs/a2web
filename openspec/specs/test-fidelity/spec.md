# test-fidelity Specification

## Purpose

Defines what a test double standing in for an LLM must prove about itself, and what a replay cassette must be able to express. A double that ignores the prompt it is handed reports success while measuring nothing, and every assertion layered above it inherits that blindness; a cassette that cannot express a field silently replays the degraded branch. This capability makes both failure modes structurally loud rather than invisible.
## Requirements

### Requirement: An LLM test double SHALL prove it satisfies the contract it doubles

A test double that ignores the prompt it is handed is not a witness. It reports success while measuring nothing, and every assertion layered on top inherits that blindness.

Every test double standing in for an LLM provider or extractor SHALL either:

1. **satisfy the contract it doubles** — when handed the router contract (`EXTRACT_ROUTER_V1`), return a response from which the routing payload is recoverable; or
2. **explicitly declare the degraded arm it exists to double** — a double whose purpose is to exercise `unparsable`, `unclassified`, or `provider_error` SHALL declare that intent in a machine-checkable form.

A double that does neither SHALL fail the check. Undeclared blindness is the defect.

The check SHALL carry a non-vacuity floor: it SHALL assert that it discovered at least a stated minimum number of doubles, and SHALL fail when it discovers none. A check reporting "0 violations in 0 candidates" is indistinguishable from a passing one.

The check SHALL be contract-SENSITIVE in both directions: a double hard-wired to always return a router envelope regardless of the prompt SHALL also fail, being just as blind as one that never returns an envelope.

This requirement SUBSUMES and REPLACES the single-double fidelity test introduced for `_StubProvider`; that point fix SHALL be deleted rather than retained alongside the general mechanism.

#### Scenario: A prompt-blind double is rejected

- **WHEN** a double discards its `system` / `user` arguments and returns a canned response regardless of the contract
- **THEN** the fidelity check fails, naming the double and the contract it failed to satisfy

#### Scenario: A declared degraded double is accepted

- **WHEN** a double exists specifically to exercise the `unparsable` arm and declares that intent
- **THEN** the fidelity check passes for that double without requiring a recoverable envelope

#### Scenario: An always-JSON double is rejected

- **WHEN** a double returns a router envelope even for a contract that did not request one
- **THEN** the fidelity check fails, because the double is insensitive to the contract rather than faithful to it

#### Scenario: The check refuses to pass vacuously

- **WHEN** the discovery walk finds zero LLM doubles
- **THEN** the check FAILS rather than reporting success

### Requirement: Replay cassettes SHALL record the routing payload and fail loud when they cannot

The eval replay harness reconstructs an `ExtractionResult` from a frozen cassette. It SHALL populate the routing payload from the cassette rather than defaulting it to `None`, so replayed cases exercise the same branch production does.

The cassette format SHALL record the routing payload at capture time. Capturing only post-parse fields (`answer`, token counts, cost, latency, model, template name) makes the artifact structurally incapable of expressing what the routing path produced.

A cassette that cannot express a routing payload SHALL cause the replay to FAIL LOUD, naming the case and the required re-capture. It SHALL NOT silently default to `None`: a silent default is precisely the failure mode this requirement exists to remove, and would re-create it under a new name.

No backward-compatible fallback SHALL be provided for cassettes predating the format. They SHALL be re-captured.

#### Scenario: A routing-bearing cassette replays the recovered branch

- **WHEN** a cassette recorded a routing payload and the case is replayed
- **THEN** the reconstructed `ExtractionResult` carries that payload and the routing outcome is `recovered`

#### Scenario: A legacy cassette fails loud

- **WHEN** a cassette predating the format is replayed
- **THEN** the replay FAILS with an error naming the case and the re-capture command, and does NOT silently substitute `None`

#### Scenario: A deliberately degraded cassette is expressible

- **WHEN** a case exists to exercise a lost routing payload
- **THEN** the cassette can record that explicitly, distinguishing "recorded as lost" from "format cannot say"

### Requirement: A structural guard matches every spelling of the construct it names

An AST-based guard SHALL match every call form of the construct named in its
docstring, its test name, and any documentation citing it. A guard that names
"regex over markup" and matches only `re.compile` does not cover `re.search`,
`re.sub`, `re.match`, or `re.findall`, and reports green over live violations.

Any census or split-claim in a guard's docstring — "18 legitimate patterns and 4
rotted ones, the split is clean" — SHALL have been taken with the matcher that
ships. A census taken with a narrower matcher describes a different population
than the guard enforces, and reads as evidence for a claim it does not support.

When a matcher is widened, the widening SHALL be observed to fail against a real
violation before the violation is fixed. Widen, watch red, then fix: a matcher
that was never seen to fail is not known to match.

#### Scenario: An inline regex over markup is caught

- **WHEN** a handler calls `re.search` or `re.sub` with a pattern containing
  markup
- **THEN** the markup-funnel guard fails

#### Scenario: A widened matcher is proven against a real violation

- **WHEN** a guard's matcher is widened
- **THEN** it is observed failing on an existing violation before that violation
  is repaired

### Requirement: A load-bearing constant has a witness that fails when it moves

A constant whose value changes product behaviour SHALL have a test that fails
when the value moves in either direction. The witness SHALL be a behavioural
test over captured input, not an assertion about the value.

Asserting a constant's value, or sizing a fixture from the constant, is an
endogenous oracle: the fixture and the constant were authored together and can
only confirm they agree. `assert len(_PROSE) >= LENGTH_FLOOR` is a fixture
measured from the thing it is meant to verify.

At minimum this covers thresholds that silently disable a capability. A record
detector gated at a heading fraction of 1.00 detects nothing on a listing whose
titles are not headings — removing the ADR-0015 index and the ADR-0009
completeness signal at once, with no diagnostic.

A constant that has moved to a dependency SHALL carry its witness there. The
obligation follows the constant across a promotion boundary; it does not lapse
because the code left the repository, and it is NOT discharged by asserting a
dependency's internals from the consumer.

#### Scenario: A threshold is witnessed in both directions

- **WHEN** a load-bearing threshold is moved up past its captured witness, or
  down past it
- **THEN** a test fails in each case

#### Scenario: A fixture is not sized from the constant it tests

- **WHEN** a test verifies a length threshold
- **THEN** its fixture length is a captured property, not derived from the
  threshold
