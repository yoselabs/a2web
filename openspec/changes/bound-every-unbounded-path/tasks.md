# Tasks

Groups 1–3 are independent. Group 1 is the security-shaped one and is cheapest;
do it first.

## 1. `hn.py` recursion is unbounded on untrusted input

**SHIPPED 2026-08-01.** Both shapes reproduced as `RecursionError` at depth
5000 before the fix. One deviation, recorded at 1.4 below. The architecture
guard's FIRST draft was itself vacuous — it accepted the substring `budget`
anywhere in the function, including the parameter name, and so stayed green
when the bound was deleted from the body; it now requires an actual comparison.
Caught only by running the fix-reverted check against the guard as well as the
witnesses.

- [x] 1.1 Write the failing test: a synthetic HN tree nested past 1000 levels
      raises `RecursionError` through `_render_kid`. Written in the real API
      shape, not an approximation — it controls one variable (depth), which is
      the legitimate use of a synthetic fixture.
- [x] 1.2 Write the second failing test: a chain of DELETED comments, which
      recurses via `hn.py:240` with `depth` unchanged and therefore defeats a
      depth cap.
- [x] 1.3 Add `_MAX_DEPTH = 20` and `_MAX_COMMENTS = 400`, matching `habr.py`
      name-for-name and value-for-value.
- [x] 1.4 ~~Advance `depth` on the deleted-comment path.~~ **Deliberately NOT
      done.** Advancing `depth` there would re-indent every existing thread
      containing a deleted comment — a wire change to fix a bound. Decrementing
      the shared comment budget on that path bounds the recursion just as hard
      (≤ `_MAX_COMMENTS` frames) with no rendering change, which is what ships.
      `test_the_deleted_chain_is_bounded_by_the_comment_budget` asserts the
      bound rather than the mechanism, so it stays honest either way.
- [x] 1.5 Declare truncation in the render when a bound is hit, as
      `arxiv.py:288` does for listings.
- [x] 1.6 Add the architecture guard: every handler rendering a recursive
      structure has a depth bound. Give it a non-vacuity floor asserting it
      found the three known tree-renderers.

## 2. The LLM call has no timeout

**SHIPPED 2026-08-01.** Two design choices worth carrying forward:

- 2.3/2.5 done by wrapping the PROVIDER at `select_provider`, not by wrapping
  each `complete()`. Five call sites exist today and the sixth would be written
  without a bound — which is how the unbounded state arose. One seam covers
  every caller, including ones not yet written, and composes with
  `anyllm.cost.with_cost_guard` the same way.
- 2.4's hint rides the EXISTING degrade seam because `LLMTimeout` subclasses
  `AnyLLMError`. Extractor and judge already convert that into an empty answer
  plus a carried `provider_error`; an `a2effect` type would have escaped as an
  exception those callers have never seen, and would have forced
  `packages/llm_extract/` to import a domain module it must not.

Two defects in the first draft, both caught by existing guards rather than by
review: wrapping unconditionally produced a truthy `TimeoutProvider(inner=None)`
that destroyed the `no provider → None` contract the whole `ResourceUnavailable`
seam rests on, and the new doubles did not declare `DOUBLES_ARM`.

- [x] 2.1 Write the failing test: a provider that never returns hangs the
      extraction call.
- [x] 2.2 Add an operator-configurable LLM timeout setting.
- [x] 2.3 Wrap `complete()` at a2web's seam with `asyncio.timeout`.
- [x] 2.4 Emit an operator hint on expiry, worded as *a2web stopped waiting* —
      not as an upstream cancellation a2web cannot verify.
- [x] 2.5 Apply at every `complete()` call site (extractor, judge, bench judge).
- [x] 2.6 File the shelf promotion: `anyllm.LLMProvider.complete()` needs a
      per-request timeout. Record it in BACKLOG under T7, not as a task here.

## 3. There is no per-fetch deadline

**SHIPPED 2026-08-01.** 3.1's measurement is recorded at the `fetch_deadline_s`
setting so it sits next to the number it justifies. 3.4 is enforced at the
DISPATCH SITE (`_within_budget`), not inside each tier: there are eight tiers
plus the handlers, and a bound re-implemented nine times is the one that will be
missing from the tenth. The check happens BEFORE a hop starts rather than by
cancelling one mid-flight — a running hop has usually already paid its network
cost, and killing it converts a slow-but-succeeding fetch into a failure.

- [x] 3.1 Measure the current worst-case ladder walk, so the default is derived
      rather than guessed. Record the measurement.
- [x] 3.2 Add the deadline setting, defaulted above the measured worst case.
- [x] 3.3 Set a monotonic deadline at `fetch()` entry; carry it on
      `FetchContext`.
- [x] 3.4 Bound each hop by `min(own timeout, remaining budget)`.
- [x] 3.5 On expiry, produce `status: failed` + `retrieval_incomplete: true` +
      an operator hint naming the deadline.
- [x] 3.6 Test that no further tier or escalation is dispatched after expiry.
- [x] 3.7 **Decided: NO separate default.** `fetch_raw` skips the LLM, so its
      worst-case serial walk is 227s against `query`'s 407s — both comfortably
      under the single 480s deadline. A second knob would have to be kept in
      sync with the same per-hop constants for no protection the first one does
      not already give, and a deadline nobody re-derives when a hop constant
      changes is worse than none. One deadline, derived, documented at the
      setting.

## 4. Request bounds become configuration

**SHIPPED 2026-08-01.** 4.1's inventory: 14 request bounds (5 tiers, 9
handlers); `browser_idle_timeout_s` and `browser_reaper_interval_s` are idle/poll
intervals and correctly out of scope. 4.2 routes them through a SCALE
(`request_timeout_scale`) rather than 14 absolute overrides or one flat value —
the constants are individually tuned and their ratios carry meaning, so 14 knobs
would be a second copy of the table that drifts and one flat value would cap the
paid render at the probe's budget. Four sites had no `state` in scope
(archive/habr/v2ex/github) and thread the resolved value instead.

- [x] 4.1 Inventory the 34 timeout sites; identify which are request bounds
      (versus idle/poll intervals, which are out of scope).
- [x] 4.2 Route the request bounds through settings.
- [x] 4.3 Test that an operator-set value reaches the call site.

## 5. Close out

- [x] 5.1 `make check` green.
- [x] 5.2 Confirm each witness fails when its fix is reverted.
- [x] 5.3 Add a corpus entry for a deadline-exceeded fetch, per the
      never-lose-a-case rule.
- [x] 5.4 Update `CLAUDE.md` — it documents no deadline today.
- [x] 5.5 Move the BACKLOG entries to `BACKLOG-CLOSED.md`.
