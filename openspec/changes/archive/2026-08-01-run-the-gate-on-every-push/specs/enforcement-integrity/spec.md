## ADDED Requirements

### Requirement: The quality gate runs on every push and pull request

The full quality gate — lint, type check, test suite, coverage floor, and all
architecture guards — SHALL execute on every push and on every pull request, not
only on release.

An architecture guard exists to fail the build when a violation lands. A guard
that runs only at tag time does not do that: the violation lands, survives, and
is discovered later in a batch, attributed to whoever cut the release. The
repository's stated strategy — encode the invariant as a test, let CI fail —
requires CI to run at the moment of landing.

The release workflow SHALL continue to run the gate independently. A tag must
verify rather than assume the commit it points at was green.

#### Scenario: A violation fails on the push that introduces it

- **WHEN** a commit violating an architecture guard is pushed
- **THEN** the gate fails on that push

#### Scenario: A pull request is gated

- **WHEN** a pull request is opened or updated
- **THEN** the gate runs against it

#### Scenario: Release still verifies

- **WHEN** a release tag is pushed
- **THEN** the gate runs again as part of the release, independently of any
  earlier run

### Requirement: A declared enforcement mechanism runs, or is recorded as absent

Every enforcement mechanism this repository documents — a CI gate, a commit
hook, a lint pass — SHALL either execute in the environment the documentation
claims, or be removed and its absence recorded.

A hook invoking a retired tool, or a guard described as enforced by a mechanism
no contributor has installed, reports as enforcement while providing none. This
is the same failure the anti-vacuity rule addresses for guards: an enforcement
that cannot fail is indistinguishable from one that passes.

Where a mechanism is deliberately best-effort — a convenience hook that exits
zero when its dependency is missing — the documentation SHALL say so and SHALL
name what the actual floor is.

#### Scenario: A hook calling a retired tool is removed

- **WHEN** a pre-commit hook invokes a tool no longer present in the project
- **THEN** the hook is removed and the loss of that check is recorded

#### Scenario: A best-effort mechanism is not described as a hard block

- **WHEN** documentation describes a guard as a hard block
- **THEN** that guard fails closed in CI, or the documentation names the
  condition under which it does not run and identifies the real floor
