# image-publishing Specification

## Purpose
TBD - created by archiving change deployable-container-ci. Update Purpose after archive.
## Requirements
### Requirement: Release tags gate on the full check before building

The CI pipeline SHALL, on a release tag (`v*`), run the full quality gate (`make check` — lint + ty + tests + arch) and SHALL NOT build or publish an image if the gate fails.

#### Scenario: Failing gate blocks publish

- **WHEN** a `v*` tag is pushed and `make check` fails
- **THEN** no image is built or pushed, and the workflow reports failure

#### Scenario: Passing gate proceeds to build

- **WHEN** a `v*` tag is pushed and `make check` passes
- **THEN** the pipeline proceeds to the image build/publish job

### Requirement: Public multi-tag image on GHCR

On a passing release build, the pipeline SHALL push the image to `ghcr.io/yoselabs/a2web` tagged with both the release version and `latest`, and the package SHALL be publicly pullable without authentication.

#### Scenario: Version and latest tags are published

- **WHEN** the build job completes for tag `vX.Y.Z`
- **THEN** `ghcr.io/yoselabs/a2web:X.Y.Z` and `ghcr.io/yoselabs/a2web:latest` both exist

#### Scenario: Anyone can pull

- **WHEN** an unauthenticated client runs `docker pull ghcr.io/yoselabs/a2web:latest`
- **THEN** the pull succeeds

### Requirement: Published version matches the release tag

The image published for a tag SHALL carry the same a2web version as `pyproject.toml` at that tag (the existing release-artifacts version invariant), so a pulled image's `--version` matches the tag it was built from.

#### Scenario: Image version equals tag

- **WHEN** the image built for `vX.Y.Z` is inspected
- **THEN** the a2web version inside equals `X.Y.Z`, matching `pyproject.toml` at that commit

