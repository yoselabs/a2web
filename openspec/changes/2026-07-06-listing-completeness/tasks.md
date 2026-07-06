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

## Slice 2 — Bounded scroll-to-complete (opt-in; after Slice 1 merges)

### 5. Scroll-to-stable on the render tiers

- [ ] 5.1 Test: the local backend scroll loop stops when the record count is
      stable across a step, and when `scroll_cap` / `scroll_budget_s` is hit
      (whichever first); keeps the largest snapshot.
- [ ] 5.2 Test: `ZyteTier.fetch(..., scroll=True)` sends a bounded
      `actions: [scrollBottom, waitForTimeout]×N` sequence in the `browserHtml`
      request body; `scroll=False` sends today's plain request (regression).
- [ ] 5.3 Generalise the local `_scroll_and_retry` into a scroll-until-stable
      loop; add the Zyte `actions` path.

### 6. `listing_partial` escalation trigger (shared cap)

- [ ] 6.1 Test: a `listing_partial` verdict on a non-scrolling tier (raw/jina)
      with `complete_listings=True` requests a scrolling render; the free
      own-browser is preferred before paid egress.
- [ ] 6.2 Test: the render shares the single one-paid-dispatch cap — a fetch that
      already spent a render (gate wall / obstacle) does NOT get a second render;
      the signal stands.
- [ ] 6.3 Test: oracle `total > SCROLL_MAX` (broad search) → no scroll, signal +
      steer only ("don't scroll the universe").
- [ ] 6.4 Test: after a scroll render, re-count → oracle met/stable drops the
      signal (complete); capped/virtualised/still-short keeps `listing_partial`
      (loud miss holds).
- [ ] 6.5 Wire the trigger through `escalate_to_render` / `_escalate_paid` +
      the shared cap; add `complete_listings` + `scroll_cap` / `scroll_budget_s`
      / `SCROLL_MAX` to `AppSettings`.

### 7. Close-out

- [ ] 7.1 `make check` green (coverage ≥85%).
- [ ] 7.2 `make bench` — confirm the four-axis output benchmark did not regress
      on token cost / clarity for non-listing pages (listings should improve on
      completeness).
- [ ] 7.3 `make install-global` so the live MCP binary picks up the change.
