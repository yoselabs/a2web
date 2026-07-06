# Design — listing-completeness

## The axis this change adds

The pipeline measures retrieval on a **presence** axis and has no measure on a
**sufficiency** axis. This is the whole idea, so it's worth pinning:

```
                        presence: "is answer-bearing content here at all?"
                        ─────────────────────────────────────────────────
   obstacle=empty  ─────▶  SPA shell, 0 real items      → paid render (shipped)
   obstacle=blocked ────▶  soft wall the LLM summarised → paid render (shipped)
   wall verdicts    ────▶  captcha/anti-bot/paywall     → try_user_browser (shipped)

                        sufficiency: "did I get ALL items of a listing that IS here?"
                        ────────────────────────────────────────────────────────────
   40 of 40         ─────▶  complete                    → nothing
   31 of 40         ─────▶  PARTIAL (real items, but not all)  → THIS CHANGE  ← the gap
   31 of 12,000     ─────▶  PARTIAL & unbounded         → signal + steer (no scroll)
```

A page can be present-but-insufficient: genuine records, every gate green, no
obstacle — and still a truncated sample. Nothing fires today because every
existing signal keys off *failure to get content*, and here we *got* content,
just not all of it.

## Why not fold this into `obstacle`?

Tempting (the machinery is right there), but wrong:

- `obstacle` is emitted by the LLM extractor about the **answer**. A partial
  listing has a perfectly good answer over the items that *did* load — the LLM
  has no way to know 9 more exist off-DOM. Sufficiency is a **structural**
  property (count vs. advertised total), not a semantic one. It must be measured
  by the pipeline, not asked of the model.
- `_INCOMPLETE_OBSTACLES = {empty, blocked}` drives a plain `browserHtml` render
  with **no scroll**. Even if we forced an obstacle here, that render would
  re-fetch the SPA and still get the first 31. The missing capability is the
  scroll, not the trigger.

So: new structural verdict, new signal, **reuse** the escalation plumbing.

## Slice 1 — the signal

### Progress count (free, already computed)

`extract_records(raw_html)` runs on every fetch inside `_run_extraction_escalation`
(no handler/shape gate — confirmed `fetcher.py:1117`). `len(record_set.records)`
is the generic `loaded`. Today it's logged in `StageEnded.extra["records"]` and
discarded. We keep it on the `FetchContext`.

### Oracle (the advertised total)

New pure `listing_oracle(html, *, records) -> int | None`, tried in reliability
order:

1. **Structured**: JSON-LD / microdata `ItemList` → `numberOfItems`. Most
   reliable; unambiguous.
2. **Visible count text**: a small multilingual regex table — `N sonuç`
   (Turkish), `N results`, `N ürün`, `showing A–B of N`, `N products`,
   `N+ items`. Take the max plausible match on the page.
3. **None** → no numeric oracle. Fall back to a **structural** partial signal
   only: is there a `rel=next`, a load-more control, or pagination nav *and* were
   we served by a non-scrolling tier (raw/jina)? If so, "more exists" (no count).

Oracle extraction is pure and lives in its own module (a2web domain glue, not a
package — it reads no settings but is web-shaped). It never blocks: any failure
returns `None` and the page is treated as "no oracle."

### Verdict (reuse, don't rebuild)

```python
readiness = content_expectations.assess(loaded=len(records), total=oracle)
# ready   → complete, emit nothing
# partial → listing_partial signal (+ items_loaded/items_total)
# fail    → oracle says items exist but zero parsed; this is the presence axis —
#           defer to the existing obstacle/wall machinery, do not double-signal.
```

`assess` is already generic; only its docstring names Reddit. No code change to
the contract — this change is its second caller.

### Signal shape

