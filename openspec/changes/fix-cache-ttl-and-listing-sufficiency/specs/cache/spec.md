## ADDED Requirements

### Requirement: Cache TTL reflects content volatility

The TTL applied to a cached response SHALL be chosen from what the content is,
not from a substring test on its content-type header.

A content-type test that treats "not HTML" as "static" assigns the longest TTL
to the most volatile content a2web serves: the JSON and Atom responses its own
site handlers produce from upstream APIs. An issue list, a forum thread and a
paper listing are live data whose whole value is currency.

A response produced by a site handler from an upstream API SHALL default to a
short TTL. The long TTL SHALL apply only to content that is genuinely static.

#### Scenario: A handler's API response is not cached as static

- **WHEN** a site handler returns a response with a JSON or XML content-type
- **THEN** the cache entry receives the short, live-data TTL, not the static
  asset TTL

#### Scenario: A genuinely static asset keeps the long TTL

- **WHEN** a response is a static asset
- **THEN** the long TTL applies

### Requirement: A declared cache setting is read by the path it names

Every cache TTL setting exposed to operators SHALL be read by code. A setting
that is declared and never referenced SHALL be removed rather than left in
place.

An unread setting is indistinguishable, to the operator setting it, from one
that works. It reports as configuration and behaves as decoration.

#### Scenario: No unread cache setting survives

- **WHEN** the test suite runs
- **THEN** every TTL setting declared in `AppSettings` is shown to be read by at
  least one code path, and an unread one fails the suite naming it

#### Scenario: A renamed setting fails loudly

- **WHEN** a TTL setting is renamed and a reader is not updated
- **THEN** the read fails, rather than falling back to a duplicated literal
  default and silently changing behaviour
