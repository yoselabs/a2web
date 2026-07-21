## ADDED Requirements

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
