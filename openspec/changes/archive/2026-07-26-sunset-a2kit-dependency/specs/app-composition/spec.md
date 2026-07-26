## ADDED Requirements

### Requirement: The app composes on the MCP server library directly, with no framework layer

a2web SHALL construct its MCP surface directly on the underlying MCP server
library. There SHALL be no application-framework layer owning composition,
dependency resolution, surface projection, or dispatch. Consequently there SHALL
be no dependency-injection container, no provider registry, and no
framework-derived runtime object.

#### Scenario: No framework dependency remains

- **WHEN** the dependency set is inspected
- **THEN** it contains the MCP server library directly and contains no
  application-framework package

#### Scenario: Tools are registered directly

- **WHEN** the server is built
- **THEN** tools are registered on the MCP server object directly, without a
  router-registry or surface-projection layer

### Requirement: A single composition root builds every long-lived resource

All long-lived resources SHALL be constructed in exactly one composition root,
which SHALL also be the construction path used by tests, the evaluation CLI, and
the benchmark harness. A second construction path for the same object graph SHALL
NOT exist.

#### Scenario: One composition root

- **WHEN** the codebase is analyzed
- **THEN** exactly one function constructs the long-lived resource graph, and all
  consumers obtain resources from it

#### Scenario: Tests substitute fakes through the same root

- **WHEN** a test needs a fake resource
- **THEN** it supplies a factory override to the composition root rather than
  mutating a registry after construction

### Requirement: Expensive resources are constructed only when their code path runs

Resources whose construction has real cost SHALL be held as deferred handles and
SHALL NOT be constructed unless the code path that needs them actually executes.
Awaiting a deferred handle SHALL construct and enter the resource at most once
per process, and subsequent awaits SHALL return the same instance. A resource
whose construction failure is expected on an unconfigured install SHALL surface
that failure per-request rather than at startup.

#### Scenario: An unused expensive resource is never constructed

- **WHEN** a request is served entirely from cache or from a path that needs
  neither a rendering engine nor a model provider
- **THEN** neither resource is constructed and neither is entered

#### Scenario: A deferred handle is memoized

- **WHEN** a deferred handle is awaited more than once
- **THEN** the underlying resource is constructed exactly once and the same
  instance is returned

#### Scenario: An unconfigured provider degrades per-request

- **WHEN** no model provider is configured and a request needing one arrives
- **THEN** the request fails with an explicit unavailability signal and the
  process does not fail at startup

### Requirement: Resources are torn down in reverse construction order

Entered resources SHALL be released in reverse order of the order in which they
were entered, so a resource is never released before something that was
constructed using it. A resource whose entry raised SHALL NOT be released. A
failure while releasing one resource SHALL NOT prevent the remaining resources
from being released.

#### Scenario: Dependency-safe unwind

- **WHEN** a resource is constructed during another resource's entry
- **THEN** the inner-constructed resource is released before the outer one

#### Scenario: A failed entry is not released

- **WHEN** a resource's entry raises
- **THEN** its release is never invoked

#### Scenario: A release failure is isolated

- **WHEN** one resource's release raises
- **THEN** the remaining resources are still released

### Requirement: A tool's wire parameters are declared explicitly in its signature

The parameters a tool advertises SHALL be exactly the parameters written in the
registered function's signature. Whether a parameter is caller-facing or
internally supplied SHALL NOT depend on an ambient registry, so that registering
a new internal resource can never remove a caller-facing parameter from the
advertised schema.

#### Scenario: The advertised schema matches the source

- **WHEN** a tool's advertised input schema is inspected
- **THEN** it contains exactly the parameters written in the registered
  function's signature, with their declared descriptions and defaults

#### Scenario: Internal resources are not advertised

- **WHEN** a tool needs an internal resource
- **THEN** that resource is reached through the enclosing object rather than
  declared as a parameter, and it cannot appear in the advertised schema

### Requirement: A readiness probe asserts the substrate explicitly

The readiness probe SHALL obtain its resource explicitly and SHALL assert only
that the storage substrate is usable. It SHALL NOT assert that a model provider
is configured, because the fetch-only surface serves correctly without one.

#### Scenario: Readiness reflects the substrate

- **WHEN** the readiness probe runs and storage opens
- **THEN** the probe reports ready

#### Scenario: Readiness ignores model configuration

- **WHEN** no model provider is configured but storage opens
- **THEN** the probe still reports ready

## MODIFIED Requirements

### Requirement: Typed events are emitted synchronously and cannot disrupt the caller

Typed event payloads SHALL be emitted through a synchronous call. Event emission
SHALL NOT require awaiting, because the asynchronous form existed only to serve a
live-notification forward that has no consumer.

Every event sink SHALL be isolated such that a failing sink cannot propagate an
exception into the emitting code path, and a sink failure SHALL NOT recurse
through the event system. Each event SHALL be delivered to a given sink exactly
once.

#### Scenario: Emission does not require awaiting

- **WHEN** a typed event is emitted from application code
- **THEN** the call is synchronous and the payload fields are preserved on the
  emitted record

#### Scenario: A failing sink cannot break the caller

- **WHEN** a sink raises while handling an event
- **THEN** the exception does not propagate into the emitting code path and the
  remaining sinks still receive the event

#### Scenario: No duplicate delivery

- **WHEN** an event that produces external telemetry is emitted
- **THEN** exactly one telemetry record is produced, not two
