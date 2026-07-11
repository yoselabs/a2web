## Why

The withheld-body index (`also_here`, ADR-0015) under-fires on rich pages. When
a narrow factual ask is run against a page whose body carries sections the answer
did not surface, the model reads "answered the asked question" as "covered the
page" and emits `also_here=[]`. Indexing the withheld content is the entire point
of withholding the body; the clause must fire.

Surfaced while investigating a Koçtaş product query that returned an empty index
(`eval/findings_2026-07-11-also-here-underfires.md`). Koçtaş itself turned out to
be a *separate* problem — an SPA under-fetch (only ~1.6k chars of price/stock
JSON-LD reached the extractor; specs/reviews are client-rendered), where
`also_here=[]` is actually correct. But the same investigation confirmed the
rich-page gap on Wikipedia, which this change fixes.

## What Changes

- Strengthen the `also_here` clause in `EXTRACT_ROUTER_V1` so **"covered"** means
  *relayed everything the page holds on the topic* — NOT merely *answered the
  asked question*. A narrow ask on a `product` / `article` / `reference` /
  `thread` almost never covers the page, so index the unsurfaced sections. Keep
  the `listing` carve-out (defer to `options` / `refinement_axes`) and the
  genuinely-thin-page escape (emit nothing only when nothing is left unreturned).
- Bump `EXTRACT_ROUTER_V1` version 6 → 7 (wording change, same `name`).

## Capabilities

### Modified Capabilities

- `extraction`: the `also_here` router-prompt instruction gains the
  covered-the-PAGE-not-the-QUESTION distinction.

## Impact

- `src/a2web/packages/llm_extract/prompts.py` — `_ROUTER_SCHEMA_DOC` also_here
  clause + version bump + history comment.
- Validated by a thin live spike on `wikipedia-narrow-ask-indexes` (rich
  server-rendered page): `also_here` now yields 7 terse query-grammar entries
  where it was empty. Koçtaş captured separately as `koctas-product-spa-thin-fetch`
  (the SPA under-fetch lever). Cheap/subscription provider only — never metered.
