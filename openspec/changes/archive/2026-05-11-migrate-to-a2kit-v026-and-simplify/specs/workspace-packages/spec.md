## ADDED Requirements

### Requirement: Repository layout is a uv workspace with internal packages

The repository SHALL be a uv workspace. The root `pyproject.toml` SHALL declare `[tool.uv.workspace]` with `members = ["packages/*"]`. The directory `packages/` SHALL contain one subdirectory per internal package, each with its own `pyproject.toml`, `src/<package_name>/`, and `tests/` tree. The packages SHALL be `proxy-pool`, `browser-pool`, and `block-detector`.

#### Scenario: Workspace members detected

- **WHEN** `uv sync` runs from the repo root
- **THEN** the lockfile resolves `proxy-pool`, `browser-pool`, and `block-detector` as workspace path dependencies, not from PyPI

#### Scenario: Each package has its own pyproject

- **WHEN** a maintainer inspects `packages/proxy-pool/pyproject.toml`, `packages/browser-pool/pyproject.toml`, and `packages/block-detector/pyproject.toml`
- **THEN** all three files declare their own name, version, dependencies, and `[build-system]` and DO NOT reference `a2web` as a dependency

### Requirement: Packages declare narrow types; no reverse imports

Each internal package SHALL define its own narrow types for its public API surface (enums, dataclasses, protocols). A package SHALL NOT import any symbol from the `a2web` namespace. Adapter modules in `src/a2web/proxy/` and `src/a2web/browser/` SHALL translate between package-native types and a2web's domain types (e.g., the package's resolution result → a2web's `Diagnostic` row).

#### Scenario: Package imports linted

- **WHEN** lint runs over `packages/proxy-pool/src/` or `packages/browser-pool/src/`
- **THEN** no module imports anything matching `from a2web` or `import a2web`

#### Scenario: Adapter layer exists for each package

- **WHEN** a maintainer inspects `src/a2web/proxy/__init__.py` and `src/a2web/browser/__init__.py`
- **THEN** each module imports its package counterpart and exposes adapter functions that translate package-native types to a2web domain types

### Requirement: `make check` runs across the workspace

The repo-root `Makefile` SHALL expose `make check`, `make lint`, `make ty`, `make test` targets that aggregate across a2web and every workspace package. A failure in any package SHALL fail the aggregate target.

#### Scenario: Test failure in a package fails make check

- **WHEN** a test in `packages/proxy-pool/tests/` is induced to fail and `make check` is run from the repo root
- **THEN** the target exits non-zero and the failing test output is visible

### Requirement: a2web declares packages as workspace dependencies

`pyproject.toml` at the repo root SHALL list each internal package as a dependency using uv workspace syntax: `proxy-pool = { workspace = true }`. The `[tool.uv.sources]` table SHALL be configured so resolving these names does not reach PyPI.

#### Scenario: Workspace dependency resolution

- **WHEN** `uv sync` runs against a clean cache
- **THEN** `proxy-pool` and `browser-pool` resolve to the local workspace paths and the lockfile records `source = "workspace"`
