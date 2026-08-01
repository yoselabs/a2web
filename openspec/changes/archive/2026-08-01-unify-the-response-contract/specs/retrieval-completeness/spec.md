## ADDED Requirements

### Requirement: The terminal classification is carried, not reconstructed

The classification of what a failed retrieval means SHALL be computed once from
the observations and carried to every consumer as a typed value. No consumer
SHALL reconstruct it by inspecting a rendered operator hint's code, message, or
severity.

Recovering an upstream decision from a downstream rendering is unsound in both
directions: the rendering is chosen *from* the decision, so reading it back
recovers only what the message catalogue happened to encode, and a change to the
copy silently changes the classification. Reading a hint's severity in order to
recover a boolean that was passed into the hint factory is a round-trip through
a message catalogue.

The operator hint is a rendering of the classification for a human reader. It is
not the source of truth for incompleteness, and SHALL NOT be described as one.

#### Scenario: A downstream consumer reads the typed outcome

- **WHEN** the response projection needs to know why a retrieval failed
- **THEN** it reads the carried terminal classification, not an operator hint's
  code or severity

#### Scenario: Changing hint copy does not change classification

- **WHEN** an operator hint's message text or severity wording is edited
- **THEN** the terminal classification of the same observations is unchanged

### Requirement: The severity ladder is declared in one place

The mapping from confidence to hint severity — `critical` for a wall, `warning`
for an unverified or residual condition, `info` for a verified dead URL — SHALL
be stated once, in the module that owns the response contract. Hint factories
SHALL cite that declaration rather than each restating the policy in prose.

A ladder discoverable only by reading nine docstrings scattered through a
type-definition file is folklore. It is what makes a severity comparison
downstream look like a reasonable check instead of an obvious defect.

#### Scenario: A hint's severity derives from the declared ladder

- **WHEN** a hint factory chooses a severity
- **THEN** it derives it from the single declared ladder

#### Scenario: The ladder has one definition site

- **WHEN** the severity policy is searched for
- **THEN** exactly one declaration is found
