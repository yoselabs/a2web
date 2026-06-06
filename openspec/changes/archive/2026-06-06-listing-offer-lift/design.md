## Context

`ask` runs the adaptive tier cascade, then a small server-side extractor (Haiku) reads the page's `content_md` and produces the answer. For pages whose answer-bearing data is embedded JSON rather than prose, `_phase_extract` runs an unconditional structured-extraction ladder; the first rung, `json_in_script`, detects payloads (`ld_json`, `next_data`, microdata, …) and `domain.py::json_to_markdown_rows` synthesizes a markdown surface the extractor can read.

Observed failure (live, `debug=true`) on `https://www.hepsiburada.com/mikrofon-aksesuarlari-c-411155`:
- `raw` (curl_cffi) wins, status 200, ~1.2s — **not** JS-gated.
- The page carries one JSON-LD `ItemList` with 36 `Product` entries, each `{name, image, offers:{price, priceCurrency, url}, aggregateRating}`.
- Synthesized `content_md` is a table with only `name | image`. `ask` returns "no pricing visible, click into each product," empty `try_url`, and `obstacle: empty`.

Root cause is one helper. `_rows_to_md_table` infers columns from a row's keys and skips any value that is a `dict`/`list` (`if k.startswith("@") or isinstance(v, (dict, list)): continue`). For a `Product` row the only top-level scalars are `name` and `image`; `offers` (carrying price, currency, url) and `aggregateRating` are nested dicts → dropped. The extractor never sees prices or URLs, so it cannot answer price questions, cannot satisfy the router prompt's "`try_url` URLs MUST appear verbatim in content" rule, and reads the page as data-poor.

Multi-site validation (raw curl_cffi probe of 5 listing pages) framed the scope:

| Site | raw | Where listing price+url lives | This change covers it? |
| --- | --- | --- | --- |
| Hepsiburada | 200 | JSON-LD `ItemList` + `Product.offers` (36) | Yes — target shape |
| Trendyol | 200 | escaped inline JSON (`"products"` arrays), no JSON-LD/`__NEXT_DATA__` | No — non-LD app-state |
| Yandex Market | 200 | deep custom JS state (`snippet_type:product`, nested prices) | No — non-LD app-state |
| Amazon | 503 | bot-walled — no data at raw tier | No — tier problem |
| e-katalog | 404 | inconclusive (bad probe URL) | — |

The JSON-LD shape is the most standardized and is what Hepsiburada (a real, common case) emits. The other shapes are genuinely separate problems and are out of scope here.

## Goals / Non-Goals

**Goals:**
- Lift nested commerce fields (`offers.price`+`offers.priceCurrency`, `offers.url`, `aggregateRating.ratingValue`) from JSON-LD `ItemList` / `Product` rows into the synthesized markdown the extractor reads.
- Preserve the product URL **verbatim and un-truncated** so `try_url`/`next_links` populate and the LLM can cite a real drilldown.
- Make price-bearing listings answer price questions ("the cheapest is X at 3690 TRY") and stop the false `obstacle: empty`.
- Lock the behavior with a deterministic fixture + capability tests in `make check`.

**Non-Goals (recorded scope boundaries):**
- Extraction of non-JSON-LD embedded app-state (Trendyol / Yandex). Tracked for a later change.
- Browser-tier escalation for bot-walled raw responses (Amazon-class 503). Separate tier/handler work.
- An `obstacle: dynamic` / `needs-js` enum value. Obstacle is question-relative; once the data we already have is surfaced, this page is not obstructed. A real `dynamic` signal belongs to the browser-escalation work, not a label here.
- Corpus-wide deterministic replay/refresh eval infrastructure ("VCR" for the whole bench corpus). Its own future change — this change adds only the single Hepsiburada fixture.
- Any change to the `AskResponse` / `FetchResponse` envelope or tool signatures.

## Decisions

**D1 — Lift at the shared chokepoint, not only the JSON-LD branch.** Both the JSON-LD path (`_ld_json_to_markdown`) and the framework-state path (`_framework_state_to_markdown`) funnel rows through the same renderer. Normalizing commerce fields at that boundary fixes the nested-drop once for every shape that reaches it. _Alternative rejected:_ patch only `_ld_json_to_markdown` — narrower, but leaves the identical bug latent on the framework-state path.

**D2 — Linked markdown records for commerce rows, not a wider table.** Render product rows as `- [name](url) — 3690 TRY ⭐ 4.7`. _Why:_ `_rows_to_md_table` caps every cell at 80 chars; Hepsiburada product URLs run ~70–90 chars, so a `url` column would truncate and re-break the verbatim-URL rule. Link records keep the URL intact, read as real drilldowns the LLM reliably treats as links, and put price/rating inline. _Alternatives rejected:_ (a) table with the url column exempt from the cap — sprawling wide rows, still table-shaped; (b) compact table + a separate links block — duplicates product identity and forces the LLM to re-join name↔url.

**D3 — Combined price cell `"3690 TRY"`.** Lift `offers.price` and `offers.priceCurrency` into one human/LLM-readable token. _Why:_ the answer wants them together ("cheapest is 3690 TRY"); a split price/currency pair adds a column with no extraction benefit.

**D4 — Commerce-shape gate so non-commerce ItemLists don't regress.** After normalization, render via `_rows_to_md_records` only when rows look commerce-shaped (a simple threshold: at least half the rows carry a `price` or `url`); otherwise fall back to the existing `_rows_to_md_table`. _Why:_ ItemList is also used for non-product lists (breadcrumb-like indexes); those should keep their current rendering.

**D5 — Drop the synthetic `image` field.** Image-CDN URLs carry no answer value and cost extractor tokens. _Why:_ removing them shrinks input and removes noise; nothing downstream reads the synthesized image column.

**D6 — Trimmed real fixture, matching repo norm.** `tests/fixtures/hepsiburada_listing.html` is a minimal HTML shell carrying the real `ld+json` `ItemList` block with ~5 real products (real name/price/currency/url/rating), ~1–2 KB — consistent with existing fixtures (277 B–8 KB), not a 1.5 MB page dump. _Why:_ deterministic, realistic schema.org shape, no repo bloat. The existing `trendyol_search_next_data.html` fixture is now stale vs. the live site; not touched here (its own follow-up).

## Risks / Trade-offs

- **Commerce-shape gate misfires on an edge list** (false positive renders a non-product list as link records, or false negative keeps a product list as a table) → conservative threshold (≥half rows carry price/url) plus a regression test asserting a non-commerce ItemList still renders as a table.
- **Markdown-link injection from product names** containing `]`/`)`/newlines → sanitize link text (strip/replace bracket and newline chars) when building `[name](url)`.
- **Other sites that DO emit JSON-LD but with thinner offers** (price but no url, or url but no price) → graceful field omission: emit whatever is present (`- [name](url) — 3690 TRY`, or `- name — 3690 TRY` when no url), never fabricate.
- **Scope misread as "fixes all e-commerce"** → the validation table and Non-Goals make explicit that Trendyol/Yandex/Amazon are not covered; this prevents silently assuming coverage.

## Migration Plan

Pure additive behavior change inside one domain module plus tests; no schema, dependency, or wire change. Ships in a normal release; `make install-global` to propagate to the local MCP binary. Rollback is reverting the `domain.py` diff — no data or contract migration.

## Open Questions

None blocking. Deferred (own changes): non-LD app-state extraction (Trendyol/Yandex), bot-wall browser escalation (Amazon), corpus-wide replay/refresh eval infra, and whether a future `obstacle: dynamic` signal is warranted once browser-escalation telemetry exists.
