# a2web call-trace audit — what 2,856 real calls say about the envelope

**Date:** 2026-08-07
**Corpus:** every a2web tool call in `~/.claude/projects` transcripts — 2,856 calls
across 224 sessions, 2026-05 → 2026-08 (86% in 2026-07).
**Method:** deterministic extraction + sequence analysis over the raw JSONL
(`scratchpad/a2web-audit/extract.py`, `seq.py`), plus 16 parallel Haiku analysts,
one per ~170KB shard of session dossiers, each required to cite session file +
call number for every claim.

This is an observational audit of *shipped behaviour*. It proposes nothing about
implementation; it reports what the traces show.

---

## 1. What a2web is actually used for

| Site class | Calls | Share |
|---|---:|---:|
| Shopping / marketplace | 1,547 | 54% |
| Vendor, spec & review sites | 789 | 27% |
| Forums & community (Reddit, Technopat, HA, GitHub) | 383 | 13% |
| Search engines (DDG, Brave, Google) | 137 | 4% |

Top hosts: hepsiburada.com (602), kaspi.kz (317), old.reddit.com + reddit.com
(207), trendyol.com (72), limpopo.kz (52), shop.kz (52).

**The dominant workload is comparison shopping in TR/KZ markets**, driven by the
`products-picker` skill. a2web's real job, most of the time, is *reading a price,
a stock state, and a variant list off a marketplace page*. The envelope was
designed for prose pages; the traffic is tabular commerce.

## 2. Envelope-level signals across the corpus

| Signal present in response | Calls | Share |
|---|---:|---:|
| `confidence: high` | 1,567 | 54% |
| `also_here` | 801 | 28% |
| `confidence: low` | 672 | 23% |
| `other_pages` | 550 | 19% |
| `retrieval_incomplete` | 526 | 18% |
| `confidence: medium` | 502 | 17% |
| `next_links` | 449 | 15% |
| `status: failed` | 406 | 14% |
| `try_user_browser` | 145 | 5% |
| tool-level error / timeout | 96 | 3% |
| challenge / wall detected | 88 | 3% |

`operator_hints` codes actually emitted, whole corpus:

| code | n | | code | n |
|---|---:|---|---|---:|
| `content_guidance` | 822 | | `browser_unavailable` | 35 |
| `retrieval_incomplete` | 284 | | `extraction_empty` | 35 |
| `try_user_browser` | 145 | | `answer_truncated` | 34 |
| `listing_partial` | 95 | | `browser_internal_error` | 21 |
| `content_thin` | 42 | | `llm_error` | 18 |
| `listing_more` | 36 | | `reddit_forbidden_try_archive` | 7 |

Note `listing_partial` (95) and `listing_more` (36): a2web *already knows* when it
is looking at a listing and when it has shown only part of one. The machinery to
detect the case exists; what the response doesn't carry is the rows.

**14% hard failure + 18% `retrieval_incomplete`.** ADR-0009 is holding — failures
are loud, not silent. That part of the design works.

The quality problem is not honesty, it's *completeness*:

| Answer text admits a gap | Calls | Share |
|---|---:|---:|
| "not stated / not shown / not listed / not provided" | 423 | 14% |
| …specifically **stock/availability** missing | 120 | 4% |
| …specifically **price** missing | 68 | 2% |
| …specifically **product URLs** missing | 37 | 1% |

## 3. The money finding — wasted follow-up calls

Deterministic sequence analysis (not model judgement) over all 224 sessions:

| Pattern | Occurrences |
|---|---:|
| **Listing/search page → ≥2 same-host product-page drilldowns** | **242 listings → 885 drilldown calls** |
| Retry of the same URL after a failure | 67 |
| ≥3 consecutive failures against the same host | 66 |
| Re-query of the same URL with re-worded query | 60 |
| `fetch_raw` on a URL already hit with `query` | 47 |

