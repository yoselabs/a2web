## ADDED Requirements

### Requirement: The documented automatic provider order is the shipped order

The provider order this specification declares for automatic selection SHALL be
the order the resolver applies, including every conditional reordering.

Where the resolver promotes a provider ahead of the documented order under some
configuration, that promotion SHALL be stated with its condition. A specification
asserting that a provider is last, and reasoning from that ("it can never shadow
a working path"), while the shipped resolver puts it first under a common
configuration, inverts a live routing invariant and its stated safety property at
once.

Provider routing decides which backend is billed. A wrong belief about the order
is a wrong belief about cost, which is why this order is documented at all.

Provider identifiers in this specification SHALL be identifiers the resolver
accepts. An identifier that fails at resolution documents a boot that cannot
happen.

#### Scenario: A conditional promotion is documented with its condition

- **WHEN** the resolver promotes a provider ahead of the declared order
- **THEN** the specification states the promotion and the configuration that
  triggers it

#### Scenario: Documented identifiers resolve

- **WHEN** an operator configures a provider using an identifier from this
  specification
- **THEN** the resolver accepts it
