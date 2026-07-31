# Tasks

## 1. Handler-served API responses are cached for seven days

- [x] 1.1 Write the failing test: a handler returning `application/json` or
      `application/atom+xml` receives the 168-hour TTL.
- [x] 1.2 Add the producer-declared volatility field to `TierResult`.
- [x] 1.3 Populate it in the handlers that serve upstream APIs (arxiv, github,
      hn, reddit, discourse, habr, v2ex).
- [x] 1.4 `_ttl_for` reads the declaration first; the content-type heuristic
      remains only as the fallback for the generic HTTP tiers.
- [x] 1.5 The cross-reference to 4.1 did not apply — 4.1 measures listing
      counts, not cache freshness. Used the already-declared
      `cache_ttl_live_m` (5 min), which existed with exactly this intent and
      was the dead setting group 2 had to resolve. Wiring it up answered both.
- [x] 1.6 Assert a genuinely static asset still gets the long TTL.

## 2. `cache_ttl_live_m` is declared and unread

- [x] 2.1 Decide: wire it up as the short TTL from group 1, or delete it if it
      exactly duplicates `is_live_only`. Look before deciding.
- [x] 2.2 Implement the decision.
- [x] 2.3 Add the guard: every TTL setting declared in `AppSettings` is read by
      at least one code path. Give it a non-vacuity floor — it must assert it
      found the known settings, or an empty walk reads green.

## 3. `_ttl_for` masks a settings rename

- [x] 3.1 Replace `getattr(settings_obj, ..., <literal>)` with direct attribute
      access, deleting the duplicated defaults.
- [x] 3.2 Type the parameter as `AppSettings` rather than `object`, so a rename
      is a type error and not a runtime fallback.

## 4. Listing sufficiency never runs on the handler path

- [x] 4.1 Reproduce: fetch the arXiv listing corpus case and confirm
      `operator_hints` carries no `listing_partial` while the rendered markdown
      says "25 of 445". Record both.
- [x] 4.2 Carry the rendered count and advertised total on `TierResult` from
      listing-rendering handlers. `arxiv.py` already computes both and discards
      them.
- [x] 4.3 Write them into the same `record_count` / oracle inputs the
      record-miner path writes — one assessment, two sources.
- [x] 4.4 Confirm `listing_partial` now fires on the arXiv case with counts
      matching the prose.
- [x] 4.5 Assert a complete listing emits no hint.
- [x] 4.6 Add the prose/hint agreement test — the anti-drift clause.
- [ ] 4.7 **NOT DONE — deliberately, see below.** Only `arxiv` actually holds an
      advertised total, verified against the committed capture (408 advertised,
      25 rendered). `discourse` and `v2ex` compute no total at all, so there is
      nothing to declare. `reddit`'s total is a COMMENT count, already wired via
      `comments_loaded`/`comments_total`. `hn` has `nbHits` in the Algolia
      payload, but its semantics on a `tags=front_page` query are unverified —
      the front page IS 30 items, so a larger `nbHits` would emit a FALSE
      `listing_partial`. A false "incomplete" is worse than none: it teaches the
      caller to ignore the signal. Needs a captured HN fixture first; left open
      rather than guessed.

## 5. Close out

- [x] 5.1 `make check` green.
- [x] 5.2 Confirm each witness fails when its fix is reverted.
- [ ] 5.3 **NOT RUN.** `make bench` is live-network and spends LLM quota
      (ADR-0016), so it is not something to fire off unasked. The change is
      otherwise complete and the four-axis harness tests pass in `make check`.
- [x] 5.4 Superseded note corrected in `eval/findings_2026-07-28-full.md`.
- [x] 5.5 Move the BACKLOG entries to `BACKLOG-CLOSED.md`; leave the
      `_MAX_RECORDS × DEFAULT_TOLERANCE` entry open with a note that
      `_MAX_RECORDS` was not found in `src/`.
