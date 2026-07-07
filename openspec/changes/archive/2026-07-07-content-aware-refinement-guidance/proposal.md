## Why

When a fetch returns a truncated listing, a2web today emits an honest `listing_partial`
hint but nothing that lets the caller actually *escape* the truncation. Worse, the
retrieved sample is often not just partial but **biased**: a search sorted by ascending
price (`&siralama=artanFiyat`) returns the cheapest N of 1123, so any "best product"
judgment over that batch is systematically wrong — the tool silently launders a biased
sample into a confident shortlist. The only affordances offered ("narrow your query",
"open in a browser tool") are a dead end for a caller whose only web tool *is* a2web.

The fix is not per-site pagination (an unwinnable per-site/per-region parsing war) but
to give the reasoning model — server-side on `ask`, or the caller's own model on
`fetch_raw` — enough **context** to narrow intelligently, plus content-type-keyed
guidance on what matters for the kind of page in hand. This is the never-silently-miss
tenet (ADR-0009) applied one level up: a biased sample is also an unfinished job, and
the tool should say so and hand over the levers to finish it, without ever knowing a
single website.

## What Changes

- **Surface a context bundle as reasoning fuel**, not a prose verdict: the requested URL
  with its query params parsed but **uninterpreted** (opaque `key=value` pairs), the
  already-computed page kind, and the `items_loaded` / `items_total` counts — assembled
  deterministically with zero site or language knowledge, so the model (server-side or
  caller-side) can decode meaning itself.
- **LLM-side partialness detection on the `ask` path**, so a truncated listing is caught
  even when the regex count oracle's noun list misses the page's language (RU `товаров`,
  JP `件`, …). The regex oracle becomes a cheap fast-path, not the sole gate — closing
  the region-coverage gap that a distributed tool depends on.
- **Content-type-keyed guidance**, dynamically composed per-fetch from the existing
  closed `structural_form` / `shape` / `genre` enums (per-**kind**, never per-site):
  injected into the server-side extraction prompt on `ask`, and/or surfaced as guidance
  in the returned envelope for the caller's model on `fetch_raw`. This is *not* a change
  to the static MCP tool description (which MCP cannot vary per-fetch).
- **Dimensional refinement axes on a partial listing**: the model proposes *axes to
  re-query on* (add a price floor, sort by rating, split by connector sub-type, narrow by
  brand) — **never specific values** drawn from the biased sample. The dimensional-only
  discipline prevents laundering a truncated read into a biased recommendation.
- Explicitly **kills deterministic pagination** as a non-goal: no `page` / `offset` /
  cursor parameter, because paging contracts are per-site chaos (`?sayfa=`, cursor tokens,
  POST bodies, signed scroll tokens) and a generic param that silently no-ops on most
  sites is worse than none.

## Capabilities

### New Capabilities
- `refinement-guidance`: content-type-keyed guidance and dimensional refinement axes,
  reasoned over the content-in-hand plus the uninterpreted URL context bundle, keyed off
  the existing closed content-kind enums. Site- and language-agnostic by construction
  (the reasoning lives in the model, not in a parser). Axes are dimensional-only on a
  biased/partial sample — never values.

### Modified Capabilities
- `listing-completeness`: partialness detection SHALL also be reasoned LLM-side on the
  `ask` path (not gated solely on the language-limited regex count oracle), so truncation
  is caught across regions the noun list does not cover. The regex oracle remains the
  deterministic fast-path.
- `ask-response`: the ask envelope SHALL carry the dimensional refinement axes (conditional
  field, omitted when absent) on a partial listing, and MAY carry the content-type guidance.

## Impact

- **Code**: `src/a2web/fetcher.py` (partialness detection seam; context-bundle assembly on
  `FetchContext`), `src/a2web/fetcher_response.py` (surface parsed query params + guidance),
  `src/a2web/models.py` (new conditional refinement-axes field on `AskResponse`; optional
  guidance field), `src/a2web/packages/llm_extract/prompts.py` + `extractor.py` (per-kind
  guidance fragment; dimensional-axes reasoning + wobble parse of the axes), `listing_oracle`
  stays as the fast-path.
- **Wire contract**: additive, conditional fields on `AskResponse` (omit-empty via
  `_prune_wire`) — no breaking change to existing parsers; no tool-signature change (Ask-First
  gate not triggered). The static MCP tool description is unchanged.
- **Constitution**: reinforces substrate-indifference — the load-bearing logic is model
  reasoning over content, not a per-site facet parser. No new top-level dependency.
- **Non-goal**: deterministic per-site pagination (explicitly out of scope).
