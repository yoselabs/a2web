# Finding — `also_here` on narrow asks: two distinct causes (2026-07-11)

## Trigger

Thin post-v2 sanity checks + a user-flagged Koçtaş product query returning **no
suggested URLs and no same-page index** — suspicious for an e-commerce page.

```
uv run a2web web query \
  --url=".../einhell-te-cd-18-48-li-i-darbeli-matkap-.../p/5001125801" \
  --query="What is the price of this product, its currency, and is it in stock?"
→ answer: "Price: 4,221.97 TRY ... In stock."   (also_here / other_pages absent)
```

## Instrumented probe (provider=claude-code, guarded — $0 metered)

```
structural_form:    product
content candidates:  trafilatura(1343), json_synth(1067), json_synth(622), json_synth(195)
content_md total:    1604 chars   ← THIN
digest gate fires:   TRUE   (json_synth present) ; links: 55
routing.also_here:   []
routing.other_pages: []
```

**What the extractor actually saw** (all ~1.6k chars): the product JSON-LD
(name / manufacturer / price / stock / sku), OpenGraph meta, breadcrumbs, and a
"question-posting criteria" FAQ blob. **No spec table, no description body, no
reviews.** Koçtaş renders all of that client-side (heavy SPA); the raw +
json_synth tiers only ever saw price/stock.

## Two distinct causes — do not conflate

1. **Koçtaş: an SPA UNDER-FETCH, not an under-index.** `also_here: []` is
   *correct* — a2web indexed nothing because it fetched nothing beyond
   price/stock. `other_pages: []` is *correct* — the 55 links are category nav,
   and the reviews link is JS-rendered (surfacing a guessed one violates
   ADR-0014). The narrow answer succeeded, so the gate never escalated to a
   browser render. **Open lever (un-decided):** should a2web browser-render a
   thin SPA product page for completeness even when the narrow answer already
   succeeded? Cost vs completeness — a separate change, not this one.
   Corpus: `koctas-product-spa-thin-fetch` (class `spa`).

2. **A real prompt gap on RICH pages, now fixed.** On a page whose body *does*
   carry the unsurfaced sections, the model was treating "answered the asked
   question" as "covered the page" and emitting `also_here: []`. Fixed by
   strengthening the clause: **"covered" = relayed everything the page holds,
   NOT merely answered the question**; a narrow ask on product/article/
   reference/thread almost never covers the page → index the unsurfaced sections.
   (`EXTRACT_ROUTER_V1` v6 → v7, change `also-here-indexes-rich-pages`.)

## Validation (the fix works — on a page that actually has the content)

Wikipedia (`Rust_(programming_language)`, 41,918 chars, server-rendered), narrow
ask "who created Rust and when":

```
also_here: ['stable release version', 'developer / core team composition',
            'Rust Foundation founding date + members',
            'language paradigms + influences',
            'memory safety mechanism (borrow checker)',
            'ecosystem tools (Cargo, Clippy, Rustfmt, rust-analyzer)',
            'adoption timeline: Mozilla 2009, 1.0 release May 2015, Foundation Feb 2021']
```

7 terse query-grammar entries indexing the unsurfaced sections — the
withheld-body index working as designed. Corpus: `wikipedia-narrow-ask-indexes`.

## Not a cost spike

Both the thin bench cell and every probe ran on the `claude-code` subscription
with the cost guard active — **$0 metered**. The primary "nothing spikes"
concern is clean.
