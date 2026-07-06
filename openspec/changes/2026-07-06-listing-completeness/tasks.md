# Tasks — listing-completeness

Test-first (BDD). `make check` (lint + ty + test, coverage ≥85%) is the gate.
Slice 1 is independently shippable and merges before Slice 2 is started.

## Slice 1 — Honest partial signal (free; ships alone) — DONE

> Implemented 2026-07-06. Full gate green (lint + ty + 1081 tests + 90%
> coverage + arch). Tests in `tests/capabilities/listing_completeness/`.
> Design refinements made during build (all within the proposal's intent):
> — `listing_oracle(html)` takes only `html` (no `records` param); the numeric
>   oracle (JSON-LD `numberOfItems` via regex — no `json.loads` — + noun-anchored
>   visible count) is Slice 1. The countless structural "more exists" fallback
>   (`rel=next` / load-more) is deferred to a follow-up (no oracle → silent for
>   now, honest but not yet exhaustive).
> — the count rides a new `FetchContext.record_count` set in
>   `_escalate_via_records`; the phase reads it (no double-parse).
> — `_phase_listing_completeness(fc, raw_html=...)` is invoked from the tail of
>   `_phase_extract` (where `raw_html` lives), not from `_run_pipeline`.
> — the shape-aware steer copy lives in the hint's `message`/`fix`; wiring a
>   distinct `try_url` narrow-query entry is folded into Slice 2 (needs the
>   URL-shape branch that also gates scroll-vs-steer).

### 1. Item-count oracle (pure)

- [x] 1.1 Test: `listing_oracle` reads JSON-LD `numberOfItems`; a visible-count
      match ("40 sonuç", "1,234 results", "showing 1–24 of 40", "N ürün"); `None`
      otherwise. Anchored to item nouns — "1000 reviews" / "4.7 rating" do NOT match.
- [x] 1.2 Add `src/a2web/listing_oracle.py` — pure, settings-free, never raises.

### 2. Sufficiency verdict (reuse `assess`)

- [x] 2.1 `content_expectations.assess(loaded, total)` drives the verdict — its
      second caller (covered via the fetch/ask integration tests).
- [x] 2.2 Promote `len(record_set.records)` onto `FetchContext.record_count`
      (stop discarding the count computed in `_escalate_via_records`).
- [ ] 2.3 Generalise the `content_expectations` module docstring beyond Reddit
      (deferred — docstring-only, no behaviour).

### 3. Signal + envelope fields

- [x] 3.1 `listing_partial_hint(loaded, total)` → `OperatorHint(
      code="listing_partial", severity="info")` naming the counts.
- [x] 3.2 Test: `items_loaded`/`items_total` present on `AskResponse` /
      `FetchResponse` for a partial listing, pruned for a non-listing page.
- [x] 3.3 Test: a partial listing sets the hint and does NOT set
      `retrieval_incomplete` / `status: failed` (info, not wall).
- [x] 3.4 Added `items_loaded`/`items_total` to both models + the hint factory;
      plumbed through `build_response` / `build_ask_response`.

### 4. Completeness phase

- [x] 4.1 Test (fetch + ask, stubbed tiers): a listing whose DOM carries 31
      records with an oracle of 40 returns `items_loaded: 31`, `items_total: 40`,
      and a `listing_partial` info hint — real answer intact.
- [ ] 4.2 Distinct narrow-the-query `try_url` steer for search URLs (folded into
      Slice 2 with the scroll-vs-steer URL-shape branch).
- [x] 4.3 Test: a complete listing (40 of 40) emits no signal and no `items_*`.
- [x] 4.4 `_phase_listing_completeness(fc, raw_html=...)` runs after extraction.
- [x] 4.5 Spec deltas green: `openspec validate --strict`.

## Slice 2 — Bounded scroll-to-complete (opt-in) — DONE (Zyte path)

> Implemented 2026-07-06 on top of Slice 1. Full gate green (1095 tests, 90%).
> Tests in `tests/capabilities/listing_completeness/test_listing_completeness_scroll.py`.
> Scope note: the **Zyte scrolling render** is the Slice 2 mechanism (fully
> deterministic-testable via a stubbed scrolling paid tier). The **local
> own-browser scroll-to-stable loop** (5.1/5.3) is deferred to Slice 2b — it
> needs live-browser verification (out of `make check`), and the Zyte path
> already delivers the capability + the whole orchestration.

### 5. Scroll on the render tier

- [ ] 5.1 Local backend scroll-until-stable loop (deferred to Slice 2b — live).
- [x] 5.2 Test: `_zyte_extract_request(scroll=True)` appends a bounded
      `[scrollBottom, waitForTimeout]×cap` action sequence in `browserHtml`
      mode; `scroll=False` / `raw` send the plain request (regression).
- [x] 5.3 Zyte `actions` path added (`_zyte_extract_request` + `scroll=` on
      `ZyteTier.fetch`, cap from `settings.listing_scroll_cap`).

### 6. `listing_partial` escalation trigger (shared cap)

- [x] 6.1 Test: a partial listing on a non-scrolling tier with
      `complete_listings=True` requests a scrolling render (via `_escalate_paid`,
      `scroll=True`). Own-browser-preference is part of deferred Slice 2b.
- [x] 6.2 Test: shares the single paid-dispatch cap — `_listing_wants_render`
      returns False when `paid_dispatches >= 1` (a prior wall/obstacle render).
- [x] 6.3 Test: oracle `> listing_scroll_max` (broad search) → no scroll, signal
      stands (the hint's copy carries the narrow-the-query steer).
- [x] 6.4 Test: after the render, re-count → oracle met drops the signal;
      still-short keeps `listing_partial` with the updated count; render-added-
      nothing (no key) keeps the Slice 1 signal.
- [x] 6.5 Wired `_phase_listing_render` through `_escalate_paid` + shared cap;
      added `complete_listings` / `listing_scroll_max` / `listing_scroll_cap`
      to `AppSettings`.

### 7. Close-out

- [x] 7.1 `make check` green (1095 tests, coverage 90%).
- [ ] 7.2 `make bench` — live-network + LLM quota; run before a release, not in
      the dev loop (deferred per project convention).
- [ ] 7.3 `make install-global` — run at release time so the live MCP binary
      picks up the change (deferred; the feature is off by default anyway).
