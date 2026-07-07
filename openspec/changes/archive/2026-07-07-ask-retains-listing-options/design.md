## Context

`ask` distills a page to a lean answer — its reason to exist. For a decision over
a catalog that identity backfires: the model crowns a popularity-ranked winner and
`build_ask_response` discards the rest, because the parsed `RecordSet` is rendered
to markdown in `_escalate_via_records` and only `record_count` survives on
`FetchContext`. The premium/niche item — fewer reviews, lower crowd rating by
nature — is exactly what a "best pick" deletes.

The prior change (`content-aware-refinement-guidance`) added axes + a bias hint
telling the caller the sample is unrepresentative — yet the answer still asserts a
single best, contradicting its own hint. This change resolves that: the answer may
rank, but the field it ranked over stays on the wire.

## Goals / Non-Goals

**Goals:**
- Retain the parsed `RecordSet` through to the ask projection.
- Surface a conditional, page-order `options` list on `AskResponse` for listings.
- Keep the ranked verdict in `answer`; keep the `options` list neutral (un-re-ranked).
- Additive, gated, omit-empty; non-listing `ask` unchanged.

**Non-Goals:**
- Retrieval diversity — fetching the premium tail excluded by a cheapest-first
  sort. That is a stratified / multi-sort fetch (skill-driven, preference-aware).
- Typed price/rating fields — parsing those generically is per-site scar tissue;
  price/rating ride as the record's own detail text, as the model saw it.
- Re-ranking the options list inside a2web — imposing a rank order re-introduces a
  preference function; the list is page-order, the opinion lives only in `answer`.
- Changing `fetch_raw` (already returns the full record block) or the tool signature.

## Decisions

**D1 — Retain the structured `RecordSet`, don't re-parse.**
`_escalate_via_records` already builds the `RecordSet`; add `fc.record_set:
RecordSet | None` alongside the existing `fc.record_count`, and thread it onto
`FetchResponse` so `build_ask_response` can project it. *Alternative rejected:*
re-run `extract_records` at the ask seam — wasteful and risks divergence from the
count already promoted onto `fc`.

**D2 — Options are neutral (page-order), the answer is the opinion.**
The `options` list preserves the parsed order; a2web does not sort it by rating or
price. Rationale: any ordering a2web imposes is a preference function, and the
whole point is that the caller's preference ("I'll pay premium") differs from the
crowd's. The ranked verdict stays in `answer` where it is clearly an opinion, not
a property of the shelf. *Alternative rejected:* rank the list by the model's
judgment — re-creates the skip problem one level down (the caller reads top-of-list
as "best" and stops).

**D3 — Compact per-record projection, not full markdown.**
Each option is `ListingOption {title, url, detail}` where `title` = the record's
`heading_text` (fallback to a text lead), `url` = `heading_link`, `detail` = the
record's own detail text carrying price/rating. This is far leaner than dumping the
whole record markdown block and is structured for the caller. *Alternative
rejected:* surface the record-synth markdown via `include_content` — heavier,
unstructured, and off by default so it does not fix the "answer discards the shelf"
default behavior.

**D4 — Gate on a parsed listing; cap the set.**
`options` is populated iff a `RecordSet` was parsed (`record_count`/`record_set`
set) — deterministic, independent of the LLM routing. Absent on non-listings.
Capped at a sane ceiling (e.g. 50) so a pathological first batch cannot balloon the
envelope; the cap is a no-skip-within-fetched guarantee, not a completeness claim
(the existing `listing_partial` signal still owns completeness).

**D5 — Additive, omit-empty wire field.**
`options` defaults to `[]` and is dropped by `_prune_wire` when empty — same path
as `ask_here` / `refinement_axes`. No required-field change; contract snapshot
re-blessed additively.

## Risks / Trade-offs

- **[Envelope re-bloat on listing asks]** → the deliberate trade for "don't skip";
  scoped to listings only, compact per-record projection, capped ceiling. Non-listing
  asks are byte-identical to today. Watch the bench clarity/token axes.
- **[Caller reads options[0] as "the best"]** → D2 page-order keeps the list neutral;
  the ranked opinion lives only in `answer`. Document the neutrality on the field.
- **[Records carry noisy detail text]** → `detail` is whatever the record detector
  captured (already what `fetch_raw` shows); no new parsing, no new failure mode.
- **[Premium item still missing]** → out of scope by design; the retained set is the
  fetched (cheapest-first) sample. The `listing_partial` + refinement-axes signals
  already tell the caller to re-query a different band. Called out as a non-goal so it
  is not mistaken for solved.

## Migration Plan

Additive, behind the listing gate. No data migration. Rollback = revert; the
conditional field simply stops appearing. Re-bless the contract snapshot. Run
`make bench` after landing (moves the listing `ask` payload shape).

## Open Questions

- Cap value: 50 is a starting ceiling; the typical first batch is ~30-40. Revisit if
  bench shows either truncation-within-fetched or bloat.
- Should `detail` be lightly trimmed (collapse whitespace / cap length) for wire
  compactness, or passed through verbatim as the record captured it? Leaning: a light
  whitespace collapse + per-detail length cap, no semantic edit.
