## ADDED Requirements

### Requirement: A handler that retrieved a challenge page does not report success

A handler that extracts content from HTML SHALL consult the block catalogue
before returning `Verdict.ok`. Where the retrieved body carries a challenge or
block fingerprint, the handler SHALL return a wall verdict rather than rendering
the challenge as content.

A handler knows what it asked for and what it received. That a downstream gate
also inspects the rendered body is a backstop, not a reason for the handler to
report something it did not observe.

The check SHALL consult the catalogue with the body's REAL extracted text, and
therefore inherits the catalogue's own two-tier precision: vendor fingerprints
(widget ids, cookie names, asset paths) match at any length; prose markers match
only below the length floor. It SHALL NOT force the prose markers on by
declaring the extracted text empty — those markers are ordinary English phrases
and the length floor is the only thing keeping them safe.

This applies to handlers that extract from HTML. Handlers consuming a structured
API are unaffected: a challenge page is not valid JSON and already fails them
into a non-`ok` verdict.

#### Scenario: An interstitial is not content

- **WHEN** a handler retrieves HTTP 200 whose body is a browser-verification or
  anti-bot interstitial
- **THEN** the handler returns a wall verdict, not `Verdict.ok` with the
  interstitial rendered as the page

#### Scenario: A fingerprinted wall is caught behind a long body

- **WHEN** the body carries a vendor fingerprint that cannot occur in prose
  (a turnstile widget id, an Akamai cookie name, a Baxia asset path) and its
  extracted text is long enough to clear the length floor
- **THEN** the handler still returns a wall verdict

#### Scenario: An article that quotes a wall phrase is not a wall

- **WHEN** a page has a full article body that happens to contain a catalogue
  prose marker — a cited title such as "Network Security Enhancements for
  Python 2.7.x"
- **THEN** the handler returns `Verdict.ok`; a prose marker under a full body is
  not evidence of a challenge

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

#### Scenario: All upstreams walled surfaces the wall

- **WHEN** every upstream in the list has been tried and at least one returned a
  challenge page
- **THEN** the handler returns `Verdict.block_page_detected`, so the wall is
  recorded as an observation and the terminal classifier can reach a `wall`
  outcome

#### Scenario: The handler does not pre-judge the whole cascade

- **WHEN** a tier-0 handler found every upstream walled but a later tier then
  retrieves the page
- **THEN** the response is `ok` and carries NO critical `try_user_browser` hint

The critical hint is attached by the cascade's failure floor on a `wall`
terminal, not eagerly by the handler. Whether a URL was retrieved AT ALL is a
property of the whole cascade, and a tier-0 handler does not yet know it; an
eager hint asserts "this URL was NOT retrieved" over a response that carries the
content (ADR-0009 protects against a silent miss, not against a loud false one).

#### Scenario: Order does not determine the outcome

- **WHEN** a randomised failover list contains both a working and a walled
  upstream
- **THEN** the result is the working upstream's content regardless of the order
  the two were tried in