**885 calls — 31% of the entire corpus — are product-page drilldowns that follow a
listing page a2web had already fetched.** Fan-out by listing host: hepsiburada
156, kaspi 39, alash-electronics 12, old.reddit 11, apltech 8.

The 16 independent analysts converged on this without being told the numbers.
Every single batch ranked it #1 or #2. Batch estimates of preventable waste ran
14–28% of calls.

### 3.1 Why the drilldowns happen

The listing page carries a price/rating/stock per row in the DOM. `query` returns
**prose about the listing** — often an aggregate ("prices range 939–12,823 TRY")
or a single product — so the caller must open each item to get per-item facts.

> batch_1 s5 CALL 5, 7 — Hepsiburada PSU and case searches, 36 items each,
> answer says "stock not stated on this page" while per-row badges are visible.
> batch_8 — Kaspi search rows return `price: undefined` for ~a third of items
> whose product pages carry the price.
> batch_9 CALL 1,3,4 — Robotistan/Motorobit "36 products found", zero per-item
> price, stock, or URL returned.

### 3.2 Re-query of the same URL — the tell

The re-worded second query is the clearest evidence of a missing field, because
the agent is visibly *begging*:

> `4c628f31` calls 7→19, hepsiburada Salomon XT-6.
> Q1: "exact product name, current price in TRY, in-stock add-to-cart?"
> Q2: "Which EU sizes are available/in stock in the size selector? Specifically
> EU 42.5, 43, …"
> — **variant/size-selector state is never in the first answer.**

> `6d928616` calls 41→47, kaspi Palit RTX 5060 Ti.
> Q1: "Exact current price in KZT … **Read the JSON-LD/offers**"
> Q2: "Exact current price in KZT **today**, in stock or not …"
> — the caller is coaching a2web on extraction strategy. Twice.

> `b74867c9` calls 4→7, dns-shop.ru.
> Q2: "**Find and state the exact numeric price in rubles (RUB / ₽)** shown for
> this product. Look for…"

All 60 re-queries are the same shape: **price, stock, variant availability**.

### 3.3 Re-query after `retrieval_incomplete` is architecturally futile

Batch 3's sharpest observation: when a2web says `retrieval_incomplete` in prose,
the caller re-queries the same URL with different wording — but the page did not
change. Nothing about a re-worded query changes what the tier fetched. The
response tells the caller *that* something is missing, never *why*, so the caller
guesses. Evidence: incehesap.com calls 8→11 then 10→13, where the second and
third queries ask for "JSON-LD offers price" then "meta itemprop price" — the
caller cycling extraction strategies a2web already exhausted.

## 4. Wrong answers (the "garbage" bucket)

Rare but real; analysts flagged 2–11% per batch. Two classes matter:

**a) Wrong page served, reported as `high` confidence.**
> batch_1 s1 CALL 16 — requested a hepsiburada drill product page; response title
> was "Decathlon Şikayet ve Yorumları" (sikayetvar.com, a complaints site) with an
> answer about bike assembly. No redirect flagged. Re-query on the same URL
> returned the correct page.
> batch_8 s1 CALL 2 — Trendyol request, Hepsiburada title returned.
> batch_11 — fertilizer search on Hepsiburada returned irrigation/sulfur pages.

This is the most serious finding in the audit: **a host/identity mismatch between
the requested URL and the served content is not detected**, and the envelope
reports `confidence: high` over it. It is also a grounded-URL concern (ADR-0014)
one level up: the *content* isn't grounded in the requested URL.

**a2) Marketplace search returns a different product family, at `high` confidence.**
Distinct from (a): the fetch is correct, the *site's own search* returned junk,
and a2web relays it without noticing the query terms are absent from the results.
> batch_12 s1 CALLs 7, 8, 13, 18 (hepsiburada) — query `pindstrup` → "Gölgelik
> File" (shade cloth); `pindstrup+torf` → "Kalsiyum Nitrat"; `kekkila` → "Plagron".
> batch_15 s5 CALLs 15–21 — "fide küveti deliksiz" (seedling trays) → baby bath
> tubs, then kitchen storage containers. Seven calls burned before a different
> Turkish term worked.
> batch_15 s3 CALLs 1–11 (kaspi) — "AMT M-1" (guitar pedal) → 387k results across
> computer parts, auto parts, phone cases.

