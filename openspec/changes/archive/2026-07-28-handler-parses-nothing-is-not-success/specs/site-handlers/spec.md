## ADDED Requirements

### Requirement: A handler that parsed nothing does not report success

A site handler whose success is defined by a parse yielding units — entries,
records, items, posts — SHALL consult that yield before choosing a verdict. A
zero-unit parse SHALL NOT return `Verdict.ok`.

A handler that matched nothing has no evidence about the page. It cannot
distinguish a genuinely empty listing from stale selectors, and those are the
two sides of the empty-vs-wall invariant. The honest verdict is the one that
lets the cascade try another tier.

Nor SHALL a handler's rendered output assert a count it did not observe. A
render of the form "Papers (0)" presents a parse failure as an observation about
the page.

Where a handler cannot distinguish "parsed nothing" from "parsed a genuinely
empty page", this requirement SHALL NOT be applied to it — a handler that
returns non-`ok` on a real empty listing sends the cascade to a browser for
nothing. That distinction is per-handler and is established by inspection, not
assumed.

#### Scenario: Stale selectors do not read as an empty page

- **WHEN** a handler's parse yields zero units because the site's markup changed
- **THEN** the handler returns a non-`ok` verdict and the cascade continues to
  another tier
- **AND** the handler does not render a body asserting that zero units exist

#### Scenario: Success requires yield

- **WHEN** a handler parses a listing and finds entries
- **THEN** it returns `Verdict.ok` with those entries rendered

#### Scenario: A verbose empty render is still not success

- **WHEN** a handler's zero-unit render is long enough to clear the quality
  gate's length floor
- **THEN** the verdict is still non-`ok` — the guard is the parse yield, not the
  rendered length

### Requirement: Handler listing parses read the DOM, not byte patterns

A handler that extracts structured units from HTML SHALL do so by parsing the
document, not by matching regular expressions against its bytes. Attribute quote
style, attribute order, and whitespace inside tags are not part of a page's
meaning, and a parse that depends on them fails silently when they change.

This applies to markup. Regular expressions over URLs, JSON strings, or free
text are unaffected.

#### Scenario: Quote style is not a failure mode

- **WHEN** a page serves single-quoted attributes where it previously served
  double-quoted ones
- **THEN** the handler's parse is unaffected

#### Scenario: Entries are scoped to their container

- **WHEN** a listing page carries anchors outside the listing container that
  resemble entry links
- **THEN** they are not counted as entries

## MODIFIED Requirements

### Requirement: arXiv listing handler matches and populates candidates

An `ArxivHandler` SHALL extend `matches(url)` to additionally return `True` for category-listing URLs of the form `https?://arxiv.org/list/<cat>/<yymm>` and `https?://arxiv.org/list/<cat>/recent`. On a listing URL the handler SHALL fetch the listing HTML, parse the entries **from the document structure** (the `dl` listing container and its `dt`/`dd` pairs), and populate `TierResult.next_links` with up to 10 abs-page links, each built as:

- `anchor` — the paper title (truncated to 120 chars if longer)
- `url` — `https://arxiv.org/abs/<id>`
- `reason` — comma-joined author surnames (truncated to 80 chars)
- `kind` — `"drilldown"`

A listing parse yielding zero entries SHALL NOT return `Verdict.ok`.

> The prior wording said "parse the entries" without saying how, and the
> implementation used three regexes requiring double-quoted attributes and no
> space before `=`. arXiv serves neither. Measured 2026-07-28: 0 entries on the
> live page, `Verdict.ok`, a 40-char body reading `## Papers (0)`. The guard test
> stayed green throughout because its fixture was hand-written to match the
> regexes rather than captured from arXiv.

#### Scenario: Category listing matches

- **WHEN** `ArxivHandler().matches("https://arxiv.org/list/cs.LG/2401")` is called
- **THEN** the return value is `True`

#### Scenario: Listing populates abs candidates

- **WHEN** the handler parses a listing page with 15 entries
- **THEN** `TierResult.next_links` contains exactly 10 entries, each with `kind == "drilldown"` and `url` matching `https://arxiv.org/abs/<id>`

#### Scenario: Listing parses a captured live page

- **WHEN** the handler parses a fixture captured from the live arXiv listing
- **THEN** the entry count equals the `dt`/`dd` pair count of the committed
  capture, established once by inspection
- **AND** each entry carries a title and authors distinct from its id

> NOT "the count the page advertises for itself" — there is no such single
> number. The page carries per-section counts (`showing 47 of 47`), a partial
> marker (`showing first 3 of 110`), and a `Total of 408 entries` footer, and it
> renders a variable number of day-sections between requests. A guard written to
> the advertised count would be unimplementable, or would pin one section and
> pass while the parser dropped another.

#### Scenario: A multi-section listing yields every section's entries

- **WHEN** the listing renders more than one day-section inside its container
- **THEN** entries from every section are parsed, not only the first

#### Scenario: Zero parsed entries is not success

- **WHEN** the listing container is absent or yields no `dt`/`dd` pairs
- **THEN** the handler returns a non-`ok` verdict rather than rendering `Papers (0)`

#### Scenario: Single abs URL still returns empty candidates

- **WHEN** the handler runs on `https://arxiv.org/abs/2401.12345`
- **THEN** `TierResult.next_links == []`
