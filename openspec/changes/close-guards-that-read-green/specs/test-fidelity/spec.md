## ADDED Requirements

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
