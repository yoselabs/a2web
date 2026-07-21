# Design

## The conflation, stated precisely

`length_floor` answers two questions with one verdict:

```
  "is this page thin because it is WALLED?"   ← block-detection (what the floor is FOR)
  "is there enough content to extract?"       ← content-sufficiency (what it's USED as)
```

For a walled page these coincide (a wall renders thin). For a genuinely small
complete page they diverge: it is thin AND complete AND unwalled. The gate,
running before extraction and proceeding only on `verdict == ok`, treats the
second question as answered "no" whenever the first heuristic fires — so a
complete 230-char page never reaches the extractor that could answer from it.

## Why a sibling to `is_confirmed_empty`, not an edit to it

`is_confirmed_empty` promotes a thin page to an "no results" *assertion of
absence* — a strong, cacheable-forbidden claim reserved for search-shaped URLs
where "0 results" is a meaningful, verifiable state. A complete small page is a
different claim: not "there is nothing here" but "what is here is small and
whole". Folding a non-search branch into `is_confirmed_empty` would blur the two
claims and weaken the search-shaped guard that keeps the empty promotion honest.
So: a separate predicate, sharing the evidence primitives (`has_hard_wall_evidence`,
`has_subresource_block_evidence`) but with its own terminal term.

```
  is_confirmed_empty            is_complete_small_page
  ──────────────────            ──────────────────────
  browser render read empty     browser render read the SAME small content
  HTTP tier returned a body      HTTP tier returned a body
  no 4xx / challenge             no 4xx / challenge
  no subresource_blocks          no subresource_blocks
  no hard-wall evidence          no hard-wall evidence
  is_search_shaped(url)   ◄──┐   (no URL-shape term)
                             └── the ONLY differing term
  → synthetic "no results"       → extractor runs on the real body
  → NEVER cached                 → cacheable? (open)
```

## Preserving the false-positive asymmetry

The empty-vs-wall invariant errs toward the wall side because a false "no results"
is a confident silent miss (the ADR-0009 harm). The same asymmetry applies here:
a false "complete small page" could present a *walled* 230-char shell as a
complete answer. The corroboration term is what defends against it — a wall that
200s with a thin shell would have to survive an independent browser render (which
watches subresources) *also* coming back thin with no subresource blocks. That is
exactly the walled-API fake-empty case the invariant was built around, and the
same browser-as-second-retrieval defense applies. If any wall evidence appears,
the page stays a `failed` `content_thin` — never promoted.

## Open decisions for confirmation

1. **Cacheability.** The empty promotion is never cached because a wrongly-cached
   empty is a repeating silent miss. A complete small page is real content, so
   caching is *correct when the promotion is correct* — but a false positive would
   cache a wall. Options: (a) cache it (trust the corroboration conjunction), (b)
   wire-only like the empty promotion (safe, re-fetches on repeat). Recommendation:
   (b) initially — the corroboration already cost a browser render, so not caching
   repeats that cost, but the safety matches the empty sibling and can be relaxed
   later if false positives prove absent.

2. **Confidence.** `low` (it is still a thin page) vs `medium` (two independent
   tiers agree on the content). Recommendation: `low` — the floor fired, and low
   confidence signals the caller to sanity-check, consistent with a thin page.

3. **"Substantially the same content".** A similarity threshold invites tuning
   noise. Recommendation: the weaker, robust predicate — both renders are
   non-empty AND both under the floor AND neither carries wall evidence. Agreement
   on *thinness without a wall* is the signal; byte-similarity is not required and
   would be fragile against trivial render differences.

4. **Escalation cap.** Bare-fallthrough `length_floor` gets exactly one browser
   render (the corroborating witness), not the current up-to-two. A floor
   violation that DOES carry wall suspicion keeps the existing escalation budget.
