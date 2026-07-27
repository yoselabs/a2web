# public-distribution Specification

## Purpose

Defines what the repository owes a stranger who finds it: a delivered license
grant, a shipping tree free of one operator's personal environment, and a README
that orients someone with no prior context. These are properties of the artifact
rather than of the running system — a project can be entirely correct and still
be unadoptable.
## Requirements

### Requirement: The repository ships its license grant

The repository SHALL carry the full text of its declared license as a root
`LICENSE` file, matching the license identifier declared in `pyproject.toml`. The
grant SHALL be delivered as text, not asserted in metadata alone.

#### Scenario: License text is present and matches metadata

- **WHEN** the repository root is inspected
- **THEN** a `LICENSE` file exists containing the full Apache-2.0 text
- **AND** its SPDX identifier matches `pyproject.toml`'s `license` field
- **AND** GitHub's license detector recognizes the repository as Apache-2.0

### Requirement: The shipping tree carries no operator-personal identifiers

Files that ship in the public repository SHALL NOT contain identifiers specific
to a single operator's environment — personal usernames, private host names, or
absolute home-directory paths. Generic self-hosting nouns (e.g. "homelab") are
permitted; a named private gateway, a personal domain, or a macOS home-directory
prefix followed by a user name is not. Archived changes and regenerable artifacts are out of scope.

#### Scenario: A personal identifier fails the hygiene guard

- **WHEN** a shipping file (outside `openspec/changes/archive/**` and regenerable
  artifacts) contains a denylisted identifier — a personal username, the private
  gateway host, or an absolute home path
- **THEN** the personal-strings guard fails and names the file and match

#### Scenario: The hygiene guard cannot pass vacuously

- **WHEN** the personal-strings guard runs
- **THEN** it asserts it scanned at least a floor number of files, so a guard that
  matched nothing because it walked an empty set fails rather than passes

### Requirement: The README is a public front door

The `README.md` SHALL orient a newcomer with no prior context: what a2web is, its
primary tools, how to install it via the supported public channels, a minimal
quickstart, how to configure it, and how to run the contributor gate.

#### Scenario: A newcomer can install and run from the README alone

- **WHEN** a reader with no prior context follows the README
- **THEN** it states what a2web is and names the `query` and `fetch_raw` tools
- **AND** it gives a git-tag pin install and a public container-image pull
- **AND** it shows a minimal run + one call, the `A2WEB_*` configuration surface,
  and the `make check` contributor gate
