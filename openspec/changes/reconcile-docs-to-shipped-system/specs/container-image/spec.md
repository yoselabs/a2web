## ADDED Requirements

### Requirement: The image's browser contents are stated once, per build configuration

Whether a container image contains a browser SHALL be stated in exactly one
place, and SHALL distinguish the default build from the published release build
where they differ.

The presence of a browser determines whether a served instance can escalate to a
rendered retrieval. An agent that believes the served instance has no browser
routes around a capability it has; an operator who believes the default build has
one deploys an image that cannot escalate. Both errors are currently available
from documents in this repository, in opposite directions.

Where the answer depends on a build argument, the specification SHALL name the
argument and the value used for the published image, rather than asserting an
unconditional answer.

#### Scenario: The default build's contents are stated

- **WHEN** an image is built with no build arguments
- **THEN** the specification states whether it contains a browser

#### Scenario: The published image's contents are stated

- **WHEN** the release workflow publishes an image
- **THEN** the specification states whether that image contains a browser, and
  the build argument that determines it
