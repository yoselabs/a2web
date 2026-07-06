## Why

a2web silently returns partial listings as if they were complete. Live case
(2026-07-06): a Hepsiburada search (`/ara?q=…`) returned "31 listings" with
`confidence: high`; the same URL in a real browser shows 40 products. The extra
nine load on scroll. Nothing in the response signalled that the retrieval was a
sample — the caller had no way to know it was holding 31 of 40.

This is a **different miss** from everything shipped so far, on an axis the
pipeline does not yet measure:

- **Presence axis (already covered).** The extractor's `obstacle ∈ {empty,
  blocked}` catches "the answer-bearing content isn't here at all" (SPA shells,
  confabulation, soft walls) and drives a paid render
  (`obstacle-driven-render-escalation`, `search-retrieval-and-confabulation-guard`).
- **Sufficiency axis (this change).** A listing page can render perfectly, pass
  every gate, carry real records — and still be **partial**, because
  infinite-scroll / lazy-load only materialised the first batch. No obstacle
  fires (the content that *is* present is genuine), so nothing catches it.

The floor tenet (ADR-0009) says a caller must never mistake a miss for a
complete answer. A truncated listing is exactly that miss — currently silent.

The foundation already exists: `_escalate_via_records` runs `extract_records`
on **every** fetch (no handler gate) and computes `len(record_set.records)` —
a generic progress count — then logs it and throws it away
(`fetcher.py:1117`). The `content_expectations.assess(loaded, total)` oracle
contract is built and battle-tested for Reddit comments, and its docstring
already anticipates "a future browser rung scrolling/paginating." This change
promotes that discarded count into a decision and wires the anticipated rung.

## What Changes

Two independently-shippable slices.

### Slice 1 — Honest partial signal (the floor; no new cost)

- **Generic item-count oracle.** A pure `listing_oracle(html, records)` extracts
  the advertised total from a listing page: JSON-LD / microdata
  `ItemList.numberOfItems` first, then a multilingual visible-count regex
  ("40 sonuç", "1,234 results", "showing 1–24 of 40", "X ürün"). Returns
  `total | None`.
- **Sufficiency verdict.** Reuse `content_expectations.assess(loaded=len(records),
  total=oracle)` verbatim — the Reddit-comment instance generalises to any
  listing. `partial` when records fall short of the oracle within tolerance.
- **`listing_partial` operator hint** (`severity: info`) — names loaded/total
  (or "more available" when the oracle is unknown but a structural
  "more exists" signal — `rel=next` / a load-more control / pagination nav — is
  present on a non-scrolling tier). Steering is **shape-aware**: for a
  search-shaped URL it advises narrowing the query (riding the existing
  `try_url`/`ask_here` machinery); for a bounded list it advises scroll / open
  in browser.
- **`items_loaded` / `items_total`** envelope fields on `AskResponse` and
  `FetchResponse`, mirroring `comments_loaded` / `comments_total`. Omitted from
  the wire when the page is not a listing.
- **Does NOT set `retrieval_incomplete`.** That flag means *walled* (zero
  useful retrieval); a partial listing returned real content. The signal is a
  loud `info`, not a `failed` status — this is the deliberate honesty-severity
  placement between `comments_partial` (info) and `try_user_browser` (critical).

Slice 1 alone would have made the Hepsiburada session honest. It rides a count
the pipeline already computes and adds zero fetch cost.

### Slice 2 — Bounded scroll-to-complete (the action; opt-in cost)

- **Scroll actions on the render tiers.** The existing render (Zyte
  `browserHtml`; local Playwright/zendriver backend) renders once and does not
  scroll for completeness. Add a **bounded scroll-until-stable-or-cap** loop:
  Zyte gains an `actions: [{action: scrollBottom}, {action: waitForTimeout}]`
  sequence; the local backend generalises its single-shot `_scroll_and_retry`
  into a scroll-until-the-record-count-stops-growing loop. Termination needs no
  oracle — stop when the count stabilises **or** a scroll cap / time budget hits.
- **`listing_partial` as a new escalation trigger.** A partial listing served by
  a non-scrolling tier (raw/jina) escalates to a **scrolling** render. This
  reuses `escalate_to_render` / `_escalate_paid` and **shares the single
  one-paid-dispatch-per-fetch cap** with the gate-wall and obstacle triggers —
  at most one render regardless of how many triggers fire. Free own-browser
  (with scroll) is preferred before paid egress where available.
- **Steer, don't scroll, when the gap is unbounded.** When the oracle is
  known-huge (a broad search with thousands of hits), skip the scroll entirely
  and emit the signal + a narrow-the-query steer. Completeness of a 12,000-hit
  search is neither achievable nor useful; the oracle is what lets the pipeline
  tell a 40-item list from a 12,000-hit search.
- **Re-label after scroll.** Reached the oracle / stabilised → drop the signal
  (complete). Capped / still short → keep `listing_partial` (loud miss holds).

## Capabilities

### New Capabilities

- `listing-completeness`: the sufficiency contract for listing pages — a generic
  item-count oracle vs. the parsed record count, resolved via
  `content_expectations.assess`, surfaced as an honest `listing_partial` signal,
  and (Slice 2) closed by a bounded scrolling render or a narrow-the-query steer.

### Modified Capabilities

- `ask-response`: gains `items_loaded` / `items_total` and the `listing_partial`
  hint; a partial listing is an honest `info` signal, not a `retrieval_incomplete`
  wall.
- `fetch-response`: gains `items_loaded` / `items_total` and the `listing_partial`
  hint (signal-only — `fetch_raw` cannot scroll).
- `tier-pipeline`: a new completeness assessment runs after record extraction; a
  `listing_partial` verdict on a non-scrolling tier is a new escalation trigger
  sharing the one-paid-dispatch cap.
- `browser-tier`: the render gains a bounded scroll-until-record-count-stable-or-cap
  loop, replacing the single-shot host-seed-gated scroll for completeness.
- `paid-fetch-tiers`: the paid render gains a `listing_partial` trigger and sends
  scroll `actions` in `browserHtml` mode; the one-dispatch cap is shared.

## Impact

- **Code**: new `src/a2web/listing_oracle.py` (pure count extraction); `fetcher.py`
  (completeness phase + `listing_partial` trigger wiring, reusing `_escalate_paid`
  / the shared cap); `content_expectations.py` (docstring generalisation only —
  `assess` is already generic); `models.py` (`items_loaded`/`items_total` +
  `listing_partial_hint` factory); `fetcher_response.py` / `build_ask_response`
  (field + hint plumbing); `tiers/zyte.py` (scroll `actions`); the local browser
  backend (`packages/browser_backends/*` scroll-to-stable loop).
- **Wire contract**: additive only — two new optional fields + one new hint code
  (a free string; no schema change). No field removed, no tool-param change. A
  partial listing that previously read `high`/complete now carries the signal.
- **Cost**: Slice 1 is free (rides an existing count). Slice 2 adds at most one
  render per fetch, sharing the existing paid-dispatch cap, gated to listing
  shapes and bounded by a scroll cap; unbounded searches steer instead of
  spending. Larger post-scroll payloads cost more extractor tokens — bounded by
  the cap.
- **Dependencies**: none added (Zyte `actions` is a request-body field; local
  scroll uses the existing backend).
- **Out of scope** (→ `BACKLOG.md`): multi-page URL crawling (`?page=2,3,…` as a
  distinct retrieval strategy — this change scrolls, it does not paginate by
  URL); per-site oracle handlers (generic extraction only; Reddit's comment
  oracle stays the handler-specific instance); DOM-virtualised listings where
  rows unmount on scroll and the count never accumulates (the signal is the
  honest backstop — scroll cannot beat virtualisation and must say so).
