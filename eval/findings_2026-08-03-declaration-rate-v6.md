# Finding — v6: the multiplier is 7-17%, and the corpus says why (2026-08-03)

`eval/spikes/declaration_rate_v6.py`, 44 URLs from `eval/corpus.yaml`.
No LLM — fetch, parse JSON-LD, label, count.
Raw: `eval/spikes/declaration_rate_v6_summary.json`.

v4/v5 settled the conditional: *given* a page declares a subject entity,
relaying the first ~20 fields adds real coverage for ~360 wire tokens. The
feature's value is that lift times **how often the antecedent holds**. This is
the multiplier.

---

## Result

```
  44 urls, 42 retrieved (2 walled to a stub from this machine)

    subject       3    Product                          <- feature fires
    unknown       4    ProductGroup, DiscussionForumPosting,
                       NewsMediaOrganization, Store      <- fires too, see below
    document      7    Article / WebPage / WebSite       <- structural_form, no lift
    none         28    retrieved fine, publishes no JSON-LD
    unreachable   2

    RATE = 7.1% .. 16.7%   of retrieved pages
    distinct hosts firing: 5 of ~35
    fields when it fires : 22.3 raw -> 19.3 after cap-20
```

**Expected value of the feature, averaged over this corpus:**

```
  +0.20 lift  x  0.07..0.17 rate  =  +0.014 .. +0.034 coverage
  cost paid only on the 7-17%     =  ~360 wire tokens there, 0 elsewhere
```

Small in the mean. **Not** small where it fires: a `Product` page goes from a
prose answer to the publisher's own price / availability / sku / brand /
rating, exactly, for free.

---

## I shipped the ADR-0018 defect inside the spike measuring it

The first run reported **7.1%** flat. That number was wrong, and wrong in a way
this repo has a named rule against.

`_label()` is a **label table** (v4 wrote it that way, deliberately, citing
ADR-0018). The bucketing code then did:

```python
elif labels:          # anything not in the SUBJECT list
    bucket = "document"
```

Which turned the label table back into a **gate**. Everything a2web's closed
vocabulary did not recognise was filed as "document metadata, no lift":

```
  nike        ProductGroup             74 fields   <- a product. 74 fields.
  v2ex        DiscussionForumPosting   51
  reuters     NewsMediaOrganization    35
  bhklima     Store                     3
```

It understated the answer by **more than half** (7.1% -> 16.7%). ADR-0018 exists
because a closed vocabulary discards what it does not know; the spike sent to
measure how much gets discarded discarded it the same way. Fixed: `unknown` is
its own bucket, counted, never folded, and the headline is a **range** so
neither bound can be quoted alone.

This is also the strongest evidence ADR-0018 has. Its own counter-evidence
section conceded the ceiling looked "cheap today (2 dropped types / 26 pages)".
Here the closed list dropped **4 of 7 firing pages, including the richest one.**

---

## Why the rate is this low: read the corpus classes

```
  listing     10    none 10                <- 100% no declaration
  gated       11    none 7, unknown 2, document 1, unreachable 1
  affordance  10    subject 2, unknown 1, document 2, none 5
  comments     4    none 3, unknown 1
  article      2    document 2             <- declares, but about the DOCUMENT
  spa          2    none 2
  clean        5    subject 1, document 2, none 1, unreachable 1
```

**Every listing page in the corpus declares nothing subject-level.** That is not
a measurement artifact — a listing's subject *is* the list, and publishers emit
`ItemList`/`CollectionPage` (document-shaped) or nothing.

So the corpus is **biased against** the feature, and knowably so: `eval/corpus.yaml`
was assembled for fetch difficulty (walls, SPAs, soft-404s, affordances) and for
listing/index behaviour, which are precisely the classes that do not declare.
Commerce product pages — where the feature is strongest — appear about six times
and most are walled from this machine.

**Both directions of bias are real and I am not going to pick one:**

- The corpus **understates** the rate for a2web's commerce traffic (product
  pages declare heavily; this corpus barely contains reachable ones).
- The corpus **overstates** nothing — 28 of 42 pages publishing no JSON-LD at
  all is a fact about the open web, not about a2web.

The honest statement is: **7-17% here, higher on commerce, ~0% on listings.**

---

## Limits

1. **n=42, one corpus, one machine.** No proxies, no paid keys, jina
   unreachable — 2 URLs walled to a stub and excluded rather than silently
   counted as "publishes nothing" (the v3 defect).
2. **The upper bound assumes `unknown` types are subject-level.** Three of the
   four clearly are; `Store` (3 fields) is marginal. The true rate is nearer the
   top of the range than the bottom, but I did not adjudicate each one.
3. `_MIN_HTML = 2000` is the stub cutoff. A wordier interstitial above it would
   be miscounted as `none`.

---

## What follows

1. **Ship it, capped at 20, and let it be silent when it does not fire.** The
   cost profile is right: ~360 tokens on 1 page in 6-14, zero on the rest. There
   is no case where it makes a page worse.
2. **Do not gate on `_ENTITY_TYPES` or any closed list.** Measured, not
   asserted: the closed list drops 4 of 7 firing pages including a 74-field
   `ProductGroup`. Pass the declared type through as a string, labelled. This
   promotes ADR-0018 from Proposed to backed-by-measurement.
3. **Set expectations honestly.** This is not a semantic interface to the web.
   At 7-17%, with `Article`/`WebPage` dominating what *is* declared, the data to
   query the web by meaning is not being published. That is a finding about the
   web, not about a2web, and it caps the grand version of the idea regardless of
   what a2web builds.
4. **The listing result is the interesting residue.** Listings are a2web's
   highest-value class (`next_links`, `other_pages`, ADR-0015) and declare
   nothing subject-level, ever. Whatever index quality comes from, it will not
   come from schema.org.
