## Context

`a2web-axb` shipped a downgrade-only confidence cap + `served_url_differs`
hint when the served page's registrable domain differs from the requested
URL's (`build_response`, `fetcher_response.py:922-943`). That is a
deterministic, URL-level signal — it catches redirect/content swaps but is
structurally blind to the audit's §4a2 shape: the served page IS on the
right site, but is the wrong product/entity relative to the caller's `ask`
(hepsiburada `pindstrup` → shade cloth; `kekkila` → calcium nitrate; kaspi
`AMT M-1` → unrelated computer/auto parts). There is no URL-level signal for
this; it needs comparing the caller's query against what the page actually
served.

**The naive version doesn't work.** Comparing the query against `fc.title`
(the page's `<title>` tag) looks like the obvious move, but a marketplace
search-results page's `<title>` conventionally echoes the search term
regardless of result relevance ("pindstrup arama sonuçları" / "search results
for pindstrup") — that pattern shows ZERO mismatch exactly in the cases the
audit flagged, since the title always contains the query term even when
every listed item is unrelated. The signal has to come from what was
actually SHOWN, not the chrome around it.

This change was implemented immediately after `type-listing-commerce-fields`
(a2web-gvy), which is what makes the right signal available: `fc.record_set`
(when the page is a listing) carries the individual item titles
(`record.heading_text`) the page actually returned. Comparing the query
against those — not the page title — tests the thing that actually matters:
did the marketplace's own search return anything related to what was asked.

**The caller-facing query is reliably English.** `routers.py`'s `query`
tool description examples are all English ("return policy", "battery vs
mains life", "RTX 4090 price, stock") regardless of the fetched page's
language — a2web's calling convention, not a coincidence of the corpus. That
matters for scope: the "locale handling for Turkish/Russian terms" the bd
issue flags as a risk is about the SERVED content's language (item titles),
not the query's. The query side needs no locale-specific vocabulary at all.

## Goals / Non-Goals

**Goals:**
- Catch the audit's zero-overlap failure mode: a listing query returns items
  that share no substantive term with what was asked, on a same-domain page.
- Reuse the exact mechanism `served_url_differs` established — downgrade-only
  confidence cap, a new `operator_hints` code, no envelope shape change.
- No new dependency — stdlib normalization only, matching the rest of this
  module's style (`registrable_domain`, `_is_commerce_shaped`).
- A query with no substantive (non-operator) tokens produces NO signal
  (skipped, not flagged) rather than a guess — the common "browse a category"
  query shape (`"list top laptops under $500"`) has no product identity to
  compare and must not misfire.

**Non-Goals:**
- The confusable-model-variant shape on a SINGLE product page (Lenovo
  15AKP10 asked, 15IRX10 served) — there are no listing item titles to check
  against on a detail page, and the signal there is inherently partial-overlap
  (both strings share "Lenovo", differ only in a model suffix), which is a
  materially harder, higher-false-positive-risk problem than exact
  zero-overlap. Its own design pass, own bead, if pursued.
- Any per-listing-item flagging, or filtering/hiding mismatched items —
  ADR-0012 (never manufacture a selection): this only affects `confidence`
  and adds an explanatory hint, exactly like the domain check. `answer` and
  `options` are untouched.
- A curated per-locale stopword list for the SERVED side. The served item
  titles need no stopword filtering — length-floor + exact-token-match
  already excludes short function words without a maintained list.
- Stemming, fuzzy/edit-distance matching, or any new dependency. A future
  change can revisit if plain token overlap proves too strict in practice
  (measured via `make bench`, not assumed here).
- Partial-overlap thresholds ("share at least 50% of tokens"). Zero-overlap
  is the one unambiguous signal in this data; a partial threshold is exactly
  the "threshold tuning against false positives on legitimate paraphrase"
  risk the bd issue calls out, and is not resolved by this change.

## Decisions

**D1 — Compare against served item titles (`record_set.records[].heading_text`),
not the page `<title>`.** As argued in Context: the page title echoes the
query on a search-results page regardless of relevance, defeating the
signal exactly on the audit's own failure cases. Item titles are what the
site's search actually returned, which is the fact in question. Consequence:
this check is scoped to LISTING pages only (`structural_form == "listing"`
AND `fc.record_set` non-empty) — a single-entity page has no item titles to
compare against, which is also why the confusable-variant shape (a
non-listing shape) is out of scope here rather than half-addressed.
*Alternative rejected:* compare against `fc.title` — cheaper (no listing
gate needed) but structurally blind to the failure mode this change targets.

**D2 — All-or-nothing across the served set, not per-item.** Flag only when
NONE of the parsed item titles share a substantive token with the query;
if even one item overlaps, don't flag. A marketplace search legitimately
returns some off-target results alongside relevant ones (normal ranking
imprecision) — flagging that would make the hint noise. The audit's actual
failure cases are total misses (every returned item is a different category),
which all-or-nothing catches cleanly. *Alternative rejected:* a coverage
threshold ("flag if <20% of items overlap") — introduces exactly the
partial-threshold tuning problem the Non-Goals exclude, for a case the
audit data doesn't evidence.

**D3 — A small, fixed, English-only operator-word list stripped from the
QUERY side only; zero substantive tokens after stripping means SKIP, not
flag.** Per Context, the query is reliably English by a2web's own calling
convention, so this is a ~20-word constant, not a locale-maintenance
liability (`price, stock, review, reviews, rating, vs, versus, compare,
comparison, best, top, cheapest, list, spec, specs, availability, delivery,
warranty, color, colour, size, alternatives, in-stock, stock?`). A query like
`"price, stock"` (the tool's own example for a specific product already
identified by the fetched URL) strips to nothing — correctly SKIPPED, not
flagged, because there is no product-identity token in the query to check at
all; a query like `"RTX 4090 price, stock"` strips to `{rtx, 4090}` and
proceeds. *Alternative rejected:* no stopword list, compare all query
tokens — a bare `"price, stock"` query would then need to find "price" or
"stock" literally inside a served item title to avoid a false flag, which
fails constantly (item titles are product names, not price/stock language),
making the check unusable on the exact query shape the tool's own examples
recommend.

**D4 — Normalization: casefold + Unicode NFKD, strip combining marks, split
on non-alphanumeric, drop tokens under 3 chars. No stemming.** Handles
Turkish/Cyrillic diacritics on the SERVED side generically (NFKD decomposes
`İ`/`ı` and combining marks; casefold handles case-insensitive comparison
across scripts reasonably) without a language-specific library. A brand or
model token (`"RTX"`, `"pindstrup"`, `"kekkila"`) that appears verbatim (or
near-verbatim after normalization) in a served item title is exactly the
signal this needs; stemming would add a real dependency (none exists in this
repo today, `pyproject.toml` has no stemming/fuzzy-match library) for a
capability the audit's evidence doesn't require — every zero-overlap failure
case is a clean brand/category miss, not a near-miss inflection difference.
*Alternative rejected:* add `snowballstemmer` or similar — Ask-First
top-level dependency for a capability not evidenced as needed yet.

**D5 — Reuse the exact confidence-cap + hint shape `served_url_differs`
established; independent of it, both can fire.** Downgrade-only (`high` →
`medium`, never raises), new hint code `query_title_mismatch`, same
`OperatorHint` construction pattern as `served_url_differs_hint`. Consistency
with the shipped precedent means no new mental model for the caller: two
independent "the identity assumption may not hold" signals, same mechanism.

## Risks / Trade-offs

- **[The operator-word list under- or over-strips]** — a query using an
  operator-ish word as part of the actual product identity (rare, but e.g. a
  product literally named "Best Buy") could over-strip and lose a real
  signal, defaulting to SKIP (safe direction — a lost signal is a missed
  catch, not a false flag). → Accept; revisit only if `make bench` or a
  future corpus sample shows this actually happening, not preemptively.
- **[Zero-overlap still occasionally correct]** — a legitimate paraphrase
  or a query in the site's own local-language spelling of a brand could
  produce zero overlap on a genuinely correct result. → This is exactly why
  the cap is downgrade-only (never fails the fetch, never asserts a hard
  wrongness) and the hint's message explains what triggered it — same
  posture as `served_url_differs`'s own docstring reasoning ("a2web cannot
  tell those apart from a mixup — only flag that the identity assumption may
  not hold").
- **[Scope reads as smaller than the bd issue's title]** — "query-term vs
  served-title mismatch on listings" could be read as covering non-listing
  pages too. → Non-Goals section is explicit; `a2web-byy`'s close reason
  should name the confusable-variant shape as the deferred remainder,
  mirroring how `a2web-gvy`'s close reason named its own deferred shapes.

## Migration Plan

1. Add a pure token-overlap helper (normalize/tokenize per D4, operator-word
   strip per D3, all-or-nothing comparison per D2) near `served_url_differs`
   in `fetcher_response.py`.
2. Add `query_title_mismatch_hint()` to `hints.py`, mirroring
   `served_url_differs_hint`'s docstring/shape.
3. Wire the check into `build_response`, gated on `fc.inputs.ask` non-empty,
   `fc.routing.structural_form == "listing"`, and `fc.record_set` non-empty
   (per D1) — independent of, and after, the existing `served_url_differs`
   block; same downgrade-only cap variable.
4. Extend `openspec/specs/fetch-response/spec.md` with a new Requirement,
   sibling to "a cross-domain landing caps confidence and is flagged".
5. Tests: token-overlap helper unit tests (stopword stripping, NFKD
   normalization, all-or-nothing logic); `build_response` integration tests
   mirroring `test_served_url_identity_mismatch.py`'s shape (zero-overlap
   flags, some-overlap doesn't, non-listing doesn't, empty-after-stopword
   query doesn't, cap is downgrade-only).
6. `make check` + `make recon-check`; mutation-verify the new logic.
7. Update `a2web-byy`'s close reason to name the confusable-variant Non-Goal
   as the deferred remainder (own bead if pursued later).

## Open Questions

- Exact operator-word list membership — draft one in Migration step 1 against
  the audit's own quoted queries and `routers.py`'s tool-description
  examples, not a comprehensive English vocabulary; extend only if a real
  false-positive/false-negative is observed.
- Whether the same check should also apply when `structural_form` is
  `unclassified`/`unparsable` but `fc.record_set` still parsed something
  (the DOM miner can fire independent of routing) — leaning yes, since the
  gate that matters is "were there item titles to compare," not the LLM's
  own classification, but decide at implementation time against what
  `build_response`'s existing `is_listing` gate (used for `options`) already
  does, for consistency.
