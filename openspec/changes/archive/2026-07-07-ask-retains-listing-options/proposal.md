## Why

On a listing-selection question ("which crimping tool is best?"), `ask` today
returns a single winner and **discards every other option** — the parsed records
are rendered to markdown and thrown away, so the wire carries only the model's
pick plus ≤10 bare drilldown links (no price, no rating). The premium/niche
outlier — which by nature has fewer reviews and a lower crowd rating, so it never
wins a popularity ranking — is deleted from the answer entirely. That is the
wrong loss: **ranking is a fair response to "best", but skipping the field is
not.** The option a willing-to-pay-more buyer wants is exactly the one a distilled
"best pick" hides.

Ranking and skipping are two different behaviors `ask` currently fuses. This
change separates them: keep the ranked verdict, but stop deleting the shelf it
came from.

## What Changes

- **`ask` retains the parsed listing options.** When a fetched page is a listing
  (the record detector produced a `RecordSet`), the `ask` envelope carries a
  conditional `options` list — one neutral entry per parsed record (title, url,
  and the record's own detail line carrying price/rating as the model saw it).
  The `answer` still crowns a top pick when asked; the `options` list stays
  **page-order, un-re-ranked** — a2web states the field, the caller applies its
  own preference (e.g. "I'll pay premium").
- **The structured `RecordSet` is retained on `FetchContext`** instead of being
  discarded after markdown rendering, so the ask projection can populate `options`
  without re-parsing.
- **Gated + omit-empty:** `options` appears only on a listing (record set parsed),
  is absent from the wire on articles / single entities, and rides through the
  existing `_prune_wire` empty-drop path. Additive field — no tool-signature
  change, no change for the non-listing `ask` path (its lean identity is intact).
- **Bounded, honest:** `options` carries the parsed (fetched) records only, capped
  at a sane ceiling; it does NOT claim completeness — the existing
  `listing_partial` / refinement-axes signals still say the fetched set is a
  partial, possibly biased sample.
- **Explicit non-goal:** retrieval diversity (the premium tail excluded because the
  page was fetched cheapest-first) is NOT addressed here — that is a stratified /
  multi-sort fetch concern, and preference-driven ("I'll pay premium") retrieval
  belongs to the shopping caller, not a2web.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ask-response`: the `ask` envelope SHALL carry a conditional, page-order
  `options` list projected from the parsed listing records (rank-don't-skip),
  omitted from the wire on non-listing pages.

## Impact

- **Code**: `src/a2web/fetcher.py` (retain `RecordSet` on `FetchContext` in
  `_escalate_via_records`), `src/a2web/models.py` (new `ListingOption` model +
  conditional `options` field on `AskResponse`; omit-empty via `_prune_wire`),
  `src/a2web/fetcher_response.py` (`build_ask_response` projects the retained
  record set into `options`, gated on a parsed listing), `FetchResponse` carries
  the retained set through to the ask projection.
- **Wire contract**: additive, conditional field on `AskResponse` (omit-empty) —
  no breaking change to existing parsers; no tool-signature change. Contract
  snapshot re-blessed (additive).
- **Payload size**: a listing `ask` grows by the option rows (the shelf the caller
  asked to see) — the deliberate trade for "don't skip"; non-listing asks are
  unchanged.
- **Constitution**: no per-site parsing — `options` are the generic `RecordSet`
  already produced by the record detector; price/rating ride as the record's own
  text, not typed per-site fields.
