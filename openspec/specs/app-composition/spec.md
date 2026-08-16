# app-composition Specification

## Purpose
TBD - created by archiving change pr1-app-composition. Update Purpose after archive.
## Requirements
### Requirement: Closed-enum diagnostic verdicts

The system SHALL define `Verdict` as a closed `StrEnum` with members `ok`, `paywall`, `block_page_detected`, `anti_bot`, `length_floor`, `content_type_mismatch`, `connection_error`, `timeout`, `not_found`, `rate_limited`, `proxy_unavailable`, `other`. The `Diagnostic` model SHALL carry the verdict plus an optional `subsystem: str | None` for sub-classification (e.g., `cloudflare`, `datadome`, `anubis`).

#### Scenario: Verdict enum is closed

- **WHEN** code attempts to construct a `Diagnostic` with a verdict outside the defined set
- **THEN** pydantic raises a validation error at construction time

### Requirement: Closed-enum status, confidence, and cache state

The system SHALL define `FetchStatus` as a closed `StrEnum` (`ok`, `failed`), `Confidence` as `(high, medium, low)`, and `CacheState` as `(hit, miss, bypass)`.

Every member of `FetchStatus` SHALL have at least one producer in `src/`. A member that no code path can emit SHALL NOT be declared: it presents a calling agent with a state it can never receive, and any consumer branching on it holds unreachable code. `status` carries one bit — whether the ladder terminated cleanly; the detail lives in `Verdict`, `TerminalOutcome`, `retrieval_incomplete`, and `operator_hints[].code` (ADR-0019).

#### Scenario: Each enum is closed at construction

- **WHEN** code attempts to construct a `FetchResponse` with an out-of-set status, confidence, or cache value
- **THEN** pydantic raises a validation error

#### Scenario: A declared status with no producer fails the suite

- **WHEN** a member is added to `FetchStatus` and no code path in `src/` assigns or returns it
- **THEN** the architecture guard fails, naming the unproduced member

#### Scenario: A comparison is not a producer

- **WHEN** the only occurrence of a `FetchStatus` member in `src/` is a comparison against it (`status == FetchStatus.<member>`)
- **THEN** the guard still reports the member as unproduced, because a comparison against a value nothing emits is the dead consumer branch the rule exists to prevent

### Requirement: Configuration via single YAML file plus env vars

The system SHALL load configuration from `AppSettings` (pydantic-settings). The settings model SHALL read, in precedence order: (1) `A2WEB_*` env vars, (2) the YAML file at `$A2WEB_CONFIG` if set, (3) `~/.a2web/config.yaml` if it exists, (4) hard-coded defaults. The fetch tool MUST be callable with no config file present.

The YAML schema SHALL include at minimum: `default_ua: str`, `stealth: bool`, `proxies: dict[str, ProxyEntry]`, `routes: list[RouteRule]`, `cache_ttl_static_h: int`, `cache_ttl_article_h: int`, `cache_ttl_live_m: int`, `log_retention_days: int`, `diagnostics_default: "off" | "brief" | "full"`, `live_only_hosts: list[str]`. The `jina_key` field SHALL be sourced from `A2WEB_JINA_KEY` only and never persisted to the YAML by the tool.

The system SHALL NOT include Firecrawl or Bright Data API key fields in v0.1.

#### Scenario: Zero-config startup

- **WHEN** no config file exists at `~/.a2web/config.yaml` and no `A2WEB_*` env vars are set
- **THEN** `AppSettings()` constructs successfully with defaults and `a2web web fetch --url=...` exits 0

#### Scenario: YAML config overrides defaults

- **WHEN** a YAML file at `$A2WEB_CONFIG` sets `stealth: true`
- **THEN** `AppSettings().stealth` is `True`

#### Scenario: Env var overrides YAML

- **WHEN** the YAML sets `stealth: false` and `A2WEB_STEALTH=true` is exported
- **THEN** `AppSettings().stealth` is `True`

#### Scenario: Jina key is env-only

- **WHEN** the YAML contains a `jina_key` field
- **THEN** that field is ignored; `AppSettings().jina_key` resolves only from `A2WEB_JINA_KEY` (empty string when unset)

### Requirement: OperatorHint docstring acknowledges agent-readable code

