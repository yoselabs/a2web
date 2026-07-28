## ADDED Requirements

### Requirement: A handler that retrieved a challenge page does not report success

A handler that extracts content from HTML SHALL consult the block catalogue
before returning `Verdict.ok`. Where the retrieved body carries a challenge or
block fingerprint, the handler SHALL return a wall verdict rather than rendering
the challenge as content.

A handler knows what it asked for and what it received. That a downstream gate
also inspects the rendered body is a backstop, not a reason for the handler to
report something it did not observe — the gate consults the catalogue only for
sub-floor bodies, so a verbose interstitial reaches it as apparently-valid
content.

This applies to handlers that extract from HTML. Handlers consuming a structured
API are unaffected: a challenge page is not valid JSON and already fails them
into a non-`ok` verdict.

#### Scenario: An interstitial is not content

- **WHEN** a handler retrieves HTTP 200 whose body is a browser-verification or
  anti-bot interstitial
- **THEN** the handler returns a wall verdict, not `Verdict.ok` with the
  interstitial rendered as the page

#### Scenario: A verbose interstitial is caught too

- **WHEN** the interstitial's extracted text is long enough to clear the gate's
  length floor
- **THEN** the handler still returns a wall verdict — the handler's check is not
  gated on rendered length

#### Scenario: A structured-API handler is unaffected

- **WHEN** a handler consumes a JSON API and the host returns an HTML challenge
- **THEN** the existing parse failure already yields a non-`ok` verdict and no
  additional check is required

### Requirement: A walled upstream does not shadow the rest of a failover list

A handler that tries several interchangeable upstreams SHALL treat an upstream
that returns a challenge page as a FAILED upstream and continue to the next one.
It SHALL NOT return the challenge as the result while untried upstreams remain.

A failover list exists so that one bad upstream does not decide the outcome.
An upstream that answers with a wall has not served the request, and returning
at it converts a recoverable situation into a failure whose identity depends on
list order.

Where the list is randomised per request, this is additionally a source of
nondeterminism: the same URL returns content or a challenge depending on shuffle
order.

#### Scenario: A walled upstream is skipped

- **WHEN** the first upstream tried returns a challenge page and another
  upstream remains untried
- **THEN** the handler tries the next upstream

#### Scenario: A walled upstream registers as a failure

- **WHEN** an upstream returns a challenge page
- **THEN** that upstream's circuit breaker records a failure, so a persistently
  walled upstream is tripped rather than retried on every fetch

#### Scenario: All upstreams walled fails loudly

- **WHEN** every upstream in the list has been tried and at least one returned a
  challenge page
- **THEN** the handler returns `Verdict.block_page_detected` with the critical
  `try_user_browser` operator hint, so the caller is told the URL was not
  retrieved (ADR-0009)

#### Scenario: Order does not determine the outcome

- **WHEN** a randomised failover list contains both a working and a walled
  upstream
- **THEN** the result is the working upstream's content regardless of the order
  the two were tried in
