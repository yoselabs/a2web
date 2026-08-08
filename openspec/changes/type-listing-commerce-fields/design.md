## Context

`ask` on a listing page projects the parsed structural record set into
`AskResponse.options: list[ListingOption]` (`title`, `url`, `detail`) — the
"rank, don't skip" shelf added by `ask-retains-listing-options` (2026-07-07).
`detail` carries whatever the record's own text held, price and rating
included, but as one opaque string.

Two producers can fill the underlying record set (`fc.record_set`), and their
precedence is already locked by a named test
(`test_dom_records_keep_precedence_when_both_exist`,
`tests/capabilities/link_affordances/test_json_ld_listing_index.py`): the
generic DOM-region miner (shelf `record_mine`, `extract_records`) writes
first if it fires at all; the JSON-LD / framework-state path
(`_escalate_via_json` → `_rows_to_record_set`) only fills the slot when the
DOM miner found nothing. "The fix is strictly ADDITIVE — it may never replace
an index that shipped" is the test's own words. This design does not touch
that precedence.

The JSON-LD path already normalizes commerce fields before they reach
`Record.text` — `_normalize_commerce_row()` in
`src/a2web/packages/structured_render.py:483` lifts `offers.price` +
`offers.priceCurrency` into a combined string and
`aggregateRating.ratingValue` into `rating`. It has the full `offers` dict in
hand but never reads `offers.availability` (schema.org's stock signal) or
`offers.seller`. Confirmed on `tests/fixtures/ld_json_product.html`
(`"availability": "https://schema.org/InStock"` present) that the schema.org
vocabulary carries this; confirmed on `tests/fixtures/hepsiburada_listing.html`
that a real listing-level JSON-LD `ItemList` — the corpus's #1 host, 602
calls — parses cleanly today with the DOM miner producing nothing (`extract_records`
returns `None` on that fixture), so JSON-LD wins by the fallback rule with no
precedence fight on at least this shape of page.

That same fixture's `ItemList` rows carry only `{name, image, offers:{price,
priceCurrency, url}}` — no `availability`, no `seller` — at the listing level;
those fields only showed up in the corpus's single-`Product`-page fixture.
This is a real, checkable ceiling, not a parsing gap: sites often only
publish stock/seller on the item's own page, not in the search-result JSON-LD
summary. The design has to represent that as "not stated here" rather than
implicitly promising the field can always be filled.

## Goals / Non-Goals

**Goals:**
- Type `price`, `currency`, `rating`, `stock`, `seller` on `ListingOption`,
  each independently optional, sourced only from the JSON-LD /
  framework-state ladder rung.
- Reverse the 2026-07-07 Non-Goal ("typed price/rating fields... per-site
  scar tissue") specifically for this source: it's a generic schema.org
  read, not per-site parsing, so the objection that motivated the Non-Goal
  doesn't apply to this scope.
- Keep `detail` as the free-text remainder / fallback, so nothing regresses
  for the DOM-mined path or for fields that don't fit the typed set.
- Make the "field wasn't in the source" case (stock/seller absent from a
  listing's own JSON-LD) legible as an honest gap, not silently `None`
  indistinguishable from "we failed to look."

**Non-Goals:**
- DOM-text mining for commerce fields. This is exactly the "per-site scar
  tissue" the 2026-07-07 Non-Goal warned about — regex/heuristic price
  sniffing on `record_mine`'s generic flattened `text` is a new correctness
  surface (false positives on non-price numbers, locale currency formats)
  and belongs to its own change if pursued, not bundled here.
- Touching `record_mine.Record` (shelf-owned, frozen, deliberately generic —
  shared with forum/thread mining) or `fc.record_set`'s DOM-wins precedence.
  Both stay exactly as `test_dom_records_keep_precedence_when_both_exist`
  locks them.
- Fetching an item's own product page to backfill stock/seller when the
  listing's JSON-LD doesn't carry it. That is the exact per-row-fetch cost
  this change exists to avoid; a filled-in field bought that way isn't a
  free win, and ADR-0012 (never manufacture) argues against a2web
  synthesizing data the page itself didn't assert at this level.
- Promoting `options`/rows to a first-class `rows` field replacing `answer`
  prose, or any other envelope restructuring beyond the new `ListingOption`
  fields. Out of scope for "ship the small version."
- Splitting the *synthetic markdown* rendering of price+currency (still
  combined per `listing-offer-lift` D3, for the LLM-facing view) — only the
  wire `ListingOption` fields split them (see D3 below).

## Decisions

**D1 — Reopen the 2026-07-07 Non-Goal, scoped to the JSON-LD source only.**
The prior Non-Goal's stated reason was "parsing those generically is
per-site scar tissue." `_normalize_commerce_row` already reads the
schema.org `offers`/`aggregateRating` vocabulary generically — no site-specific
code, works identically for hepsiburada, any other JSON-LD-emitting site, and
any future one. That's the opposite of scar tissue. The audit supplies the
counter-evidence the 2026-07-07 change didn't have: 60 corpus calls show
`detail`'s free text is not, in practice, "enough" — callers re-derive typed
facts from it via a second fetch. *Alternative rejected:* leave the Non-Goal
standing and treat this as `detail`-formatting polish instead (e.g.
"lead with price") — doesn't remove the re-fetch, since the caller still has
to parse prose to get a comparable field across rows.

**D2 — Carry typed fields via a parallel field on `RecordSet`/`Record`
population, not a new side-channel on `FetchContext`.**
`_rows_to_record_set` (JSON-LD path, `ladder.py:198`) already has the full
normalized row dict (`price`, `currency` — once split, see D3 — `rating`,
`stock`, `seller`) before it flattens to `Record.text`. Rather than adding a
new `fc.commerce_rows` list that `_records_to_options` would have to
zip back against `record_set.records` by position (fragile — any filtering
mismatch between the two lists silently misaligns row N's price with row M's
title), thread the typed values through as new optional fields already
attached to each `Record` the JSON-LD path builds, and read them in
`_records_to_options` when present.

This does NOT mean widening the shelf `record_mine.Record` dataclass — that
type is frozen and shared with the DOM/thread-mining path, which has no
commerce concept. Instead: a2web-local wrapper.
`_rows_to_record_set` already constructs `Record` instances one-for-one
from `rows`; keep the parallel `list[dict]` of normalized rows *alongside*
the `RecordSet` it built (e.g. return a tuple, or attach via a small
a2web-owned companion mapping keyed by list position within that single
function's scope — position-keyed is safe here specifically because both
lists are built in the same loop, unlike a cross-function zip). Only
`_records_to_options` (a2web code, not shelf) needs to know about it.
*Alternative rejected:* re-derive typed fields by re-parsing `Record.text`/
`detail` in `_records_to_options` — string-matching a rendered "3690 TRY —
⭐ 4.7" back into fields is the exact fragility this change exists to avoid
one layer up.

**D3 — Split `price`/`currency` on the wire; keep them combined in the
synthetic markdown.** `listing-offer-lift` D3 (2026-06-06) chose one
combined string specifically for the LLM-facing markdown the extractor
reads — that reasoning (the prose answer wants them together) still holds
for `content_md`/`fc.content_candidates`, untouched by this change. The
*new* consumer is a machine-facing typed field a caller programmatically
filters/sorts on ("show me options under 2000 TRY"), where a combined
string forces the caller to parse it right back apart — reintroducing the
same class of problem this whole change is fixing. The two renderings
diverge from the same source dict without conflict because they're now two
different call sites reading two different fields of the same normalized
row.

**D4 — `stock`/`seller` absence is `None`/omitted, not a `found: false`
sentinel — for this change.** The audit's broader "typed missing-field
report" idea (`fields: {price: {found: false, reason: ...}}`) is a bigger
envelope-shape decision affecting more than `ListingOption`, and is its own
audit recommendation (#2), not this one. Here, a `None` field on an
already-optional, per-row shelf entry is legible enough: the caller sees a
list where some rows have `stock` and some don't, which is a materially
different (and more honest) reading than a single opaque `detail` string
that appeared to already cover "everything the page had." Revisit if the
full typed missing-field change lands and wants a shared representation.

## Risks / Trade-offs

- **[Coverage looks bigger than it is]** — because DOM-mined listings
  (whenever `record_mine` fires) get zero typed fields by design (D2/Non-Goals),
  a caller could read "no price field" as "page has no price" when really
  it's "this page's index came from the DOM path." → Document on
  `ListingOption` itself (docstring) that typed fields are JSON-LD-sourced
  only and their absence says nothing about whether the page shows the data;
  `detail` remains the exhaustive fallback either way, so no information is
  lost, only some of it stays untyped.
- **[`stock`/`seller` may rarely populate at all]** — per the fixture
  finding, listing-level JSON-LD often omits them even on sites that emit
  rich JSON-LD for price. → Ship anyway (price/currency/rating alone
  address the bulk of the 60 re-query calls, which are dominantly
  price/stock-worded but the audit's own price-specific tally, 68 calls, is
  the surer win); note in the PR/bead that stock/seller coverage should be
  measured post-ship via a follow-up corpus sample rather than assumed.
- **[Envelope re-bloat]** — mitigated by the existing `_OPTIONS_DETAIL_BUDGET`
  /cap machinery on the shelf; typed fields are short scalars (a price
  number, a 3-letter currency, a rating float) and don't meaningfully add to
  the per-option byte cost the existing budget already accounts for via
  `detail`. Confirm in tasks with a byte-budget test alongside the existing
  `test_option_shelf_byte_budget.py`.
- **[D2's position-keyed carry breaks if row-filtering diverges]** — if a
  future edit makes `_rows_to_record_set` skip a row that its parallel
  normalized-dict list still includes (or vice versa), row N's price
  silently pairs with row M's title. → Keep the two lists built from a
  single loop over the same `rows` input (as designed), and add a test
  asserting per-row identity (e.g. title substring match) between a
  `ListingOption` and its source dict, not just field presence.

## Migration Plan

1. Extend `_normalize_commerce_row` to lift `offers.availability` → `stock`
   (map schema.org `https://schema.org/InStock`-style URIs to a short
   enum/string) and `offers.seller.name` → `seller`; keep `price` and
   `priceCurrency` as separate output keys instead of pre-joining them
   (the join moves to the markdown renderer only).