A cheap keyword-overlap check between the requested query and the returned
titles would at minimum stop `confidence: high` being asserted here.

**b) Confusable model variants.**
> batch_6 s3 CALL 3 — asked for Lenovo 15AKP10 (AMD Ryzen AI), got a review of
> 15IRX10 (Intel) — different silicon, different thermals, answered confidently.
> batch_6 s7 CALL 9 — asked ASUS FA607, got FA608WV (different generation).

The page is *about a different product than the URL implies*, and nothing checks
the returned title against the requested identity. The same class shows up as
outright extraction slip: batch_2 CALL 8 requested a Bianchi GR0014 product page
and got back "Corelli Broster Strowild" as the product name, corrected only by a
re-query.

**c) `status: failed` + `confidence: high` + empty answer — 42 calls.**
Verified deterministically, not model-judged. 35 of them carry
`operator_hints: [{code: extraction_empty}]` reading *"Fetched N characters of
content but extraction produced an EMPTY answer"* — median N = 8,788, max 78,623.

Two things are wrong at once. `confidence` is being reported on an answer that
doesn't exist, which makes the field unreadable for a caller doing the obvious
thing (branch on confidence). And a page that was successfully fetched — up to
76KB of it — is thrown away because one LLM extraction returned empty, leaving
the caller with nothing to work from. Batch 9 reached the same conclusion from
the other end and proposed the same remedy: when the fetch succeeded and
extraction didn't, return the body.

## 5. Host behaviour

| Host | Observed behaviour |
|---|---|
| hepsiburada.com | Best-supported; but search rows lack per-item stock; intermittent timeouts after ~6 consecutive queries (rate-limit shaped) |
| kaspi.kz | `price: undefined` on many search rows; region filter (Magnum zone) silently truncates 12,216 results to 12 shown, never declared |
| trendyol.com | Frequent timeout/failure; one confirmed cross-domain content mix-up |
| ozon.ru, citilink.ru | Near-total failure in-corpus, no tier escalation observed |
| limpopo.kz, sportidea | Category pages return navigation trees, not product rows; costs 2–4 calls per traversal |
| old.reddit.com `/search` | Fails consistently; direct thread URLs succeed |
| html.duckduckgo.com | CAPTCHA loops; Brave/Ecosia work but are only found by hand |
| notebookcheck, techpowerup | Bot-walled |
| vendor `/spec.html` (BenQ, ASUS) | Metadata only; `fetch_raw` succeeds where `query` doesn't |
| keychron.com | 6 calls over 45 min, all nginx placeholder / 404 (batch 10) |
| psref.lenovo.com | `thin_content` is a JS placeholder comment; reported failed (batch 14) |
| akakce.com | `offerCount: 0` returned at `confidence: high` — zero-inventory reads as a valid answer (batch 10) |
| dukkanmuzik.com | 3 calls, `tier: none` — no tier attempted at all (batch 15) |

## 6. What the traces argue a2web should return in the FIRST response

Ranked by calls the corpus says they'd have removed.

1. **Per-row structured listing extraction.** When the page is a listing, return
   the rows as rows — `{title, price, currency, rating, review_count, stock,
   seller, url}` per item, plus `rows_shown` / `rows_total` — instead of prose
   about the listing. Addresses the 885-call drilldown fan-out directly, and
   satisfies the existing TSV-table wire path rather than needing new shape.
   *Caveat against ADR-0012: this is relaying every row the page states, not
   ranking or selecting — the ordering must stay the page's own.*

