# Backlog

Deferred items from the v0.1 build, grouped by target milestone. Each entry
records its source (PR id or engineering doc section), a one-line
description, why it was deferred, and a rough scope tier (S / M / L).

> **Lifecycle.** Items are removed in the change that ships them, and added
> by any future OpenSpec change whose proposal carries an "Out of Scope"
> deferral. Keep this file current — every change that defers adds, every
> change that ships removes.
>
> **Closed entries live in [`BACKLOG-CLOSED.md`](BACKLOG-CLOSED.md).** When an
> item ships, move it there rather than deleting it — several closed entries
> record the incident a surviving invariant exists to prevent.
>
> **Single source of truth.** This file consolidates every known
> deferral. Upstream context: `~/Documents/Knowledge/Projects/120-a2web/v0.1-engineering.md`
> §10 (original v0.2/v0.3 deferrals); §9 (build order) is fully shipped
> and lives in `openspec/changes/archive/`. New deferrals land here, not
> in design docs.

---

## 2026-08-02 — shelf: `record_mine`'s two detection thresholds are unwitnessed (S, shelf)

**Source:** `close-guards-that-read-green` §5.1/§5.2, re-examined 2026-08-02.

Both constants live in
`shelf/packages/record-mine/src/record_mine/detector.py` — `_CONSISTENCY_MIN =
0.70` (`:60`) and `_HEADING_FRAC_MIN = 0.50` (`:62`) — and gate whether a
repeated DOM region is recognised as a record set at all
(`detector.py:320`).

They were a2web's when the tasks were written; `record_extract` was promoted to
the shelf since. **Checked in the shelf clone: its tests reference
`heading_frac` zero times.** The promotion carried the constant and left the
gap, so the number is unwitnessed on both sides of the boundary.

Why it matters, unchanged from the original finding: at `_HEADING_FRAC_MIN =
1.00` record detection dies on any listing whose item titles are not `<hN>` —
which silently removes ADR-0015's index and ADR-0009's completeness signal at
once, in a2web, from a shelf-side edit.

What it needs is what a2web's §5.3 got: a CAPTURED listing page with the
awkward property (titles in `<div>`/`<span>` for 5.1; mixed sponsored/promoted
card types for 5.2), asserted to still detect. A hand-written fixture cannot
falsify either — it would encode the same assumption as the detector.

Do it as shelf work at the next `record-mine` touch, not by reaching across the
boundary from here.

## 2026-08-02 — the comment-thread handlers extract links they cannot carry (S, structure)

Surfaced by `repay-the-shelf-debt` §3.4. Now that `handlers/reddit.py` and
`handlers/twitter.py` go through `content_extract.extract_markdown` instead of
calling `trafilatura.extract` directly, each parse returns **links and headings
alongside the markdown** — measured against the captured `oldreddit_thread.html`:
**6 links**, where the old direct call extracted none.

They are dropped on the floor. `tiers.Rendered` carries `content_md`, `title`,
`byline`, `headings` and no `links` field, so the handler has nowhere to put
them. Threading them through means widening that boundary type and deciding what
the orchestrator does with handler-supplied links — which interacts with
`_compose_next_links` and the ADR-0015 index, so it is not a field addition.

**Headings are a different answer: there is nothing to regain.** The same
measurement found old.reddit renders the thread with ZERO `h1`-`h6` elements, so
the synthesized `Heading(level=1, text=title)` both handlers build is the only
heading available, and switching to `extracted.headings` would have emptied the
list. Do not "fix" that on the assumption the funnel must be richer.

Worth doing because the alternative source is worse: these links come from the
page's own anchors on a real parse, which is exactly the provenance ADR-0014
requires, and the generic miner is guessing from shape by comparison.

## 2026-08-02 — the planner's foreign witness covers one rule of fourteen (S, verification)

`close-guards-that-read-green` §4.1 asked for an outcome-level witness for
`actions/playbook.py` — one observing the RESULT of a routing decision rather
than restating the decision. **Built and it works, but measure what it covers
before treating it as coverage.**

The witness is the `steps` key now blessed on every replay baseline: the ordered
`tier:verdict` sequence a fetch actually dispatched, produced by the real
orchestrator over frozen bytes. Nothing in the corpus names a rule, so it cannot
agree with the planner by construction — which is exactly what the ~49 example
tests in `test_decide_next.py` cannot claim, since they re-encode the rule table
they are checking.

**Probed by deleting rules from `_RULES` and re-running the replay suite:**

| rule deleted | replay result |
|---|---|
| `cloudflare_403_429_archive` | akakce baseline FAILS ✓ |
| `gate_paywall_or_block_archive` | all green — no case exercises it |
| `exhausted_429_escalate` | all green — no case exercises it |
| `gate_browser_signal` | all green — no case exercises it |

So: 1 of 4 probed, and `_RULES` holds fourteen. The corpus's seven cases produce
only four distinct dispatch sequences (`raw→extract→gate`, `site_handler→gate`,
`raw→jina`, and the selftest), because every case but akakce succeeds on the
first tier. **A planner witness needs cases that FAIL interestingly**, and the
corpus is mostly happy paths.

The work is capture-bound, not code-bound: each missing rule needs a captured
page that provokes it (a paywall the gate flags, an exhausted 429, a JS-required
page the gate routes to browser). Capture is the cost; the assertion is free
once the bytes exist.

**Do not delete the example tests to "fix" this.** They are the readable
statement of what each rule means and they catch a deletion or a typo. They are
labelled as documentation in that file's docstring; the error was ever counting
them as verification.

## 2026-08-01 — the bench cannot separate a real quality move from noise (S, eval correctness)

Source: `eval/findings_2026-08-01-pm.md` §Headline.

Two bench runs twelve hours apart over the SAME 42 slugs, across a change that
touched neither answer selection nor extraction, moved `a2web_extract` quality
3.52 → 3.33 and `a2web_detail` 3.27 → 3.40. Those are the sizes of move someone
would plausibly attribute to a prompt or pipeline change — and here they are
pure judge/live-page variance.

There is no repeat-run baseline, so the harness cannot say what ±X means. Any
future claim of the form "this change improved quality by 0.2" is currently
unfalsifiable, in both directions: a real regression of that size is equally
invisible.

Cheapest fix: run the bench twice against an unchanged tree and record the
spread in the axes report, so a delta can be read against it. Roughly $18 and
40 minutes, once. Alternatively pin the corpus to captured pages for the quality
axis (the replay harness already does this for deterministic axes) so live
content rotation stops being a variable.

Related and separate: the `next_links` judge scores page content rather than set
structure (entry above), which is a defect in what is measured rather than in
how noisy it is.

**MEASURED 2026-08-01 — `eval/findings_2026-08-01-noise-floor.md`.** The run pair
was done (two full runs, byte-identical `src/`, ~30 min apart). Cost was ~30 min
of subscription quota per run, not the $18 estimated above — the bench runs on
`claude-code-sdk` under ADR-0016, so it never bills the metered API and the
estimate was wrong in kind, not just in size.

Result: **system-mean floor is ±0.2 on quality and ±0.2 on clarity.** The two
moves this entry was opened over (0.19 and 0.13) are both inside it — they were
not small real effects, they were not effects.

Two things the measurement found that the entry did not anticipate, and which
are why this stays OPEN rather than closing here:

1. **The mean and the cell need different thresholds.** 102 of 124 quality cells
   were identical, but 21 cells moved ≥2 points and the max swing was the full
   5.00. The system mean is calm only because 42 cells average the swings out. A
   per-slug claim is currently worth nothing without repeats; the bench answers
   "did the system move", never "did this page get better".
2. **The noise is retrieval luck, not judge mood.** The swings cluster on walled
   pages. `walled-page-with-preceding-info-hint` scored quality 5 / clarity 0 in
   one run (jina `length_floor`, wall correctly declared) and quality 1 / clarity
   5 in the other (archive tier happened to hit, answer stale). The cell measures
   whether a Wayback snapshot was reachable that minute. Worse, the two axes
   reward opposite branches, so any change touching wall handling or archive
   dispatch will show quality movement confounded with luck.

What remains, and it is a corpus decision rather than a harness one: either the
adversarial slugs' criteria score the **envelope's honesty** — deterministic, and
what ADR-0009 actually requires — instead of the answer's content, or those slugs
get pinned to captured pages. Until then the noisiest cells in the corpus are
measuring the network.

## 2026-08-01 — converge the item set, once `reason` can survive the trip (M, structure)

Source: `openspec/changes/lift-the-item-set-and-renderer/` §4, deferred with its
evidence in that change's `design.md`.

"A set of items on a page" still has seven-plus spellings (`fetcher.py`'s
`RecordSet`, JSON-LD `ItemList`, and the per-handler renderers in `hn`,
`discourse`, `arxiv`, `reddit`, plus GitHub/Wikipedia candidates-only), and the
four operations over it — render · derive-next-links · cap-and-declare ·
project-to-wire — are re-implemented at each.

**Two reasons this did not ship with the rest of the change.**

First, the shared derivation every handler would converge ONTO was itself wrong:
`_records_to_next_links` labelled every catalog row `source · discussed page` —
the aggregator vocabulary — so commerce listings announced they were
"discussing" the products they sell. Fixed in `4628924`, found only by surveying
the target before converging. Converging first would have generalised the defect
to five more sites and called it unification.

Second, and still open: each handler's `reason` carries site-specific signal —
arXiv's author list, hn's `N points, M comments`, github's `issue · N comments`,
discourse's `N replies`, reddit's post age. The shared function emits a fixed
`"item page"` / `"discussed page"`. Converging as written replaces all of them
with a constant, which is a real loss of caller-facing signal dressed as
deduplication.

D2 rejects the polymorphic answer (a protocol per site — that leaves four
operations x N sites). So the convergent type needs to carry a producer-supplied
`reason`/`anchor` through the shared operations. That is a design question the
change never posed. Answer it first.

Related: the same "a later stage must not discard a producer's own claim" rule
was violated three separate times the week of 2026-07-28 (`other_pages[].kind`,
`_compose_next_links`, and the whole handler index in `79d85e8`). Whatever §4
converges on should make that structurally hard, not conventionally discouraged.

**HELD 2026-08-01, deliberately, with an answer already on the table.** The
producer-supplied-`reason` shape above was proposed and was NOT adopted — the
maintainer has further input on what the convergent type should be and wants to
supply it before anyone writes the design amendment. Do not start §4 on the
strength of the proposal in this entry; it is a candidate, not a decision. This
paragraph exists so a future session does not read "the answer is nearly forced"
and take that as a go-ahead.

## 2026-08-01 — the `next_links` judge scores page content, not the envelope (S, eval correctness)

**PROMPT FIXED 2026-08-01; the axis is not yet re-measured.** The rewrite is in
`bench_judge._NEXT_LINKS_TEMPLATE`, pinned by
`tests/capabilities/output_benchmark/test_next_links_judge_respects_adr_0012.py`.
Root cause was worse than "scores the wrong thing": the judge was penalising
entries a2web relayed faithfully — "an internship list, not a repo to adopt" —
which is exactly what ADR-0012 REQUIRES a2web to do. The axis rewarded editorial
filtering the product forbids, so an a2web obeying its own invariant could not
score full marks. An eval that rewards violating the spec applies steady pressure
in the wrong direction on every run.

Still open: nothing has re-measured the axis under the new prompt, and per the
noise-floor entry a single run cannot settle it — that needs a run PAIR. Also
unresolved is §6.5's ADR-0014 question, deliberately left rather than guessed:
the judge is blind (task string + rendered block, no page), so "stop assuming
good faith about fabrication" cannot be honoured by a prompt change. URL
traceability is deterministic and belongs in a check that can read the page.


Source: `eval/findings_2026-08-01.md` §2.

The axis fell 3.44 → 2.56 (`a2web_extract`) across runs whose envelopes differ
only by the `kind`/`anchor` corrections. Reading the judge reasoning shows why:
it is scoring that day's rows, not the link set's structure.

- `gh-trending-best` 5 → 1: *"a mix of unrelated repositories … rather than the
  actual trending Python repositories"* — a different day's trending list.
- `lobste-active` 5 → 3: *"comment counts of 15, 1, 4, 14, and 5, meaning the
  story with 1 comment is likely not…"*.
- `hn-front` 5 → 3: penalises 10 links for a top-5 task — the same 10 links the
  previous run scored 5.

This is the failure the `eval/corpus.yaml` header exists to prevent (phrase
criteria against stable structural facts so an entry survives content rotation);
the rule was applied to corpus `criteria` and never to the judge prompts. At n=9
of 42 it is also the thinnest axis, so it is the one most likely to be
over-read — as it nearly was here, where the drop looked like a regression in
the very change under test.

Fix: re-phrase `bench_judge`'s `next_links` prompt against structural properties
— is every link traceable to the page (ADR-0014), correctly kind-tagged, free of
nav chrome, non-duplicative of the answer — and drop topical relevance to the
day's rows. Until then, treat the axis as non-comparable across runs and say so
where it is reported.

## 2026-07-31 — the file-size ledger, and what it actually measured (framing)

**Source:** structural scan, 2026-07-31. Five parallel agents on three axes —
line count, responsibility count, change coupling — plus an AST function census.
Working rule the scan was run against: **500 lines is uncomfortable, 600 is
critical.**

`src/` over the line, measured:

```
2771  fetcher.py            929  models.py             923  handlers/reddit.py
 756  llm_eval/runner.py    740  fetcher_response.py   649  llm_extract/extractor.py
 551  domain.py             513  actions/playbook.py
```

602 functions in `src/`; **51 over 50 lines, 13 over 100**. The longest is not in
`fetcher.py`:

```
236  routers.py:57              register_web_tools     ← 355-line file, one function
193  fetcher_response.py:363    build_response
190  llm_extract/extractor.py   extract
181  fetcher.py:1079            _phase_tier_loop
154  fetcher_response.py:584    build_ask_response
146  routers.py:66              query                  ← nested inside the 236
```

**Two results that reframe the whole exercise.**

**(1) Size is not the signal; co-change is.** `handlers/reddit.py` is 923 lines
and #2 in total line churn (2237) — and it is *cheap*, because its changes stay
inside it: 17 commits, and its strongest partner is 5 co-changes with `hn.py`.
Whereas `tiers/__init__.py` is small and has **never once changed without
`fetcher.py`** (12/12, P=1.00). Any size-driven refactor would attack Reddit and
leave the registry alone, which is exactly backwards. Rank by co-change first,
size second.

**(2) `fetcher.py` grew monotonically THROUGH its own structural refactor.**

```
2026-05-15   913        2026-07-01  1728
2026-06-01  1610        2026-07-15  2547   ← +819 in two weeks
2026-06-15  1711        2026-07-31  2771
```

v0.23 (`7b864afc`, "fetcher orchestrator structural refactor") reorganized the
inside into named phases. The curve did not bend. It is the cost centre on all
three axes simultaneously — biggest file (3× the next), most commits (78, 2× the
next), most churn (6361 lines = **10.8% of all `src/` churn**). A second
same-shaped refactor should be expected to produce the same result; the entries
below are about the seam, not the tidying.

Positives worth pointing at, so "good" is nameable in this codebase:
**`handlers/`** (9 files, 60+ commits, strongest inter-handler pair = 5),
**`llm_eval/`** (closed cluster, essentially never pairs with `fetcher.py`), and
the **`packages/` leaves** (each pairs almost exclusively with its own test).
Those boundaries work. Whatever they do, the response contract does not do.

Already dead, do NOT spend on: `settings ↔ state`, `routers ↔ server`,
`models ↔ routers` were all real couplings pre-sunset and are gone now. The
sunset fixed them.

Scan method note: co-change ranking excluded 11 bulk commits (>20 `src/` files)
and was re-run at a ≤8-file cutoff as a sensitivity check — the top of the
ranking is unchanged, so nothing below is a migration artifact.

## 2026-07-31 — THE CHANGE SET: which tracks became OpenSpec proposals

The tracks below are the *queue*. This is the *plan* — ten changes covering
them, in dependency order. **All ten are authored** (2026-07-31): 313 tasks,
every one validating. See the ordering note at the end — authored is not the
same as ready to start.

| # | change | covers | status |
|---|---|---|---|
| 1 | `close-wire-level-adr-0009-leaks` | T3 + T7 live: TSV severity loss, github silent degrade, reddit interstitial, `paid_auth_error` hint, dead `a2effect` branch | **SHIPPED** 2026-07-31 → `BACKLOG-CLOSED.md` |
| 2 | `bound-every-unbounded-path` | T3 + T7 live: no LLM timeout, no per-fetch deadline, `hn.py` unbounded recursion | **SHIPPED** 2026-08-01 → `BACKLOG-CLOSED.md` |
| 3 | `fix-cache-ttl-and-listing-sufficiency` | T3: 7-day TTL on live API data, dead `cache_ttl_live_m`, listing sufficiency OFF | **SHIPPED** 2026-08-01 (4.7/5.3 open, see tasks) → `BACKLOG-CLOSED.md` |
| 4 | `run-the-gate-on-every-push` | T4 CI — **do first**, everything else's guards are inert until it lands | **authored** |
| 5 | `close-guards-that-read-green` | T4 remainder: markup funnel misses `re.search`/`re.sub`, two guards answer a different question, two cited guards don't exist, 22 doubleable constants, playbook 1.00 lockstep, partial eval loss exits 0, the corpus cannot see the envelope | **authored** |
| 6 | `unify-the-response-contract` | T2 — absorbs the 41 external `FetchContext` reads, unblocking #7 phase two | **SHIPPED** 2026-08-01 (34/36; §2.2-2.4/2.7 remainder deferred, see tasks) → `BACKLOG-CLOSED.md` |
| 7 | `decompose-fetcher-into-files` | T1 — the 26-file tree, the retrieval→comprehension→sufficiency loop, `install()` | **authored** |
| 8 | `lift-the-item-set-and-renderer` | T5/T7: `domain.py`'s 360-line zero-coupling renderer (ledger Row 1), the item set (Row 2) — closes a LIVE ADR-0015 gap | **authored** |
| 9 | `repay-the-shelf-debt` | T7: ~~`page-tsv`~~, ~~`content-extract`~~, ~~`json-in-html`~~, ~~adopted-then-bypassed primitives~~ — `record-mine` / `dom-schema` / `any-browser` open, each blocked on evidence a2web cannot fabricate | **§1, §3, §5-§10 shipped 2026-08-02** |
| 10 | `reconcile-docs-to-shipped-system` | T6 — last, because #6/#7 re-invalidate parts of it | **authored** |

**Ordering — authored is not ready.** #4 goes first: every guard the other nine
add is inert until the gate runs on a push. #6 blocks #7 phase two (the 41
external `FetchContext` reads must be absorbed before `context.py` can be
sliced), and #7 phase one must not run concurrently with #6 — v0.23 is the
demonstration of what a refactor that is also a bug fix costs. #10 goes last,
because #6 and #7 re-invalidate parts of it. Where a later change rests on an
assumption an earlier one will test, the design says so and names the tripwire.

**Three items are lifted out of their change and ship early** (two now shipped), because each is
live harm rather than structure:

