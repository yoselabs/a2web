## Context

a2web is a distributed, multi-region fetch tool: strangers point it at their own regional
sites (Ozon, Rakuten, Mercado Livre) in their own languages. Today a truncated listing gets
an honest `listing_partial` hint (`items_loaded` / `items_total`) via `listing-completeness`,
but two failures remain:

1. **The hint offers no escape lever.** Its prose ("narrow your query", "open in a browser
   tool") is a dead end when a2web is the caller's only web tool.
2. **The sample is often biased, not merely partial.** A price-ascending search returns the
   cheapest N; judging "best" over that batch is systematically wrong, and the tool presents
   it as a neutral shortlist.

The generalization test (proposal) showed that any *parser-based* fix — decoding
`siralama=artanFiyat`, reading a facet sidebar — is per-site/per-language scar tissue that
rots across regions. The one thing that generalizes perfectly is **reasoning over the content
in hand**: the LLM decodes `artanFiyat`, `по возрастанию цены`, and `安い順` alike, and reads
any site's items with no selector. The design therefore pushes all *interpretation* into the
model and keeps a2web's deterministic layer to pure *context assembly*.

## Goals / Non-Goals

**Goals:**
- Assemble a deterministic, zero-interpretation **context bundle** (URL + parsed-but-opaque
  query params, computed page kind, item counts) and hand it to the reasoning model.
- Detect partialness LLM-side on `ask`, closing the regex oracle's language-coverage gap.
- Compose **content-type-keyed guidance** per-fetch from the existing closed kind enums
  (per-kind, never per-site).
- Emit **dimensional refinement axes** on a partial listing — axes to re-query on, never
  values drawn from the biased sample.
- Keep the change additive and constitution-clean: no per-site knowledge, no new top-level
  dependency, no tool-signature change.

**Non-Goals:**
- Deterministic per-site pagination (`page` / `offset` / cursor). Explicitly killed —
  per-site paging contracts are unwinnable generically.
- Interpreting query params deterministically (would require a per-site/per-language param
  dictionary — the exact scar tissue banned).
- Changing the static MCP tool description per-fetch (MCP advertises it once at `list_tools`).
- Facet-sidebar scraping (site-specific DOM).

## Decisions

**D1 — Split deterministic context-assembly from LLM interpretation.**
a2web computes only facts it can know without understanding any site: the URL with query
params parsed into opaque `key=value` pairs, the already-computed `structural_form` / `shape`
kind, and `items_loaded` / `items_total`. The model decodes all *meaning*. Rationale: parsing
generalizes badly across regions; reasoning generalizes perfectly. *Alternative rejected:* a
deterministic "you sorted cheapest-first" hint — secretly requires knowing `siralama` is a
sort key and `artanFiyat` is Turkish for ascending price. Banned scar tissue.

**D2 — LLM-side partialness detection as a superset of the regex oracle.**
The `listing_oracle` regex stays as a cheap deterministic fast-path, but on the `ask` path the
extractor also judges partialness from the content it holds (repeated item structure + a
visible total it can read even when our noun list can't). Partialness fires if *either* signal
trips. *Alternative rejected:* gate solely on the regex oracle — silently misses every language
not in the noun list, i.e. exactly the regional users the tool is distributed to.

**D3 — Content-type guidance keyed off existing closed enums, composed into the prompt.**
Guidance fragments are selected by the already-computed content kind (`listing` → completeness
+ sort-bias + refinement axes; `discussion` → consensus-vs-dissent, recency; `article` →
claims, recency, stance; `product` → price, specs, availability). On `ask` the fragment is
composed into the server-side extraction system prompt; on `fetch_raw` (no server LLM) the
same context bundle is surfaced in the envelope for the caller's model. "Dynamic prompt" =
extraction prompt + response guidance, never the static MCP schema. *Alternative rejected:*
per-site guidance tables — kinds are a small universal closed set; sites are not.

**D4 — Refinement axes are dimensional-only, enforced in the extraction prompt + schema.**
The model proposes axes (`narrow by brand`, `add a price floor`, `sort by rating`, `split by
sub-type`) — never values (`buy Boblov`, `the ₺270 ones are best`). Rationale: the model only
saw the biased sample, so any *value* it names inherits the truncation bias; only the *axis* is
safe, because the next fetch surfaces real values across the full field. Enforced by prompt
instruction and by shaping the schema as a list of axes (with rationale + how-to-apply),
parsed through the existing `wobble` funnel.

**D5 — Additive, conditional wire fields.**
Refinement axes ride `AskResponse` as a conditional field, omitted via `_prune_wire` when
empty (consistent with `next_links`, `genre`, etc.). No breaking change; no tool-signature
change; Ask-First gate not triggered.

## Risks / Trade-offs

- **[Model laundering the biased sample into value recommendations]** → D4 dimensional-only
  discipline in prompt + schema shape; a capability scenario asserts axes-not-values on a
  sorted/truncated sample.
- **[Over-triggering refinement axes on complete listings or non-listings]** → gate on
  `partial AND kind==listing`; omit fields otherwise (prune-wire), mirroring
  `listing-completeness`'s "complete listing emits nothing" scenario.
- **[LLM partialness detection adds prompt tokens / cost on ask]** → fragment is small and
  fires only on the ask path; `fetch_raw` stays signal-only. Acceptable on the distilled-answer
  product.
- **[Guidance fragments drift into per-site specificity over time]** → architectural guard:
  fragments key off the closed kind enums only; a test asserts no site/host string appears in
  the guidance table.
- **[Regex fast-path and LLM detection disagree]** → LLM detection is a superset; when either
  trips, the honest partial signal stands. Never suppresses an existing signal.

## Migration Plan

Additive and behind existing gates. No data migration. Rollback = revert; conditional wire
fields simply stop appearing. Bench (`make bench`) after landing, since this moves output
quality/shape on listing URLs.

## Open Questions

- Should the content-type guidance also surface on `fetch_raw` as an envelope field, or only
  as the raw context bundle (letting the caller's model own all interpretation)? Leaning:
  raw bundle only on `fetch_raw`, composed guidance only on `ask`.
- Exact home of the dimensional-not-value discipline: a2web extraction prompt (protects every
  caller) vs. products-picker skill. Leaning a2web, so all callers are protected from the
  laundering trap for free.
