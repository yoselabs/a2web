# Tasks

## 1. Handler-served API responses are cached for seven days

- [ ] 1.1 Write the failing test: a handler returning `application/json` or
      `application/atom+xml` receives the 168-hour TTL.
- [ ] 1.2 Add the producer-declared volatility field to `TierResult`.
- [ ] 1.3 Populate it in the handlers that serve upstream APIs (arxiv, github,
      hn, reddit, discourse, habr, v2ex).
- [ ] 1.4 `_ttl_for` reads the declaration first; the content-type heuristic
      remains only as the fallback for the generic HTTP tiers.
- [ ] 1.5 Set the short TTL from the measurement in task 4.1, not by guess.
- [ ] 1.6 Assert a genuinely static asset still gets the long TTL.

## 2. `cache_ttl_live_m` is declared and unread

- [ ] 2.1 Decide: wire it up as the short TTL from group 1, or delete it if it
      exactly duplicates `is_live_only`. Look before deciding.
- [ ] 2.2 Implement the decision.
- [ ] 2.3 Add the guard: every TTL setting declared in `AppSettings` is read by
      at least one code path. Give it a non-vacuity floor — it must assert it
      found the known settings, or an empty walk reads green.

## 3. `_ttl_for` masks a settings rename

- [ ] 3.1 Replace `getattr(settings_obj, ..., <literal>)` with direct attribute
      access, deleting the duplicated defaults.
- [ ] 3.2 Type the parameter as `AppSettings` rather than `object`, so a rename
      is a type error and not a runtime fallback.

## 4. Listing sufficiency never runs on the handler path

- [ ] 4.1 Reproduce: fetch the arXiv listing corpus case and confirm
      `operator_hints` carries no `listing_partial` while the rendered markdown
      says "25 of 445". Record both.
- [ ] 4.2 Carry the rendered count and advertised total on `TierResult` from
      listing-rendering handlers. `arxiv.py` already computes both and discards
      them.
- [ ] 4.3 Write them into the same `record_count` / oracle inputs the
      record-miner path writes — one assessment, two sources.
- [ ] 4.4 Confirm `listing_partial` now fires on the arXiv case with counts
      matching the prose.
- [ ] 4.5 Assert a complete listing emits no hint.
- [ ] 4.6 Add the prose/hint agreement test — the anti-drift clause.
- [ ] 4.7 Extend to the other listing handlers (hn front page, discourse topic
      list, reddit listing), each with a captured fixture.

## 5. Close out

- [ ] 5.1 `make check` green.
- [ ] 5.2 Confirm each witness fails when its fix is reverted.
- [ ] 5.3 Re-run the arXiv listing bench cell and record the result against the
      2026-07-28 baseline (detail 5 / extract 5 on answer; the `next_links` axis
      is what should move now).
- [ ] 5.4 Update `eval/findings_2026-07-28-full.md` — its "that half is shelf
      work and stays open" note is superseded by D3's route-around.
- [ ] 5.5 Move the BACKLOG entries to `BACKLOG-CLOSED.md`; leave the
      `_MAX_RECORDS × DEFAULT_TOLERANCE` entry open with a note that
      `_MAX_RECORDS` was not found in `src/`.
