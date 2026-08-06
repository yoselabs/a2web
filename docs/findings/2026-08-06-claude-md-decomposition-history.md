# CLAUDE.md decomposition — relocated incident history

**Date:** 2026-08-06. This file exists because `CLAUDE.md` grew to ~69KB
(~27k tokens) by accreting both live rules and the incident narrative that
justified them, in one file loaded unconditionally every session. The rules
stayed in `CLAUDE.md` (tightened) or moved to the `docs/architecture/*.md`
module-reference files; the "this failed, here is exactly how" narrative
that predates or accompanies them moved here. Nothing below is a live rule —
each item's enforcing mechanism (if any) is named at the top of its section
in `CLAUDE.md` or the relevant `docs/architecture/` file.

## Wire encoding

**TSV columns from one row.** `_derive_columns` read only `rows[0]` and
deleted every key the first row happened to elide. Rows are heterogeneous
BY CONSTRUCTION — model serializers elide fields at their default
(`OperatorHint._omit_default_severity`, `PruneEmpty`) — so reading `rows[0]`
dropped the `critical` severity from `try_user_browser` whenever a quieter
hint preceded it in the row list: ADR-0009's loudest signal reached the
agent unmarked. `structured_content` was unaffected by the bug, which is
why the ~1350 existing field-presence assertions against `call_wire` missed
it entirely — the defect was only visible on `call_text`, the channel the
agent actually reads. Fixed 2026-07-31 by making columns the UNION of every
row's keys via the one shared `wire.encode_rows`.

## fetcher_response.py — response contract

**Member-count drift in the docstring.** Before the `ResponseContext`
Protocol replaced a hand-maintained name-ledger (2026-08-03,
`decompose-fetcher-into-files` §7.0), the module's own docstring claimed
"42 of 72" fields read from `FetchContext` while the superseded `_READS`
ledger it was describing held 45 entries, and that ledger's own docstring
said "44 of 74" — three different numbers, all wrong at the moment of
reading, all describing the same set. `CLAUDE.md` itself repeated one of
these numbers for a while, which is why its current text says "never
restate the member count in prose" instead of stating one. The Protocol
made the field impossible to typo: `ty` checks names AND types at every
call site, and immediately caught a defect the ledger structurally could
not — `fc.routing` is the package-side `llm_extract.RouterPayload`, not the
pydantic mirror of the same name in `models.py`.

## Tier ordering

**`_PAID_TIER_ORDER` silence.** `_PAID_TIER_ORDER = ("zyte", "firecrawl")` —
zyte first — existed in code but `CLAUDE.md` said nothing about which paid
rung ran first until 2026-08-02. A reader relying on the doc for "what order
do paid tiers try" had no way to know without reading the tuple itself.

## Fetcher pipeline — later stages discarding a producer's claim

This failed FOUR times in one week, all the same shape: a later stage
silently replaced or relabelled what an earlier, more-informed stage
produced, instead of only adding to it.

1. The `other_pages` fold rewrote every handler `kind` to `structural`,
   false for 7 of 7 handler links, and dropped `anchor` entirely.
2. `_compose_next_links` deleted handler links the LLM did not repeat back
   — the LLM leads, it does not filter, and treating "the LLM didn't
   mention it" as "the handler was wrong" threw away real findings.
3. `_run_extraction_escalation` replaced a site handler's whole index with
   the generic miner's, discarding site-specific structure the handler
   understood and the miner was only guessing at from markup shape.
4. `_records_to_next_links` labelled every catalog row "source · discussed
   page" — the aggregator's own vocabulary — so commerce listings announced
   they were "discussing" what they sell.

The fix in each case: a later stage may ADD to an index, never silently
replace or relabel it. `fetcher_response.py`'s docstring names this rule for
its own scope; it applies upstream of it too.

**Truncation declared against an unfalsifiable number.** `hn` compared what
it rendered against what it had ASKED Algolia for — the same number by
construction, since the request size and the render count are the same
input threaded two ways — so the "truncated" note was structurally
unreachable: a search matching 912 stories looked identical to one matching
30. Fixed by reading the SOURCE-stated total (`nbHits`) instead, or saying
the weaker true thing ("of what we received", as `reddit` does).

**Recursion in a comment-tree renderer.** `hn._render_kid` had no depth cap,
and a thread nested past CPython's frame limit raised `RecursionError` out
of the handler entirely — a crash caused by untrusted remote input (the
comment tree structure), not a bug in the renderer's logic. A depth cap
alone is insufficient: a branch that does not advance `depth` (a chain of
deleted comments, which the site keeps as empty placeholder nodes) defeats
it. Fixed with depth cap AND a shared node budget, plus declaring the
truncation — a caller that cannot tell "the thread ends here" from "a2web
stopped rendering" reads the first into the second, the ADR-0009 harm.

