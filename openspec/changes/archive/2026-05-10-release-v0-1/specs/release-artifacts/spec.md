## ADDED Requirements

### Requirement: Repository carries a CHANGELOG.md at root

The repository SHALL contain a `CHANGELOG.md` file at the repo root following the Keep-a-Changelog convention. Each tagged release SHALL have a corresponding section heading `## [<version>] - <YYYY-MM-DD>` containing zero or more of `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security` subsections. Entries MUST be user-facing summaries; internal PR references MAY appear in parentheses for traceability.

#### Scenario: v0.1.0 release section is present

- **WHEN** an operator opens `CHANGELOG.md` after the release commit
- **THEN** the file contains a `## [0.1.0] - 2026-05-10` section with at least one entry under `### Added` summarizing the cascade

#### Scenario: Future releases append, never rewrite

- **WHEN** a later release (e.g. v0.1.1, v0.2.0) is cut
- **THEN** a new `## [<version>]` section is added above the v0.1.0 section; existing entries are not edited

### Requirement: Repository carries a BACKLOG.md at root

The repository SHALL contain a `BACKLOG.md` file at the repo root listing every known deferred item. Each entry SHALL include: source reference (PR id or engineering doc section), one-line description, why it was deferred, and a rough scope tier (S/M/L). Items SHALL be grouped by target milestone (`PR7e`, `PR8b`, `PR10b`, `v0.2`, `v0.3+`).

When a deferred item ships, its entry SHALL be removed in the same change that ships it. When a new deferral is created (e.g. a future "Out of Scope" section in another OpenSpec change), the item SHALL be added to BACKLOG.md as part of that change.

#### Scenario: BACKLOG.md exists at v0.1.0

- **WHEN** an operator inspects the repo at the v0.1.0 tag
- **THEN** `BACKLOG.md` exists, contains at least the PR7e, PR8b, PR10b, and v0.2 groups, and each entry has source / description / why-deferred / scope

#### Scenario: Stays current

- **WHEN** a future change ships a backlog item (e.g. PR8b's youtube handler)
- **THEN** that change's task list includes "remove the corresponding entry from BACKLOG.md"

### Requirement: Project version reflects current release state

`pyproject.toml` `[project].version` SHALL match the most recent annotated git tag at all times on the `main` branch. Pre-release commits beyond the most recent tag MAY use a `.devN` or `.rcN` suffix, but a tagged commit MUST carry the bare version string (no suffix).

#### Scenario: v0.1.0 commit version

- **WHEN** the operator inspects `pyproject.toml` at the v0.1.0 tag
- **THEN** the `version` field reads `"0.1.0"` exactly (no `.dev0`, `.rc0`, etc.)

#### Scenario: Tag is annotated

- **WHEN** an operator runs `git show v0.1.0`
- **THEN** the output shows an annotated tag (with author, date, and message), not a lightweight tag