2. Update the markdown renderer (`_render_rows` / `_rows_to_md_records`) to
   join `price`+`currency` back into one display string, since it now
   receives them split — no visible change to `content_md` output.
3. Carry the typed fields from `_rows_to_record_set` through to
   `_records_to_options` per D2; add `price`, `currency`, `rating`, `stock`,
   `seller` fields to `ListingOption` (all optional, default `None`/absent
   on the wire, same omit-empty discipline as the rest of the model).
4. Update `openspec/specs/ask-response/spec.md`'s "ask retains the parsed
   listing options" requirement with new scenarios (typed fields present on
   a JSON-LD-sourced listing; typed fields absent on a DOM-mined listing;
   `stock`/`seller` absent when the source JSON-LD didn't carry them).
5. New/updated capability tests: extend
   `tests/capabilities/link_affordances/test_json_ld_listing_index.py` and
   `tests/capabilities/ask_response/test_listing_options.py`; add the
   row-identity test from the Risks section.
6. Re-bless wire contract goldens (additive field, `make bless-wire`).
7. This is an envelope shape change → Ask-First confirmation before
   implementation, per `AGENTS.md`, same as `a2web-7bj.12`.

## Open Questions

- Exact `stock` representation: raw schema.org URI tail (`InStock`,
  `OutOfStock`, `LimitedAvailability`, ...) passed through as a string, or a
  normalized closed enum? Leaning string passthrough (mirrors how `price`
  already carries the site's own currency code verbatim) — decide at
  implementation time against what the fixtures/live corpus actually emit.
- Whether `seller` should be a plain string (name only) or carry a URL too
  (schema.org `Organization` can have both) — decide against what real
  listing JSON-LD actually populates; don't design a shape for a field
  never observed non-empty.
