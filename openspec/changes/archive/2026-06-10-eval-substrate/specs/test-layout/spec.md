## ADDED Requirements

### Requirement: the eval corpus and replay harness have canonical homes

Corpus fixtures SHALL live under `eval/corpus/<corpus>/<case>/` (committed). The deterministic
replay harness and its assertions SHALL live in the test layer (under `tests/`) so they are collected
by `make check`. The capture/refresh dev tooling SHALL live in a non-packaged `eval/` dev module and
SHALL NOT be importable from the shipped `a2web` package.

#### Scenario: replay tests are collected by make check

- **WHEN** `make check` runs
- **THEN** the deterministic replay tests are collected and gate the run alongside the existing suite

#### Scenario: capture tooling is not in the shipped package

- **WHEN** the shipped `a2web` package imports are inspected
- **THEN** no eval capture/refresh module is importable from `a2web.*`

### Requirement: only deterministic checks gate make check

Tests wired into `make check` SHALL be deterministic and SHALL NOT make live network, browser, or LLM
calls. Any check requiring a live LLM judge or live network SHALL run only under `make bench` and SHALL
NOT be collected by `make check`.

#### Scenario: a replay test makes no live call

- **WHEN** a deterministic replay test runs under `make check`
- **THEN** it reads only frozen fixtures and makes no network, browser, or live-LLM call
