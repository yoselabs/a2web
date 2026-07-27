## ADDED Requirements

### Requirement: Sufficiency is checked regardless of which tier served the listing

The listing-completeness check SHALL run on every retrieval path that produced a
body, including paths that install pre-rendered markdown. A listing SHALL NOT
escape the sufficiency check because an anti-bot wall forced it onto the browser
tier.

This is the ADR-0009 sufficiency axis, and it was off across the entire
pre-rendered population — including the browser, which is the tier most likely
to be serving an infinite-scroll listing in the first place, because that is
what forced the browser. A truncated sample retrieved by the browser was
returned as a confident complete answer, which is the exact harm the capability
exists to prevent, on the exact population where it is most likely to occur.

#### Scenario: Browser-served truncated listing is reported partial

- **WHEN** a listing is retrieved by the browser tier, its rendered DOM advertises
  a total that exceeds the parsed record count beyond tolerance
- **THEN** the `listing_partial` signal and the `items_loaded` / `items_total`
  counts are emitted, exactly as on the raw tier

#### Scenario: Handler-served listing is reported partial

- **WHEN** a site handler installs pre-rendered markdown for a listing whose body
  carries a countable record region and a numeric oracle beyond tolerance
- **THEN** the sufficiency verdict is emitted rather than skipped

#### Scenario: Complete browser-served listing stays silent

- **WHEN** a browser-served listing's record count meets its oracle within
  tolerance
- **THEN** no partialness signal is emitted, as on any other path
