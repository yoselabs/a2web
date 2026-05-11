# Retrospective — Phase B research vs reality

Written after Phase B landed. Documents the gap between the OSS-adoption plan (5 swaps) and what actually shipped (1.5 swaps). Goal: improve future research briefs.

## Outcomes

| Swap | Plan | Reality | Reason |
|---|---|---|---|
| trafilatura metadata bundle | adopt | **shipped** | API genuinely matches — single call, bundled output |
| fit-md → trafilatura native | validate then delete | **shipped** | Validation gate passed (0/4 fixtures regress >20%) |
| htmldate removal | drop | **shipped** | Trafilatura's `extract_metadata().date` replaces it |
| hishel HTTP cache | adopt | **deferred** | API requires owning transport, not a wrapping shim |
| aiometer hedged race | adopt | **deferred** | "first result" semantics ≠ "first success" we need |
| purgatory proxy quarantine | adopt | **deferred** | Sync API vs async breakers — net more code |
| stdlib RotatingFileHandler | adopt | **deferred** | Sync handler wrapped in to_thread loses async semantics |

**Hit rate: ~30%.** Three of four "adopt this OSS library" recommendations reversed on closer inspection.

## What went wrong with the research

The research agent (general-purpose, web-search) evaluated candidates against four filters: Python 3.12+, MIT/Apache/BSD, recent maintenance, light deps. All four reversed swaps **passed** those filters. The filters didn't catch what mattered.

What the filters missed, in order of how often it bit us:

1. **API shape vs. our shape.** hishel wants to own the HTTP transport (request_sender callback). Our cache is a thin wrapper outside the tier loop. Adopting hishel would mean restructuring every tier — not a shim, a re-architecture. The research saw "hishel does HTTP cache" and stopped there.

2. **Sync vs async surface.** purgatory exposes `.get_breaker(...).context()` (async). ProxyPool exposes `.acquire()` (sync). Library swaps that change function color propagate through every caller.

3. **Subtle semantic differences.** aiometer's `run_any` is "first result wins, cancel losers." We want "first success wins, fall back to second if first returns None." Same word "race," different contract.

4. **Effort to wrap vs effort to keep.** stdlib RotatingFileHandler is well-tested and free of deps, but to preserve our `await write_record(...)` interface we'd wrap in `asyncio.to_thread` — a thread hop per write, less idiomatic than the 98 LOC aiofiles version we already have.

## What worked

trafilatura's `extract_metadata()` was the one clean adoption because:
- API match: takes HTML, returns dict-like object with title/author/date/image — exactly what we wanted to extract.
- No transport ownership change.
- No sync/async friction (called inside our existing `asyncio.to_thread` chokepoint).
- Already a transitive dep (we used `trafilatura.extract` for body); using the metadata side just consumed more of the existing API.

The fit-md validation gate also worked because the design called for empirical verification before deletion. Pattern: "swap is OK iff validation passes" trumps "swap is OK iff library exists."

## Lessons for future research briefs

When asking an agent to evaluate OSS swap candidates, the brief should require:

1. **Quote the candidate library's primary entry-point signature.** Forces inspection beyond README. Catches sync/async mismatch immediately.
2. **Diagram the integration shape.** "Where does the library sit relative to our code — wrapping us, wrapped by us, alongside us?" Catches transport-ownership mismatch (hishel) and the "you must restructure to fit our shape" gotchas.
3. **Run one integration test.** Even a 10-line synthetic adapter that exercises the seam catches semantic mismatches (aiometer's first-result vs first-success).
4. **Quantify the LOC delta honestly.** "library is N LOC, our code is M LOC, shim is K LOC" — final answer must include K. Research had a habit of comparing "lib's LOC" to "our LOC" without counting the bridge.
5. **Lower confidence threshold.** Default to "keep custom" unless integration is provably ≤ 50 LOC of glue and semantics match exactly. 80% of "could swap" never reaches "should swap."

A small `evaluate-oss-swap` skill that bakes these into the prompt is worth creating before the next research-driven refactor.

## Net effect

- **Plan:** Phase B drops ~510 LOC, swaps 5 libraries.
- **Actual:** Phase B drops ~180 LOC, swaps 1 library (trafilatura's metadata side, htmldate dropped).
- **Backlog gain:** four deferred items with specific architectural reasons, not vague TODOs. Future revisits can be evidence-driven.
- **Codebase honest:** 189/189 tests pass, 87.40% coverage. The deferrals are visible in BACKLOG.md, not silently dropped.

The headline target ("drop the most LOC possible") shifted toward the more durable goal ("only swap when the swap is clearly better"). That's the right tradeoff at v0.2.