- `OperatorHint(code="listing_partial", severity="info")`. Message names
  `loaded`/`total` when known ("Parsed 31 of 40 listed items; more load on
  scroll"), or "more items available (page 1 of a longer listing)" when only a
  structural signal exists.
- `items_loaded` / `items_total: int | None` on both envelopes, pruned from the
  wire when the page is not a listing (mirrors the `comments_*` precedent
  exactly).
- **Not** `retrieval_incomplete`. Decision: partial-listing is `info`. The floor
  tenet is satisfied by *loudness*, not by a `failed` status — we did return
  real, usable records. `retrieval_incomplete` stays reserved for walls/obstacles
  (zero-useful-content). This keeps the two axes legible on the wire.

### Steering (rides existing fields)

For a **search-shaped** URL (`?q=` / `/ara` / `/search` / `/ara?` patterns) the
correct completion of a too-broad result set is *refine the query*, not
*paginate*. The hint's `fix` and an added `try_url` entry advise a narrower
query. For a **bounded list** (small known oracle) the hint advises scroll / open
in browser. The vehicle (`try_url`, `ask_here`) already exists on the envelope;
only the partial signal is new.

## Slice 2 — the action

### Scroll-until-stable (termination without an oracle)

The render tier loops: render → count records → scroll to bottom → wait for
network idle / a short settle → re-count. Stop when the count does not grow
across a step (DOM-stable) **or** `scroll_cap` scrolls / `scroll_budget_s`
elapsed. The oracle is **not** needed to terminate — only to *label* success
afterward.

- **Zyte `browserHtml`**: server-side, so we can't loop adaptively. Send a fixed
  bounded `actions` sequence (`scrollBottom` + `waitForTimeout`, repeated
  `scroll_cap` times) in one request; Zyte executes them before snapshotting.
- **Local backend** (Playwright/zendriver): adaptive loop in-process (we can
  re-measure between scrolls), generalising the existing single-shot
  `_scroll_and_retry`. Preferred when available — no paid egress.

### Trigger + budget (shared, not parallel)

`listing_partial` on a non-scrolling tier requests a scrolling render via the
existing `escalate_to_render` / `_escalate_paid` path. It **shares** the single
one-paid-dispatch-per-fetch cap with the gate-wall and obstacle triggers — so a
fetch that already spent its render (e.g. an obstacle render) does **not** get a
second one for the listing; the signal simply stands. This keeps the cost
envelope identical to today's worst case (one render per fetch).

### Scroll-vs-steer decision

```
oracle known & (total - loaded) small & total ≤ SCROLL_MAX   → scroll
oracle known & total > SCROLL_MAX (broad search)             → steer, no scroll
oracle unknown & structural "more exists"                    → scroll if cheap
                                                               (local browser),
                                                               else signal only
```

`SCROLL_MAX` bounds "worth completing" (e.g. a few hundred items). Above it,
scrolling is the lunatic errand; steer instead.

### Re-label

After a scroll render, re-extract, re-count, re-assess. `ready` → drop the
signal, return complete. `partial` (capped / virtualised / still short) → keep
`listing_partial` — the miss stays loud. This is the honest backstop for
DOM-virtualised listings where scroll cannot accumulate the count.

## Sequencing / risk

- **Ship Slice 1 first, alone.** It's free, additive, and independently
  valuable (makes every partial listing honest). It de-risks Slice 2 by making
  the verdict observable in production before we spend renders on it.
- **Slice 2 behind a settings toggle** (`complete_listings: bool`, default
  conservative). "Slower is fine" is the stated appetite, but flipping the common
  listing path from free-curl to paid-render is a cost-profile change that
  deserves an operator switch, not a silent default.
- **Oracle false positives**: a stray "1000+ reviews" number misread as an item
  count would fabricate a partial signal. Mitigation: structured `ItemList`
  first; the visible-count regex is anchored to result/product/item nouns, not
  bare numbers; tolerance in `assess` absorbs small gaps; and an `info` signal is
  low-blast-radius if occasionally wrong.
- **`fetch_raw` path**: gets the signal (record count exists) but never the
  scroll (no LLM, no render escalation on that path) — documented, not a bug.

## Non-goals

- URL-based pagination crawling (`?page=2,3`) as a retrieval strategy — a
  distinct, larger design; this change scrolls one page.
- Per-site oracle handlers — generic extraction only.
- Making the LLM count items — sufficiency is structural, measured off the DOM.