- ~~`endpoint-auth` (#10 §1)~~ — **SHIPPED 2026-08-01.** An operator following
  the spec literally got an **UNAUTHENTICATED** endpoint. Fixed in code as well
  as prose: the docs half alone would have left every existing bare-spelling
  deployment silently open, so `a2web-serve` now refuses to boot on unprefixed
  auth vars.
- ~~`provider-selection` (#10 §1)~~ — **SHIPPED 2026-08-01.** A live routing
  invariant documented inverted; under ADR-0016 that is where a wrong belief
  costs money. The scan found a second, sharper defect alongside it: the three
  provider ids README offered for `A2WEB_LLM_PROVIDER` all raise at settings
  construction, so a documented boot could not boot.
- the JSON-LD `ItemList` deriving neither `next_links` nor `options` (#8 §1) —
  a LIVE ADR-0015 hole, shipped as the first commit of that change so the lift
  has a witness already in place.

**The two round-2 ledger defects now have homes.** `fetcher.py:1058`
(archive-post-gate never runs the extraction ladder — the documented
four-consumer starvation, fifth copy, still live) is #7 §3.3, where the loop
restructure makes it *unexpressible* rather than fixed a fifth time. The JSON-LD
`ItemList` gap is #8 §1, above.

## 2026-07-31 — TRACKS: how the 2026-07-31 findings group, and what depends on what

38 entries landed on 2026-07-31 across two scans (an openspec/verification drift
sweep, then the large-files structural scan). They are **not** 38 independent
pieces of work. Six tracks, with the dependency edges that matter:

```
  T1 DECOMPOSE fetcher/  ──depends on──▶  T2 RESPONSE CONTRACT
        │                                       │
        │ closes H1 structurally                │ absorbs the 41 external
        │                                       │ FetchContext reads
        ▼                                       ▼
  T3 LIVE DEFECTS (independent — ship first, they are days not weeks)

  T4 GUARDS THAT READ GREEN          T5 MODULE-PURPOSE DRIFT
  T6 DOCS TELL A DIFFERENT STORY     (both independent of T1/T2)
```

**T1 · Decompose `fetcher/`** — the entry immediately below is the umbrella.
Subsumes: *no "install a fetch result" type* (`install.py` is a node in the
tree), *five escalation decisions live outside the "single policy function"*
(the loop is what re-homes them), and *the sufficiency question has no name*
(2026-07-31, prior scan — answered by `sufficiency/` being a directory).
Structurally closes *listing sufficiency is OFF*. Blocked on nothing.

**T2 · The response contract — SHIPPED 2026-08-01**, umbrella and all three
subsumed findings closed (`BACKLOG-CLOSED.md`). **T1 phase two is unblocked**:
the 41 external `FetchContext` reads are absorbed into the response contract's
own interface, which was the ordering constraint. Note for whoever runs T1: the
response module deliberately stayed in `fetcher_response.py` rather than moving
to `src/a2web/response/` — that split waits on phase two, because its boundary
is the `FetchContext` slice phase two redraws.

**T3 · Live defects — independent, ship first.** *listing sufficiency is OFF* ·
*reddit's old.reddit channel can serve an interstitial as `ok`* · *`_ttl_for`
caches almost everything for 7 days* · *`_MAX_RECORDS` × `DEFAULT_TOLERANCE`
dead zone* · *`paid_auth_error` has no operator hint* · *stale provider ids
break a documented boot* · *`endpoint-auth` spec yields an UNAUTHENTICATED
endpoint* (SECURITY, and a spec fix, not a code fix). None of these wait on a
refactor. Doing them first also means T1 is not simultaneously a bug fix and a
move, which is the failure mode v0.23 already demonstrated.

**T4 · Guards that read green while not covering what they name.** ~~*there is
no CI on push or PR*~~ — **SHIPPED 2026-07-31** (`5fa4a19`), see
`BACKLOG-CLOSED.md`; the rest of this track is now worth what it reads, because
a guard finally runs on a push · *the markup-funnel guard misses
`re.search`/`re.sub`* · *two named guards answer a different question than
advertised* · *two cited architecture guards do not exist* · *22 constants can
be doubled with zero test failures* · *a wire regression on ADR-0009 is one
re-bless from green* · *`playbook.py` and its test are in 1.00/1.00 lockstep* ·
*a partial eval loss exits 0* · *45 of 86 prompt rules have neither code nor
test* · *the corpus cannot see the envelope* (**HIGHEST LEVERAGE** in this
track) · *invariants with no code implementer*.

**T5 · Module-purpose drift — same shape as T1, different files.** Each is "one
file, several purposes", and each is independently shippable: ~~*`domain.py` is
69% an undocumented renderer*~~ (SHIPPED 2026-08-01 — `packages/structured_render.py`; `domain.py` is 149 lines) · *`extractor.py` holds ~200 lines its siblings
are named for* · *`reddit.py` is four retrieval channels behind one `matches()`*
· *cross-handler duplication: seven shapes, partial adoption* ·
*`llm_eval/systems.py` carries a second fetch stack* · *`routers.py` is one
function with a hole in it* (LOW — git says fading) · *the Registry half of
Strategy+Registry isolates nothing* · *test files that have drifted from their
subject*.

**T6 · Docs describe a system that is not the one shipped.** *CLAUDE.md
describes a different system than the one shipped* · *openspec canonical specs
contradict shipped code* · *naming rot: `_prescribe_browser_on_wall`*. Cheap,
and T1/T2 will invalidate parts of them again — so **do T6 last**, or do only
the load-bearing half now.

**Superseded, do not action from the older text:** *21 behavioural rules live
only as prompt English* → superseded by *45 of 86*. *2026-07-28
regex-over-markup OUTSIDE `handlers/`* → superseded by *the markup-funnel guard
misses `re.search`/`re.sub`*.

**T7 · Substrate a2web hand-builds while already owning it.** Added by a second
scan the same day (five agents: shelf adopt-gaps, stdlib hand-rolls,
failure-handling vocabularies, concurrency/lifecycle, a rule-of-three ledger).
Evidence: [`docs/findings/2026-07-31-primitives-scan.md`](docs/findings/2026-07-31-primitives-scan.md).
Its live defects belong to T3; the rest is independent of T1/T2 and can run in
parallel with them. Entries listed below.

**Recommended order:** T3 (+ T7's live defects) → T4's CI entry → T1 phase one →
T2 → T1 phase two → T5/T7 → T4 remainder → T6.

## 2026-08-01 — deferred from `close-guards-that-read-green`

**§5.1-5.3 — constants that change behaviour, still unwitnessed.** Three
constants whose value silently changes what a2web detects, each needing a
CAPTURED page with a specific property before a witness means anything:

- `detector._HEADING_FRAC_MIN` — needs a listing whose item titles are
  `<div>`/`<span>` rather than headings; the witness must FAIL at `1.00`.
- `_CONSISTENCY_MIN` — needs a listing with mixed card types (sponsored /
  promoted rows among organic ones).
- `LENGTH_FLOOR` — `tests/capabilities/extraction/test_wire_content_md.py:17`
  asserts `len(_PROSE) >= LENGTH_FLOOR`, a fixture SIZED FROM the constant, so
  it cannot fail whatever the constant becomes. Needs a real page straddling it.

Deliberately not faked: a fixture hand-written beside the constant reproduces
the exact defect these tasks exist to fix. They need capture work.

**§4 — ~~the playbook has no foreign witness~~ SHIPPED 2026-08-02.** The witness
is the `steps` key on every replay baseline (the dispatch sequence the real
orchestrator produced from frozen bytes), and the 49 restating tests are now
labelled as documentation in their own docstring. **What it covers is measured
and thin — see the 2026-08-02 entry above; do not read it as covering the
table.**

**§6 — the corpus cannot see the envelope.** The quality judge never receives
the fetched page (`JUDGE_V1` has slots for ask/criteria/answer only), 33 corpus
criteria are unread, and ~~`replay.py::observe()` omits `retrieval_incomplete` and
`narrative` so the akakce wall baseline cannot regress on them~~ (SHIPPED
2026-08-02 — both are in the projection and blessed on every non-ok case;
`narrative` needed a duration scrub, since it embeds real wall-clock timings and
was the one projection field not deterministic from frozen bytes). Includes §6.5:
`_NEXT_LINKS_TEMPLATE` instructs the judge to *"never penalize an entry for
being unfamiliar or assume it is fabricated"* — an instruction that exists
because the judge could not verify, and which **disarms ADR-0014** once it can.
Verification is a live `make bench` run (network + LLM quota, ADR-0016).

**The fake-fidelity slot is empty.** `verification-provenance.md` names a
standing fake-fidelity contract as one of three mechanizable remedies and cited
a test that does not exist; the zendriver backend moved to the shelf and took it
along. The failure it caught — the dead `--no-sandbox` rung — is unguarded in
a2web today. Either restore a witness for whichever fakes a2web still
hand-writes, or verify that `any_browser` holds it.

## 2026-08-02 — a two-LLM-call fetch reports one call's tokens (S, cost truthfulness)

**Surfaced by `decompose-fetcher-into-files` §3.5, deliberately not fixed there**
— it is a behaviour change and that change lands only the move. Two
non-idempotencies in `_phase_extract_answer`, both consequences of re-entry
nobody was counting until the re-entry was hoisted to one head (`_phase_answer`).

**1. `extraction_meta` is overwritten, not accumulated.** An obstacle render or
a listing scroll re-runs extraction, and the second run replaces
`fc.extraction_meta` wholesale — `prompt_tokens`, `completion_tokens`,
`cost_usd`, `latency_ms`. So a fetch that made TWO billed LLM calls reports the
cost of one. The wire's `tokens` block and every eval-harness cost column
under-report by exactly the calls a render triggered, which is the population
where cost is highest — the under-report is biased toward the expensive fetches.

**2. `next_links_llm` can survive content it no longer describes.** The
assignment sits inside `if request_next_links and result.next_links:`, so a
second extraction that returns NO links leaves the first call's list in place —
links validated against the pre-render markdown, presented alongside an answer
derived from the post-render page. `_validate_llm_next_links_against_markdown`
exists precisely to stop a URL that is not on the page from reaching the
caller (ADR-0014); this route gets one there anyway, by staleness rather than
hallucination.

**Fix shape.** (1) wants accumulation, not assignment: sum the token counts and
costs across entries, keep the last model/template, and decide what `cache_hit`
means across two calls. (2) wants an unconditional assignment — `fc.next_links_llm
= validated` with `validated` empty when the model returned nothing — plus a test
that a second extraction returning no links CLEARS the first one's.

Both are pinned open by `test_the_answer_stage_has_exactly_one_caller`, which
keeps the re-entry visible at a single site while they are unfixed.

## 2026-08-02 — two sufficiency fields survive a re-comprehension that should retract them (S, ADR-0015 truthfulness)

**Same shape as the `next_links_llm` staleness above, on the sufficiency axis
instead of the link axis** — and found by writing `decompose-fetcher-into-files`
§5's guard rather than by a failure, which is the argument for having written it.

The escalation loop (§3.2) made a SECOND comprehension pass routine: `escalate`
re-runs the ladder, sufficiency and the gate over the newly installed body. Two
fields have no clearing write on any path, so the second pass can leave the
first body's value in place:

- **`fc.record_count`** is written only inside `if record_set is not None:` /
  `if json_record_set is not None:`. A re-comprehension over a body that yields
  no records keeps the OLD count, and `_phase_listing_completeness` then assesses
  that count against the NEW page's oracle total — two pages' numbers in one
  verdict.
- **`fc.regex_oracle_total`** is written only when the numeric oracle matched.
  A second pass over a page with no oracle keeps the first total, and
  `_apply_llm_listing_oracle` stands down on exactly that field
  (`if fc.regex_oracle_total is not None: return`) — so the language-agnostic LLM
  superset silently declines to fire because of a number from a body that is
  gone.

The fix in both cases is what §3.4 already did for `items_loaded`/`items_total`/
`items_more`: make the assessment symmetric, so a pass that finds nothing
RETRACTS rather than leaving the previous claim standing. That is a behaviour
change, hence filed.

Pinned open by `test_fetcher_residual_ordering.py`'s
`_SURVIVES_RECOMPREHENSION` ledger, which will not let a third sticky field
appear without naming itself.

## 2026-08-02 — a failed archive dispatch leaves no diagnostic row (S, ADR-0009 visibility)

**Decided in `decompose-fetcher-into-files` §1.3, deliberately not applied there**
— that change's rule is that the only behaviour change is the ladder-skip fix,
and adding rows changes `diagnostics_summary` prose. Recorded so the decision is
not re-derived.

`_dispatch_archive` appends a `Diagnostic` **only on success**. Browser, paid,
and the tier loop append **always**. The divergence has a stated reason in the
docstring — a failed escalation is "tried, didn't help" and "should not displace
the originating verdict" — and **that reason stopped being true.**

`resolve_verdict` reads `Observation`s, not `Diagnostic`s (`decision_log.py:119`
filters on `ObservationKind`), and verdict became a pure projection of the
decision log in v0.23. A `Diagnostic` has no path into verdict resolution at
all. The justification survived the refactor that invalidated it, which is the
same shape as a stale allowlist entry: prose that reads as a decision and is
protecting nothing.

**What it costs.** ADR-0009 says the caller must never mistake a miss for a
complete answer, and the diagnostics list is where "what did you try" lives. A
failed archive dispatch leaves a gap exactly where an attempt was — the response
cannot show that archive ran and did not help, so "we never tried" and "we tried
and it failed" render identically. That is the cheap half of the ADR-0009 harm,
but it is the same direction.

**Fix:** append the `Diagnostic` before the success check in `_dispatch_archive`,
with the failing verdict. Expect `diagnostics_summary` deltas in tests that
exercise a failed archive escalation — those deltas are the fix working, not a
regression.

## 2026-08-01 — T7 promotion candidate: `anyllm` needs a per-request timeout

**Filed while shipping `bound-every-unbounded-path` §2.** `anyllm.LLMProvider.complete()`
has NO timeout parameter and no internal bound, so a provider that never returns
hangs its caller forever. a2web now bounds it product-side with
`llm_resource.TimeoutProvider`, wrapping the provider at `select_provider` —
the same shape as the shelf's own `anyllm.cost.with_cost_guard`, and it composes
with it.

**Why it belongs in the shelf, not here.** Every consumer of `anyllm` has this
hole, and each will discover it the same way — as a hang in production rather
than an error. The wrapper a2web wrote is ~20 lines with no a2web-specific
policy in it; only the *default value* is product policy. That is the
promotion signature: mechanism generic, value local.

**Shape to promote:** a `timeout_s` parameter on `complete()` (per-request, since
a long extraction and a short judge call want different bounds), or failing
that, an `anyllm.with_timeout(provider, seconds)` wrapper alongside
`with_cost_guard`. a2web's `TimeoutProvider` becomes a thin pass-through once
either lands.

**Do not drop the wording when promoting.** The error says *a2web stopped
waiting*, never *the LLM timed out* — the caller cannot observe whether the
upstream request was cancelled, whether the model is still generating, or
whether tokens were billed. The shelf version should say *the client stopped
waiting* for the same reason.

## 2026-08-02 — the judge wobble that killed a bench: contained, NOT analyzed (S, eval correctness)

**Containment shipped in `dcdfd5a`. The analysis is deferred to here — do not
read the fix as closing the question.**

**What happened.** A live `make bench` died at cell 24 of 132, ~$3.18 spent, no
report written. `_derive_reached`'s docstring claimed `overall` was "known-good"
by the time the derive ran, because the STRICT policy had validated it. It had
not: STRICT checks PRESENCE, never type, and the only int coercion lives in
`_build_judge_fields`, which the funnel calls AFTER every field policy has
resolved. A derive runs BEFORE the `into` callable, so it can never lean on it.
One judge returned `overall: [2]`; the raw `TypeError` flew past the funnel's
`ParseError` handler and past the runner's per-cell `except JudgeParseError` —
a whitelist of one — and took the whole matrix with it.

**What shipped:** the derive coerces and raises `ParseError`; `_funnel_verdict`
fails ONLY as `JudgeParseError`. Both pinned by tests that go red when that fix
alone is reverted. Verified live — the re-run completed 132/132 and the SAME
wobble recurred **four times**, each costing one unscored cell instead of the
run.

**What is still open, and why it is not cosmetic.**

1. **The wobble is recurring and trivially recoverable, and we currently discard
   it.** 4 of 132 judge calls (~3%) returned `overall` as a ONE-ELEMENT list —
   `[2]`, `[4]`. That is not garbage; it is an unambiguous scalar in a list. We
   now degrade it to UNSCORED, so ~3% of the quality signal is dropped on the
   floor every run, silently, in a benchmark whose entire job is measuring
   quality. Decide deliberately: unwrap a length-1 list of a number (a
   `WobbleTolerance` question, and arguably `parse_with_policy`'s job, not
   a2web's), or keep discarding it and say so in the report.
2. **The unscored cells are not distributed at random.** Three of the four hit
   `webfetch_baseline`. A wobble that correlates with the system under test
   biases a cross-system comparison, and the leaderboard's per-system `n`
   (41 / 43 / 44) is the only place that shows it. Check whether the
   correlation is real or coincidence before trusting a close margin — the
   headline `a2web_extract 2.98 vs a2web_detail 2.95` is well inside it.
3. **The isolation is still a whitelist.** The runner's three judge call sites
   each catch exactly `JudgeParseError`. That is now sound because the funnel
   normalizes, but the property lives in the funnel and nothing asserts the
   runner may not grow a fourth call site that bypasses it. No guard.
4. **Nothing bounds the blast radius of a mid-matrix crash.** `asyncio.gather`
   over 132 cells means any one escaping exception discards 131 completed
   results INCLUDING their spend. The rows were written to disk per-cell, but no
   report was assembled from them. A `return_exceptions=True` + partial report
   would have turned $3.18 of loss into $3.18 of data.

The shelf-side half is filed separately as
**"T7 promotion candidate: `llm_wobble` runs a DERIVE callable unguarded"**
below — item 3 here is a2web's containment, that entry is the upstream fix.

## 2026-08-02 — shelf: `record_mine.render_record` de-dups the heading link only (XS, output quality)

**Measured, small, and filed mainly so nobody re-discovers it and over-estimates
it the way the bench judge did.**

`record_mine/render.py::render_record` already implements the right rule twice —
it peels `heading_text` off the body smush, and drops `heading_link`'s href from
the links line — and applies it to exactly ONE link. The remaining N are left
alone, so every non-heading anchor label appears once inside the body (which is
the record's collapsed own-scope text, anchors included) and again in the ` · `
link line. `lobste-active` renders:

```
- [Where's your website?](…)
  0 culture arscyni.cc authored by arsCynic … caches Archive.org Ghostarchive | 1 comment 1
  [0](…) · [culture](…) · [arscyni.cc](…) · [arsCynic](…) · [Archive.org](…) · [Ghostarchive](…) · [1 comment](…) · [1](…)
```

Every body token except the timestamp and the words "authored by" / "caches" is
a repeated anchor label. Two smaller defects ride along: duplicate links to the
same href under different labels (`[1 comment]` and `[1]`), and a raw URL used
as its own label.

**Size it before acting.** The 2026-08-02 bench judge called this *"10x the
necessary tokens"* and *"each entry appears twice"* across four cases.
Measured across six affected cases: **~2,455 of 190,916 body chars — 1%**, worst
case `lobste-active` at 8%, `gh-trending-best` at 4%, and three of the six named
cases at exactly **0%**. It is real and worth fixing as hygiene; it is not a
token driver and will not move `a2web_detail`'s 4,494-token envelope, which is
the page itself.

Shelf-owned (`record_mine`), so it is a shelf fix, not an a2web one. The rule to
extend is already written — only its scope is wrong.

**Standing lesson, recorded in `eval/findings_2026-08-02.md` too:** a judge's
quantitative prose is not a measurement. Promoting one into a defect report
without measuring is how a bench finding becomes a wild-goose refactor.

## 2026-08-02 — T7 promotion candidate: `llm_wobble` runs a DERIVE callable unguarded

**Filed after a live bench died at cell 24 of 132.** `llm_wobble._apply_field`
calls `policy.derive(parsed)` with nothing around it, so a derive that raises
propagates out of `parse_with_policy` as its own type — **not** as `ParseError`.
Every consumer catches `ParseError` (that is the funnel's whole contract), so
whatever the derive raises sails past the handler that exists to contain it.

**Why the shelf, not here.** The trap is structural, not a2web's:

- STRICT means *present*, never *well-typed* — `_apply_field` returns
  `parsed[field]` as-is. Nothing in the funnel validates a value's TYPE.
- The only place a consumer CAN type-check is the `into` callable, and the
  funnel calls `into` **after** every field policy has resolved.
- So a derive necessarily reads values that nothing has validated yet, while
  the docstring shape everyone reaches for ("STRICT already checked its peer")
  is exactly the wrong mental model. a2web wrote that sentence and believed it
  for months.

The consequence is asymmetric in the way that makes it worth fixing upstream:
the funnel exists to survive model wobble, and this is the one path where
*ordinary* wobble crashes the process instead.

**Shape to promote:** wrap the `policy.derive(parsed)` call so any exception
becomes `ParseError` with the field name and offending value in the message
(`from exc` preserved). Consumers keep one handler and the funnel keeps its
promise. a2web's product-side coercion in `_derive_reached` becomes redundant
belt-and-braces rather than the load-bearing guard, and `_funnel_verdict`'s
blanket clause can narrow back to named types.

**Cross-check when promoting:** the SKIP/DEFAULT paths are fine (no callable),
but `WobblePolicy.default` is a plain value today — if it ever becomes a
callable, it needs the same treatment.

## 2026-07-31 — T7: substrate a2web hand-builds while already owning it

**Source:** primitives & elevation scan, 2026-07-31. Full evidence in
[`docs/findings/2026-07-31-primitives-scan.md`](docs/findings/2026-07-31-primitives-scan.md).

Three recurring failures, in cost order:

1. **Adopted, then reimplemented by hand.** A shelf primitive is a declared
   dependency — sometimes imported *and re-exported* — while its job is done
   inline elsewhere anyway.
2. **Named once, spelled N times.** The drift between copies is the promotion
   signal: it proves nobody maintains them as one thing.
3. **A bound present in some copies, absent in others.** The dangerous variant of
   (2) — the missing bound is invisible next to N siblings that have it.

| finding | tier |
|---|---|
| ~~[`page-tsv` still ships all three encoder defects a2web fixed](docs/findings/2026-07-31-primitives-scan.md#the-largest-un-repaid-debt-page-tsv-still-ships-all-three-encoder-defects)~~ **SHIPPED** — see below | closed |
| [five more shelf gaps a2web has already paid for](docs/findings/2026-07-31-primitives-scan.md#five-more-shelf-gaps-a2web-paid-for) — ~~`content-extract`~~, ~~`json-in-html`~~ done; `record-mine` / `dom-schema` / `any-browser` open | M, shelf promotion |
| ~~[`prune_dict` imported, re-exported, never called](docs/findings/2026-07-31-primitives-scan.md#prune_dict--imported-re-exported-never-called)~~ **CLOSED** 2026-08-02 → `BACKLOG-CLOSED.md` | closed |
| ~~[`fmt_dur` adopted, then bypassed one import away](docs/findings/2026-07-31-primitives-scan.md#fmt_dur--adopted-then-bypassed-one-import-away)~~ **CLOSED** 2026-08-02 | closed |
| ~~[`http_fetch` bypassed by jina and three tiers](docs/findings/2026-07-31-primitives-scan.md#http_fetch--bypassed-by-jina-and-by-three-tiers-generally)~~ **CLOSED** 2026-08-02 — and the breaker it would have gained never opened | closed |
| ~~[`lean-wire` unused where its whole reason applies](docs/findings/2026-07-31-primitives-scan.md#lean-wire--not-used-where-its-whole-reason-applies)~~ **CLOSED** 2026-08-02 | closed |
| ~~[four unused `a2effect` surfaces a2web hand-rolls](docs/findings/2026-07-31-primitives-scan.md#a2effect--adopted-at-one-boundary-taxonomy-unused)~~ **CLOSED** 2026-08-02 — 2 adopted, 2 declined with measurement | closed |
| [ten failure vocabularies, ~21 hand-written conversion sites](docs/findings/2026-07-31-primitives-scan.md#the-failure-vocabulary-census) | L, structure |
| [30 copies of elapsed-ms; three clocks disagree](docs/findings/2026-07-31-primitives-scan.md#elapsed-time-arithmetic--30-copies-3-clocks) | M, structure |
| [four "how long ago" impls, four input units](docs/findings/2026-07-31-primitives-scan.md#how-long-ago--4-impls-4-input-units-3-renderings) | S, structure |
| [upstream-API JSON has no owner; 5 copies of one bug](docs/findings/2026-07-31-primitives-scan.md#upstream-api-json--no-owner-and-5-copies-of-one-misunderstanding) | M, structure |
| [the never-raises pattern: 7 claimed, 5 impls, all disagree](docs/findings/2026-07-31-primitives-scan.md#the-never-raises-pattern--7-claimed-5-impls-all-disagree) | M, structure |
| [handler page-rendering — the largest un-elevated shape in `src/`](docs/findings/2026-07-31-primitives-scan.md#handler-page-rendering--the-largest-un-elevated-shape-in-src) | L, structure |
| [truncate-to-cap: 6 impls, 4 markers](docs/findings/2026-07-31-primitives-scan.md#truncate-to-cap--6-impls-4-markers) | S, structure |
| [host matching: 6 impls that disagree on case and `www.`](docs/findings/2026-07-31-primitives-scan.md#host-matching--6-impls-that-disagree-on-case-and-www) | S, structure |
| [whitespace collapse: 6 impls, 2 mechanisms](docs/findings/2026-07-31-primitives-scan.md#whitespace-collapse--6-impls-2-mechanisms) | XS, structure |
| [four double-checked-lock bodies for one idea](docs/findings/2026-07-31-primitives-scan.md#four-double-checked-lock-bodies-for-one-idea) | S, structure |
| [45 caps, no declaration site; six ceilings on one wire field](docs/findings/2026-07-31-primitives-scan.md#45-caps-no-declaration-site) | M, structure |
| [16 silent swallows, 11 on a retrieval path](docs/findings/2026-07-31-primitives-scan.md#silent-swallows--16-total-11-on-a-retrieval-path) | M, correctness |
| [degrade-to-default that can mask a settings rename](docs/findings/2026-07-31-primitives-scan.md#degrade-to-default-that-can-mask-a-rename) | S, correctness |
| [the documented 5 retry layers do not hold](docs/findings/2026-07-31-primitives-scan.md#retry-the-documented-5-layers-do-not-hold) | M, docs + structure |
| [`ProxyPool` diverges from the resource pattern](docs/findings/2026-07-31-primitives-scan.md#lifecycle-the-one-thing-that-is-a-single-concept) | XS, structure |
| [unpromoted a2web substrate with no shelf home](docs/findings/2026-07-31-primitives-scan.md#unpromoted-a2web-substrate-with-no-shelf-home) — ~~`scope.py`+`lazy.py`~~ shipped as `async-scope-v0.1.0`; `field_to_typer_annotation` deferred to its own change | S, shelf promotion |
| [CLAUDE.md drift round 2 — browser cap, globals, `to_thread`](docs/findings/2026-07-31-primitives-scan.md#doc-drift-found-in-this-round-claudemd) | S, docs — joins T6 |

**Round 2 — the rule-of-three promotion ledger** (fifth agent, returned late).
Evidence appended to the same findings doc.

| finding | tier |
|---|---|
| [archive-post-gate never runs the extraction ladder — 5th copy of a documented bug](docs/findings/2026-07-31-primitives-scan.md#row-3--the-escalation-sequence-five-install-sites-four-sequences) | M, correctness — **LIVE** |
| [JSON-LD `ItemList` derives no `next_links`/`options` while the DOM path derives both](docs/findings/2026-07-31-primitives-scan.md#row-2--the-item-set--and-a-live-adr-0015-gap) | M, correctness — **LIVE**, ADR-0015 |
| [`domain.py:188-551` — a 360-line renderer with ZERO domain coupling](docs/findings/2026-07-31-primitives-scan.md#row-1--domainpy188-551-is-a-renderer-with-zero-domain-coupling) | L, promotion — highest ratio in repo |
| [the item set: 7+ spellings, 4 operations re-implemented per site](docs/findings/2026-07-31-primitives-scan.md#row-2--the-item-set--and-a-live-adr-0015-gap) | L, promotion |
| [`map_non_ok` discards a 403 challenge body before anything can inspect it](docs/findings/2026-07-31-primitives-scan.md#additional-bugs-surfaced-independent-of-any-promotion) | S, correctness |
| [`extractor.py` — 3 incompatible LLM-parse failure contracts; `_note_malformed` on 2 of 8 fields](docs/findings/2026-07-31-primitives-scan.md#additional-bugs-surfaced-independent-of-any-promotion) | M, correctness |
| [`hn.py` H2 count and `headings[1]` can disagree; 3 sibling answers, 1 wrong](docs/findings/2026-07-31-primitives-scan.md#additional-bugs-surfaced-independent-of-any-promotion) | S, correctness |
| [`discourse.py:227` emits 50 `next_links` vs a 10 cap — pinned green by the probe](docs/findings/2026-07-31-primitives-scan.md#additional-bugs-surfaced-independent-of-any-promotion) | S, correctness |
| [401/403 maps four ways across six mappers; browser drops 429](docs/findings/2026-07-31-primitives-scan.md#additional-bugs-surfaced-independent-of-any-promotion) | M, structure |
| [dead branch `>=500` then `>=400` copy-pasted into two tiers](docs/findings/2026-07-31-primitives-scan.md#additional-bugs-surfaced-independent-of-any-promotion) | XS, correctness |
| [`_manifests/llm_providers/` holds ONLY `__pycache__` — verify the loader can't resurrect it](docs/findings/2026-07-31-primitives-scan.md#the-inverse--built-once-or-more-general-than-any-caller-needs) | S, correctness |
| [`JUDGE_V1` cannot be rendered by `PromptTemplate.render`; 3 brace disciplines coexist](docs/findings/2026-07-31-primitives-scan.md#the-inverse--built-once-or-more-general-than-any-caller-needs) | S, structure |
| [`listing_has_more` — 13 lines, zero handler call sites](docs/findings/2026-07-31-primitives-scan.md#the-inverse--built-once-or-more-general-than-any-caller-needs) | XS, dead code |
| [`TierResult` — 25 fields, ~18 written by exactly one tier](docs/findings/2026-07-31-primitives-scan.md#the-inverse--built-once-or-more-general-than-any-caller-needs) | M, structure |
| [`Tier.fetch(**kwargs)` silently drops a misspelled kwarg in every tier](docs/findings/2026-07-31-primitives-scan.md#the-inverse--built-once-or-more-general-than-any-caller-needs) | S, structure |
| [`_load_tier_registry` re-walks packages the shelf loader already walked](docs/findings/2026-07-31-primitives-scan.md#the-inverse--built-once-or-more-general-than-any-caller-needs) | S, shelf gap |
| [widen `_common.empty_result` and delete 17 sites (−78 lines, interface ≈ 0)](docs/findings/2026-07-31-primitives-scan.md#recurs-but-shallow--do-not-promote) | S, structure |
| [`handlers → tiers` import cycle: moving 2 types deletes 18 lazy imports](docs/findings/2026-07-31-primitives-scan.md#recurs-but-shallow--do-not-promote) | S, structure |

**Explicitly NOT elevated, with reasons** (recorded so they are not re-proposed):
reddit's retry loop — its comments encode a live-measured penalty-box model that
`tenacity`/`stamina` would take the schedule from and lose the reason;
hedged-race-first-wins (`tiers/archive.py:130-163`) — DEEP and STABLE but exactly
one call site, so flag-when-second-caller-appears, not now; bounded-parallelism
(`llm_eval/runner.py:333`) — n=1, and `asyncio.Semaphore` is already the named
concept; enum↔string round trips and dataclass→dict flattening — scanned, came up
empty. Joined 2026-08-02 by four more, each with its measurement in
`BACKLOG-CLOSED.md`: `_find_product_or_item_list`, `_normalize_commerce_row`,
`a2effect.raises_as` (it re-raises where every candidate site returns a
`TierResult`), and `field_to_typer_annotation` — the last DEFERRED rather than
declined, because the generic unit is a backend-neutral `analyze_param` spanning
a2web and a2kay.

## 2026-07-31 — decompose `fetcher.py` into single-purpose files (L, structure — T1 UMBRELLA)

**Source:** structural scan + design session, 2026-07-31. Line budgets from the
AST census; the tree is the applied form of the decomposition criterion below.

`fetcher.py` is 2771 lines. The v0.23 "structural refactor" reorganized its
interior into named phases and **the growth curve did not bend** (913 → 1610 →
1711 → 1728 → 2547 → 2771). Interior reorganization is not the fix.

### The criterion

**One file, one purpose.** Exceptions, and only these two: an **aggregation
point** (a composition root or entrypoint whose purpose IS to assemble), and a
**utils leaf** (shared mechanism with no domain decision in it).

Applied to `fetcher.py`, four of its phases fail the criterion outright —
`_phase_tier_loop` carries 5 jobs, `_phase_extract_answer` 6, `_phase_extract`
3, and the three escalators share a duplicated tail.

### The tree

```
src/a2web/fetcher/
├── __init__.py            fetch() — AGGREGATION                    ~60
├── pipeline.py            the ordered chain, nothing else          ~50
├── context.py             FetchContext                              281
├── telemetry.py           UTILS                                      58
│
├── retrieval/             "get bytes for this URL"
│   ├── cache.py           TTL policy, read, write                    41
│   ├── conditional.py     the 304 path                              ~35   ← out of tier_walk
│   ├── cookies.py         resolve + staleness                        90
│   ├── proxy_lease.py     lease/report protocol                     ~45   ← out of tier_walk
│   ├── tier_walk.py       the walk itself                          ~180
│   ├── install.py         TierInstall + the one chokepoint          ~80   NEW
│   └── escalate/
│       ├── archive.py · browser.py · paid.py                       ~75 ea
│       └── _tail.py       shared install + re-gate — UTILS LEAF     ~35
│
├── comprehension/         "what did we get"
│   ├── prerendered.py     the handler-payload path                  ~70   ← out of ladder
│   ├── json_synth.py      JSON body → content                       ~60   ← out of ladder
│   ├── ladder.py          trafilatura → escalation rungs           ~140
│   ├── gate.py            evaluate / regate                          132
│   └── menu.py            candidates → prompt + wire                 191
│
├── sufficiency/           "is this ALL of it?"     ← has no name today
│   └── completeness.py    assess · oracle · scroll decision          138
│
├── answer/                "what did the caller ask"
│   ├── digest.py          {{n}} build + rehydrate (ADR-0014)          52
│   ├── prompt_call.py     the LLM call + degrade                     ~90   ← out of extract
│   ├── obstacle.py        the re-render decision                     ~60   ← out of extract
│   └── links.py           records→NextLink, LLM validation            95
│
└── verdict/               "what do we tell the caller"
    ├── promotions.py      empty · small-page                         ~50
    └── terminal.py        classify + hints (actions/ owns the        ~45
                           pure half already)
```

26 files, largest 281 (`context.py`), then 191. Nothing over 300.

### The load-bearing part is the loop, not the tree

`retrieval → comprehension → sufficiency` **is a loop**, and the code does not
model it as one. Today escalation hand-calls comprehension from inside
retrieval, which is why:

- H1 exists at all — escalators re-enter at *comprehension* and skip sufficiency
  entirely (`_run_extraction_escalation` 4 call sites vs
  `_phase_listing_completeness` 2)
- `_phase_listing_render:2716-2722` re-implements assess-and-set inline, because
  there is no loop head to return to
- `_phase_extract_answer` is re-entrant 3× and not idempotent — *answer* is
  being used as the loop body
- the single paid budget is resolved by call order across four competitors

**Have escalation return a retry signal instead of calling forward.** Then there
is exactly one path from retrieval through comprehension to sufficiency, and a
stage cannot be skipped because nothing calls it directly. That also dissolves
the `retrieval → comprehension` import cycle that blocks a naive file split
(anti-seam A2 in the scan) — **the cycle WAS the loop, un-named.**

`install.py` is the second load-bearing piece: six transport fields (`body`,
`content_type`, `final_url`, `tier_used`, `pre_rendered_payload`, `status_code`)
are each written by six functions across three groups.
`_install_rendered_fields` already unified the *content* half after it caused a
live bug and explicitly excluded the transport half (`:1279-1281`). One
`install(ctx, TierInstall)` is what lets `tier_walk` and `escalate` be siblings
rather than one 576-line file.

### Rejected: a Stage protocol with declared reads/writes

Considered and dropped. A `Stage` protocol carrying `READS`/`WRITES` field sets
would make the five prose-only ordering constraints (`:1955`, `:2315`, `:2337`,
`:2344`) checkable at build time, and would make H1 *unexpressible*. It was
rejected as a framework where a criterion was asked for — it spends magic budget
the Constitution does not want spent, for a guarantee the loop restructure
already delivers structurally.

**What that costs, stated plainly:** the residual ordering hazards — the paid
budget resolved by call order, `fc.record_count` never resetting
(`:1725-1732`, no `else: None`), `_install_gate_archive` not setting
`status_code` — go back to being conventions. They become **one architecture
test**, not a framework. Cheaper, and the project already has that habit. If
that test proves hard to write, reopen this decision rather than living with the
convention.

### Sequencing

**Phase one — the tree + the loop.** Does NOT need `context.py` sliced;
`FetchContext` stays whole. Closes H1 structurally.

**Phase two — slice `context.py` per node.** **Blocked on T2**: 41 of its 69
fields are read externally by `fetcher_response.py`, so the response contract
must absorb those reads first. Attempting both phases at once turns a
decomposition into a rewrite.

### Anti-seams — verified, do not cut these

- `_phase_tier_loop` / `_dispatch_action`: the `:1247` escalation-win check is
  correct **only because** `_install_won_tier` at `:1254` has not run yet.
- `_phase_empty_promotion` / `_phase_complete_small_page_promotion` /
  `_apply_terminal` are one mutually-exclusive chain expressed by early returns,
  with `small_page_promoted()` reading a field written 460 lines away. They go
  into `verdict/` together or not at all.
- `_phase_extract`'s pre-rendered branch: `:1299-1323` documents that it once
  returned *before* the ladder and starved four consumers for months. Splitting
  it into `prerendered.py` must preserve the ladder call, not just the branch.
- `FetchContext`: 69 fields, ~19 test modules import it. Phase two only.

**Open question for the proposal:** `escalate/_tail.py` is the one file placed by
judgement rather than census — it is the shared ~35-line install-and-re-gate tail
(`_escalate_browser:2136-2151` ≈ `_escalate_paid:2236-2253`). It qualifies as a
utils leaf under the criterion; confirm that reading before writing it.

## 2026-07-31 — the remaining 36 findings (evidence in `docs/findings/`)

Full evidence — measurements, `file:line` citations, verification notes — lives in
[`docs/findings/2026-07-31-structural-scan.md`](docs/findings/2026-07-31-structural-scan.md).
Tracks and dependency order are in the TRACKS entry above. One line each:

| finding | tier |
|---|---|
| [listing sufficiency is OFF on the population it exists for](docs/findings/2026-07-31-structural-scan.md#listing-sufficiency-is-off-on-the-population-it-exists-for-m-correctness--live) | M, correctness — LIVE |
| [no "install a fetch result" type; six fields written six ways](docs/findings/2026-07-31-structural-scan.md#no-install-a-fetch-result-type-six-fields-written-six-ways-m-structure) | M, structure |
| [`domain.py` is 69% an undocumented renderer](docs/findings/2026-07-31-structural-scan.md#domainpy-is-69-an-undocumented-renderer-m-structure) | M, structure |
| [`routers.py` is one function with a hole in it](docs/findings/2026-07-31-structural-scan.md#routerspy-is-one-function-with-a-hole-in-it-s-structure) | S, structure |
| [the Registry half of Strategy+Registry isolates nothing](docs/findings/2026-07-31-structural-scan.md#the-registry-half-of-strategyregistry-isolates-nothing-s-structure) | S, structure |
| [a partial eval loss exits 0](docs/findings/2026-07-31-structural-scan.md#a-partial-eval-loss-exits-0-s-verification) | S, verification |
| [`llm_eval/systems.py` carries a second fetch stack](docs/findings/2026-07-31-structural-scan.md#llm_evalsystemspy-carries-a-second-fetch-stack-s-structure) | S, structure |
| [test files that have drifted from their subject](docs/findings/2026-07-31-structural-scan.md#test-files-that-have-drifted-from-their-subject-s-structure) | S, structure |
| [reddit.py is four retrieval channels behind one `matches()`](docs/findings/2026-07-31-structural-scan.md#redditpy-is-four-retrieval-channels-behind-one-matches-m-structure) | M, structure |
| [cross-handler duplication: seven shapes, partial adoption](docs/findings/2026-07-31-structural-scan.md#cross-handler-duplication-seven-shapes-partial-adoption-m-structure) | M, structure |
| [45 of 86 prompt rules have neither code nor test](docs/findings/2026-07-31-structural-scan.md#45-of-86-prompt-rules-have-neither-code-nor-test-l-verification) | L, verification |
| [`extractor.py` holds ~200 lines its siblings are named for](docs/findings/2026-07-31-structural-scan.md#extractorpy-holds-200-lines-its-siblings-are-named-for-m-structure) | M, structure |
| [five escalation decisions live outside the "single policy function"](docs/findings/2026-07-31-structural-scan.md#five-escalation-decisions-live-outside-the-single-policy-function-m-structure) | M, structure |
| [`endpoint-auth` spec yields an UNAUTHENTICATED endpoint if followed](docs/findings/2026-07-31-structural-scan.md#endpoint-auth-spec-yields-an-unauthenticated-endpoint-if-followed-s-security) | S, SECURITY |
| [`_MAX_RECORDS` × `DEFAULT_TOLERANCE` dead zone](docs/findings/2026-07-31-structural-scan.md#_max_records--default_tolerance-dead-zone-s-correctness--adr-0009-live) — **STAYS OPEN**: `_MAX_RECORDS` was not found anywhere in `src/`, so the interaction the finding describes could not be reproduced and the entry is unverified. Do not close it on the strength of the finding alone. | S, correctness — ADR-0009 LIVE, unverified |
| [22 constants can be doubled with zero test failures](docs/findings/2026-07-31-structural-scan.md#22-constants-can-be-doubled-with-zero-test-failures-m-verification) | M, verification |
| [openspec canonical specs contradict shipped code](docs/findings/2026-07-31-structural-scan.md#openspec-canonical-specs-contradict-shipped-code-m-docs--4-load-bearing) | M, docs — 4 load-bearing |
| [CLAUDE.md describes a different system than the one shipped](docs/findings/2026-07-31-structural-scan.md#claudemd-describes-a-different-system-than-the-one-shipped-s-docs) | S, docs |
| [stale provider ids break a documented boot](docs/findings/2026-07-31-structural-scan.md#stale-provider-ids-break-a-documented-boot-s-correctness--live) | S, correctness — LIVE |
| [naming rot: `_prescribe_browser_on_wall`](docs/findings/2026-07-31-structural-scan.md#naming-rot-_prescribe_browser_on_wall-xs-cosmetic) | XS, cosmetic |
| [invariants with no code implementer](docs/findings/2026-07-31-structural-scan.md#invariants-with-no-code-implementer-m-l-structure) | M-L, structure |
| [the corpus cannot see the envelope](docs/findings/2026-07-31-structural-scan.md#the-corpus-cannot-see-the-envelope-l-verification--highest-leverage) | L, verification — HIGHEST LEVERAGE |
| [the sufficiency question has no name](docs/findings/2026-07-31-structural-scan.md#the-sufficiency-question-has-no-name-m-structure--answered-by-t1) | M, structure — ANSWERED by T1 |

## 2026-07-28 — retire the twitter handler? (S, decision — REVISIT, do not act yet)

**Source:** `handler-never-reports-ok-on-a-challenge`, D4 + task 7.3.

The two entries that used to sit here — "the handler returns `ok` on a wall" and
"does it have any reachable upstream?" — are both ANSWERED and were removed.
The handler is now truthful, and the survey of ten public instances on
2026-07-28 found NONE working (5 walled, 4 dead, 1 redirector into a walled one).

Retirement was measured and rejected: handler-absent degrades the same URL to
`not_found` with an `info`-severity `content_not_found` hint, which claims the
page might not exist — false. Handler-present is `block_page_detected`, which is
the honest signal.

**Two things must happen before retirement is reconsidered:**

1. Re-survey from a PROXIED route. One network is one data point (task 7.3).
2. Note that D4's comparison was weakened by this environment having no browser
   at the time; a later live run showed the cascade reaching the tweet via jina
   anyway (2204 chars), so the handler is not the only path to the content.

Retiring while the failover bug was unfixed would have been wrong regardless —
the bug returns with the next working upstream. That bug is now fixed, so this
is a clean decision whenever the proxied survey happens.

## 2026-07-28 — a prose-only challenge above the length floor still reads as content (S, correctness)

**Source:** `handler-never-reports-ok-on-a-challenge`, D1b.

`challenge_verdict` inherits `block_detector`'s two-tier precision: vendor
fingerprints match at any length, prose markers only below `LENGTH_FLOOR`. So a
WORDIER interstitial than the captured 416-char one still extracts as content.

The obvious fix — force the prose markers on — was tried and refuted in one live
run: the wikipedia article for Python turned `block_page_detected` on a cited
title, "PEP 466 – Network Security Enhancements for Python 2.7.x". The length
floor is the only thing making those markers safe.

The real fix is a TIGHTER fingerprint for the xcancel/Anubis interstitial family
(a widget id or asset path), matched length-independently. Wants a second
captured sample from the family first — generalising a fingerprint from one page
is how a false positive gets catalogued.

## 2026-07-28 — the wall check belongs at the `SiteHandlerTier` seam (S, design)

**Source:** `handler-never-reports-ok-on-a-challenge`, task 7.2 + Open Questions.

Two handlers now call `challenge_verdict` themselves. A check at the tier seam
would cover every current and future handler in one place, and would not need
remembering. It is the better shape and a bigger change — `SiteHandlerTier` must
distinguish "handler declined" (`no_match`) from "handler retrieved a wall".

Worth doing when a FOURTH handler needs it, not before.

---

## 2026-07-27 — investigate dual health-degradation mechanisms (S, design smell)

Source: `shelf-sweep-promotions` §10.1 (Q4 RECONCILE-pass follow-up, filed not
done). Is a2web running **two independent health-degradation mechanisms** that
should be one — `_ProxyHealth` quarantine and the `purgatory` circuit breakers
(`state.py`, per-host/per-proxy/global)? Not a promotion question — a design-smell
investigation: confirm whether the two overlap, conflict, or are legitimately
complementary (proxy-selection health vs breaker trip). If redundant, converge on
`purgatory`; if complementary, document why both exist so the next reader doesn't
re-ask. Scope: S (investigation), possibly M (converge).

## 2026-07-27 — trim the `query` default-path envelope noise (S, breaking, decision-gated)

Source: `trim-ask-envelope-noise` change (dropped as a standalone proposal —
no committable spec end-state until the field decision is made). It is the
surviving half of the archived `envelope-wire-hygiene`; the other half (the a2kit
`encode_envelope` empty-leak + populated-destruction defect) died with a2kit and
is fixed and pinned in `wire.py`.

The operator's standing "the `query` envelope is too noisy" complaint is about
the `structuredContent` shape itself — a2web's own `@model_serializer` output on
the default (`debug=False`) path — not the encoder. Re-assess `AskResponse` field
tiers and decide, per candidate (`confidence`, `tier`, the failure-story fields,
any residual meta), whether each earns default-wire presence or demotes to
`debug=True`. `answer` + the ADR-0015 index (`also_here`/`other_pages`) are
**untouchable — never trimmed**.

- *Why deferred, not proposed:* it is **breaking for wire parsers** (ADR "Ask
  First" names the envelope shape), so the tier decision is a human call made
  against evidence, not an automatic prune — and the spec end-state cannot be
  honestly written until that decision lands. The apply step is small
  (`models.py` field tiers + `_prune_wire`, wire-only serializer contract
  preserved) and lives in `AskResponse` only (`FetchResponse` stays page-shaped;
  the encoder in `wire.py` is already correct).
- *Validation gate:* the **clarity axis of `make bench`** (live-network, spends
  LLM quota, run under the ADR-0016 subscription provider — never metered)
  confirming clarity rose or held while answer-quality/contract did not regress.
  Not in `make check`. When picked up: dump the current default-path envelope on
  a representative set (success/listing/failure/empty-unverified), decide + record
  the per-field rationale, apply, then bench. Scope: S.

## 2026-07-27 — confirm a genuinely-distinct robust browser engine + bench (M, blocked on shelf `any-browser`)

Source: `fix-zendriver-robust-rung` (ARCHIVED 2026-07-26) §1-2/§4.2, folded to the
shelf's `any-browser` 5.2c. `browser_robust` is supposed to be a *second,
independent* evasion witness when the fast `browser` rung (patchright) is
fingerprinted — a same-engine retry is not independence, and independence is
load-bearing for `classify_terminal`. In the slimmed container zendriver's CDP
connect handshake fails (`Failed to connect to browser`) while patchright launches
fine as the same uid, so the robust rung can silently collapse to the same engine.

The `correlated_witness` guard (archived §3) already makes a same-engine robust
rung *observable* rather than silent (v0.47.1). The remaining work: once
`any-browser` ships the container CDP-connect root-cause fix, verify the robust
rung is genuinely a different engine/fingerprint than the fast rung (a
differentiated stealth profile of a working backend, or a reinstated Camoufox
rung), then run `make bench` — §3 alone did not change render behaviour, so the
bench is meaningful only after the engine/launch actually changes. Scope: M
(a2web-side), blocked on the shelf `any-browser` fix (L, infra/CDP).

## 2026-07-26 — promote `PromptTemplate` to `anyllm.prompt` when a 2nd consumer appears (S)

Source: `openspec/changes/shelf-sweep-promotions` §3.2 (DEFER verdict). The
`PromptTemplate` render mechanism in `src/a2web/packages/llm_extract/prompts.py`
(a versioned template → `anyllm.PromptParts` renderer, two cache modes) is a
plausible companion to anyllm's cache-breakpoint `PromptParts`, but promoting it
now hits the micro-software bottom-right trap: LOW reuse (no 2nd consumer) ×
ALREADY isolated (tidy module) = pure relocation cost, the domain doesn't shrink
(the concrete a2web templates — product — stay). Revisit when a real second
anyllm consumer wants cache-aware prompt rendering; then it graduates beside
`PromptParts`. Until then it lives in a2web unchanged.

## 2026-07-22 — re-home the Rego policy lint dropped with a2kit (S)

`make lint` used to end with `uv run a2kit lint rego src/ pyproject.toml` — a
Rego policy bundle (duplicate-body detection, private-name collision, import
hygiene) gated by the allowlist in `policies/data.json`. The sunset removed
a2kit and with it the only engine that ran those policies.

- **This is a real loss, not dead ceremony.** It fired twice in Phase 1 alone,
  catching the `_resolve` / `link_digest._resolve` collision and the three-way
  `_safe_emit` collision. Nothing else in `make check` looks for either.
- **`policies/data.json` is deliberately KEPT** — the allowlist entries carry
  written rationales that are still true, and re-deriving them would be the
  expensive part of restoring the check.
- **Two routes.** (a) A shelf package, if the Rego bundle is generic enough to
  serve more than one consumer — plausible, since none of the rules are
  a2web-specific. (b) A local AST check under `tests/architecture/`, which is
  where a2web's other structural rules already live and needs no Rego engine.
  (b) is smaller; (a) is the one that pays for the other consumers.
- **2026-08-02 — `a2effect.lint` is NOT the replacement. Question closed.**
  `repay-the-shelf-debt` §8.7 asked whether it was, since a2effect ships
  something called `lint` in a repo that records losing `a2kit lint rego` as a
  real loss. It is not the same kind of thing. Three real, registered rules
  exist (`A2K-RAISES-CLOSURE`, `A2K-RAISES-NOT-TYPED`, `A2K-RAISES-UNCOVERED`),
  but all three key on an `Annotated[T, Raises(...)]` return-annotation
  convention a2web uses nowhere. Rego was a general policy engine over arbitrary
  rules (duplicate bodies, private-name collisions, import layering); this is
  three rules over one convention.

  **Two things worth keeping from the check.** First,
  `lint_path(Path("src/a2web"))` returns **0 messages over the entire tree** —
  which reads as "we pass" and means "it does not apply to us". Anyone who runs
  it and reports green is reporting nothing; that is the shape this repo has now
  found in `tach.toml`, `testpaths`, and the shelf catalog. Second, it is
  narrower than even the convention suggests: `A2K-RAISES-NOT-TYPED` fires only
  when a `Raises(...)` member's dotted prefix is in a hardcoded six-library
  allowlist (`httpx`, `asyncpg`, `redis`, `sqlalchemy`, `fastapi`, `starlette`).
  Probed directly — `Raises(httpx.HTTPError)` fires, `Raises(curl_cffi.CurlError)`
  does not, and a2web's tiers use `curl_cffi`. So even after adopting the
  annotation convention across the codebase, it would still say nothing about
  a2web's actual dependencies.

  Route (b) — a local AST check under `tests/architecture/` — therefore stands
  unchanged as the smaller option, and route (a) is unaffected.
- **Why deferred.** It gates nothing today that other guards do not, and the
  sunset's remaining phases are the critical path. The risk is purely that it
  is forgotten, which the `Makefile` comment and this entry exist to prevent.
- **2026-07-31 — its stand-in hook had been dead since the sunset.**
  `.pre-commit-config.yaml` still carried an `a2kit-rego` hook running
  `uv run a2kit lint rego src/ pyproject.toml`. a2kit was removed on 2026-07-22,
  so from that day the hook could only fail to spawn — it read as architectural
  policy enforcement while enforcing nothing, for nine days, in a repo whose
  anti-vacuity rule exists for exactly this. Removed by
  `run-the-gate-on-every-push`; the gap is now visible instead of papered over,
  which is what this entry is for. Also worth noting the shape: the loss was
  *recorded* (this entry, the `Makefile` comment, CLAUDE.md's "dropped — a real
  loss") and the dead hook still survived every one of those readings.

## 2026-07-16 — jina foreign-egress corroboration on empty-marked thin (M)

Source: openspec change `empty-vs-wall-discrimination`, design.md "implementation-
revealed correction" + Fable council (2026-07-16). The empty→ok promotion
corroborates via the BROWSER (a thin 200 wins the tier loop, so the free jina rung
never runs on it). That leaves TWO gaps this single track closes:

- **The IP-reputation residual.** A wall that fake-empties our HTTP AND browser
  egress identically (both our IPs) cannot be ruled out — only a foreign egress
  (jina) can. Today's conjunction can't see it.
- **No-browser deploys never promote.** Without a browser backend there is no
  corroborating render, so a genuine empty always looks `failed` (empty_unverified).

- **Scope (M).** Make an empty-marked `length_floor` NOT win the tier loop —
  continue the free ladder to jina before/instead of the browser escalation. Then
  jina either (a) retrieves REAL content on its different IP → the fetch succeeds
  with content (strictly better than "empty"), or (b) also reads empty → a
  FOREIGN-egress corroboration term for `is_confirmed_empty` (add jina-source body
  tier as an accepted corroborator alongside the browser regate). A jina 403/thin-
  wall blocks promotion (conservative, correct).
- **Why deferred.** It changes tier-loop WIN semantics for the empty-marked case
  (a 200 that currently ends the walk would continue), which touches the hot path
  and carries regression surface across the free ladder. Costs one extra jina fetch
  per empty search (cheap). Land it behind its own change with the ladder tests
  green. Until then, browser-corroboration + attached `thin_content` is the honest
  floor and the residual is narrow.
- **The general principle (why this matters beyond empties).** This is a
  CORRELATED-WITNESS problem: corroboration is only as strong as the INDEPENDENCE
  of the witnesses, and our two default witnesses share an egress. raw (datacenter
  proxy IPs) and our own browser are both roughly "egress A"; jina (r.jina.ai) is
  the only "egress B" we have. A wall keyed on IP REPUTATION fake-empties both
  egress-A witnesses identically — they "agree" from the same blind spot. jina's
  different IP would DISAGREE (retrieve the real content) if it exists, which is
  what makes it an independent witness. The lesson generalizes: `classify_terminal`'s
  `_CORROBORATION_THRESHOLD = 2` (used for the 404 `gone_confirmed` upgrade too)
  counts OBSERVATIONS, not INDEPENDENT EGRESSES — two raw+browser 404s are weaker
  corroboration than raw+jina. NOT proposing a full egress-diversity-weighted-
  corroboration refactor (raw and browser are not perfectly correlated — different
  TLS fingerprints, the browser passes walls raw can't, often a different IP pool),
  but any future corroboration tightening should weight witness independence, not
  just count. This is the architectural (not intrinsic) half of the "asymmetry"
  discussion — the empty-vs-wall COST asymmetry is intrinsic and correctly kept.

## 2026-07-16 — cap uncorroborated-404 browser escalation at one rung (S)

Source: openspec change `fetch-failure-semantics`, task 4.4 (`_decide_uncorroborated_404_escalate`).
Per ADR-0017 "effort ∝ existence prior," a single uncorroborated HTTP 404
(`gone_unverified`) has a low prior that content exists, so a full fast→robust
browser escalation on it is arguably wasted spend.

- **Scope (S).** Add a guard that caps an uncorroborated-404 browser escalation
  at one rung (fast Chromium only; no robust CDP follow-up) when the sole
  evidence is a lone 404.
- **Why deferred (twice).** (1) Browser is already globally capped at 1/fetch, so
  this only shaves a sub-rung, not a runaway. (2) The one browser probe on a 404
  is exactly what upgrades `gone_unverified → gone_confirmed` (raw-404 + browser-404
  = corroboration) — cutting it lowers confidence on the honest-dead verdict rather
  than saving meaningful cost. (3) It touches the shared fast→robust ladder guard
  and carries regression risk on the reddit-404 path. Low leverage; revisit only if
  browser-on-404 spend shows up as a real cost line.

## 2026-07-11 — SSRF egress denylist for internal/private targets (M)

Source: homelab deploy exploration (a private infra repo's `add-a2web-backend` change).
When a2web runs as a networked MCP server it fetches any URL a caller supplies,
from inside the server's network. With no egress guard a caller can pivot a2web
into private targets it could not reach itself: docker service names on shared
bridges (`http://litellm:4000`, `http://ha-mcp:8087`), other tailnet IPs, and
cloud metadata (`http://169.254.169.254/`). Auth gates WHO can call; once in,
any caller inherits an internal fetch primitive.

- **Scope (M).** Add an egress denylist that rejects (loud diagnostic, never a
  silent fetch) targets resolving into private/link-local ranges: `10/8`,
  `172.16/12`, `192.168/16`, `169.254/16`, `127/8`, `::1`, `fc00::/7`. Apply on
  the RESOLVED IP (guard DNS-rebind), on redirects too, across every tier (raw /
  jina / zyte / browser). A settings allowlist escape hatch for deliberate
  internal fetches (default empty).
- **Why deferred.** The first homelab deployment gates callers to a solo GCP
  test-user allowlist (~just the operator), so practical exposure is low; the
  priority was shipping `ask` + `fetch_raw`. Revisit before any multi-user or
  shared-URL exposure of an a2web-backed gateway.

## 2026-07-11 — surface-page-links-to-extractor: eval gates (bench-deferred)

Source: openspec change `surface-page-links-to-extractor`, tasks 9.1/9.2 + the
answer-inline-links / `content_md` follow-up. The link-affordance feature shipped
(digest → `{{n}}` handles → closed-set rehydration, on-the-page-only grounding
(ADR-0014), off-domain flag, answer-inline links, uptake telemetry, prose+JSON-LD
`content_md`). Three items are **bench-deferred** because `make bench` is
live-network and spends LLM quota (deliberately not in `make check`):

- **9.1 — adversarial sentinel re-run (S).** Re-run the `{{n}}`-collision sentinel
  eval against the deployed extractor (DeepSeek V4 Flash) whenever the model
  changes. The matrix already exists; this is a re-run, not new work.
- **9.2 — token-budget assertion (S).** Add a bench assertion that extractor
  OUTPUT tokens stay ≤ the pre-digest baseline and the digest INPUT stays within
  budget (~1.4k input tokens on a product page; gated to `structural_form ∈
  {product, listing}`, so articles pay nothing).
- **Full `affordance`-corpus bench (S).** Run `make bench` across the new
  `affordance` corpus class (hepsiburada/amazon reviews, trendyol which-best,
  github issues, contact-page channels) to score the answer-inline-links +
  `content_md` concatenation changes for quality/cost/neutrality before they are
  considered fully validated. Findings → `eval/findings_<date>.md`.

## 2026-07-11 — uncommitted envelope/verdict changes from already-archived changes (not fully green)

Source: pre-existing dirty working tree — NOT `surface-page-links-to-extractor`.
Several openspec changes are **archived (marked done) but never committed to git**;
their code sits uncommitted in `models.py` / `fetcher_response.py` /
`decision_log.py` and the contract goldens, tangled together:

- `2026-07-09-drop-structural-form-shape-wire` — dropped `genre`; pulled
  `structural_form`/`shape` off the `AskResponse` wire.
- `2026-07-11-escalate-on-status-derived-walls` / `-thin-page-walls` /
  `-unify-escalation-executor` — added `Verdict.dns_error` + `Verdict.blank_page`
  and reworked wall/escalation.

Net effect: the response/verdict envelope shape changed, but **three capability
tests still assert the OLD shape** (always-present `status`) and are red with the
same `KeyError: 'status'`:

- `tests/capabilities/ask_response/test_ask_response.py::test_ask_status_is_failure_only`
- `tests/capabilities/ask_response/test_ask_response.py::test_ask_failure_carries_narrative`
- `tests/capabilities/fetch_response/test_fetch_response.py::test_fetch_raw_failure_carries_status_and_narrative`

The a2web contract goldens (`tests/contracts/tool_schemas.json`,
`ask_success_rich.json`) are ALSO half-re-blessed in the tree. Closing this =
finish those archived changes, update the three stale tests, then
`make bless-contracts` (a2web-only golden-snapshot update: `A2WEB_BLESS_CONTRACTS=1
pytest tests/contracts/test_contracts.py` overwrites the goldens with current wire
output) — done per-change, NOT as one lump, so each contract delta stays
attributable. Then commit. Scope: M. Owner: whoever authored those archived changes.

## 2026-07-09 — Telegram message search (explore session, shelved)

Source: 2026-07-09 `/opsx:explore` session. Idea: a new `telegram_search` tool
alongside `ask`/`fetch_raw` — search across many public Telegram channels by
keyword without knowing the channel ahead of time, then expand a hit into a
±20-message context window (via the existing no-login `t.me/s/<channel>
?before=<id>` public preview surface, which a2web could fetch today with its
normal tiers). Shelved for now — no proposal started — but the option space is
narrowed enough to be worth recording precisely.

- **🟡 Apify "Telegram Keyword Search Scraper" as the search backend.**
  Best-shaped candidate found: open-corpus (no pre-specified channel list),
  ~15-20s freshness, $2.50/1,000 results pay-per-use, no Telegram
  account/MTProto (scrapes the public `t.me/s/` surface — same trust category
  a2web already operates in), no payment friction (normal Western SaaS
  billing). Would pair with a new `t.me/s/<channel>?before=<id>` context-
  expansion hop (parse ±N messages + `reply_to`/`forwarded_from` references)
  built the same way as existing site handlers. Not spiked yet — a real query
  against it (coverage, result quality, rate-limit ceiling at scale) is the
  next step before any proposal. Scope: M (new tool + new handler-shaped
  fetch logic + a paid-tier settings toggle, mirroring the existing
  Firecrawl/paid-tier pattern in `tiers/paid.py`).
  Ruled out in the same session: **TGStat** (genuine open-corpus + real-time
  API, but priced as a per-tracked-keyword monitoring product — 2,100-12,600₽
  ($25-150+)/mo — not ad hoc free-text search, plus payment from outside
  Russia is reportedly broken for non-Russian cards, plus coverage skews hard
  CIS/Russian-sphere); **Telemetr.io** (its cross-channel Post Search API is
  "coming soon", not shipped); **Lyzem** (no API, unverifiable coverage);
  general web search (`site:t.me` — confirmed weak/noisy, not a real
  substitute); **TGDataset** (a free academic dataset — 121k channels/498M
  messages/2023 snapshot — but Zenodo-hosted with zero remote-query capability;
  would require downloading a ~20GB shard and self-hosting MongoDB, which is
  exactly the "not yet" the user drew a line at).

- **⛔ Personal-account (MTProto) Telegram access — explicitly not pursued.**
  The original framing was "people sign in with their own Telegram account
  and we use the Telegram API on their behalf." Ruled out deliberately, twice
  over: (a) storing a live per-user MTProto session is a permanent,
  password-equivalent credential — a materially heavier multi-tenant secret-
  custody problem than anything a2web does today (contrast `cookie_jar.py`,
  which only ever mirrors *the operator's own* local browser cookies for
  their own single-user use); (b) automating a personal Telegram account
  (even a single a2web-owned service account, not just end-user accounts) to
  bulk-search channels sits in Telegram's ToS gray zone for "automated
  account" behavior — the user was explicit they don't want to challenge ToS.
  Record this rejection so a future session doesn't re-litigate it without
  new information (e.g. Telegram publishing an official Bot API search
  surface, which does not exist today).

---

## 2026-07-07 — Output benchmark for structured-data pages (S)

Source: `structured-data-answers` + `structured-grounded-completeness`
(shipped v0.35.0, 2026-07-07), task 6.2. Deferred because `make bench` is
live-network and spends LLM quota, so it is deliberately out of `make check`.

- **Add a contact/LocalBusiness case to `eval/corpus.yaml`.** A thin page
  whose only answer source is JSON-LD (the `veito.com/iletisim-EN.html`
  shape) — the class the v0.35.0 exemption now answers. Guards against a
  future regression that re-fails these pages at the length floor.
- **Run `make bench` and record findings** in `eval/findings_<date>.md`.
  Quantifies the answer-quality / data-contract-conformance movement on the
  structured-page class (the four-axis harness tests in `make check` keep the
  harness from rotting but do not measure live quality). Scope: S — one corpus
  entry + one bench run + a short findings note.

## 2026-07-07 — DataDome / hard-wall handling (Koçtaş explore session)

Source: 2026-07-07 explore session on what looked like a real DataDome wall
(`koctas.com.tr`, product price apparently behind a challenge). Original
read: a2web escalated the full free ladder and hit `anti_bot` every time,
so the fix had to be "pass the wall" (cookies, wall memory, a `partial`
status, a DataDome-specific marker). **This framing was wrong — see the
2026-07-09 re-probe below, which supersedes items 🔴🟡🟡 here.** Only the
🟢 item is corrected-and-kept.

- **⚪️ (superseded) Wire the operator's real cookies into the browser
  tier.** Was framed as the keystone fix for "DataDome-shaped" walls. The
  2026-07-09 re-probe shows Koçtaş isn't cookie-gated at all — the raw
  `curl_cffi` tier gets a clean `200` with the full answer already in
  JSON-LD, no session needed. Cookie-wiring may still be worth doing for a
  genuinely session-gated site, but Koçtaş is not evidence for it. Not
  pursuing off this incident.

- **⚪️ (superseded) Per-domain wall memory (kill the ~40s tax).** Correct
  problem (repeat-fetching a known-bad host is wasteful), wrong host
  attribution — Koçtaş's cost wasn't tax from a genuinely unbeatable host,
  it was one avoidable false-positive escalation (see 🔴 below). Revisit if
  a future incident finds a host that is *actually* deterministically
  unbeatable across the free ladder.

- **⚪️ (superseded) Activate the dead `partial` status (shell-vs-answer
  split).** Motivated by "OG/JSON-LD metadata leaked through but price
  didn't" — but the price *did* come through (see re-probe); there was no
  shell/answer split to model here. Still a plausible envelope idea for a
  host where the split is real, just not proven by this incident.

- **🟢 (confirmed, corrected) Site runs Akamai Bot Manager Premium, not
  DataDome.** The 07-09 re-probe's gate diagnostic reads `subsystem:
  akamai_bmp`, matched by `_AKAMAI_BMP_MARKER` in
  `packages/block_detector.py:194-199` (already exists — the original
  "no DataDome pattern" framing was itself imprecise; a2web already names
  this wall class, just under its real name).

---

## 2026-07-09 — Koçtaş re-probe: it wasn't a wall (supersedes 2026-07-07 above)

Source: same-day explore session re-poking the identical Koçtaş product URL
with the current install. `ask` returned the correct price/currency/stock
("4,221.97 TRY... In stock") with zero cookies and zero browser-session
trickery. The 2026-07-07 read was simply wrong for this host: two real,
narrow gaps explain the whole story, and neither is "pass the bot wall."

- **✅ SHIPPED (`answer-bearing-gate-exemption`) Gate ignores `answer_bearing`
  when deciding to force browser escalation.** `fetcher.py`'s domain-level
  `evaluate()` wrapper (not `packages/block_detector.py` — correction from
  implementation: the pure package function has no `structured_answer`
  param; the domain wrapper already did, for the existing bare-`length_floor`
  promotion) fired `anti_bot`/`akamai_bmp`/`turnstile` on marker presence
  alone, **length-independent** — confirmed deliberate by
  `tests/packages/test_gate.py:48-61` (asserts the verdict fires even with
  600 chars of content). Fixed: when content is above `LENGTH_FLOOR` and a
  `content_candidates` entry has `answer_bearing=True`, the `akamai_bmp`/
  `turnstile` branches now promote to `Verdict.ok` and skip the escalation.
  Live-reverified on the exact Koçtaş URL: diagnostics trace dropped from
  4 steps (raw → extract → gate → **browser**) to 3 (raw → extract → gate,
  verdict `ok`), total latency ~8.6-9.3s → ~5.5s, same correct answer.
  `anubis`/`alibaba_punish`/`cf_iuam`/`search_captcha`/generic
  `block_page_detected` untouched. See
  `openspec/changes/answer-bearing-gate-exemption/` (design.md has the full
  decision record + risk analysis).

- **🟡 (deferred, redefined) `_pick_display_candidate` picks by length, not
  by answer-bearing, once prose clears the length floor.**
  `fetcher.py:1350-1373`: the `answer_bearing` short-circuit only fires when
  prose is *sub-floor* (`len(prose_md) < LENGTH_FLOOR`). Koçtaş's actual page
  has ABOVE-floor prose that is pure boilerplate (a Q&A submission-policy
  footer, ~1300 chars) which beats the shorter but correct `json_synth`
  block on the length comparison — so `fetch_raw` (and anything reading
  top-level `content_md`/`meta`) silently gets the wrong content, while
  `ask` dodges it because `assemble_menu` sends every non-subset candidate
  to the extractor regardless of the display pick.
  **Attempted and reverted in `answer-bearing-gate-exemption` (2026-07-09):**
  an unconditional "answer_bearing beats prose" rule regressed ordinary
  articles — `Article`/`NewsArticle` are `json_in_html._PREFERRED_LD_TYPES`
  too, so routine SEO `Article` JSON-LD (headline/author/date) on any
  normal blog/news page is `answer_bearing=True`, and the rule silently
  swapped real article prose for that metadata stub
  (`tests/capabilities/tier_pipeline/test_fetcher.py::test_blog_fixture_yields_real_envelope`
  caught it). A pre-existing test
  (`tests/capabilities/quality_gate/test_structured_answer_exemption.py::test_above_floor_prose_keeps_display_over_structured`)
  independently confirms the current sub-floor-only behavior is deliberate,
  not an oversight. `answer_bearing` measures structured-payload strength,
  not prose relevance — the wrong signal to gate this on alone. Two
  candidate directions for a real fix, both needing their own design pass:
  (a) a `@type`-level split — treat `Product`/`LocalBusiness`/`ContactPoint`/
  `Event` ("entity" schemas, rarely co-occurring with substantial unrelated
  prose) differently from `Article`/`NewsArticle`/`ItemList`/`BreadcrumbList`
  ("editorial" schemas that routinely do) — requires plumbing the schema
  `@type` onto `ContentCandidate` (currently just a bool); or (b) an actual
  prose-quality signal, e.g. threading trafilatura's own extraction
  confidence (`_ExtractResult.score`, already computed, currently dropped)
  onto the candidate and gating on that instead of/alongside
  `answer_bearing`. Scope: M (needs the new signal, not just a conditional
  tweak). Full postscript in
  `openspec/changes/answer-bearing-gate-exemption/design.md`.

---

## 2026-07-06 — listing-completeness Slice 2b (local-browser scroll)

Source: `listing-completeness` (Slice 2 shipped the Zyte scrolling render; this
is the deferred free path).

- **🟢 Free local-browser scroll-to-stable loop.** Slice 2's bounded
  scroll-to-complete goes through the paid Zyte `browserHtml` render
  (`_phase_listing_render` → `_escalate_paid(scroll=True)`). The *free* own-browser
  path — generalising the local backend's single-shot `_scroll_and_retry` into a
  scroll-until-the-record-count-is-stable-or-cap loop, and preferring it before
  paid egress in `_phase_listing_render` — was deferred because it needs
  live-browser verification (out of `make check`) and the Zyte path already
  delivers the mechanism + full orchestration. When built: a keyed paid tier is
  no longer required to complete a partial listing. Composes with the existing
  `content-expectations action loop for a scrolling browser rung` note below (same
  seam, different consumer). Scope: M.

---

## 2026-07-06 — json-endpoint-direct-routing deferrals

Source: `json-endpoint-direct-routing` (Out of Scope). Shipped: JSON responses
are synthesized in-place (raw-tier JSON→ok, extract-phase synthesis, never-lose
text fallback, length-floor exemption). Four adjacent tracks were deliberately
left out — Issue 3 from the 2026-07-05 Reddit/HN feedback report is now closed;
these are the residual follow-ups.

- **🟡 Requested-vs-actual fetch URL transparency (M).** The second half of the
  feedback report's Issue 3: when the orchestrator rewrites the fetched URL
  (jina-wrapping, `rewrite_captcha_host` → DDG, archive), the caller sees only
  the original request URL. Surface both — what was asked for and what was
  actually fetched. This is an **envelope change** (ask-first — touches the wire
  shape parsers depend on); the existing `url` deviation field covers redirects
  but not tier-level rewrites. Its own small change. Scope: M.
- **🟢 Reddit `429` → escalate-to-render (S).** Today only a Reddit search/listing
  `403` triggers the straight-to-Zyte `escalate_to_render` shortcut (v0.29.0). A
  `429` (rate_limited) takes the slow ladder — it still reaches Zyte, just less
  directly. One-line extension in `handlers/reddit.py` to also render on 429.
  Scope: S.
- **🟢 `obstacle` drives escalation, not just confidence (M).** design.md open
  question from v0.29.0. The LLM's `obstacle` signal is born in
  `_phase_extract_answer`, AFTER all escalation, so a confabulated SPA that slips
  the gate only gets flagged `retrieval_incomplete` — it can't trigger a re-fetch
  / render. Reordering so `obstacle` can drive a render (a second extraction
  pass) would close the loop. Bigger pipeline change. Scope: M.
- **🟢 Generic SPA-search-host coverage (M).** The fat-shell confabulation
  problem (a JS SPA whose shell exceeds the length floor) is host-agnostic, but
  only HN + Reddit are wired to `escalate_to_render`. Other JS-SPA search UIs
  still rely on the `<500`-char `js_required` net, which misses fat shells. No
  concrete failing host reported yet — trip condition: a benchmark URL confabulates
  through a fat SPA shell. Scope: M.
- **🟢 Body-sniff JSON served as `text/html` (S).** JSON detection keys on the
  response content-type; a misconfigured API serving JSON under `text/html`
  misses and takes the HTML path. A body-parse-on-mismatch fallback would catch
  it, but risks HTML false positives — deferred until a real case surfaces. From
  `json-endpoint-direct-routing` design Risks. Scope: S.

## 2026-07-05 — deployable-container-ci deferrals

Source: `deployable-container-ci` (Out of Scope). Shipped: slim Dockerfile,
local build verification, GHCR publish workflow, transport-native `/health`.

- **Google OAuth endpoint auth (M)** — the container's HTTP MCP endpoint ships
  with **no auth** (run behind Tailscale/private LAN). Blocked on an upstream
  a2kit `GoogleAuth` AuthSpec: v0.49.1 advertises it in the `packages.auth`
  docstring but does not export/implement it (only `APIKeyAuth`/`TokenAuth`
  ship). Filed `docs/history/A2KIT_FEEDBACK_v0.49.md` (round 16). Operator
  decision: add `GoogleAuth` to a2kit first, bump the pin, then wire
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` (change §5 tasks stay open).
- **Multi-arch image (S)** — publish is `linux/amd64` only. Add
  `linux/arm64` via a `docker/build-push-action` platforms matrix + QEMU when a
  concrete arm64 homelab target appears (buildx arm64 with baked browsers is
  slow, so gate it on real need).
- **Published "full" / "browser" image (S)** — only the slim browserless image
  is published; the `INSTALL_BROWSER=true` and `INSTALL_CLAUDE_CODE=true`
  variants are build-your-own. If a published browser tag is ever justified
  (e.g. a homelab without a Zyte key that needs local browser escalation), it's
  a one-line matrix addition.
- **Multi-stage build to drop `git` from the runtime layer (S)** — `git` is
  installed for the a2kit git-dependency resolve and currently stays in the
  final image. A builder stage could copy just the venv + browsers and shed
  `git`. Marginal size win; deferred.
- **Codex/ChatGPT-subscription reuse (out of scope, operator-owned)** — reusing
  an OpenAI Codex subscription is handled by the operator's own gateway
  (OpenAI-compatible endpoint), consumed via `OPENAI_BASE_URL`. Not an a2web
  concern.

## 2026-06-26 — Browser backend pluggability (roadmap + Camoufox/Playwright compat)

Surfaced by the Trendyol incident (`surface-browser-internal-errors-as-hints`):
the browser tier is hostage to a single Firefox fork's version-skew, and can't
read Chromium-only SPAs. Plan = a pluggable `BrowserBackend` interface (mirror
of the LLM provider seam) with multiple swappable engines, chosen by a
SPA-read/robustness/speed comparison.

- **🟢 Camoufox ⇄ Playwright version-skew guard (compat note).** The Trendyol
  driver crash was `daijro/camoufox` #635/#617: Playwright **1.60.0**
  (PR microsoft/playwright#39767) added an unguarded `pageError.location.url`
  deref; Camoufox's juggler emitted `Page.uncaughtError` without a location →
  driver crash. Producer-side fix = camoufox **PR #625** (commit `b05563291d`,
  juggler always emits location). **As of 2026-06-26 #625 is MERGED BUT
  UNRELEASED** — it is 3 commits *ahead* of the newest published browser build
  (`v150.0.2-beta.25`, 2026-05-11); latest pip `camoufox==0.4.11` pins an older
  FF135 build. Playwright will NOT fix it (vanilla PW-Firefox always emits
  location → not their bug). **We are immune today ONLY because Playwright is
  pinned 1.59.0 < 1.60.0** — the deref doesn't exist yet; the camoufox build
  version is irrelevant to that. **GUARDRAIL: do NOT bump `playwright` to ≥1.60
  until a Camoufox *release* contains `b05563291d`** (or build the browser from
  source with the patched juggler). Add a pinned-pair compat test. The durable
  fix is a Chromium backend (Change 2), which has no Firefox-juggler coupling.
  Scope: S (pin assertion + compat test); the real exit is `browser-backend-*`.
- **✅ Browser-backend roadmap — SHIPPED (collapsed to 2 changes).**
  (1) `browser-backend-interface` — extracted `BrowserBackend` + `RenderedPage`,
  moved Playwright mechanics into `PlaywrightBackend` (ARCHIVED 2026-06-27).
  (2) `browser-backend-bakeoff` — the originally-planned changes 2-4 collapsed
  into one evaluate-then-commit change: a live render-layer bake-off of
  patchright + rebrowser + zendriver, then **keep two** (patchright fast rung +
  zendriver robust rung — they're complementary, not strictly ranked; the
  Chromium drop-ins fail the Trendyol/Hepsiburada SPAs zendriver reads), pruned
  rebrowser, gated Camoufox, dropped `camoufox`/`playwright`/`<1.60`. Wired as
  two browser tiers on the *existing* gate→playbook escalation (the
  `gate_browser_signal` rule, cap `1→2`), not a new mechanism. The
  pinned-pair compat test idea is moot — `playwright` is no longer a dep.
- **🟡 zendriver robust rung: add a shared-browser pool.** The robust rung
  (`browser_robust`, zendriver) launches a fresh Chromium per render (v1, D3) —
  ~4-5x slower than the pooled fast rung (~6.7s vs ~1.4s in the bake-off). A
  per-host context pool (mirroring `PlaywrightBackend`) would close most of that
  gap. Low urgency: browser is the escalation tier, so the cost only bites when
  the fast rung can't read the page. Scope: M.
- **✅ zendriver robust-rung launch + subresource blindness — FIXED 2026-07-25.**
  Two bugs, one session, both in `packages/browser_backends/zendriver.py`.
  (1) The rung could not launch on the pinned zendriver 0.15.3: `--no-sandbox`
  was passed via `Config.add_argument`, which that version rejects with a
  `ValueError`, so every launch returned `unavailable` (container included).
  Fixed by `config.sandbox = False` + a config-safe arg subset. (2) The rung
  never populated `RenderedPage.subresource_blocks`, so it was permanently `0`
  and `is_confirmed_empty` could promote a walled-API 200 to an `ok` "no
  results" answer — an ADR-0009 silent miss. Fixed with a CDP
  `Network.responseReceived` handler registered before navigation, counting
  401/403/429 XHR/fetch via the shared `_CHALLENGE_STATUSES`. The `browser`-marked
  smoke (which had been silently skipping on the launch failure) now passes
  against real zendriver. Both surfaced by the shelf-sweep Q2 review; the
  permissive test-fake `Config` that hid bug 1 was tightened to reject the same
  argument the real one does. See CHANGELOG [Unreleased].
- **🟢 Camoufox re-enable when #625 ships.** The Camoufox launcher code is
  retained, gated to `Unavailable` in `_manifests/browser_backends/camoufox.py`.
  When a Camoufox *release* contains juggler `b05563291d` (PR #625), re-enable =
  flip the manifest `_build` back (the commented body is kept inline) + re-add
  `camoufox[geoip]` to `pyproject.toml`. Until then it stays unselectable.

## 2026-06-25 — LLM provider seam leftovers (from `centralize-provider-selection` + `inject-provider-via-di`)

Discovered while centralizing provider selection and injecting the provider via
DI. None block those changes; all are latent cleanups surfaced by the audit.

- **🟡 claude-code's availability gate is vacuous.** `ClaudeCodeProvider.__init__`
  is a no-op — real readiness (OAuth/OS session) is only known at the first
  `complete()`. So `load_surface` always lists `claude-code` as "available", and
  `auto` always picks it first, only discovering an unusable session at call
  time (the error surfaces as a generic fetch failure, not a clean
  "provider unavailable" degrade). Options: a real construction-time probe, or
  fall back to the next provider on the first `complete()` failure. Scope: M.
- **🟢 `provider.name` spelling drift + redundancy.** `providers/base.py`'s
  comment cites `claude_code` while the runtime id / manifest name is
  `claude-code`. Selection keys off the **manifest name** (authoritative);
  `provider.name` is effectively dead for routing. Reconcile the comment and
  consider dropping `provider.name` as a selection input. Scope: S.
- **🟢 `ModelSpec` is now a thin single-field wrapper.** After deleting the dead
  `.provider` field + `.key()`, `ModelSpec` carries only `model: str`. Candidate
  to collapse into a plain model-id string (or keep as a typed nominal if a
  second field ever returns). Low priority — touches every construction site.
  Scope: S.

---

## 2026-06-25 — reliable AliExpress / Alibaba access (from `block-detector-recognize-alibaba-baxia`)

That change shipped only the **best-effort** slice: the gate now recognizes
Alibaba's Baxia "punish" interstitial and escalates raw→browser (or fails
honestly with `subsystem=alibaba_punish`) instead of dying silently at bare
`length_floor`. Live PoCs this session established that *reliable* access is a
much larger, IP-bound problem. Deferred, in dependency order:

- **🔴 Browser tier honors `proxy_url` (the keystone).** `tiers/browser.py`
  currently does `del proxy_url` (line ~135) — Camoufox always exits the raw
  host IP. So today you can *render* (browser, no proxy) OR *route through a
  clean IP* (raw, no rendering), never both. AliExpress needs both at once.
  Until this lands, no proxy spend helps the browser tier. The user has
  residential proxies (non-KZ) ready to prototype against once this exists.
  Scope: M.
- **🔴 Per-IP behavioral pacing / rotation.** PoC root cause: AliExpress's
  Baxia is driven by per-IP behavioral reputation, not fingerprint — even a
  real Chrome on a real residential IP hit the slider once the IP was flagged
  by a request burst. Reliable access needs rate-limiting + rotation across a
  residential pool so no single IP trips the "punish" state. Scope: M.
- **🟡 KZ residential proxy provisioning.** The KZ AliExpress *locale* needs a
  KZ-geo residential IP (the user's Istanbul IP geo-redirects to
  tr.aliexpress / aliexpress.ru). Procurement, not code. Scope: S (config).
- **🟡 AliExpress product-JSON handler.** Even once a browser renders the page,
  trafilatura extracts ~nothing from the product grid; the data lives in an
  embedded `_init_data_` / `runParams` blob. A tier-0 handler (reddit/hn/arxiv
  shape) that parses it would be far more robust than prose extraction.
  Scope: M.
- **⛔ Out of scope, permanently:** CAPTCHA-solving (the Baxia slider /
  image-select). Strategy is *avoidance* (clean IP + pacing + real
  fingerprint), never solving. This means reliable access is **probabilistic**
  against an adaptive anti-bot — never guaranteed.

Note: this is purely an anti-bot + IP-reputation problem. The earlier
"simulate an AI agent" idea is irrelevant here (AliExpress is not a UA
allowlist site). Contrast akakçe.com, which is the inverse: it *blocks*
declared AI-agent UAs via Cloudflare while serving plain scrapers fine.

---

## v0.5 simplification stages (shipped / deferred)

- ✅ **Stage 1 — a2kit v0.27.2 migration (DONE in v0.5 step 1).** Delivered:
  Resource pattern (SqliteResource, BrowserPool, LlmExtractorResource);
  non-Optional AppState; DI-aware lifecycle hooks; typed-event direct emit
  (no `_emit`/`_event_payload` shim). PR5 "lazy state cleanup" from the
  earlier punch list is folded into this — the Resource pattern delivered
  it.
- ✅ **Stage 2a — `packages/` scaffold + browser_pool moved.** Created
  `src/a2web/packages/` with the contract README, the
  `test_packages_independence` invariant (load-bearing — fails CI if any
  module under `packages/` imports from `a2web.<domain>`), and moved
  `BrowserPool` over as the first proof-of-concept package.
- ✅ **Stage 2b–2g — seven packages promoted (DONE in v0.5 step 9).**
  All seven in-tree microsofware modules now live under `src/a2web/packages/`:
  `browser_pool`, `block_detector`, `http_cache`, `proxy_routing`,
  `llm_extract` (folder), `content_extract`. Five are flat `.py` files;
  `llm_extract/` stays a folder for its multi-author surface
  (extractor, judge, cache, prompts, errors, providers/).
  *NDJSON log package deleted post-v0.5.0 — see Stage 2j.* The
  `test_packages_independence` invariant guards the no-domain-import
  contract for all of them.
- ✅ **Stage 2h — seam-shim layer nuked (DONE in v0.5 step 11).** The
  per-domain seam directories (`cache/`, `gate/`, `proxy/`, `log/`,
  `extract/`, `llm/`) — ~580 LOC of one-line re-exports — were deleted.
  Surviving domain-coupled glue (`compute_profile_hash`, `is_live_only`,
  `log_from_response`) lives in `domain.py`. The AppSettings-aware
  `LlmExtractorResource` lives in `llm_resource.py`. `llm_eval/`
  promoted to top level. Packages now imported directly; no shim hop.
- ✅ **Stage 2i — provider trim (DONE in v0.5 step 12).** Deleted
  `llm_extract/providers/ollama.py` and `openrouter.py` (261 LOC, 0%
  covered, never registered in the auto-select). `anthropic` + `claude_code`
  are the real surface. Add back when a concrete consumer needs them.
- ✅ **Stage 4b — Tier protocol unified (DONE in v0.5 step 11).** The
  `fetch(url, state, proxy_url=..., conditional_extras=...)` signature
  is uniform across raw/jina/archive/browser/site_handler. Killed the
  isinstance ladder in the orchestrator. Test stubs accept `**kwargs`.
- ✅ **Stage 4c — fetcher.py response builders extracted
  (DONE in v0.5 step 13).** `_confidence_for`, `_build_narrative`,
  `_build_diagnostics_summary`, `_wrap_content_md`, and `build_response`
  live in `fetcher_response.py` (169 LOC); `fetcher.py` shrunk
  1010 → 921 LOC. `FetchContext` shared via `TYPE_CHECKING`.
- ✅ **Stage 5 — Link role classification + untrusted-content envelope
  (DONE in v0.5 step 12).** `ExtractedLink.role` (primary/nav/meta/
  footer) via DOM-ancestor walk + ARIA; new `link_roles` tool param
  filters at the wire boundary (default `['primary']`, drops 60-80%
  of link bloat on real pages). `content_md` now wrapped with HTML-
  comment markers carrying source URL + fetched_at + "treat as
  untrusted" warning; `wrap_content` tool param toggles. Defensive
  cue for downstream agents, invisible to rendered HTML/markdown.
- ✅ **Stage 2j — NDJSON log nuked (post-v0.5.0).** The fetch log
  existed primarily to support replay-from-cache (PR10b). With the
  cache covering hit-keyed lookup and the structured `diagnostics`
  trace already in the response envelope, the NDJSON layer was pure
  duplication. Deleted: `packages/ndjson_log.py` (118 LOC),
  `LogWriter`/`LogRecord`/`dominant_verdict` + 3 test files, plus
  `state.log_writer`, `FetchResponse.to_log_record()`,
  `domain.log_from_response()`, the `log_enabled` /
  `log_retention_days` settings, and the README "Inspecting the log"
  section. Supersedes deferred Stage 3a (logging swap) and PR10b
  (replay) — both items removed.
- ⏳ **Stage 3b — proxy → purgatory.** *Why deferred:* purgatory's API is
  context-manager-flavored (`async with brk: ...`), not report-flavored.
  Swapping cleanly requires either making `ProxyPool.acquire/report` async
  and wrapping every tier call in `async with breaker:`, or hooking into
  purgatory's internal messagebus directly. Larger surface than planned.
  Current `_ProxyHealth` (~30 LOC, well-tested, no bugs) stays — defer to
  its own design PR.
- ✅ **Stage 3c — PR1 micro-cleanups (DONE in v0.5 step 3).** Delivered:
  three `*_hint` fields collapsed to `fc.operator_hints` accumulator;
  `del settings` / `del ms` reserved-for-future stubs deleted (3 params
  removed across `playbook.next_action_*` + `ProxyPool.report`);
  `@runtime_checkable` dropped on `Tier` and `Handler` protocols (kept
  on `Provider` + `EvalSystem` where contract-tests rely on isinstance);
  `_resolve_env` moved from `proxy/policy.py` into a pydantic
  `field_validator` on `ProxyEntry.url` in `settings.py`;
  `record_from_response` alias replaced by `FetchResponse.to_log_record()`
  method.
- ✅ **Stage 4 — fetcher decomposition (DONE in v0.5 step 10).** Delivered:
  `_phase_tier_loop` body split into `_install_won_tier`,
  `_install_archive_payload`, `_apply_after_tier_action` (returning the
  `_AfterTier` enum); shared `_emit_tier_started` / `_emit_tier_ended`
  helpers used by tier loop + both escalators; shared
  `_regate_after_escalation` helper. `_phase_extract_answer` stays at
  the a2web seam by design (intrinsically domain-coupled — uses
  FetchContext, FetchResponse, OperatorHint).

---

## 2026-05-25 — bench follow-ups (v0.24+)

- 🟢 **`bench-shutdown-thread-leak`** — operator pain RESOLVED 2026-06-11.
  Source: 2026-05-25 v0.23 bench run. After the final cell ends and
  `write_all(report)` completes, the Python process hung in `Py_FinalizeEx →
  wait_for_thread_shutdown` on a non-daemon background thread parked in
  `_queue_SimpleQueue_get` (a curl_cffi / SDK worker on `queue.SimpleQueue.get`).
  Output was fully written; only the exit blocked, requiring a manual SIGKILL —
  and the lazily-launched Camoufox subprocess lingered while the parent hung.
  **Landed:** `llm_eval/__main__.py::main()` now flushes stdout/stderr and
  calls `os._exit(rc)` after `asyncio.run` returns — skips interpreter finalize
  (so no thread-join hang) and the parent dies immediately (so Camoufox reaps
  itself via its parent-death pipe). Mechanism proven deterministically (a
  non-daemon SimpleQueue thread hangs normal return; `os._exit` exits clean).
  **Still OPEN (low pri):** upstream root-cause attribution — *which* dep leaks
  the non-daemon thread. **Not a2kit** — the bench never starts the MCP server
  or `a2kit.run`, and refound LDD is threadless stdlib logging; a2kit has no
  non-daemon thread on this path. `SimpleQueue.get` rules out `anyio` (uses
  `queue.Queue`) and aiosqlite (daemon, joined). Prime suspects: `curl_cffi`
  (libcurl multi-handle) or the playwright/camoufox pipe transport (Camoufox is
  what visibly lingered). Cheap probe to attribute without a full bench: in a
  subprocess, run one minimal `fetcher.fetch` over the raw (curl) path and one
  over the browser tier, then `threading.enumerate()` the surviving non-daemon
  threads after `asyncio.run` returns — names the culprit module without LLM
  spend. (Heavier fallback: arm `faulthandler.dump_traceback_later` in a live
  bench and grep the parked thread's filename.) Scope: S.

---

## 2026-05-26 — structural-refactor follow-ups (ADR-0001 deferrals)

From the 2026-05-26 explore session that produced ADR-0001 + three openspec
changes (`wobble-typed-funnel`, `arch-fitness-functions-bootstrap`,
`unify-plugin-manifests`). Three audit findings were deliberately NOT folded
into the change set — each earns its own pass when its trip condition fires.

- 🟢 **`reddit-policy-to-planner`.** Source: 2026-05-26 explore audit
  (Cluster D). `handlers/reddit.py:155-160` carries shape-aware escalation
  policy inline (`if shape in ("search", "listing"): RetryViaArchive`).
  Correct behaviour, wrong layer — escalation policy belongs in
  `actions/playbook.py`, not inside the handler. Cost of moving today: low
  but unclear value (only Reddit needs it). Trip condition: a second handler
  wants shape-aware escalation. Until then, the inline check is acceptable.
  Scope: S.

- 🟢 **`askresponse-composite-fields`.** Source: 2026-05-26 explore audit
  (Cluster E). `AskResponse` exposes 7 router-shape fields flat
  (`structural_form` + `shape` + `genre` + `obstacle` + `ask_here` +
  `try_url` + implicit grouping). Natural sub-models are
  `PageClassification(structural_form, shape, genre)` and
  `NextSteps(obstacle, ask_here, try_url)`. Consumers today must reason
  about which fields belong together. Cosmetic until consumer count > 2;
  serializer keeps wire flat for back-compat. Trip condition: a third
  external consumer of `AskResponse` ships, or we hit a real bug from
  flat-field reasoning. Scope: S.

- 🟢 **`tier-loop-state-machine`.** Source: 2026-05-26 explore audit
  (Cluster B). `fetcher._phase_tier_loop` is 141 LoC mixing proxy
  acquisition + conditional-request header building + after-tier action
  dispatch + observation logging + loop control. Refactoring into an
  explicit `TierIteration` state with Command-typed actions would flatten
  the phase function. The current shape works; the risk is future tiers
  expanding it further. Trip condition: a new tier needs bespoke
  rate-limit-backoff or auth-retry policy, OR the function crosses
  ~200 LoC. Scope: M.

- 🟢 **`cross-package-coupling-cleanup`.** Source: 2026-05-26 Tach spike.
  `packages/block_detector.py:23` imports `a2web.packages.escalation` —
  one `packages/X` reaching into another `packages/Y` instead of through
  domain glue. Grandfathered into `tach.toml`'s ignore list by
  `arch-fitness-functions-bootstrap`; this entry tracks the actual
  refactor (likely: move `EscalationSignal` to a shared location, or
  invert the dependency). Scope: S.

- 🟢 **`wobble-to-a2kit`.** Source: 2026-05-26 ADR-0001 "Negative /
  accepted cost". If `wobble.parse_with_policy` graduates into `a2kit`
  as a public library primitive, the funnel must defend itself against
  library consumers (who can't depend on a2web's pytest-archon CI).
  That's the moment to add phantom-types + beartype runtime enforcement
  (Recipe B from the explore session). Today: in-tree, AST-test backstop
  is sufficient. Trip condition: a second project (a2kit-internal or
  otherwise) needs the wobble shape. Scope: M.

---

## 2026-05-25 — fetcher-orchestrator-refactor-v1 follow-ups (v0.23+)

Shipped `fetcher-orchestrator-refactor-v1` (v0.23). Closed TIER-1 audit smells
#1 (dual-semantics state slots), #2 (three construction paths drift),
#3 (escalation contract scattered), plus TIER-2 #5 (boundary freeze). Four
follow-up items surfaced during the audit that we deliberately deferred —
none are blocking, each earns its own design pass.

- 🟢 **`unify-resource-protocol`.** Source: 132-a2kit-structural-audit
  (TIER-2, Smell #4). Resources today split into "crash on unavailable"
  (Sqlite required) and "graceful unavailable" (BrowserPool, LlmExtractor
  via `unavailable_lazy`). Pattern works but is implicit — a future reader
  has to read `bootstrap_state` and `unavailable_lazy` to learn which is
  which. Worth promoting to a typed Protocol (`OptionalResource` vs
  `RequiredResource`) once a third resource needs the choice. Trip
  condition: third resource arrives. Scope: S.
- 🟢 **`url-shape-router-helper`.** Source: 132-a2kit-structural-audit
  (TIER-2 DX). Each handler reimplements URL-pattern matching
  (`matches(url)`) and there's a per-handler skip-on-no-match
  bookkeeping convention via `TierResult(no_match=True)`. A shared
  URL-router helper (host + path-shape declared once per handler) would
  drop ~50 LOC across 9 handlers and make adding a new handler a
  three-line registration. Scope: S.
- 🟢 **`package-folder-vs-flat-convention`.** Source: 132-a2kit-structural-audit
  (TIER-2 DX). `packages/` currently mixes flat `.py` (browser_pool,
  block_detector, http_cache, proxy_routing, content_extract, escalation)
  and folders (`llm_extract/`, `cookie_store/`). Convention: folder when
  multi-author surface, flat otherwise. Document this in
  `src/a2web/packages/README.md` and add a one-line test that asserts
  any folder package exports its public surface from `__init__.py`.
  Scope: S.
- 🟢 **`handler-failure-visibility-in-response`.** Source:
  132-a2kit-structural-audit (TIER-2 operator UX). When a site handler
  short-circuits with a non-ok FetchVerdict (rate limit, timeout,
  404 from an API endpoint), the response carries
  `status=failed` + `narrative` but the operator can't tell from the
  envelope which tier failed — they have to read `debug.diagnostics`.
  Worth surfacing `failed_at_tier: "site_handler:reddit"` (or similar)
  as a top-level failure-only field. Scope: S.

---

## 2026-05-23 — prompt cache + affordances followups (v0.19+)

Shipped `make-llm-prompts-cache-compliant` (v0.19): `EXTRACT_CACHEABLE_V1`
template with byte-stable prefix, `cache_control` markers on Anthropic-direct,
byte-stable concat on claude-agent-sdk (no marker API), OpenAI auto-cache
for free. Spike + capability work follows.

### LLM caching — operational follow-ups

- 🟡 **Verify Claude Code SDK auto-cache fires in production.** The probe
  confirmed the SDK has no `cache_control` API and that we rely on the CLI
  binary to apply caching given a stable prefix. We have not verified the
  CLI actually does so for one-shot `query()` calls (it definitely does for
  multi-turn conversations). Spike: write a small script that runs the
  production Extractor twice with the same `content` and different `ask`
  values, inspects `ResultMessage.usage` for non-zero `cache_read_input_tokens`
  on the second call. Scope: S (~40 LoC + a notes file in `eval/findings/`).
- 🟡 **Telemetry: cache hit/miss ratio in production.** Add a
  `tokens.cache_read` / `tokens.cache_creation` rollup on the LDD bus.
  Today the values flow into `ProviderResponse.prompt_tokens` (aggregated)
  but the breakdown is not surfaced anywhere observable. Trip condition: we
  want to know whether the 5-minute TTL is enough or extended cache (1-hour)
  is justified.
- 🟢 **Extended cache (1-hour TTL) plumbing.** Anthropic supports `cache_control:
  {type:"ephemeral", ttl: "1h"}` for higher write cost but longer hits.
  Defer until telemetry shows enough cache misses that would have hit a
  1-hour window. Scope: S (one kwarg + a settings toggle).

### Affordances — "what else this page can answer"

- ✅ **Affordances spike v1 (2026-05-24).** 5-URL probe with generic prompt.
  Findings: `eval/findings_2026-05-24-affordances-v1.md`. Follow-ups + shapes
  hit quality bar on 4/5 URLs; `missed_sections` is hallucination-prone (arXiv
  abstract case); standalone Haiku call is $0.013/URL but fold-in marginal cost
  is ~$0.002/URL (~18% on top of `ask`). Design: fold into
  `EXTRACT_CACHEABLE_V1` under `include_affordances=True`, drop
  `missed_sections`, keep `shapes` closed-enum.
- ✅ **Affordances spikes v2 + v3 (2026-05-24).** 30-URL corpus across content
  extremes × 3 prompt variants (V_GEN, V_CTX, V_LEAN). Findings:
  `eval/findings_2026-05-24-affordances-v2-v3.md`. Key results: 100% fetch
  success, 100% JSON parse success across 90 calls; closed shape vocabulary
  holds at scale; V_CTX classification 63% literal / ~80% semantic accuracy
  (model often more right than my declared labels); V_LEAN as standalone 2nd
  call only ~5% cheaper than V_GEN (page content dominates cost — fold-in is
  the only economic shape); V_CTX wins on edge cases (paywalled / 404 / unusual
  pages) at zero cost penalty over V_GEN.
- ✅ **Affordances spikes v4 + v5 (2026-05-24).** Two-axis rubric calibration.
  v4 found `page_kind_confidence` was conflating epistemic uncertainty about
  the label with content usefulness — model returned `high` on everything
  because it WAS confident, even when wrong. v5 split into two orthogonal
  axes (`page_kind_confidence` + `content_value`) following RAG-eval
  literature (Braintrust/Deepchecks/ResearchRubrics). Added hard cluster
  trigger forcing confidence ≤ medium when label falls in a confusable
  cluster. Findings: `eval/findings_2026-05-24-affordances-v5-two-axes.md`.
  Result on full 30: 0 envelope violations, 0 parse failures, 5/30 medium
  confidence (vs 30 high), content_value well-distributed (18 high / 5 med
  / 3 low / 4 omitted on obstacles). **Design LOCKED for production.**
- ✅ **Affordances production wiring (v0.20, 2026-05-24)** — superseded by
  router-shape v0.21 (2026-05-25). The single `affordances` payload was
  replaced wholesale by seven router-shape fields (`answer`, `structural_form`,
  `shape`, `genre`, `obstacle`, `ask_here`, `try_url`) per
  `openspec/changes/refactor-ask-to-router-shape/`. v0.20 lived one release.
- ✅ **Router-shape production wiring (v0.21, 2026-05-25).** Shipped under
  `openspec/changes/refactor-ask-to-router-shape/`. Three exploration spikes
  (`router_shape_v1`, `router_shape_v2_stress`, `surface_eval_v1`/`v2`)
  refined the affordances design into a router-shape envelope. `RouterPayload`
  boundary type + pydantic mirror with closed `Literal` enums on all 4 typed
  fields. `EXTRACT_ROUTER_V1` template extends `EXTRACT_CACHEABLE_V1`
  byte-for-byte on the cache prefix. Default ON; opt-out via
  `ask(include_routing=False)`. Omit-empty discipline on all 4 conditionals via
  `_prune_wire`. Includes `mcp_servers={}` + `strict_mcp_config=True` +
  `agents={}` Claude Code provider isolation (closes the personal-context
  memory leak observed in surface_eval_v1). All gates green. Remaining:
  output-benchmark A/B (`make bench` — live-network) before declaring quality
  parity vs v0.20.

### Router-shape — deferred follow-ups (v0.21+)

- 🟢 **Structured-answer mode.** When the user asks for an enumeration ("top
  N stories", "all bags reviewed with verdict"), let them supply a JSON schema
  for the `answer` field. Likely separate `extract` tool with consumer-supplied
  schema; needs schema-discovery design. Out of scope for v0.21 — surface the
  list IN the answer string for now.
- 🟢 **page_kind_confidence resurrection.** v0.21 dropped the
  confidence/content_value fields on the theory that behavioral signal
  (presence of `ask_here` / `try_url` arrays) paraphrases them well enough.
  If a real consumer wants the explicit confidence rating back, add it as a
  debug-only field — don't bloat the default wire.
- 🟢 **Genre prompt tightening for HN-front.** Pre-impl eval found `news` was
  emitted instead of `community` on HN front-page (defensible; both apply).
  Worth one prompt sentence pushing aggregator-of-tech-discussion pages to
  `community` instead of `news`.
- 🟢 **Corpus refresh**: 3 URLs in the v2-v5 corpus are stale 404s
  (`news-bbc`, `comments-lobste`, `blog-jvns/2024/01/05/2023-in-review`).
  Replace before next eval pass.
- 🟢 **Content-value second-order signal**: `content_value=low` paired with
  a content-kind page_kind could auto-trigger browser-tier escalation.
  Telemetry first to confirm the signal is reliable at production scale.

### Reddit `old.reddit.com` raw-tier fetch failure (2026-05-24)

- ✅ **Fixed via `expand-js-shell-markers` (v0.22, 2026-05-25).** Root
  cause was upstream of the handler: the block detector's marker list
  was React/Vue/Next-centric and missed Reddit's actual response shape
  (a JS-challenge anti-bot interstitial, not a content shell). Probes
  also disproved option (a): `old.reddit.com` is also 403'd to unauth
  curl_cffi. Option (c) implemented via marker detection — the existing
  `EscalateBrowser` planner rule already routes `suggested_tier="browser"`
  to Camoufox. No handler change needed.

### 403 → browser planner escalation (2026-05-25)

- 🟢 **Investigate** whether a planner rule "raw or site_handler returned
  status=403 → EscalateBrowser" earns its complexity. `eval/spikes/
  cloudflare_bypass_probe.py` (2026-05-25) showed `curl_cffi
  impersonate=chrome` already bypasses Cloudflare, and no live case has
  been found where `raw=403 ∧ browser=200`. Defer until a probe finds
  one. Open question raised during `expand-js-shell-markers` exploration.

## 2026-05-23 — post-trio followups (v0.18+)

Added after shipping `replace-cookie-store-with-browser-cookie3` (v0.16),
`replace-github-handler-with-gidgethub` (v0.17), and `add-microdata-rdfa-extraction`
(v0.18). The mission-driven-library exploration surfaced Tier-2 swaps and
two new capability ideas; recording them here so they don't slip.

### Library swaps (Tier 2 — defer until a concrete win signal)

- 🟢 **arxiv handler → `arxiv-py`.** Source: 2026-05-23 exploration. Current
  `handlers/arxiv.py` is ~290 LOC of stdlib `xml.etree.ElementTree` against
  the arXiv API. `arxiv-py` is a maintained client with sane pagination,
  retry, and typed results. Sans-IO-adjacent (uses `urllib`/`feedparser`
  internally — would need a transport adapter similar to gidgethub's
  `_CurlCffiGitHubAPI` to keep our curl_cffi tier + breakers). Trip
  condition: bug or maintenance burden on arxiv.py warrants the swap.
  Scope: M (~150 LOC out, +arxiv-py direct, +feedparser transitive).
- 🟢 **URL canonicalization → `courlan`.** Source: 2026-05-23 exploration.
  Multiple sites in domain.py (Google/Bing → DDG rewrite,
  reddit `.json` API munging, host-normalisation for breakers) reinvent
  pieces of URL canonicalization. `courlan` (the trafilatura sibling)
  centralises tracking-param stripping, host normalisation, ccTLD-aware
  language detection. Small, sans-IO, no transport opinions. Trip
  condition: a real bug class (e.g. cache-key drift from tracking-param
  duplication) surfaces. Scope: S.
- 🔴 **HN handler — NO swap warranted.** Source: 2026-05-23 exploration.
  Current `handlers/hn.py` already uses `hn.algolia.com/api/v1` and is
  cleanly structured (~230 LoC). The python-firebase / hn-py libraries
  do not improve on what we have. Recorded as a "do not pursue" entry.
- 🔴 **Reddit handler — NO clean swap.** Source: 2026-05-23 exploration.
  `praw` is async-unfriendly and owns its transport; `asyncpraw` exists
  but bundles `aiohttp`. Neither composes with our curl_cffi tier +
  breakers + proxies. The 799-LOC hand-rolled handler stays. Reconsider
  only if a Reddit-side API contract change forces a rewrite.

### Capability ideas (new — 2026-05-23)

- 🟡 **`llms.txt` / `llm.txt` discovery.** Source: 2026-05-23. Adopt the
  emerging convention (Mintlify et al. — `/llms.txt` at site root, with
  optional `/llms-full.txt` for the full corpus) as a tier-0 detector.
  *Why interesting:* on sites that publish it, `llms.txt` is a curated
  text surface that already represents what the operator wants an LLM
  to see — strictly higher signal-to-noise than trafilatura against the
  HTML chrome. The probe is cheap (one HTTP HEAD/GET to `/llms.txt`)
  and short-circuits the entire tier cascade when present. Caveats:
  (a) convention is young — coverage is small but growing fast; need
  to confirm with a corpus probe before sinking design effort. (b) the
  spec allows it to be a markdown index pointing at *other* URLs — we'd
  want to expand referenced URLs only if the prompt asks the agent to
  drill down, not eagerly. (c) hostile `llms.txt` is a real prompt-
  injection surface (operator-controlled instructions disguised as
  content); needs the same untrusted-content envelope as page content.
  Scope: S (detector + cache hit), M (drill-down expansion + injection
  defence). Cross-ref: spec/SIG at https://llmstxt.org. Trip condition:
  corpus probe shows ≥5% of frequently-fetched hosts ship one.
- 🟡 **Agent-identity stealth (look like a human, not a bot).** Source:
  2026-05-23. Audit and minimise the signals that mark our requests as
  "AI agent". Today the default `User-Agent` is a static Safari string
  (good) but other tells leak: (a) the LLM extractor sometimes
  fingerprints with referer-less navigation patterns; (b) some handlers
  set `X-GitHub-Api-Version` (acceptable on api.github.com but a generic
  fingerprint elsewhere); (c) browser tier may carry telltale headless
  Camoufox fingerprints under certain configurations; (d) we have no
  per-host UA pinning to match the canonical browser the host expects
  (e.g. Reddit serves different content to mobile UA vs desktop).
  *Concrete pieces of work:*
  1. **UA rotation strategy** — small pool of real recent Safari/Chrome/
     Firefox UAs, pinned per-host for the session so requests look
     coherent.
  2. **Referer chains** — set realistic `Referer` headers on follow-up
     requests so we don't look like a fresh-tab fetcher on every URL.
  3. **`Sec-Fetch-*` header trio** — the modern fingerprint-via-omission
     signal; we currently omit these, real browsers send them.
  4. **AcceptedLanguage / Accept jitter** — small per-session variation
     to break the "exact same fingerprint across 1000s of requests"
     tell.
  5. **Tier-0 handler audit** — ensure no handler leaks `a2web` in any
     outgoing header. GitHub's `_REQUESTER = "a2web"` shows up in
     `User-Agent` per gidgethub — change to a generic project string.
  6. **Cookie carry-through** — when we have a `CookieJarResource`
     mirror for a host, our requests should look like the operator's
     browser session (same UA + same cookies + same Accept headers).
     Today the UA isn't pinned to match the cookie profile.
  *Why important:* Cloudflare / Akamai / DataDome are increasingly
  scoring requests as "agent vs human" not just "browser vs curl";
  even a perfect TLS fingerprint loses if the header set is
  inconsistent. The cumulative cost of looking obvious is silent quality
  loss — sites return banner-mode content instead of full content. The
  point is NOT to evade rate limits or impersonate users illegally; it
  is to avoid the increasingly-common "served degraded content because
  you look like a bot" failure mode that doesn't even surface in our
  block detector. Cross-ref: existing `cookie_jar.py` (already steps
  toward this); `tiers/raw.py` (JA3/JA4 already correct). Scope: M
  (audit + pinning), L (full Sec-Fetch-* + referer-chain semantics).
  Trip condition: any benchmark URL that returns degraded content under
  a2web but full content under a real browser session.

### Speculative — only if signal surfaces

- **Re-adopt `extruct` for RDFa.** Source: 2026-05-23 — extruct was
  added then removed mid-implementation (see `openspec/changes/archive/
  2026-05-23-add-microdata-rdfa-extraction/design.md` D1). The
  rdflib weight is only justified by RDFa coverage; eval corpus
  shows zero RDFa hit rate today. Reversible — add back if a real
  RDFa-shaped failure surfaces in a future `make bench` run
  (academic-publishing URL that ships RDFa but no microdata / LD-JSON).
  Scope: S.
- **PDF tier — SUPERSEDED (2026-07-09), don't spike independently.** Source:
  2026-05-23 — was raised in the mission-driven-library exploration but not
  pursued in the trio. Tier 4. Many high-value agent destinations (regulatory
  filings, academic papers, manuals) are PDF-first; the cascade currently
  404s or content-type-mismatches them (`content_type_mismatch` in
  `src/a2web/tiers/raw.py::_verdict_for_status`). The original `pymupdf` vs
  `marker` framing predates the shelf's `convert-md[documents]` extra and is
  stale — the engine choice is now owned by the shelf's
  `pdf-engine-verification` change (compares docling, pymupdf4llm, markitdown,
  pdfplumber, unstructured, marker on fidelity, with a2web's
  `typer==0.25.1`/`docling-core typer<0.25` conflict as a hard filter, not a
  tiebreaker, per that change's D3). a2web's own future work narrows to the
  tier-routing plumbing only — a content-type carve-out in `raw.py` +
  extraction phase, mirroring `json-endpoint-direct-routing` — once the shelf
  lands an engine and a2web decides it's worth pulling the `documents` extra
  in at all (not yet decided; this backlog item alone isn't sufficient
  evidence of value).

---

## v0.2 workspace-packaging deferral (from `migrate-to-a2kit-v026-and-simplify`)

- **Phase D — extract as uv workspace packages.** Source:
  `migrate-to-a2kit-v026-and-simplify` Phase D (tasks 4.1–4.6).
  *Superseded by v0.5's in-tree `packages/` migration.* All six
  remaining candidate microsofware modules (`browser_pool`,
  `block_detector`, `http_cache`, `proxy_routing`, `llm_extract`,
  `content_extract`) now live under `src/a2web/packages/` with the
  contract enforced by `test_packages_independence`. Promoting one
  to a separate uv workspace package is a mechanical move from there
  — wait for an actual second consumer before paying that mechanical
  cost. Scope: M per module.

## v0.2 OSS-adoption deferrals (from `migrate-to-a2kit-v026-and-simplify`)

Four OSS swaps the research recommended that turned out to be wrong fits on closer inspection. Documented here so a future change can revisit if circumstances shift.

- **hishel for HTTP cache.** Source: `migrate-to-a2kit-v026-and-simplify` Phase B 2.1+2.2. *Why deferred:* hishel v1.2's `AsyncCacheProxy` requires owning the HTTP transport via a `request_sender` callback. a2web's cache is an orchestrator-level before/after wrapper around the tier loop — it doesn't own transport. Adopting hishel would mean restructuring every tier to delegate raw HTTP to hishel, which is a fundamental architectural shift, not a shim. Reconsider if v0.3 collapses tiers to a single curl_cffi-backed transport. Scope: L.
- **aiometer for hedged archive requests.** Source: 2.7. *Why deferred:* `aiometer.run_any` returns the FIRST result regardless of value (first finisher wins, losers cancelled). Our archive tier wants "first SUCCESS" semantics — if Wayback returns None, we want to keep waiting for archive.ph. aiometer cancels and returns None instead. Custom 30 LOC of anyio task-group + capacity-1 stream stays. Scope: S.
- **purgatory for proxy quarantine.** Source: 2.6. *Why deferred:* ProxyPool's API is sync (`.acquire()`, `.report()`); purgatory's breakers are async (`.get_breaker()`, `breaker.context()`). Swap would force ProxyPool async, propagating through the orchestrator's tier loop. Net: more code, not less. Custom 30 LOC health state machine stays. Purgatory's redis-persistence value-add is the PR7e win; defer until PR7e actually needs redis. Scope: S.
Pattern: hand-rolled async code (cache wrapper, hedged race, proxy health) is hard to beat with sync libraries even when the library "covers" the use case. Trafilatura's bundled metadata (which DID land — drops htmldate) was the one clean OSS swap because the API shape genuinely matched. (RotatingFileHandler-for-NDJSON entry deleted: the NDJSON layer itself was removed post-v0.5.0 — the cache covers replay.)

---

## PR7e — Proxy polish

- **Browser-tier proxy plumbing.** Source: PR7d / PR7c. Camoufox is
  context-level (proxy lives on the persistent context, not the page);
  the v0.1 pool resolves and reports but does not configure browser
  contexts. *Why deferred:* per-host context coupling needs rework and
  is a separate scope from the orchestrator's proxy contract. Scope: M.
- **Archive-tier proxy plumbing.** Source: PR7d. Wayback / archive.ph
  hedge requests bypass the proxy pool today. *Why deferred:* the
  hedged-request task group needs proxy-aware retry semantics. Scope: M.
- **Persistent `~/.a2web/proxy-health.json`.** Source: PR7d. Health is
  in-memory only at v0.1. *Why deferred:* survives a single process;
  multi-process / restart-friendly health is a v0.2 concern. Scope: S.
- **Background health-check loop.** Source: PR7d. Quarantine is
  reactive (3 failures → 600s). *Why deferred:* proactive probes are
  observability work; in-memory reactive policy is sufficient for v0.1.
  Scope: M.
- **`a2web profile` CLI commands.** Source: PR7d. *Why deferred:* the
  multi-profile system itself is post-v0.1; CLI follows the model.
  Scope: M.
- **Global circuit breaker alarming.** Source: PR7d. Hooks exist;
  alerting does not. *Why deferred:* alerting is observability work,
  out of scope for the cascade. Scope: S.

## PR7c follow-ups

- **Anubis PoW solver / Turnstile auto-solve / cookie-consent dismissal.**
  Source: PR7c. *Why deferred:* Camoufox + realistic timing handles
  most observed cases; explicit solvers wait for v0.2 evidence. Scope: L.
- **Profile-keyed browser contexts.** Source: PR7c. *Why deferred:* the
  profile system itself is post-v0.1. Scope: M.

## PR8b — Site handlers

- **`youtube` handler.** Source: PR8. *Why deferred:* needs the browser
  tier or a `yt-dlp` opt-in dependency; both are non-trivial. Scope: M.
- **`substack` handler.** Source: PR8. *Why deferred:* trafilatura
  already handles articles; per-domain auto-detection complexity is not
  worth it without signal. Scope: S.
- ✅ **`twitter` / X handler — SHIPPED (v0.3, commit 519c011).** Nitter
  rotation with per-instance circuit breakers. 87% coverage. Was
  previously listed as deferred (auth-gated, no clean v0.1 path) —
  Nitter unblocked it.
- **Per-handler proxy plumbing.** Source: PR8. *Why deferred:* mostly
  mechanical — bundle with PR7e proxy work. Scope: S.

## Hard-access forums (Tieba / Zhihu / Discuz!)

- **Tieba / Zhihu / Discuz!-engine forums — access-blocked, needs an
  access spike.** Source: `structural-record-detection` CN-forum probing
  campaign (2026-05-22). *Finding:* for these targets the blocker is
  **access, not extraction**. A probe with curl_cffi Chrome-impersonation
  (a2web's raw-tier engine) got: Tieba → HTTP 403; Zhihu → SPA shell + 403
  on every content page; Discuz! forums (hostloc, right.com.cn) →
  login-walls / pages stripped to anonymous fetch. The structural record
  detector cannot be validated against them because there is no clean HTML
  to run it on. *Why deferred:* needs its own spike first — does a2web's
  browser tier (Camoufox) + stealth + `cookie_jar` punch through these
  anti-bot walls? Until that is known the handling cannot be specified.
  Discuz! additionally has no API (an engine-specific HTML parser would be
  needed) and its post wrappers use empty-class `<div id="post_X">` that
  the structural detector's non-empty-class guard rejects. V2EX, Discourse,
  and Habr — the accessible CN/RU targets — are covered by their own
  handler changes (`v2ex-handler`, `discourse-handler`, `habr-handler`);
  this entry is the residual hard tier. Scope: L (access spike + per-engine
  handling).

## v0.2 candidates

- 🟢 **Reader-LM v2 fallback.** Source: engineering.md §10. *Status:*
  greenlit post-v0.5.0 — owner OK with running benchmarks + deep
  research. Trip condition: corpus run shows trafilatura + readability
  miss ≥10% of content on a representative set. Scope: L (corpus
  selection + extraction harness + Reader-LM v2 wrapping + threshold
  picker). Next step: pick benchmark corpus (~50-100 URLs across
  article / docs / forum / aggregator / SPA classes).
- **Multimodal fetch (screenshot + DOM as response).** Source:
  engineering.md §10. *Why deferred:* requires the browser tier to
  emit screenshots and a response-shape change; v0.2 contract decision.
  Scope: L.
## v0.3+

- **Browser-as-a-service remote CDP.** Source: engineering.md §10. *Why
  deferred:* removes the local Camoufox dep at the cost of a network
  hop and a service to operate. Scope: L.
- **VLM image captioning.** Source: engineering.md §10. *Why deferred:*
  vision pipeline. Scope: L.
- **Distributed cache (remote backend).** Source: engineering.md §10.
  *Why deferred:* sqlite is sufficient for single-operator use. Scope: L.
- **Webhook callbacks for slow fetches.** Source: engineering.md §10
  (vision). *Why deferred:* event-sink pattern, not yet needed. Scope: M.
- **LLM-emitted hints.** Source: engineering.md §10 (vision). *Why
  deferred:* needs an evaluation harness first. Scope: L.

## v1.0 / vision

- **Search aggregation as primary surface.** Source: engineering.md §10
  (v1.0). *Why deferred:* a separate product surface, not a tier in
  the cascade. Scope: L.

---

## Findings from `benchmarks/vs-webfetch/2026-05-11/` (a2web vs Claude Code WebFetch)

20-URL benchmark, blind LLM judge, three a2web response variants. Full
write-up at `benchmarks/vs-webfetch/2026-05-11/findings.md`. Headline:
**a2web's content tier wins on quality (mean 3.40 vs WebFetch 2.95) but
the default response envelope leaks ~80% of its token budget for ~0%
quality gain on most tasks** — `links` is 49% of payload, `fit_md` is
19% of payload as a pure duplicate of `content_md`.

### v0.3 (response-envelope diet) — SHIPPED ✓ (v0.3.0)

Three items merged. Benchmark re-run on 2026-05-11 against the same
20-URL corpus shows **72% token reduction across the default response
shape**, judged equivalent quality on 17/20 URLs.

- ~~**Stop populating `fit_md` with `content_md`**~~ ✓ SHIPPED — fit_md
  stays None until a real pruning filter ships.
- ~~**Default `include_links=false` (param-gated)**~~ ✓ SHIPPED — new
  `include_links: bool = False` param on the `fetch` tool.
- ~~**Move `diagnostics` behind `debug=true`**~~ ✓ SHIPPED — new
  `debug: bool = False` param; one-line `diagnostics_summary` always
  populated.

Still deferred:

- **🟡 Classify links at extraction time** (`role:
  primary|nav|meta|footer`) and filter by default. Source: H2.
  Eyeballed HN/PyPI/gh-trending payloads — 60-80% of link entries are
  UI/nav/redundant. Even when links stay, returning only `role=primary`
  shrinks them ~5×. Scope: M.

### v0.3 (browser tier reliability) — SHIPPED ✓ (v0.3.0)

- ~~**Investigate why browser tier fires 0/20 times**~~ ✓ SHIPPED — gate
  now produces `suggested_tier="browser"` on the broader JS-shell pattern
  (Next.js / React / Vue / Twitter / Ember / noscript). Orchestrator
  already routed on the hint; the gate side was the bottleneck.
- ~~**Gate false-positive on Linear**~~ ✓ SHIPPED — all interstitial /
  block-page markers are now length-gated; substantive extracted content
  (>= LENGTH_FLOOR) keeps `status=ok` regardless of marker matches.

### v0.3 (handler coverage)

- **🟢 Add site handlers for PyPI, npm, GitHub Trending.** Source:
  benchmark finding. Current envelope/value ratios:
  - PyPI: 13,312 tokens A_full, 287 links → 1,011 tokens C_content (13×
    bloat for the same answer)
  - gh-trending: 27,167 tokens A_full, 1,142 links → 379 tokens
    C_content (71× bloat, AND only A had the data to answer the task)
  - npm: 1,874 tokens A_full → 228 tokens C_content (8× bloat)
  Handlers would return structured tier-0 output with the right
  fields, killing both the bloat and the list-extraction failure mode.
  Scope: M per handler.

### v0.4+ (link addressing / aliases)

- **🟡 Alias-addressed links for drilldown flows.** Source: 2026-05-18
  discovery design chat. *Problem:* multi-step research (Reddit thread →
  linked page; AliExpress listing → product detail; HN front page →
  comments) currently round-trips full URLs through the agent, which is
  expensive on listing-style pages where 50+ candidate URLs may each be
  100+ chars. *Idea:* return short alias IDs (e.g. 6-char) alongside
  `next_links`; store alias → URL in sqlite with short TTL scoped
  per agent session; agent passes `alias=` to the next `fetch` call.
  *Why deferred:* prerequisite (curated `next_links` field) shipped in
  v0.7 link-discovery (2026-05-18) — see CHANGELOG. Aliasing earns its
  keep only once we measure full-URL pass-through as the actual bottleneck
  on real agent traces; today's benchmark corpus doesn't yet show it.
  Adds a stateful layer that breaks the current stateless fetch contract.
  Scope: M.

### v0.3+ (untrusted-content envelope) — security posture

- **🟡 Wrap fetched content in a structural envelope** (e.g.
  `<a2web:content>...</a2web:content>` or explicit
  `is_user_authored: bool` flag) so downstream agents can syntactically
  distinguish page content from system signals / harness messages.
  Source: false-positive incident during the benchmark — even a careful
  reader misclassified a Claude Code harness reminder as page content
  when it appeared inside a tool-result envelope. If a single LLM
  judge could be confused, so can downstream agents consuming
  `content_md`. Scope: S (envelope) + M (taxonomy).

### Process / measurement

- **🟢 Make this benchmark a recurring eval.** Source: benchmark
  itself. Re-run on each v0.3+ release; track judge scores + token
  sums as regression metrics. Adds the harness, corpus, and judge
  prompts already in `benchmarks/vs-webfetch/`. Scope: S.

### Reddit self-hosted stealth-browser rung (deferred from `reddit-via-zyte`, 2026-07-04)

- **🟡 Self-hosted Camoufox/zendriver browser tier + residential egress as
  Reddit ladder rung 1.** `reddit-via-zyte` shipped the Zyte-primary public
  path and *designed* the arbitration ladder with an `Unavailable`-gated
  self-hosted rung ahead of Zyte, but did not build it. It would give a
  **free, private, logged-in** Reddit read (Zyte is paid, third-party,
  public-only).
  *Why deferred:* the blocker is not the engine — Camoufox (stealth Firefox)
  and zendriver (stealth Chromium/CDP) both pass Reddit headless — it is the
  **IP**. Both are blocked through a datacenter egress
  (a datacenter IP); the passing recipe needs a **residential IP** (or the
  operator's own node) plus headful-under-virtual-display (Xvfb/neko/Kasm) for
  the logged-in variant. That is an infra project (egress + display), not a
  code change. Spike scripts: `docs/history/spikes/browser_headful_poc.py`,
  `browser_headful_confirm.py`. Evidence: ADR-0011 (both the headful POC and
  the `reddit-via-zyte` update). Once residential egress exists, the rung slots
  in under `reddit_tier_policy` with zero ladder rewrite (it self-gates via the
  plugin `Unavailable` pattern). Scope: L (infra) + M (tier).
- **🟡 content-expectations action loop for a scrolling browser rung.** The
  `content_expectations.assess` seam resolves `ready|partial|fail`; the Zyte/
  old.reddit path uses it as a pure one-shot post-fetch assertion. A browser
  rung could instead *drive* a bounded scroll/paginate loop off the same
  verdict under a ≤3-min budget to push `loaded` toward the oracle. Designed
  into the seam + design.md, not built (no browser rung yet). Scope: M.

**Smaller `reddit-via-zyte` leftovers (deferred as out-of-scope):**

- **🟢 Caller-selectable comment sort.** The eager Zyte path hardcodes
  `sort=top` (best answers for a Q&A agent). A future tool arg could let the
  caller pick `top | new | controversial | best` (old.reddit supports all).
  Noted in `design.md` §1. Scope: S.
- **🟢 Route Reddit listings/search through Zyte too.** Only *threads* go
  eager-Zyte today; listings/search stay on keyless RSS (which works and is
  cheaper). If richer listing data is ever needed, Zyte `browserHtml` on the
  new-reddit canonical would serve it — the normalizer already emits that
  canonical. Scope: S–M.
- **🟢 old.reddit parser structural-probe test.** The selectolax parser keys on
  `div.thing.comment` / `a.comments`. If old.reddit changes shape the parser
  returns `None` and falls through to RSS (safe), but silently. A periodic live
  probe (behind a marker, not in `make check`) that fails loudly when the
  anchors vanish would catch drift before users see degraded reads. Mitigation
  noted in `design.md` risks. Scope: S.
- **🟢 Live `ask` (LLM-extraction) validation over the scored-comment render.**
  Task 6.2 live-validated the `fetch_raw` path (Zyte → parse → counts/hint). The
  `ask` path (LLM extraction over the nested comment markdown) was not run live —
  worth a one-off check that extraction quality holds on the denser, scored input
  before leaning on it in the benchmark. Scope: S.
- **🟡 Firecrawl has no old.reddit raw-mode equivalent.** The eager Reddit path
  requires Zyte specifically (`httpResponseBody` on server-rendered old.reddit).
  A deployment keyed with *only* Firecrawl falls back to RSS for Reddit. If that
  combination matters, add a Firecrawl raw-fetch shape. Scope: M.

## Live-spike confirmation of the routing-arm distribution (2026-07-27, S)

Source: `fix-extraction-signal-fidelity`, task 6.4.

The four `RoutingOutcome` arms are covered offline, one test each. What is NOT
re-measured since the change is the live DISTRIBUTION: how often each arm occurs
against a real provider, and therefore how often `index_lost` actually fires. The
design predicts near-zero (the pre-change spikes recovered routing 15/15), and a
hint that turns out to fire often is the `llm_wobble` saturation failure
repeating in a new channel — worth confirming rather than assuming.

Live-network + LLM quota, so it cannot live in `make check`. ADR-0016:
subscription provider only (`A2WEB_BENCH_PROVIDER=claude-code`).

## `arxiv` listing delivered no index from ANY source (2026-07-27, M)

Source: `fix-extraction-signal-fidelity`, full-pipeline spike (the open question
in its `design.md`).

`arxiv.org/list/cs.CL/recent` produced a distilled answer with no `also_here`, no
`other_pages`, and no `options` — nothing from any of the three index sources. A
genuine ADR-0015 gap, and a DIFFERENT one from what that change addressed: the
routing payload was recovered fine, so no signal fires. n=5 with high
run-to-run variance, so it is a lead, not a verdict.

Captured as corpus case `listing-answer-always-leaves-an-index` so it cannot be
lost. Note the new `index_lost` hint does NOT cover this: it is gated on a
degraded routing arm, and this case is `recovered`.

## Constrained decoding would delete the `unparsable` arm structurally (2026-07-27, M)

Source: `fix-extraction-signal-fidelity`, design D5 (considered, not built).

A provider-side `response_format` / `json_schema` / `tool_choice` constraint
would make an unparsable router envelope impossible, rather than recoverable —
strictly better than tolerating fences.

Blocked on substrate: `anyllm` exposes no such parameter today. And the blocker
is worse than "not yet implemented" — the two `claude-code` adapters are the
ADR-0016-mandated dev/bench default, and likely cannot expose constrained
decoding at all, so this could not cover the default path even once `anyllm`
grows the surface. Revisit if that changes.

## Intermittent failure: `akakce-cloudflare-bot-wall` replay (2026-07-27, M)

`tests/eval_replay/test_regression_corpus.py::test_regression_replay[akakce-cloudflare-bot-wall]`
has now failed twice under `make check` and passes every time in isolation and
3/3 on a full standalone `pytest` run. Observed during `fix-extraction-signal-fidelity`
and again during `foss-readiness`; neither change touches that path (the case is
a Cloudflare interstitial that never reaches the extractor).

Written down rather than shrugged at, because an intermittent failure nobody
records is how a real bug becomes "oh, that test is flaky". Unknown whether the
trigger is test ordering, the coverage plugin, or shared state in the replay
harness — `make check` differs from a bare run in both ordering and coverage.

First step when picked up: capture the actual assertion (it has only ever been
seen as a summary line), then try `-p no:randomly` with the same seed under
coverage to separate ordering from instrumentation.

## PyPI publish is blocked on the shelf packages (2026-07-27, M)

`foss-readiness` deliberately shipped git-tag + container install, not PyPI.

a2web depends on ~15 shelf packages pinned by git tag. A PyPI release of a2web
would be uninstallable from PyPI alone — `pip install a2web` cannot resolve a
`git+https://` dependency, so the wheel would either fail to install or need the
shelf vendored into it.

Publishing therefore means publishing the shelf packages first, which is its own
decision (namespace, release cadence, versioning contract across ~15 pieces) and
not one a presentation change should make by accident. Both repos are public and
installable by tag today, so nothing is blocked on this — it buys discoverability
and `pip install`, not capability.

## The eval capture harness has no CI coverage (2026-07-27, M)

`eval/_capture/capture.py` was comprehensively broken for five days after the
a2kit sunset — dead `a2kit.ldd` imports, the removed `bootstrap_state`, and a
`browser_pool=` kwarg `fetch()` no longer accepts. Repaired in
`restore-llm-fixture-fidelity`, but the reason it rotted silently is unchanged:
it is live-network by nature, so `make check` never exercises it, and its first
failure surfaces only when someone tries to capture a case — typically under
time pressure, mid-investigation.

A smoke test that imports the module and asserts `capture_case`'s signature
still matches `fetcher.fetch`'s would have caught every one of these breaks
without touching the network. Cheap; not yet built.

Sibling of the "never add a structural guard without an assertion that it found
something" rule — this is the same failure in an offline-untestable component.

## No security-disclosure channel on a now-public repo (2026-07-27, S)

`foss-readiness` shipped the LICENSE, the identifier guard, and a Contributing
section, but no `SECURITY.md`. For most repos that is a formality; for this one
it is slightly more, because a2web's whole job is *making outbound requests to
attacker-influenced URLs on someone else's behalf*. The backlog already carries
one unshipped item in that exact class (2026-07-11, SSRF egress denylist for
internal/private targets), and ADR-0014 exists because anchor labels on a
fetched page are attacker-controlled input to an LLM.

So the plausible report is not hypothetical, and today it has nowhere to go but
a public issue. A `SECURITY.md` naming a private channel and a rough response
expectation is a few lines. Worth pairing with a decision on whether the SSRF
item's status should be stated openly rather than living only here.

## Spike rot was systemic, and one class of it broke an ADR trigger (2026-07-27, S)

Measured while checking one spike: **18 of 19 spike scripts could not import.**
Nine died with the a2kit sunset (`a2kit.ldd`, `a2kit.testing`), the rest with
the shelf promotions that moved `llm_extract/providers`, `browser_pool`, and
`cookie_store` out from under hardcoded paths. Nothing went red, because no test
imports a spike and a spike is run by hand, months apart.

For the one-shot corpus under `eval/spikes/` that is mostly fine — the durable
value is the frozen `*_output.md` beside each script. Those 15 are now marked
`# SPIKE-ARCHIVED: <cause>`.

The three under `docs/history/spikes/` were a different matter: **ADR-0011 names
them as the instruments of its own re-evaluation triggers** ("Probe scripts:
`reddit_json_cookie_spike.py`"). An ADR promising "re-run this to reopen the
decision" while pointing at a script that cannot import has been frozen by
bit-rot rather than by evidence. Repaired (one-line swap to the promoted shelf
`browser_cookies`) and pinned live by
`tests/architecture/test_spike_scripts_are_runnable_or_archived.py`, which also
refuses to let those three be silenced with the archive marker.

**What remains open** is the generalization: an ADR re-evaluation trigger that
cites *anything* executable is only as good as that thing still running, and
only ADR-0011's citation happens to live in a directory a guard now watches. A
trigger citing a `make` target, a corpus entry, or a script elsewhere has no
such floor. Worth a sweep of every ADR's trigger section against what it names —
offline, and cheap enough to do by hand once.

## Two limits accepted by `close-silent-enforcement-loss` (2026-07-27, S)

Both are stated in the change's design and repeated here so they are findable
without reading an archived change.

**1. The tach coverage guard answers "is there a contract", not "is it tight".**
`test_tach_covers_every_package.py` asserts the module list and the package tree
are the same set. A package listed with permissive `depends_on` satisfies it
while granting no real protection — the guard would go green on a contract that
allows exactly what the invariant forbids. Closing this means asserting each
entry's declared dependencies are minimal, which needs a survey of what the
current entries actually declare before a rule can be written that does not
immediately need grandfathering. Noted in the test's own docstring too, since
that is where someone will be standing when it matters.

**2. Citation-checking stops at `CLAUDE.md`.** `CONSTITUTION.md` and
`docs/adr/*.md` cite paths the same way and rot the same way — the ADR sweep
already has its own entry above (ADR re-evaluation triggers citing things that
no longer run), and this is the same problem seen from the docs side. Deferred
deliberately: the `<!-- gone -->` marker convention is one day old and has
exactly one user. Extending it to two more file classes before it has survived
contact with ordinary editing would be committing to a convention on no
evidence. Revisit after the next few `CLAUDE.md` edits — if the marker gets
used correctly without prompting, extend it; if it gets worked around, the
convention is wrong and extending it would spread the mistake.

## `also_here` empty on a narrow ask against a rich page (2026-07-27, M) — ADR-0015

Live spike finding, `eval/findings_2026-07-27.md` (second run). Corpus case
`wikipedia-narrow-ask-indexes` encodes the requirement explicitly — *"`also_here`
is NON-EMPTY — the narrow ask did not 'cover' the rich article"* — and the live
result is `also_here: []`, `other_pages: []` on the Rust Wikipedia article for
"Who created Rust and in what year did it first appear?".

That is ADR-0015 ("never withhold the body without leaving the index") failing on
its canonical case. The prompt instructs the behaviour in as many words; the
model returned nothing. The answer itself was correct, which is what makes this
the ADR-0015 harm rather than a wrong answer: the caller gets a confident
one-line reply and no signal that an enormous article sat behind it.

**Before designing a fix, establish the rate.** The 4/4 reproduction is
misleading — the extraction cache very likely served trials 2–4, so the real
evidence is one or two independent observations. Re-run with the extraction
cache bypassed, across several rich pages (Wikipedia, MDN, a spec, a product
page) and several narrow asks. A prompt change made against a single observation
would be tuning on noise.

Candidate directions once the rate is known, in rough order of how much they
respect the existing design: the instruction may be losing to its position in a
long prompt (it sits inside the `also_here` field description, far down); the
model may be reading "COVERED" as satisfied by answering the asked question,
which the prompt explicitly warns against and may need to state as a rule rather
than a caution; or the narrow-ask case may need its own worked example, since
the existing examples are all richer asks.

Related: the `arxiv` listing no-index item above, and the `index_lost` hint,
which fires on lost ROUTING but by construction cannot fire here — routing
succeeded and returned a legitimately-empty index. The two failure modes are
disjoint, which is worth remembering when reading a green `index_lost` rate as
evidence that indexes are healthy. They are not the same claim.

## Routing arms: three of four unobserved in the wild (2026-07-27, S)

Same spike. `routing_outcome` was `recovered` on 14/14 URLs where extraction
ran; `unparsable`, `unclassified`, and `provider_error` did not occur, and
`index_lost` fired 0/15.

Good news for the dilution worry that motivated the run — the hint is not noise.
But it also means the four-arm split is carrying one arm in live practice, and
the degraded arms are validated only by constructed offline tests. Not a defect
and not obviously actionable; recorded so that a future reading of "0% index
loss" is understood as "rare trigger", not as "mechanism confirmed working in
production".

# ═══ Measurement-layer integrity — investigation 2026-07-28 ═══

Prompted by a fair challenge: several findings this session were reported as
"caught it" or "nearly filed the wrong thing". Catching a problem by hand is
what an unstructured layer feels like from the inside, so the near-misses were
treated as a symptom and investigated rather than as a run of good luck.

**The result is narrower than "we are unstructured", and better news.** The
product layer is genuinely well-defended: 1223 tests, 64 architecture guards,
tach module boundaries, anti-vacuity floors, and a standing rule that every
guard must be watched failing. The measurement layer — the thing that tells us
whether the product is any good — has almost none of that. Every near-miss this
session landed in that gap, which is exactly where one would predict.

The one-line version: **we built rigorous structure around the code, then judged
whether the code was good using a system with no structure at all.**

Verified defects and unproven hypotheses are kept separate below on purpose.
Nothing here commits to a fix; M1 and M2 in particular want a design
conversation before anyone touches them.

## VERIFIED — structural defects

### M1 — Two disjoint corpora, zero overlap (L, root cause)

| | `eval/corpus.yaml` | `eval/corpus/{regression,breaking}` |
|---|---|---|
| cases | 33 | 6 |
| slug overlap | **0** | **0** |
| criteria | prose, LLM-judged | fixture replay, deterministic |
| in `make check` | no | yes |
| cost to run | live network + LLM quota | free |

**Only 2 of 33 `corpus.yaml` slugs are named in any deterministic test**
(`hn-front`, `wikipedia-rust`). The other 31 are exercised by `make bench`
alone — live, quota-spending, deliberately not in CI, not run by default.

The sharp edge: CLAUDE.md's **"Never lose a case"** rule points at
`corpus.yaml`. So the discipline we are proudest of routes every newly-found
case into the corpus that nothing runs. The rule is followed faithfully and
produces an inert record.

Not obviously fixable by merging the two — they answer different questions
(fixture replay cannot judge answer quality; the bench cannot run free). The
design question is what a case's *lifecycle* is: captured where, promoted to a
fixture when, checked how often.

### M2 — Structural criteria are graded by a fuzzy judge (M)

15 of 100 criteria name an actual wire field (`also_here is NON-EMPTY`,
`status`, `obstacle`, `retrieval_incomplete`). Those are deterministically
checkable, and they are being evaluated as prose by an LLM judge inside a
harness that is not run.

The 2026-07-27 ADR-0015 finding is exactly this shape: the requirement was
written down, correctly, in the one place where only a fuzzy and unexecuted
mechanism could ever see it. A criterion that names a wire field should be
asserted, not judged.

### M3 — Silent skips indistinguishable from passes (M)

`runner._score_next_links` returns early when a system emits no block, and a
`JudgeParseError` leaves the score `None`. Already paid for: a bench run
reported `4/4` while scoring **zero cells** on the changed path
(`eval/findings_2026-07-27.md`, first section, which names it "precisely the
vacuous-guard shape CLAUDE.md warns about"). The anti-vacuity rule exists and
was never extended across the eval boundary.

### M4 — Two of four axes report a mean with no denominator (S)

`report.py`: `next_links` renders `4.0 (8)` and contract renders `12/14`, but
**quality** and **clarity** render a bare mean computed over non-`None` rows
while the `n` column counts *all* rows. A clarity mean of 4.2 over 3 surviving
cells is visually identical to 4.2 over 29.

The inconsistency is the tell — two axes get it right, so this is an absent
rule, not an absent thought.

### M5 — Inert corpus schema (S)

`needs` carries three spellings for what look like two concepts
(`content+links` ×23, `content_only` ×7, `content` ×3), has **no consumer**
anywhere outside the parser, and no closed-set validation. The only test that
touches it asserts it round-trips — testing the parser, not any behaviour.
`next_links_expected` is present on 9/33; elsewhere that axis is silently N/A
rather than explicitly not-applicable.

### M6 — URL is not identity, and nothing enforces slug selection (S)

Five URLs appear twice across ten cases, deliberately (same page, different
ask) — including two Wikipedia entries with **opposite** expectations about
whether `also_here` may be empty. Any tool that samples or selects cases must
key on `slug`; nothing states this or enforces it. This is what caused the
2026-07-27 near-miss where a sweep sampled the broad-ask entry and the finding
was nearly filed against the wrong case.

### M7 — No cache discipline in the eval path (S)

Repeat measurement is silently served from the extraction cache, so
"reproduced N times" is not N independent observations. Hit on 2026-07-27: a
4/4 reproduction was really one or two real samples, caught by suspicion rather
than by the harness saying so. Any measurement loop needs an explicit
cache-bypass and should state which mode it ran in.

## HYPOTHESES — probe before believing

### H1 — ADR-0014 and ADR-0017 may be unpinned (S)

Zero test files name either; ADR-0009 and ADR-0015 are named by 11 each.
**Weak proxy** — a test can enforce an invariant without citing it, so this may
be nothing. *Probe:* read both ADRs, grep for the behaviour rather than the
label, and record which requirement each is pinned by.

### H2 — The full-corpus pass rate may be unknown (S)

No evidence surfaced of a recent complete bench run. If true, we do not know how
many of the 33 cases currently fail — and the ADR-0015 finding shows at least
one silently does. *Probe:* look for a full-corpus artifact under `eval/runs/`
and check its date and completeness.

### H3 — Criteria may have rotted against page content (M)

The rule says phrase criteria against stable structural facts so entries survive
content rotation. Nothing checks it. *Probe:* sample 10 criteria and ask of each
whether it survives a site redesign; count the ones keyed to today's text.

### H4 — Findings may not close (S)

Roughly eight `eval/findings_*.md` exist. Whether any produced a tracked action
is unknown. *Probe:* trace three findings forward to a backlog entry or commit.

### H5 — This backlog may be a graveyard (S)

52 sections, 14 struck through, no priority or triage field, monotonically
growing. *Probe:* date-bucket the open items; if the median age exceeds the
rate of retirement, the file is an archive pretending to be a queue — and this
very entry is making it longer.

## SEQUENCE — one change at a time (set 2026-07-28)

Five changes, strictly ordered. Only the head is written as a proposal; the rest
are one line each until their predecessor lands, because each one's content
depends on what the previous exposes. Writing all five today would produce four
documents to rewrite later, which is the pattern H5 describes.

| # | change | covers | status |
|---|---|---|---|
| P1 | `close-silent-eval-loss` | M3, M4, M7, dead `next_links` axis | **proposal written** |
| P2 | corpus schema is validated | M5, M6, the 4 never-run cases | queued |
| P3 | expected-failure is declarable | M8 (needs P2's schema) | queued |
| P4 | structural criteria are asserted | M2 (needs P2's schema) | queued |
| P5 | case lifecycle | M1 + the "Never lose a case" rule | queued |

### H2 — RESOLVED 2026-07-27, and it inverts the hypothesis

A full run exists: `eval/runs/2026-07-22_024912/` — 87 cells, 29 cases × 3
systems, 8 minutes, subscription provider. The corpus pass rate was never
unknown. `a2web_extract` scored quality **0 on 6** cases, **≤2 on 10 of 29**,
and `next_links_score: None` on **29 of 29**.

The consequence is worse than the hypothesis. `wikipedia-narrow-ask-indexes`
scored 2 in that run, five days before the ADR-0015 index gap was
"discovered" by a hand-written spike and reported as new. **Detection was
correct and on time; nothing obliged anyone to read it.** The measurement layer
does not primarily lack rigour — it lacks a consumer. Re-read M1 with that in
mind: merging the corpora would not have made anyone read the 2.

Four corpus slugs never ran at all, and they are the invariant cases:
`listing-answer-always-leaves-an-index`, `router-envelope-survives-model-fencing`,
`answer-carries-no-fenced-scaffolding`, `dead-product-url-fat-404`. Folded into P2.

### M8 — Expected failure is unrepresentable, so the aggregate is uninterpretable (L, NEW)

`incehesap-404-dead-search-url` has criteria that read, in full: *reports NOT
FOUND, does NOT emit the critical `try_user_browser` hint, does NOT fabricate a
price*. The pass condition **is a loud failure**, exactly as ADR-0009 requires.
It scored quality **0**. Same shape for `walled-api-fake-empty-spa`, whose
criteria demand the fetch be classified as a wall.

`reached: False` collapses "a2web correctly refused" and "a2web broke" into one
number. Of the six quality-0 cells, at least three may be passes and the
artifact cannot say which. The leaderboard systematically punishes a2web on
precisely the cases ADR-0009 exists to create. Sequenced as P3 — it is a corpus
*vocabulary* gap, not a scoring bug, and it needs P2's validated schema to live
in.

### Root cause of the dead axis — verified, not inferred

ADR-0015 folded `next_links` into `other_pages` on the `AskResponse`.
`runner._next_links_block` still reads `envelope["next_links"]`. Confirmed
against the stored artifact
`eval/runs/2026-07-22_024912/trace/hn-front/a2web_extract/fetch_result.json`,
whose envelope keys are `['tier','confidence','answer','title','operator_hints',
'other_pages','refinement_axes']` — a populated `other_pages`, no `next_links`.

A product rename silently voided its own measurement, and the report rendered
`—`, the same glyph as "axis not applicable to this corpus". This is
`close-silent-enforcement-loss` one layer out: the anti-vacuity rule exists and
had never been extended across the eval boundary.

## Root cause of the link-loss defect — consumption, not coverage (2026-07-28)

Prompted by a fair review question on the fix: *shouldn't the trafilatura call
and its `include_links` be encapsulated in a shelf package?* It already is. That
answer inverted the diagnosis.

`content_extract.extract_markdown(html, url, *, include_links=False)` is shelf-
owned, returns markdown + links + headings + metadata from ONE off-thread parse,
and is imported by `fetcher.py:27`. **Six sites call `trafilatura.extract`
directly instead** — `tiers/browser.py`, `tiers/archive.py`,
`handlers/{wikipedia,reddit,twitter}.py` — each re-deriving a subset and dropping
links and headings on the floor.

**Chronology kills the "pre-shelf legacy" excuse:**

| date | event |
|---|---|
| 2026-05-10 | `tiers/browser.py` added WITH its own `trafilatura.extract` — while `fetcher.py:28` imported a canonical `extract_markdown` **the same day** |
| 2026-05-12 | that extractor promoted to `packages/content_extract` |
| 2026-07-08 | promoted again to the shelf, in-tree copy deleted |

The canonical extractor existed when the first bypass was written. Each promotion
moved the correct copy further up the stack and left the bypass untouched — the
distance grew and nothing noticed, because "is everyone using the canonical
thing?" was never a checked property.

**So promotion is the wrong lever.** More shelf packages without a consumption
guard yields more correct packages with more bypasses around them.

**The gap is that exactly ONE funnel guard exists.** `test_json_loads_funnel.py`
bans `json.loads` outside `wobble/`. Nothing funnels trafilatura, which has the
identical shape: a low-level library with a canonical wrapper whose guarantees
are silently lost by going direct.

Direct third-party imports in `src/a2web/`, as candidates for the same treatment:

    4  import trafilatura   ← canonical wrapper exists, no guard  (fixed by the change)
    4  import httpx         ← UNCHECKED: is there a canonical wrapper being bypassed?
    3  import aiosqlite     ← UNCHECKED
    2  import yaml          ← UNCHECKED

*Probe before guarding any of the three:* a funnel guard is only worth writing
where a canonical wrapper actually exists and is being bypassed. Direct use of a
library with no wrapper is not a defect, and a guard written from a pattern
rather than an incident still has to earn its floor.

**Same failure class as the dead `next_links` axis** (closed the same day): a
correct mechanism, silently bypassed or starved, with no guard to notice. Both
would have been caught by guards nobody had yet been bitten into writing — every
architecture guard in this repo was written AFTER its incident. The trafilatura
funnel is the first written from a pattern instead of a wound.

Tracked by `openspec/changes/restore-links-on-pre-rendered-tiers/`.


### Should ALL extraction live in the shelf, leaving no library traces in a2web? (open question, 2026-07-28)

Raised while fixing the trafilatura bypasses. The stronger form of that fix:
a2web should not know WHICH library extracts HTML at all — "stop caring which
extractor" is exactly the micro-software stop-caring litmus. Today it half-knows.

Surface as of 2026-07-28 (`src/a2web/`):

| | count | status |
|---|---|---|
| `import trafilatura` | 4 | being removed by `restore-links-on-pre-rendered-tiers` |
| `from selectolax.parser import HTMLParser, Node` | 1 | `handlers/_reddit_html.py` — untouched, unexamined |
| `from content_extract import …` | 3 | shelf, correct |
| `from html_fragment import …` | 7 | shelf, correct |
| `from json_in_html import …` | 2 | shelf, correct |

So after the current change lands, **one** library import remains, and it is in
a site handler — the place where the argument is weakest AND strongest at once.

**The tension, stated honestly rather than resolved:**

- *For full encapsulation.* A library import is a substrate detail leaking into
  product code. Every one of them is a place where the canonical wrapper's
  guarantees can be silently lost — which is not theoretical, it is precisely
  what just happened with trafilatura for two and a half months.
- *Against.* The shelf's own rule is DEEP · STABLE · WINS, and reuse-xor-
  simplification. `handlers/_reddit_html.py` walks Reddit's *specific* DOM shape.
  Pushing that into a shelf package would export a2web's domain knowledge into
  substrate — the exact inversion the packages/ boundary exists to prevent. The
  right split may be "shelf owns the parser, a2web owns which nodes matter",
  which is what selectolax already is.

**The question is therefore not "move it all" but "which half".** A parser
handed to a domain module is substrate used correctly; a parser used to
re-derive what a canonical wrapper already returns is a bypass. trafilatura was
the second. selectolax may be the first. Nobody has checked.

*Probe (cheap, offline):* read `handlers/_reddit_html.py` and answer one
question — does it use selectolax to do something `content_extract` already
does, or something only Reddit's DOM shape requires? If the former it is the
same defect and the funnel should cover it. If the latter it is correct as-is
and should be documented as deliberately direct, so the next audit does not
re-litigate it.

*Do NOT generalise into a blanket "no library imports in a2web" rule before that
probe.* A rule that bans correct usage produces exemptions, and an exemption list
nobody re-reads is how the trafilatura bypass survived three promotions. Related:
the unchecked `httpx` / `aiosqlite` / `yaml` candidates recorded above.


### SHELF GAP — `content_extract` needs an `include_comments` knob (2026-07-28)

`content_extract.extract_markdown(html, url, *, include_links=False)` exposes no
control over trafilatura's `include_comments` / `include_tables`. Two a2web
handlers pass `include_comments=True` because on a comment thread **the comments
ARE the content**:

- `handlers/reddit.py`
- `handlers/twitter.py`

Routing them through the shelf today would silently drop the page's substance —
a worse regression than the missing links the funnel exists to prevent. So both
are listed in `test_trafilatura_funnel._FUNNEL_EXEMPT` with the reason inline.

**This is a shelf gap, not a permanent a2web exception.** The fix is to promote
the knob into `content_extract` (shelf loop: read `<shelf>/docs/agent-loop.md`,
propose, release, re-pin), then delete both exemptions and let the funnel cover
all of `src/a2web/`.

Until then the funnel is enforced on 5 of the 7 original bypass sites. Stated
rather than glossed: a guard with unexplained exemptions rots into a guard with
many, which is the failure mode that let the original bypass survive three
promotions.


### NEXT — the digest gate blocks every pre-rendered page (L, 2026-07-28)

`restore-links-on-pre-rendered-tiers` fixed the links half of the pre-rendered
early return and is verified to work (arXiv envelope gained `title`/`byline`,
`headings` 0→4, extractor returns 484 links on that page). **`other_pages` is
still impossible on those pages**, for a second reason inside the same early
return:

    _phase_extract returns at fetcher.py:1276, BEFORE fetcher.py:1320
      `await _run_extraction_escalation(fc, raw_html=raw_html)`
    which is the only producer of json_synth / record_synth candidates,
    which `_build_link_digest` REQUIRES at fetcher.py:2329.

So a pre-rendered page can never satisfy the digest gate no matter how many
links it has. Measured: `eval/runs/post-link-fix` — the two target cases are
byte-identical in disposition to before the fix.

The gate is correct in its original intent (a prose article on the raw tier
should not pay for a digest). It is wrong in combination with the early return,
where it silently means "no browser-served page ever gets a digest".

*Design question for the next change, not decided here:* should pre-rendered
pages run the extraction escalation too (costly, and the pre_rendered skip exists
precisely to avoid re-work), or should the digest gate accept a different
listing-shaped signal that a pre-rendered page can actually produce? Both are
plausible; picking from one example is how the last two diagnoses went wrong.

## RETIRED (WRONG) — "a losing tier's structured output is discarded" (2026-07-28)

Filed and retired the same day. It claimed arXiv's handler builds a correct
index that the browser escalation throws away. Run rather than read, the handler
returns `next_links: 0` and 40 chars of markdown. Nothing correct is discarded.
Filed from reading that `_parse_listing_entries` exists and inferring it works —
the fourth wrong diagnosis in this investigation, all four from trusting a read
over a run. Superseded by the entry below.

## NEXT — a handler that parses nothing reports success (M, 2026-07-28)

`handlers/arxiv.py::_fetch_listing` returns `Verdict.ok` with ZERO parsed
entries, and `_render_listing` renders that as a confident `## Papers (0)`. A
parser that matched nothing reports success.

The instance: all three listing regexes have rotted. arXiv serves single-quoted
attributes and `<a href ="/abs/…">` (space before the `=`); the patterns require
double quotes and `href="`. Measured on the live page — `_LIST_ABS_RE` 0 matches
vs 50 for a tolerant equivalent, `_LIST_TITLE_RE` 0, `_LIST_AUTHORS_RE` 0.

The defect: the ok-with-nothing is why this rotted silently. Same shape as the
empty-vs-wall invariant — a confident empty asserted with no evidence the page
was empty. Fix the guard first, then the patterns; fixing only the patterns
guarantees a silent repeat at arXiv's next markup change. Ask whether the other
eight handlers have the same hole.

## Guard candidate — a spec requirement naming a deleted field (S, 2026-07-28)

`tier-pipeline`'s "Pre-rendered handler results bypass extraction" described
`tier_result.tier_extras["pre_rendered"]` — a `dict[str, Any]` bag removed when
`TierResult` became typed — through every review since. Corrected by
`narrow-the-pre-rendered-extraction-skip`. Same shape as the CLAUDE.md staleness
`close-silent-enforcement-loss` found: a document nobody re-reads describing code
that moved. Candidate for the same class of guard; needs a second instance before
the rule is worth writing.

## Known inaccuracy — `source="trafilatura"` on the pre-rendered path (S, 2026-07-28)

The escalation ladder's baseline candidate is labelled `source="trafilatura"`.
On the pre-rendered path the markdown came from the tier, which for
browser/archive/wikipedia did run `extract_markdown` inside the tier, but for the
API handlers did not. Renaming the literal is wire-visible on the candidate menu,
so it was deliberately not done inside a change whose value is one measured
behaviour delta. It will confuse the next person reading a candidate menu from a
handler fetch.

## `any-browser` container CDP-connect failure — the robust rung silently collapses (M, 2026-08-02)

In the slim container, **zendriver's CDP handshake fails while patchright
launches**, so `browser_robust_backend` falls back to the same engine as the
fast rung. The escalation still *happens* — a fast-rung failure dispatches the
robust rung, the tier reports a second attempt, the decision log records two
browser dispatches — but both attempts run the same engine, so the second one
is a retry wearing an escalation's name.

**Why this is worth an entry rather than a shrug.** The fast/robust split exists
because the two engines fail differently; a rung that silently becomes its twin
converts "we tried a genuinely different renderer and it also failed" into "we
tried the same thing twice", and the fetch reports the former. That is the
ADR-0009 shape one level down: not a silent miss, but a silently *weaker* effort
than the response claims.

Observable, not fixed: `correlated_witness` surfaces the engine actually used, so
an operator comparing the two dispatches can see they match. Nothing asserts it.

Two things to establish before fixing, in this order — the second is the
decision, and the first is what makes it answerable:

1. **Is it the container or the engine?** zendriver connects over CDP to a
   browser it expects to have launched; the slim image drops the
   `[browser]` extra's full dependency set. Reproduce outside the container
   before blaming either.
2. **What should a collapsed rung DO?** Options: fail the robust dispatch loudly
   (honest, costs the retry), keep the retry but stop calling it an escalation
   in the decision log (honest, cheaper, weaker), or ship the engine. Only the
   third is a fix; the first two are the floor while it is not fixed, and the
   floor is what ADR-0009 actually requires.

Filed from `repay-the-shelf-debt` §5.2.