2. **A typed missing-field report instead of prose "not stated".** `fields:
   {price: {found: false, reason: js_rendered|absent_on_page|extraction_failed}}`.
   423 calls admit a gap in prose today; the caller cannot tell "the page doesn't
   have it" from "we failed to read it", so it re-queries. This is the ADR-0015
   withheld-body-index principle applied to *fields* rather than sections.

3. **Requested-identity vs served-content check.** Compare the served page's
   host/title/canonical against the requested URL; on mismatch emit a failure or
   an explicit `served_url_differs` marker rather than a `high`-confidence answer
   about a different page. Covers both the redirect swaps (§4a) and, softer, the
   model-variant confusions (§4b).

4. **Declare page-level truncation and filter state.** `rows_shown` vs
   SOURCE-stated `rows_total`, and any region/availability filter the site applied
   (kaspi's 12-of-12,216). The "never declare a truncation against a number that
   cannot differ" rule already in AGENTS.md points the right way; the traces show
   listing pages as the place it isn't happening.

5. **Variant/selector state as first-class.** Size, colour, capacity selectors and
   which options are in stock. Multiple sessions burn a second call on exactly
   this and nothing else.

6. **Product URLs from listing rows, always.** 37 calls have answers explicitly
   saying URLs weren't provided; the caller then runs `fetch_raw` to recover
   hrefs. `other_pages` exists — on listing pages it should carry the row URLs.

7. **Never report `confidence` on an empty answer; return the fetched body when
   extraction comes back empty.** 42 calls assert `high` over nothing; 35 of them
   discarded a median 8.8KB that was already in hand (§4c).

Lower-confidence, flagged for judgement rather than recommended:

- **Tier auto-escalation on known-hard hosts.** Many analysts proposed it
  (ozon/trendyol/reddit-search). It conflicts with the "never retry the whole
  flow" rule and the five-layer retry design; the traces show the *need* (66
  same-host failure streaks), not that blanket escalation is the right answer.
- **Session-level dedup/caching of identical queries.** Suggested by batch 8;
  a2web is stateless per call by design, so this likely belongs to the caller.
- **Pagination guidance on token-overflow responses.** Batch 8 saw overflow
  errors with no offset/limit hint offered.
- **`drill_next_links: N` — a2web following child links itself in one call.**
  Batch 12's proposal. It would collapse the fan-out in §3, but it hands a2web a
  selection decision (which N links) that ADR-0012 says isn't its to make. Noted
  because several analysts reached for it independently; not recommended as-is.
- **Cross-seller spec discrepancy flagging.** Batch 15 found the same Bosch fan
  listed at 125 m³/h on one site and 215 m³/h on another, unflagged. Genuinely
  useful to the caller, but it requires a2web to compare two pages and adjudicate
  — squarely the "never manufacture a selection" line. If wanted, it belongs to
  the caller, which already has both responses.

Suggestions I am recording as *rejected* on the traces: session-level dedup and
response caching keyed on URL (a2web is per-call stateless by design, and the
kaspi 404s in batch 12 show product URLs go stale), and blanket suppression of a
host after one failure (batch 10) — too blunt against transient timeouts, which
the corpus shows recovering within minutes (batch 14 CALLs 3–6).

## 7. Reading of the whole thing

The failure envelope (ADR-0009) is doing its job — 14% failures are loud, and
`try_user_browser` fires where it should. The gap is one level up: **a2web
answers the question it was asked about a page, and the caller's real unit of
work is a row, not a page.** On a listing page the response is prose about a
table. So the caller re-derives the table one HTTP fetch at a time — 885 calls of
it, 31% of everything a2web has ever been asked to do.

Second gap, smaller but sharper: **`confidence: high` is asserted over content
that was never checked to be the requested content.** §4a is a correctness bug,
not an ergonomics one.

---

*Artifacts: `scratchpad/a2web-audit/` — `extract.py`, `seq.py`, `raw_calls.json`
(full call corpus), `batch_*.md` (session dossiers), `findings_*.md` (per-shard
analyst reports).*
