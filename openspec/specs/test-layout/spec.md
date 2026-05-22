# test-layout Specification

## Purpose

Defines the canonical structure of the `tests/` tree so that the test suite mirrors the codebase's architecture and the OpenSpec capability set: every test has a deterministic, spec-aligned home, the `packages/` independence boundary is visible, and fixture-path resolution survives directory depth.

## Requirements

### Requirement: tests are organized into three zones

The `tests/` tree SHALL organize test files into three zones plus supporting directories. The zones are `tests/architecture/` for meta-tests asserting invariants about the codebase itself, `tests/packages/` for tests that exercise `a2web.packages.*` modules in isolation, and `tests/capabilities/<capability>/` for domain-coupled behavior tests grouped one directory per OpenSpec capability. The supporting directories are `tests/fixtures/` (shared fixture data), `tests/contracts/` (golden contract JSON and its test), and `tests/utils/` (mirrors `src/a2web/utils/`). `tests/conftest.py` SHALL remain at the `tests/` root so its fixtures cascade to every zone.

#### Scenario: every test file lives in a zone

- **WHEN** the `tests/` tree is inspected after the regrouping
- **THEN** no `test_*.py` file remains directly under `tests/` — each lives under `architecture/`, `packages/`, `capabilities/<capability>/`, `contracts/`, or `utils/`

#### Scenario: a capability directory mirrors a spec

- **WHEN** a directory `tests/capabilities/<capability>/` exists
- **THEN** `openspec/specs/<capability>/spec.md` exists, and the directory holds the tests that verify that capability

### Requirement: a deterministic rule decides a test's zone

Each test file SHALL be placed by a deterministic rule: a test asserting an invariant about the codebase itself belongs in `tests/architecture/`; a test importing only from `a2web.packages.*` (and `models`, `settings`, or `utils`) belongs in `tests/packages/`, sub-pathed to mirror the package under test; any other test belongs in the `tests/capabilities/<capability>/` directory whose spec the test most directly verifies. A `tests/capabilities/<capability>/` directory SHALL be created only when at least one test is placed in it.

#### Scenario: a pure package test lands in the packages zone

- **WHEN** a test file imports only `a2web.packages.*` symbols
- **THEN** it is placed under `tests/packages/`, mirroring the source package's sub-path

#### Scenario: a domain-coupled test lands in a capability directory

- **WHEN** a test file imports a domain module such as `a2web.fetcher`, `a2web.routers`, or `a2web.state`
- **THEN** it is placed under `tests/capabilities/<capability>/` for the capability it verifies, never under `tests/packages/`

#### Scenario: no empty capability directory is created

- **WHEN** an OpenSpec capability has no test verifying it
- **THEN** no `tests/capabilities/<capability>/` directory exists for it

### Requirement: fixture paths resolve through a stable anchor

Test files SHALL resolve the shared fixture directory through the `FIXTURES_DIR` anchor exported by `tests/fixtures/__init__.py`, not by recomputing `Path(__file__).parent / "fixtures"`. This keeps fixture-path resolution correct regardless of how deep a test file sits in the tree.

#### Scenario: a moved test still finds its fixtures

- **WHEN** a test file that uses fixture data is placed at any depth under `tests/`
- **THEN** it locates the fixture directory via `FIXTURES_DIR` and the fixture data loads correctly

### Requirement: regrouping preserves test behavior

Moving and grouping test files SHALL NOT change test behavior. Files SHALL move with `git mv` to preserve history; the only permitted content edits are the fixture-path anchor change and the explicit file merges. The set of tests collected and their pass/fail outcomes SHALL be identical before and after the regrouping.

#### Scenario: the suite is unchanged by the move

- **WHEN** the full suite is run after the regrouping
- **THEN** the same number of tests is collected and the suite passes exactly as it did before

#### Scenario: merged files preserve every test

- **WHEN** two or more test files are merged into one
- **THEN** every test function from the source files is present in the merged file and still runs
