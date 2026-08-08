## Why

The 2026-08-07 call-trace audit (`docs/findings/2026-08-07-a2web-call-trace-audit.md`,
2,856 real calls) found 885 calls — 31% of the entire corpus — are same-host
product-page drilldowns immediately following a listing fetch, because `ask`
returns prose about a listing rather than the per-row facts (price, stock,
rating) already visible in the page. 60 of those calls are the caller literally
re-querying the same URL with a re-worded question naming price/stock/variant —
data already inside `ListingOption.detail`, just not addressable as a field.

This reopens a considered Non-Goal from the change that introduced `options`
(`ask-retains-listing-options`, 2026-07-07): "Typed price/rating fields —
parsing those generically is per-site scar tissue; price/rating ride as the
record's own detail text." That call was correct for its time — `options` was
a skipped-content index nobody was expected to parse programmatically. The
audit is the new fact: callers parse `detail` back out via a second fetch
anyway, so the structured-field cost the Non-Goal was avoiding is being paid
regardless, just as re-fetches instead of as code.

## What Changes

- `ListingOption` gains typed commerce fields (`price`, `currency`, `rating`,
  `stock`, `seller`), each `None`/absent when not present at the listing's own
  JSON-LD/framework-state level — never guessed, never backfilled by a second
  fetch. `detail` stays as the free-text fallback for everything that doesn't
  fit a typed field (variant text, promo copy, etc.) and for options with no
  typed data at all (the DOM-mined path).
- Fields are sourced **only** from the JSON-LD / framework-state ladder rung
  (`_normalize_commerce_row` in `structured_render.py`), extended to also lift
  `offers.availability` → `stock` and `offers.seller` → `seller` — fields the
  function already has the parsed `offers` dict for for but currently
  discards. Price and currency are kept as separate typed fields on the wire
  (distinct from the synthetic markdown, which keeps rendering them combined —
  see design.md D3).
- No change to the DOM-region-miner path (`record_mine`) or to `Record` (a
  shelf type, generic across listings/threads) — typed fields are absent
  (`None`) whenever a page's `options` come from that path, per the
  already-locked precedence in `test_dom_records_keep_precedence_when_both_exist`.
- No change to `also_here`, `answer`, ranking, or tool signatures.

## Capabilities

### New Capabilities
(none — this extends an existing capability's shape, not a new one)

### Modified Capabilities
- `ask-response`: the `options` shelf requirement ("ask retains the parsed
  listing options") gains typed commerce fields, each independently optional;
  `detail` remains but is redefined as the free-text remainder /
  DOM-path fallback rather than the sole carrier of price/rating text.

## Impact

- `src/a2web/models.py` — `ListingOption` gains fields (additive, wire-shape
  change scoped to a listing-only, already-optional shelf; not a new required
  field, not a tool signature change — but still an envelope shape change,
  Ask-First per `AGENTS.md`).
- `src/a2web/packages/structured_render.py` — `_normalize_commerce_row` reads
  two more `offers` sub-fields it already has in hand.
- `src/a2web/fetcher_response.py` — `_records_to_options` populates the new
  fields from whatever normalized-row data survives to `RecordSet`/`Record`
  for the JSON-LD path (see design.md for the exact carry mechanism — `Record`
  itself is shelf-owned and stays untouched).
- Wire contract goldens (`tests/contracts/wire/*.json`) — re-bless.
- `openspec/specs/ask-response/spec.md` — extend the `options` requirement.