## Architecture-guard vacuity

Guards passing while checking nothing has happened for real, twice:

- **30 of 32 architecture tests passed against an empty source tree** —
  none of them asserted they had found any candidates to check, so a walk
  that matched zero files was indistinguishable from a walk that found zero
  violations. Fixed by `_walk.walked_files(minimum=…)`, a non-vacuity floor
  now required on every walk.
- **`test_tools_return_pydantic_not_str` stayed green for the entire a2kit
  sunset** while its matcher still looked for `@a2kit.read`, a decorator
  that no longer existed anywhere in the tree by the time the sunset
  finished. The guard's own docstring described a decorator neither used
  nor deleted-and-checked — it had quietly become a test of nothing. Fixed
  by matching `@mcp.tool` and adding a tool-count floor.
- **`test_terminal_hint_coherence`** mapped `operator_error` to
  `frozenset({None})`, commented "paid_auth_error hint emitted at the paid
  tier" — no such hint existed in code at the time the comment was written.
  The allowlist entry would have stayed green through that hint's eventual
  deletion, because it asserted absence, not presence, of something that
  was never real. The lesson: an allowlist justified by something that does
  not exist is worse than no entry — it reads as a decision. Fix the
  pattern: assert the hint is PRESENT and that the code named is
  constructible, not merely that nothing unexpected showed up.

## Fixture oracle failure

**Hand-written fixtures cannot fail when the parser's own assumption is
wrong.** On 2026-07-28, both the arXiv listing parser and the Wikipedia
wikilink parser were found returning ZERO rows against live pages holding
47 entries and 1066 anchors respectively — while each sat behind a fully
green test suite built on hand-written fixtures. The fixtures had been
authored by the same person, at the same moment, using the same mental
model as the parser, so they could only confirm the parser agreed with
itself, never that it still matched the live site. Fixed by requiring
site-parse fixtures to be CAPTURED and committed
(`tests/fixtures/captured/`); synthetic fixtures remain legitimate only
where they control one variable (a count, a language) and are written in
the real markup shape.

**Handler markup parsed by regex, not DOM, failed the same way twice
more**, born from the same 2026-07-28 investigation: named capture groups
like `(?P<x>` read as ordinary markup to a naive scanner, and
`listing_oracle`'s `rel\s*=` check was itself a regex, so a regex checking
for a regex pattern missed the actual target. Fixed by funnelling all
handler markup parsing through the shelf's `dom_schema.extract`, with every
`re.compile` in `handlers/` restricted to anchored URL paths only —
enforced by `tests/architecture/test_handler_markup_funnel.py`.

## Golden files as proof

**`list_tools.json` froze a typo perfectly.** The captured golden preserved
`~95%%` — a doubled-percent typo in a tool description that every agent
reading the tool list would see — unchanged through seventeen rounds of
wire review, because a golden test only proves a surface has not *changed*;
it says nothing about whether the surface was correct when captured. It
took rendering the same underlying string through a different surface
(`--help` output) for a human to actually see it and notice the error.

## Deployment — the browser-arg claim

**This line said the opposite of the truth until 2026-08-03.** `CLAUDE.md`
claimed "no local browser" in the deployed container while
`openspec/specs/container-image` asserted Chromium unconditionally — both
describing the exact same `Dockerfile`, and neither reader could have got a
deployment right from either document. The actual fact: `Dockerfile`'s
`INSTALL_BROWSER` build arg defaults to `false` (so a bare `docker build`
produces the ~390MB browserless image), but `release.yml` passes
`INSTALL_BROWSER=true` for every published tag, so the actual published
image DOES carry the browser rung (patchright + zendriver + Chromium + its
desktop system-lib tree, ~1.35GB of a ~1.9GB image). The fix was to cite
the build argument, never a conclusion, so the two documents cannot
independently drift into contradicting facts about the same file again.
Now pinned by `tests/capabilities/endpoint_auth/test_container_browser_arg.py`,
which reads the default out of the `Dockerfile` and the override out of
`release.yml` directly, rather than trusting either doc's prose.

## CI gate history

Before 2026-07-31 the only workflow running `make check` (and therefore
every architecture guard) was `release.yml`, triggered only `on: push:
tags: v*`. That means every architecture guard ran at tag time and at no
other time — a violation could land on `main`, survive an arbitrary number
of pushes, and only surface in a batch attributed to whoever eventually cut
the next release tag, long after the change that introduced it. Fixed by
`openspec/changes/archive/2026-08-01-run-the-gate-on-every-push/`, which
added `.github/workflows/ci.yml` running on every push and PR.