The `OperatorHint` docstring in `src/a2web/models.py` SHALL be updated to acknowledge that the `code` field is a stable agent-readable branch point. The previous claim that "the AI agent never reads these to decide a next action" SHALL be removed or softened, since existing codes (`llm_unavailable`, `browser_unavailable`, `captcha_redirect`) are already useful to agents in practice and `cookies_stale` extends this pattern.

The Pydantic schema for `OperatorHint` (field names, types, defaults) SHALL NOT change. Only the docstring is modified.

#### Scenario: Docstring no longer claims agents do not read these

- **WHEN** the docstring of `OperatorHint` is read
- **THEN** it does NOT contain the substring "agent never reads these" (case-insensitive) and DOES acknowledge `code` as a stable agent-readable identifier

#### Scenario: Schema unchanged

- **WHEN** `OperatorHint.model_json_schema()` is compared between the previous release and this change
- **THEN** the schema is identical (field names, types, defaults, requirements)

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

### Requirement: Generic substrate identified by the sweep is consumed from the shared package shelf

Substrate capabilities that the sweep classified as generic SHALL be consumed
from the shared package shelf rather than maintained in-tree. Each SHALL be
pinned by an immutable released tag; a local filesystem or editable source SHALL
NOT be committed. When a capability is adopted, the in-tree implementation SHALL
be deleted rather than left alongside as a second copy.

The capabilities in scope are: extension-point discovery with graceful
degradation; tolerant policy-driven parsing of model JSON envelopes; memoization
of model completions; and engine-agnostic page rendering.

#### Scenario: An adopted capability has exactly one implementation

- **WHEN** a capability has been adopted from the shelf
- **THEN** the in-tree implementation is deleted and all call sites import the
  shelf package

#### Scenario: Sources are pinned to released tags

- **WHEN** the dependency set is inspected
- **THEN** every shelf source is pinned to a released tag and none is a local
  path or editable source

### Requirement: The product moat stays in the application

Capabilities that constitute a2web's product SHALL remain in the application and
SHALL NOT be promoted. These include bot-wall and challenge fingerprinting, proxy
routing and pool health policy, tier escalation decisions, terminal-failure
classification, the empty-result promotion rule, extraction prompts, and the
router payload schema.

Where a promoted seam is paired with product policy, the policy SHALL remain in
the application — in particular, backend selection, engine gating, the fast and
robust rung split, and the mapping from a render outcome to a verdict or operator
hint.

#### Scenario: Product logic is not in a shared package

- **WHEN** the shared packages are inspected
- **THEN** none contains bot-wall fingerprinting, proxy routing policy, tier
  escalation decisions, or extraction prompts

#### Scenario: Rendering policy stays local

- **WHEN** page rendering is adopted from the shelf
- **THEN** backend selection, engine gating, the rung split, and the
  outcome-to-verdict mapping remain in the application

### Requirement: Shared packages never depend on the application

No shared package SHALL import from the application. The dependency arrow points
from the application into the shared packages and never the reverse.

#### Scenario: The boundary holds

- **WHEN** the shared packages are analyzed for imports
- **THEN** none imports any application module

### Requirement: The provider identity is a typed value parsed once at the configuration boundary

The configured model-provider identity SHALL be parsed into the shared package's
provider type once, at the configuration field itself, so that all downstream code
is typed in terms of that shared type. Exhaustive handling of provider values
SHALL be written so that adding a provider upstream fails static checking rather
than falling through silently.

#### Scenario: Configuration yields the shared type

- **WHEN** the provider is supplied as a configuration string
- **THEN** it is validated into the shared provider type at the configuration
  field, and downstream code receives that type

#### Scenario: A new upstream provider fails statically

- **WHEN** the shared package adds a provider value
- **THEN** the application's exhaustive handling fails static checking rather
  than silently taking a fallback branch

### Requirement: Cost refusal precedes any metered model call

The check that refuses a disallowed provider-and-model combination SHALL run
before the call is made, and SHALL be owned by the same package that owns the
provider abstraction and its pricing, so the guard cannot drift from the
signature it wraps.

#### Scenario: A disallowed pair is refused before spending

- **WHEN** a call is attempted with a provider-and-model pair the policy
  disallows
- **THEN** the call is refused before any request is issued

#### Scenario: The guard cannot drift from the provider contract

- **WHEN** the provider contract changes
- **THEN** the guard fails static checking, rather than compiling against a stale
  duplicate of the signature

