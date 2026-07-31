## ADDED Requirements

### Requirement: Documented environment variables carry the prefix that applies

Every environment variable named in this specification SHALL be written with the
prefix the settings loader actually applies. A variable written bare, where the
loader requires a prefix, is not read at runtime.

For authentication configuration this is not a documentation defect but a
security one: an operator who follows the specification literally sets variables
that are never read, the authentication provider is not configured, and the
endpoint is served **unauthenticated**. The deployment appears to succeed.

Where authentication configuration is absent or incomplete, the server SHALL fail
to start rather than serve an unauthenticated endpoint, so that a
misconfiguration cannot present as a working deployment.

#### Scenario: A documented variable is read at runtime

- **WHEN** an operator sets every environment variable exactly as this
  specification writes it
- **THEN** the settings loader reads each of them

#### Scenario: Incomplete auth configuration fails loudly

- **WHEN** authentication is enabled but its configuration is incomplete
- **THEN** the server fails to start rather than serving unauthenticated
