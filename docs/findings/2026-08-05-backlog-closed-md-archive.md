# BACKLOG-CLOSED.md — full archive at deletion (adopt-beads-work-queue)

Verbatim copy of `BACKLOG-CLOSED.md` as it stood immediately before
deletion by `adopt-beads-work-queue`. Every `## ` heading below was
migrated to a closed bd issue, preserving the shipping/closing rationale
the original entry gave.

---

# Backlog — closed

Shipped, resolved, and superseded entries moved out of `BACKLOG.md`. Kept
because the *reasoning* in a closed entry is often the reason a later change is
correct — several of these record incidents (a dead parser behind green tests, a
silently-lost eval cell) that the surviving invariants exist to prevent.

Nothing here is actionable. If an entry looks live again, move it back rather
than re-deriving it.

---
## 2026-07-31 — decompose `fetcher.py` into single-purpose files (L, structure — T1 UMBRELLA) — CLOSED 2026-08-05

**Closed by `openspec/changes/decompose-fetcher-into-files`.** The original
entry is preserved below unedited; what follows is what actually shipped against
it, including where it did not.

**Shipped.** The 26-file tree became 32 files under `src/a2web/fetcher/`. The
loop landed as `retrieval/escalate/seam.py` — `escalate(fc, rung)` is the only
thing that dispatches a rung and always runs comprehension → sufficiency →
re-gate on what landed, so H1 ("escalators re-enter at comprehension and skip
sufficiency") is unexpressible rather than merely fixed. `install.py` landed and
is guarded twice: the transport half by
`tests/architecture/test_transport_install_chokepoint.py`, the content half by
`test_content_install_chokepoint.py` (2026-08-05 — the half the live `links` bug
actually happened in had been carrying an unbacked "only place" claim).

**The `Stage` protocol stayed rejected, and the bet it made paid.** The entry
said the residual ordering hazards would become "one architecture test, not a
framework", and that if that test proved hard to write the decision should be
reopened. It was not hard: `test_fetcher_phase_ordering.py` and
`test_fetcher_residual_ordering.py`.

**Did NOT ship as designed, recorded so the tree is not read as the plan.**
Five designed files never appeared. Two were real gaps and landed 2026-08-05
(`retrieval/conditional.py`, `retrieval/proxy_lease.py`) — until then
`_phase_tier_loop` was still 219 lines carrying the five jobs the census counted,
i.e. the change's own headline example was unfixed. Three others were
deliberately not built: `prerendered.py` and `json_synth.py` became
`comprehension/extract.py` instead, and `escalate/_tail.py` — flagged in the
entry as "placed by judgement rather than census, confirm that reading before
writing it" — was confirmed WRONG on reading. Task 1.1 found the two escalators'
tails differ in a load-bearing way (paid observes its own success, browser does
not, and `is_confirmed_empty` depends on that asymmetry), so a shared tail would
have merged two things that must not merge. It became `seam.py`, which dispatches
rather than deduplicates. **The census would have made that mistake; reading
prevented it** — which is the entry's own instruction working.

**The line budget was not met and the number should not be repeated.** The entry
claims "nothing over 300". Measured 2026-08-05: `__init__.py` 504 (65 imports +
a 190-line `__all__` re-export block over one 152-line `fetch()` — the
deliberate back-compat surface), `context.py` 462, `tier_walk.py` 316.

**Phase two is closed short, deliberately.** §7.2 lifted the 19 request-frozen
fields into `FetchInputs` + `FetchResources` (`FetchContext` 79 members → 62),
which bought a language-enforced property. The per-node split of the remainder
was declined: those fields are written mid-pipeline by definition, so no bundle
can be frozen, and the split would touch ~350 reference sites for naming alone.
Reasoning and the reopen condition are in that change's `tasks.md` §7.2d.

**Subsumed findings, closed with it:** *no "install a fetch result" type* (→
`install.py` + two guards), *five escalation decisions live outside the "single
policy function"* (→ `seam.py` + `_dispatch_action`), *the sufficiency question
has no name* (→ `sufficiency/`). Their rows in the 36-findings index are
annotated in place rather than deleted, so that entry's count stays true.

---

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


 five "adopted, then hand-rolled anyway" findings (M, structure)

Closed by `repay-the-shelf-debt` §6, §7, §8. The change is not finished —
`record-mine`, `dom-schema` and `any-browser` stay open in `BACKLOG.md` — but
these five findings are resolved, and the reasoning is the reusable part.

**A primitive can be imported, re-exported, and called from nowhere.**
`prune_dict` was all three, while the same omit-empty question had two *other*
answers in one file. The trap on closing it: the hand-written predicate AGREED
with the shelf's on every type a2web uses. That is the finding, not a reprieve
— nothing compared them, and they were never the same test (`value == []` is
equality against a literal; `is_empty` is isinstance-plus-length, and they
diverge on any custom `__eq__`). The fix was to promote the *predicate* public
(`lean-wire-v0.3.0`) rather than copy it a fourth time, because `_prune_wire`
genuinely could not use `prune_dict` itself.

**"Adopted, then bypassed one import away" understates the cost.** `fmt_dur`
was elevated and used at five sites, all in one file, while `live_sink.py`
rendered `f"{ms/1000:.1f}s"` — and the two disagree *below* one second
(`800ms` vs `0.8s`), not only at the ≥7s boundary the finding named. A bypass
one import away is not a style deviation; it is a second answer that nothing
compares.

**The `results.tsv` bypass was a live data hazard, not tidiness.** Four columns
are LLM-authored prose, and `csv.DictWriter(delimiter="\t")`'s QUOTE_MINIMAL
emits a newline-bearing cell quoted with the newline still literal inside — so
one logical row spans several physical lines and every `awk`/`cut` pipeline
over the file misparses silently. This is precisely the behaviour `lean-wire`
was adopted to replace, in the one place it was not used.

**The jina bypass removed a tier from the offline test harness.** Routing it
through `http_fetch` was the task; what the task's own premise surfaced was
worth more. Verifying what jina would "gain" found that one of the four gains
**did not exist** — `http_fetch`'s injected circuit breaker never opened,
because a breaker counts what raises in its context and mapping every transport
failure to a `FetchVerdict` and returning normally is the primitive's whole
contract. Five consecutive failures at `threshold=2` left it
`state=closed, failure_count=0`. Every consumer passing `breaker=` in two repos
was carrying a decoration, and CLAUDE.md's "`purgatory` for circuit breakers"
was false with zero enforcement. Fixed as `http-fetch-v0.3.0`, witnessed from
both sides deliberately — the package with a counting fake (it must not depend
on one breaker library), a2web with REAL purgatory driven through `RawTier`,
because a fake breaker encodes the same assumption as the code, which is
exactly how the pre-existing `_FakeBreaker` asserting `entered is True` passed
for the defect's entire life.

And the forked client was invisible to `patch_fetch_bytes`, so **every eval
replay whose ladder reached jina made a live HTTPS request to `r.jina.ai`** — in
CI, on every push, for the corpus's whole life, while `CassetteMiss` promised
"replay refuses to hit the network". Measured with a `socket.getaddrinfo` spy
before being believed. Closed at the class rather than the instance:
`tests/eval_replay/conftest.py` fails any live DNS lookup during a replay.
One case remains `xfail(strict)` and needs an operator decision — see
`BACKLOG.md`.

**Four unused `a2effect` surfaces: evaluated, two adopted, two declined.**
`pydantic_validation_error_enricher` was adopted for field extraction (not
translation — its raising shape does not fit a `tolerance="skip"` site), and
the evaluation surfaced a real defect underneath: the hand-rolled version read
`errors()[0]` only, so a payload violating two closed enums logged one and the
second was invisible. `raises_as` was DECLINED on a shape mismatch that matters
— it maps a foreign exception to a typed `AppError` and **re-raises**, while all
four named sites catch and **return** a `TierResult` carrying a non-ok
`Verdict`. A non-ok tier verdict is a normal ladder outcome, so routing them
through `raises_as` would turn every recoverable tier failure into a fetch that
stops at the first hiccup instead of escalating. `a2effect.lint` was probed and
is **not** the Rego replacement: `lint_path(src/a2web)` reports 0 messages over
the whole tree, which reads as "clean" and means "not applicable" — its three
rules key on an `Annotated[T, Raises(...)]` convention a2web does not use, and
its type allowlist covers `httpx` but not the `curl_cffi` a2web's tiers
actually use. Recorded as guard-reads-green, never cited as a pass.

### Explicitly NOT promoted, with reasons — carried forward

Recorded here so the next primitives scan does not re-propose them:

- **hedged-race-first-wins** (`tiers/archive.py`) — DEEP, STABLE,
  substrate-indifferent, and exactly **one** call site.
  Flag-when-a-second-caller-appears, not now.
- **reddit's retry loop** — its comments encode a live-measured penalty-box
  model that `tenacity`/`stamina` would take the schedule from and lose the
  reason.
- **`_find_product_or_item_list`** — a heuristic over app-state key names plus a
  cap that is a2web's token budget, not a fact about any format.
- **`_normalize_commerce_row`** — looked generic (schema.org `offers.price` →
  `price`) but renders `f"{price} {currency}"` into one token: a markdown-table
  decision wearing a normalizer's name. A generic version would keep the fields
  apart, which is designing a new function rather than promoting one.
- **`raises_as`** — see above; the shapes do not match.
- **`field_to_typer_annotation`** — DEFERRED, not declined. a2kay's argparse
  `_analyze` is a strict superset of it, so the generic unit is neither
  function: it is `analyze_param(annotation) -> ParamSpec`, with typer and
  argparse as thin renderers. Generic-first (shelf resolution 0010) says the
  wrong move is to promote a2web's half and make a2kay adapt. Filed as its own
  change.

---
## 2026-08-02 — T4: five guards that read green while covering less than they named (M, verification)

Closed by `close-guards-that-read-green` §1/§2/§3/§4/§7. The change is not
finished — §5.1-5.3 (capture-bound) and §6 (bench-side) stay open in
`BACKLOG.md` — but these five findings are resolved and the reasoning is the
reusable part.

**The markup-funnel guard matched `re.compile` and nothing else.** It read as a
ban on parsing markup with regexes; it was a ban on parsing markup with
*precompiled* regexes. Widening it to `search`/`sub`/`match`/`findall` turned up
two live violations in `reddit.py` — a `<!--.*?-->` strip and a
`<div class="md">(.*)</div>` capture whose own adjacent comment conceded the
nesting assumption was wrong. **The widening was run BEFORE anything was fixed,
deliberately: the red run is the only evidence the widened matcher works.** A
guard widened and fixed in one pass proves nothing about either half.

**Two guards were named for a claim they did not check, and two more did not
exist at all.** `test_packages_boundary_frozen.py` asserted dataclass
immutability, not the `__all__` freeze CLAUDE.md cited it for; the `__all__`
claim was withdrawn rather than back-filled, because one package declares one.
Two guards cited in `docs/architecture/README.md` and
`verification-provenance.md` — including a `path::function` citation — named
files that had never existed. **The document that codifies the
foreign-provenance rule had itself failed it**, and reasoned from the absent
guard's existence to advise spending verification effort elsewhere. That
recommendation had to be re-derived, and the failure it was built to catch (the
dead `--no-sandbox` rung) turned out to be unguarded. Recorded in the document
itself, not only in the fix — a doc that states a rule and breaks it is worse
than one that states nothing.

**A wire regression on ADR-0009 was one re-bless from green.** The severity that
marks `try_user_browser` critical — the loudest signal in the system — was
asserted only by inline asserts inside one golden-comparison test, and
`test_no_golden_is_degenerate` barred nothing stronger than `len(text) > 20`.
Lifted into a standalone wire capability test asserting all five signals plus
`severity == "critical"`, and **verified by downgrading the hint and confirming
the new test fails independently of any golden.** Separately, `ACCEPT_SLUG` took
any value and rewrote all twelve goldens; it now validates against the known set.

**`playbook.py` and its test were in 1.00/1.00 lockstep — fixed, and the fix is
smaller than it sounds.** 49 of 53 tests re-encoded the rule table they were
checking, so a wrong rule and a case written from the same understanding agreed
and both went green. The foreign witness is now the `steps` key on every replay
baseline: the dispatch sequence the real orchestrator produced from frozen
bytes, naming no rule and therefore unable to agree with the planner by
construction.

**But measure a witness before calling it coverage.** Probed by deleting rules
from `_RULES`: `cloudflare_403_429_archive` fails the akakce baseline;
`gate_paywall_or_block_archive`, `exhausted_429_escalate` and
`gate_browser_signal` fail nothing. One of four probed, of fourteen. The corpus
produces four distinct dispatch sequences from seven cases because every case
but akakce succeeds on the first tier — **a planner witness needs cases that
fail interestingly.** The gap is recorded in `BACKLOG.md` as a gap. The 49
restating tests were kept, not deleted: they are the readable statement of what
each rule means and they catch a deletion or a typo. The error was ever counting
them as verification, and that is now written in their own docstring.

---
## 2026-08-01 — T2: the response contract was one concept in three files (L, structure — T2 UMBRELLA)

**SHIPPED** as `unify-the-response-contract` (34 of 36 tasks; the two open ones
are named below and are ergonomics, not safety). Closes the T2 umbrella finding
and three it subsumed: *the ADR-0009 floor is derived from the severity of an
English sentence*, *`models.py` is 25% prose and 12% wire projection*, and
*`fetcher_response.py` is 740 lines CLAUDE.md never mentions*.

**The shape of the defect, because it is the one that recurs here.** Five of the
six instances were live behaviour, not tidiness: a relabelled link kind, a
dropped anchor, a dropped handler candidate set, a field that meant two things
depending on which tool you called, and an ADR-0009 floor recovered by
string-matching English prose. Every one came from the same move — **a later
stage re-deriving a decision from the artifact that decision produced.** Reading
a classification back out of a hint's CODE and SEVERITY made the hint's wording
load-bearing for a decision it was never meant to carry: rewording an operator
message could flip whether a fetch reported `retrieval_incomplete`. Fixed by
carrying `TerminalOutcome` on the response path and deleting the three
reconstructions; pinned by
`test_editing_hint_text_does_not_change_classification`.

**Two decisions worth keeping, both of which reversed the design's own lean.**

*The response module stays in `fetcher_response.py`; the directory was wrong.*
The census's "four purposes" were already four labelled bands in one file, with
no second consumer and no import cycle — a directory would have renamed bands to
filenames. Against it: this module's whole interface to the orchestrator is the
42-field `FetchContext` slice, and `decompose-fetcher-into-files` phase two moves
`FetchContext` itself. A boundary drawn before the thing it bounds settles gets
redrawn, and the redraw is what makes a refactor collide with a behaviour change
— the v0.23 failure this change opened by citing. **The directory was the shape;
absorbing the external context reads was the goal, and that shipped.**

*`retrieval_incomplete` stays ONE field with two named phases, not two fields.*
RETRIEVAL (in `build_response`: verdict, terminal classification, unanswered
ask — the only phase `fetch_raw` runs) and COMPREHENSION (in
`build_ask_response`: the extractor's `obstacle`, a witness the fetch ladder
structurally cannot have, since a rendered SPA shell fetches, extracts, and
gates perfectly well). Two fields would have exposed an internal sequencing
detail the caller cannot act on; both phases prescribe the same thing. What the
caller actually needs is that **the answer never gets quieter** — so phase 2 is
SET-ONLY: it starts from phase 1's answer and may only raise it. That is the
ADR-0009 false-positive asymmetry expressed structurally rather than as a
comment, and an extractor that reads a challenge page as ordinary prose cannot
clear a miss the ladder already proved. Pinned by
`test_phase_two_never_clears_phase_one_incompleteness`, swept across every
`obstacle` value *including* both carve-outs — a carve-out that suppresses a
raise must not be readable as licence to clear.

**The TSV question resolved into a guard rather than the refactor it asked for.**
The task said "have both halves consume one declaration". They cannot, and
finding out why was the value: a model-side `encode_rows` branch is **not**
redundant with membership in `_TSV_FIELDS` — it decides *which channel* carries
TSV. Measured: `links`/`next_links`/`other_pages` pre-encode model-side and
reach BOTH `structured_content` and `content[0].text` as TSV;
`operator_hints`/`refinement_axes`/`options`/`content_candidates` reach machine
consumers as JSON arrays and only the agent as TSV. Both intended, neither
pinned — and deleting one `encode_rows` line silently moved a field between them
while the ~1350 field-PRESENCE assertions stayed green, because the field is
present either way, just a different type. Now asserted against both real
envelopes in `test_tsv_declaration_is_single.py`; reversion-verified. Same
lesson as the TSV column-union defect one day earlier: **when the question is
what the agent receives, presence is not the assertion.**

**What stayed open, deliberately.** §2.2/2.3/2.4/2.7's remainder — twelve
factory-less hint codes (measured; the task said seven), ten raw
`OperatorHint(...)` call sites, four string dispatches. The SAFETY half shipped:
`HINT_CODES` is closed and a validator raises on an undeclared code. The rest is
ergonomics over tuned ADR-0009 operator copy, where §2.7 says *"move the strings
verbatim and diff them"* — deferred rather than rushed at the tail of a long
session, after two rushed calls that same day both had to be undone within
hours.

---
## 2026-08-01 — `page-tsv` shipped the encoder defects a2web fixed locally (M, shelf promotion)

**SHIPPED** as shelf `page-tsv-v0.2.0` + `lean-wire-v0.2.0` + `page-tsv-v0.2.1`
(shelf ledger 0075/0076/0077). Kept because three things here are the kind that
recur.

**Routing around a defect is not fixing it.** a2web hit three encoder bugs while
this code was a2kit's `packages/formatter`, filed two upstream as *"no a2web
workaround exists — this must be fixed upstream"*, got no fix, and owned a local
copy. `page-tsv` was promoted out of that same origin code and inherited all
three, so the shelf carried them for ten days after a2web stopped paying. The
sunset design read as though the rejection had settled it.

**The entry's headline claim was false, and the check was cheap.** It said
"affects `a2kay` today". a2kay imports `page_tsv.Page` as a TYPE in three routers
and nothing else — its CLI renders compact JSON explicitly and its own docstring
calls page-tsv routing *"a later enhancement"*. No a2kay path reached the
encoder. Nothing shipped wrong; the urgency was invented. A grep across the
consumer would have said so at any point.

**A fourth defect turned out to matter more than the three.** The TSV header came
from `rows[0]`, deleting every key that row happened to lack. Three separate
callers — a2web's `wire.py`, `page_tsv.render`, `page_tsv.page` — had each
answered `encode_tsv`'s "what are the columns?" and all three answered `rows[0]`.
That is rule-of-three on a *defect* rather than a shape, and the right fix was to
stop asking: `lean_wire.derive_columns`, since the encoder is the only party that
sees every row at once. **When N callers implement the same helper wrong the same
way, the signature is the bug.**

**And the gate that declared it all green was not running it.** Found only
because six new `lean-wire` tests did not move the root collection count: the
shelf's `testpaths` is hand-maintained and pytest is silent about a package
absent from it, so 8 of 26 package suites (174 tests, including `a2effect`'s 12
files and `page-tsv` itself) ran in no gate at all. All 174 passed — the loss was
that nothing would have said otherwise, over a third of the tree. Fixed and
guarded in both directions; the shelf gate went 472 → 649 tests, its coverage
base 2610 → 3544 statements. **Same shape as this repo's `tach.toml` finding: a
hand-maintained list of what to check, where a missing entry means no contract
rather than a failure.** Two instances now; a third would make it a pattern
worth a general answer.

---
## 2026-07-27 — strip ambient LLM availability from the whole test suite (S, CI correctness)

Source: the v0.48.0 release build, which failed the gate on a bare runner after
passing locally. Three releases have now died to the same class: the suite reads
whether the DEVELOPER'S MACHINE has an LLM (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
a live Claude Code session), so a test can be green on a laptop and red in CI with
no code difference. 0.47.0/0.47.1 died on provider-selection tests; 0.48.0 died on
`tests/contracts/test_cli_contract.py`, where the `Extractor.extract` stub is only
reached once `select_provider` returned something, so the `web query` goldens
silently degraded to `llm_unavailable` payloads. Each was fixed one test at a time;
none of the fixes made the next one impossible.

The structural fix is an autouse `conftest.py` fixture that strips the credential
env vars and forces `claude-code-sdk` unavailable for EVERY test, with an explicit
opt-in marker (e.g. `@pytest.mark.ambient_llm`) for the few that genuinely want the
host's providers. Then "green because my laptop has a session" stops being
writable, and the laptop and the runner are the same environment by construction.
Lint cannot catch this class (both states are type-correct and style-clean) and a
green local run cannot either, which is why it needs a fixture rather than a rule.
Scope: S.

Trigger: pick up before the next release, or immediately if a fourth release build
fails on provider availability.

**CLOSED 2026-08-01** by `openspec/changes/harden-test-env-isolation/`.
`tests/conftest.py::_hermetic_llm_env` is the autouse fixture; the `ambient_llm`
marker is the opt-out and is exercised by a test rather than merely registered;
`tests/architecture/test_hermetic_llm_env.py` is the guard, verified sensitive in
both directions (dropping one name fails and NAMES it; renaming the fixture fails).

**The measured surprise, recorded because it changes how the entry reads.** The
credential-stripped suite was ALREADY green when this was picked up — 1441
passed, identical to the keyed run, with the strip verified non-vacuous
(`ClaudeCodeSdkAdapter().available()` goes True → False under it). So the fixture
revealed nothing and fixed no test. The suite had been patched to hermeticity one
release at a time, exactly as this entry describes, and the property held only for
as long as nobody wrote the next host-reading test. What shipped converts a
property the suite had BY ACCIDENT into one it has by construction. An entry that
had been read as "N tests are broken" was really "nothing is broken today and
nothing stops it breaking tomorrow" — worth distinguishing, because the first
framing makes the work look urgent and the second makes it look skippable, and
neither is right.

---

## 2026-08-01 — `lift-the-item-set-and-renderer` (§1-§3, §5-§7; §4 deferred)

The ADR-0015 JSON-LD index hole, one onward-link cap, truncation declared at
three handlers, and the 381-line renderer lifted to
`packages/structured_render.py` with its three divergences resolved in the move.
`domain.py` 602 -> 149 lines and its docstring finally true.

Kept for the incidents, which the surviving guards exist to prevent:

- **`handler_probe.py` recorded a contract violation as health.** Discourse
  emitted 50 onward links against a stated cap of 10, and the probe baseline
  read `min_candidates=10, # observed 30` — the one mechanism positioned to
  catch it certified it instead. A baseline that records an out-of-contract
  observation as the expected one reads as a decision.
- **The Recipe allowlist dropped `recipeInstructions`.** a2web served a
  recipe's ingredients and silently dropped how to cook them, while
  `_single_entity_md`'s docstring thirty lines below argued that an allowlist
  "silently loses an unanticipated answer-bearing field".
- **A cap was written six times** for one spec invariant, which is why the
  sixth could say 50 and nobody noticed.
- **Two rushed calls had to be undone within hours**, both in this change:
  overriding a documented deferral (`hn` `nbHits`) without re-checking its
  reasoning, which shipped a FALSE partial-view note on a complete listing; and
  adding a `reddit` note that was structurally unreachable — the very defect
  being fixed in `hn` in the same commit. A deferral that carries its reasoning
  is evidence, not an obstacle.

§4 (converge the item set) is open in `BACKLOG.md` with its blocker recorded:
each handler's `reason` carries site-specific signal the shared derivation would
flatten to a constant, and D2 rejects the polymorphic answer.

## 2026-08-01 — the `options` shelf is capped by count, not by bytes (S, token cost)

Source: `eval/findings_2026-08-01.md` §3, run `eval/runs/2026-08-01_011025/`.

`_OPTIONS_CAP = 50` in `fetcher_response.py` bounds how many options reach the
wire and nothing bounds the size of each. Per-option `detail` is untruncated, so
on `arxiv-listing-partial` the shelf is 50 × ~350 chars = 17KB — against 819
bytes of `other_pages` and 255 bytes of `answer`. Measured envelope cost on that
cell went 460 → 4730 tokens, and on `listing-answer-always-leaves-an-index`
546 → 5007. Those two cells are ~90% of the mean `a2web_extract` envelope
increase (475 → 731 over the 38 slugs common to the 07-28 run).

The trigger was `24c1a01` (JSON-LD → `RecordSet`), which correctly fills the
shelf on pages that previously shipped no index at all — the ADR-0015 hole it
was written to close. The direction is right; the budget is missing.

Why it matters rather than being mere bloat: `query` withholds the page body by
default *for token economy*, and ADR-0015 requires an index of what was withheld.
A shelf that re-emits most of the body is the remedy defeating its own premise.
The shelf is an index, not a second copy.

Fix: a byte budget alongside the count, and truncate `detail`. Needs a decision
on which bound wins when they disagree (fewer full options vs more thin ones) —
probably more-thin, since the shelf's job is *coverage* of what was skipped.

**CLOSED 2026-08-01** by `_OPTIONS_DETAIL_BUDGET` (4000 chars) + `_OPTION_DETAIL_FLOOR` (60), applied as an adaptive per-option cap in `_records_to_options`. The trade was resolved toward COVERAGE — thin every entry rather than drop entries — because a dropped option is invisible to a caller that never saw the body while a shorter `detail` is visibly shorter. Witness: `tests/capabilities/link_affordances/test_option_shelf_byte_budget.py`; verified by reversion at 11,250 chars.

## SHIPPED 2026-07-31 — five wire-level ADR-0009 leaks (was: T3 + T7 live defects)

**Closed by `openspec/changes/close-wire-level-adr-0009-leaks/`, commits
`e02a142`, `ca2d9b8`, `1395f8d`, `bddb33b`, `ed2d448`.**

Five independent leaks sharing one failure shape: **a2web knew more than it told
the caller, and what it told read as success.** Each closed with a witness that
was verified to fail when its fix is reverted — a green suite is not the same
claim.

**1. TSV columns came from the first row.** `_derive_columns` read `rows[0]`
while `OperatorHint._omit_default_severity` elides `severity` at its default.
So an `info` hint followed by a `critical` one produced a table with NO
`severity` column and the critical marker was discarded — on
`try_user_browser`, ADR-0009's loudest signal. Reachable in production: a stale
cookie mirror plus a walled page.

Two things worth keeping. `structured_content` was never affected, so the
~1350 field-presence assertions could not see it; **they all read `call_wire`
and the agent reads `content[0].text`.** And the wire golden that covers the
walled path did not move: `query_failure` carries exactly ONE hint, the
critical one, so the first row held every key. The golden froze a correct table
for the wrong reason and was blind to the defect by construction — the
`query_heterogeneous_hints` capture exists so that is no longer true.

**2. `github.py` laundered degradation into `ok`.** Six sites swallowed a
`GitHubException` from a supplementary call and rendered the section empty, so
a rate-limited comments fetch and an issue with zero comments were
byte-identical. Fixed by keeping three outcomes distinct rather than two
(retrieved-with-rows / retrieved-and-empty / NOT retrieved). A seventh site had
the OPPOSITE bug — the README guard caught only `BadRequest` where four
siblings catch `GitHubException`, so a rate-limited README aborted the whole
repo fetch.

**3. `_fetch_old_reddit` returned `ok` for an interstitial.** Same shape as its
two siblings (GET HTML → trafilatura → prose), but it never ran
`challenge_verdict`, and a challenge page extracts perfectly well.

The captures showed **the call alone would not have fixed it**: the catalogue
already carried `whoa there, pardner`, but only below `LENGTH_FLOOR`, and the
real block page extracts to 779 characters. A marker gated on thinness is inert
against a wordier interstitial from the same family — which the catalogue's own
comment had stated as a known limit. Now length-independent, on the test that
justifies matching turnstile/akamai at any length.

**4. `paid_auth_error` had no hint, and three places said it did.**
`fetcher_response` seeded `retrieval_incomplete` *because* the verdict "keeps
its OWN dedicated hint"; `_apply_terminal`'s docstring agreed; and the
coherence guard allowlisted `operator_error` to `frozenset({None})` citing a
hint "emitted at the paid tier". None existed. The guard was green because it
had been told to expect nothing on the strength of a claim nobody checked, and
would have stayed green through the hint's deletion.

**5. The `a2effect` taxonomy was unreachable.** `except AppError` in
`guard_tool` never fired — a2web raised none of the five types, so a missing
LLM credential and a null deref rendered identically as `UnexpectedDefect`.
`LLMNotAvailable` → `AuthError`, `ResourceUnavailable` →
`InfrastructureError`, both keeping `RuntimeError` in their bases so existing
`except` sites still catch them. The change named a third site that turned out
not to exist: the paid tiers return a `Verdict` and contain no `raise` at all.

**What this cost, and the general lesson.** Four of the five were invisible to a
green suite for a structural reason, not an oversight: a test of a GOOD page
passes with or without a wall check; a machine-channel assertion cannot see an
agent-channel defect; and a guard told to expect nothing reports success for
finding nothing. Two new guards close the classes
(`test_handler_challenge_check.py`, and the coherence table's allowlist
converted to an assertion). The handler guard's own non-vacuity floor caught its
first draft matching six false positives.

---
## SHIPPED 2026-07-31 — there is no CI on push or PR (was: READ FIRST, T4)

**Closed by `openspec/changes/run-the-gate-on-every-push/`, commit `5fa4a19`.**

`.github/workflows/` contained exactly one file, `release.yml`, triggered on
`v*` tags. So `make check` — lint, types, the full suite, coverage >=85%, and
**every architecture guard** — ran when someone cut a release and at no other
time. Between tags a violation landed and stayed landed, to be discovered in a
batch and attributed to whoever tagged.

This reframed the whole T4 track: goldens, endogenous fixtures and missing wire
witnesses were all weaker than they read, because the gate they hang from did
not fire. It is why the track said fix this before investing in any individual
guard.

**What shipped.** The gate moved into a reusable workflow (`gate.yml`) called by
both a new `ci.yml` (push + PR, all branches) and `release.yml`, so there is one
definition and it cannot drift. Release keeps its own independent run — a tag
can point at any commit and that path publishes a public image.

**Two results worth keeping.**

1. **The baseline was GREEN.** `make check` at `469ca5c`: 1274 passed, 90.96%
   coverage, tach 69/69. The change's own design predicted the first run might
   be red and said to fix rather than weaken. It wasn't — nothing had rotted
   between tags. Recorded as a negative result: the gate's absence had not yet
   cost a landed violation, so this was prevention, not cleanup.
2. **The gate was proven by making it fail.** A deliberate `json.loads` funnel
   violation pushed to a scratch branch turned CI red in 1m30s, failing at
   `test_no_json_loads_outside_wobble` — the right guard, not an incidental
   error — and was then reverted. A CI workflow that has never failed is not
   known to work; this one now has.

**Also closed here:** the `a2kit-rego` pre-commit hook, which had been failing
to spawn since a2kit's retirement on 2026-07-22 — nine days reading as
architectural policy enforcement while enforcing nothing. See the surviving
Rego re-homing entry in `BACKLOG.md`, which now records that its stand-in was
dead, and note the shape: the loss was recorded in three places and the dead
hook survived every one of those readings.

**What is NOT closed.** Branch protection is a GitHub repository setting, not a
file. CI reports red; it does not block a merge, and `fb:no-prs` means there is
often no PR to block. CLAUDE.md's new "Enforcement — what actually blocks"
table states that plainly, per mechanism. The browser gate remains release-only
and is documented as not guarding a push.

---
## SUPERSEDED 2026-07-31 — 21 behavioural rules live only as prompt English (L, structure)

> **Superseded the same day by *45 of 86 prompt rules have neither code nor
> test*.** The count here was a subset — it counted only the
> `_ROUTER_SCHEMA_DOC` field-description clauses, not the full 5-template
> census. Kept for the reasoning, not the number. Do not action from this text.

**Source:** prompt-rule scan, 2026-07-31. ~34 rules: 8 enforced, 5 witnessed,
21 prompt-only, 3 contradictions, 2 undocumented code rules.

Structural caveat on every "witnessed" claim below: `tests/_helpers/llm_doubles.honor_contract`
SYNTHESIZES a compliant envelope whenever the router contract is detected, so
every `query` capability test and every wire golden asserts a hand-made
envelope. Those are fixture assertions, not rule witnesses.

**Worst — ADR-0014 is enforced only on the path that rarely runs.** The prompt
says twice "NEVER type a raw URL". `extractor.py:~576` accepts `item["url"]` —
any non-empty string — when there is no handle; `fetcher.py:2405` passes it
through unvalidated; and `test_rehydration_seam.py::test_legacy_url_entry_passes_through`
**asserts that `https://x.example/` reaches the wire**. Grounding holds only on
the digest path, and the digest is built only when a `json_synth`/`record_synth`
candidate exists (`fetcher.py:2358`) — so on every article/reference/thread/
tutorial page the only URL channel open to the model is the unvalidated one.
`_validate_llm_next_links_against_markdown`, the one real on-page check, is
UNREACHABLE from `query` (`extractor.extract` appends it only
`if request_next_links and not request_routing`; `query` always sets routing) —
it guards `fetch_raw` only. Inline URLs in the answer prose are never checked at
all: `rehydrate_text` substitutes `{{n}}` and nothing else.

Other prompt-only rules, by harm: `refinement_axes` "never name a specific value"
(ADR-0012 in a second costume — two free strings, unchecked); `item_total_seen`
"the total the PAGE advertises" (drives wire state, only the type is checked; and
the prompt scopes it to listings while the code gates on `record_count`);
off-domain justification discipline (the flag is computed, the gate is not — this
is the prompt-injection surface, anchor labels being attacker-controlled); the
entire `also_here` query grammar (~10 lines, zero enforcement — and the exact
under-firing regression that motivated v0.25 is invisible to `make check`
because `_index_loss_hint` is gated on the routing ARM); `other_pages.reason`
≤120 chars (never measured, never truncated); evidence-scoped absence ("NEVER
assert it does not exist at all" — a confident false negative shipping
`status: ok`); "never drop a factual value" (the safety clause on terseness);
the WebFetch copyright guardrails.

**Contradictions:** (C1) prompt says "put that continuation FIRST",
`_compose_other_pages` reorders every model drilldown behind every DOM link;
(C2) `_NEXT_LINKS_CAP = 10` is never stated in the prompt and applies AFTER C1's
reorder, so on a handler page with 10 structural links every model drilldown is
silently dropped — no wobble, no hint, no diagnostic; (C3) `item_total_seen`
scope, above.

**Undocumented code rules punishing the model:** `strip_fenced_blocks(json_only=True)`
deletes any fence opening `[`/`{` from the answer — on a `code`-shaped page an
answer correctly quoting JSON is silently gutted, and `also_here` will not
mention it because the model believes it answered. And `obstacle` has expensive
side effects the prompt never mentions: `confidence` forced low,
`retrieval_incomplete` set, a critical hint, and a PAID render dispatch.

**The guard to write first (~15 lines):** there is no test that the prompt's
closed-VALUE lists match the `Literal`s in `models.py`. `test_wobble_policies_match_prompts.py`
checks field NAMES and required/optional only — and is otherwise the one
genuinely good prompt↔code guard in the repo (vacuity floor, can-this-fail case;
use it as the template). Add one `structural_form` value to the prompt without
touching `models.py` and `_project_routing` returns `None` for every page so
classified, losing all seven router fields. Silent but for an `llm_wobble` log.

---

## SUPERSEDED 2026-07-28 — regex-over-markup OUTSIDE `handlers/` (S, correctness — SCOPED)

> **Superseded by *the markup-funnel guard misses `re.search`/`re.sub`*
> (2026-07-31).** That entry has the wider measurement: the guard matches only
> `ast.Call` with `func.attr == "compile"`, so the census this entry scoped
> itself against was incomplete. Do not action from this text.

**Source:** `handler-parses-nothing-is-not-success`, task 7.1.

The proposal left this as "of ten files calling `re.compile`, an unknown
subset". An AST spike over `src/a2web` (excluding `handlers/`, which
`test_handler_markup_funnel.py` now guards) narrowed it to THREE real sites out
of ten matches:

| site | what it does | risk |
|---|---|---|
| `listing_oracle.py:_REL_NEXT_RE` | `rel=next` pagination affordance | VERIFIED ALIVE — fires on HN + discourse, quiet on a plain article. Quote- and attribute-order-tolerant, unlike the two that died. |
| `tiers/archive.py` ×2 | strips the Wayback toolbar | if it rots, the toolbar LEAKS INTO content — visibly wrong, not a silent zero |
| `packages/block_detector.py` ×6 | fingerprints + a tag-stripper for visible-text length | OUT OF SCOPE: these are markers, not parsers. A DOM parse does not make a fingerprint catalogue better. |

`packages/llm_extract/extractor.py:384` matches a fenced code block in LLM
output, not markup — out of scope.

So the remaining exposure is small and NONE of it is the silent-zero shape that
motivated the guard. Worth converting the archive toolbar strip when that file
is next touched; not worth its own change.

The spike DID find a live defect, fixed separately: the oracle's noun list had
no "entries", so arXiv's "Total of 445 entries" read as no total at all.

## RESOLVED 2026-07-30 — a2web reported a 50-of-445 listing as complete (M, correctness)

**Source:** full-corpus bench run, `eval/findings_2026-07-28-full.md`.
Supersedes the earlier "`record_mine` returns None on `<dl>/<dt>/<dd>`" entry,
which was filed as a speculative shelf-promotion candidate and turns out to be
the CAUSE of a live silent miss.

On `arxiv-listing-partial` a2web scored **1 and 2 against WebFetch's 5** — the
worst cell in the run — answering:

> "The page header states '## Papers (25)', indicating 25 total papers. You are
> seeing all 25 on this page — no truncation notice or pagination control."

The page says "Total of 445 entries" and renders 50 behind 9 pagination links.

Verified chain (measured, not inferred):

    handler pre-renders "## Papers (25)" — no total, no pagination
      -> extract_records(html) returns None on the <dl>/<dt>/<dd> shape
      -> fc.record_count stays None
      -> _maybe_flag_partial_listing() returns at its first line
      -> listing_oracle() IS NEVER CALLED, no listing_partial hint
      -> the model answers from "Papers (25)"

**Two independent fixes. BOTH DONE.**

1. **DONE 2026-07-30 — shelf `record-mine-v0.2.0`**, adopted. A `<dl>` of
   `<dt>`/`<dd>` pairs is now a record region: both signature guards were blind
   to it (classless -> guard (a); no `h1`-`h6` -> guard (c)), and both guards are
   proxies for "this element is a record" that a `<dl>` states outright by
   specification. Additive fallback, so no page that already yielded a region
   changed. Live: `items_loaded=50 items_total=450` + the `listing_partial` hint,
   where nothing fired before. Pinned a2web-side by
   `test_definition_list_listing_yields_records_for_the_sufficiency_axis` so a
   tag downgrade cannot silently switch the axis back off.

   Does NOT contradict shelf ledger 0071, which rejected an EVOLVE of this
   package: that tested an optional CONTAINER HINT and rightly found it useless
   (location was never the problem). This is the semantics axis. See ledger 0073.

   **The wider blast radius is now a benefit, not a risk** — `record_count is
   None` disabled the sufficiency axis for ANY shape the detector missed, so
   recovering a shape switches it on for a population, not one page. Other
   missed shapes remain possible; arXiv is the one that was measured.
2. **DONE 2026-07-28** — the arXiv handler now carries the page's stated total
   into its rendered markdown (`## Papers (25 of 445)` plus an explicit
   partial-view line), sourced from `listing_oracle` rather than a new regex
   (the markup-funnel guard bars regexes in `handlers/`). Re-benched on the
   single slug: quality 1 -> 5 and 2 -> 5, clarity 5, both a2web systems now
   level with WebFetch. Pinned by
   `test_arxiv_listing_renders_the_pages_own_stated_total`.

   With (1) now also done, this page carries BOTH: the prose answer and the
   machine-readable `listing_partial` hint.

**Caveat worth carrying forward, not a defect:** `record_mine`'s `_MAX_RECORDS`
cap is 50 and arXiv renders 50 per page, so `items_loaded=50` is exact here by
coincidence. On a listing rendering MORE than 50 records, `items_loaded` is the
cap rather than the true rendered count, and the reported shortfall would be
larger than reality. The signal's DIRECTION is always right (there is more);
its precision is bounded by that cap. Do not quote `items_loaded` as an exact
rendered count without checking it against the cap.

Note for whoever picks this up: adding "entries" to `listing_oracle`'s noun list
(shipped 2026-07-28, `91a7377`) is correct and verified live, but does NOT close
this — the gate above it closes first. Do not mark this done by pointing at that
commit.

## 2026-07-16 — empty-result-as-`ok`-answer (thin-not-wall endgame) — SHIPPED

Shipped by openspec change `empty-vs-wall-discrimination` (2026-07-16). A
corroborated empty is now promoted to an `ok` "no results" answer via the pure
`is_confirmed_empty` conjunction: an empty-result marker + an independent BROWSER
render that also read empty (the browser is the second retrieval a thin 200 gets —
it wins the tier loop so jina never runs) + no 4xx/challenge/subresource-block/
hard-wall evidence anywhere + a search-shaped URL. The walled-API fake-empty is
caught by the new browser `subresource_blocks` observation (a blocked data XHR →
`wall`, the case no text reader can catch). Anything short of the conjunction stays
a loud thin miss (`empty_unverified` / `thin_unverified`, body attached). The
promoted empty is wire-only and never cached.

- **Residual (watch, do not chase).** An IP-reputation wall that fake-empties our
  HTTP AND browser egress identically is not ruled out (foreign-egress jina would,
  but the pipeline can't run it on a thin 200). Narrow; the attached `thin_content`
  is the mitigation. Also: consent/GDPR interstitials render thin with benign text
  matching neither catalogue and stay `thin_unverified` (correct — content behind
  consent). Watch bench runs for either becoming a real cost/accuracy line.

## ~~Wire-visible signal for a lost router payload~~ — SHIPPED 2026-07-27

Closed by `fix-extraction-signal-fidelity`. `routing_lost` is deleted and
replaced by a typed `RoutingOutcome`; the ADR-0015 gap is closed by an
`index_lost` warning hint gated on the DELIVERED index being empty.

Kept as a marker because the entry was wrong twice in opposite directions, and
the reason is worth more than the entry was. First it recorded "fires on every
query — permanent noise", measured against `_StubProvider`, which did
`del system, user` and returned prose whatever contract it was handed. Then it
recorded that a deliberate envelope decision was all that remained. The real
answer, once the fixture was fixed: the hint moved **zero** goldens, where the
abandoned attempt moved six. The entire difference was the test double.

Generalized lesson, and the reason this is not simply deleted: a test double that
ignores its input is not a witness, and a golden captured through one freezes the
lie rather than the contract. Now enforced by
`tests/architecture/test_llm_double_fidelity.py`.

## ~~The `surface_eval_v2` leak detector is vacuous by default~~ — SUPERSEDED 2026-07-27

Two corrections to the entry this replaces. First, it overstated the problem:
the six generic phrasing patterns (`"based on your"`, `"your interests"`) always
run; only the identity half is env-gated, so the check was weakened, not
disabled. Second, and larger — **the file cannot import at all.** It is one of
the 15 dead spikes found below, so the banner fix drafted for it would have been
cosmetic work on a corpse.

Closed by marking the script `# SPIKE-ARCHIVED:`. If it is ever revived, the
identity half needs the banner: an unconfigured run must not print a leak count
that reads as "no identity leaks" when that half never ran.

## ~~The OPTIONAL/DEFAULT triage is coupled to prompt wording, unguarded~~ — SHIPPED 2026-07-27

`tests/architecture/test_wobble_policies_match_prompts.py` parses the
`(required|optional` markers out of `_ROUTER_SCHEMA_DOC` and compares them
against `EXTRACTOR_ROUTING_POLICY`: field sets must match exactly (catching a
renamed prompt field), `(optional)` must map to `OPTIONAL`, `(required)` to
`STRICT` or `DEFAULT`.

Verified red before green, against three injected drifts: a required field
reclassified `OPTIONAL`, a policy key deleted, and a reformatted prompt that
defeats the regex (caught by the vacuity floor, not by silently governing zero
fields). The bench-judge tables are deliberately out of scope — their prompts
have no marker syntax, and inventing one to satisfy the guard would be writing
the oracle to fit the test.

## M3 / M4 / M7 — CLOSED 2026-07-28 by `close-silent-eval-loss`

Axes now carry a closed `AxisDisposition` (scored / not_applicable / unscored
with a reason); every reported statistic renders its denominator; an axis
requested on ≥1 cell and scored on 0 exits non-zero after artifacts are written;
`--no-extraction-cache` gives genuinely independent observations and the
manifest records the mode. Root cause of the dead axis was the ADR-0015
`next_links`→`other_pages` fold; `_CANDIDATE_FIELD` is now a literal per-system
table. Evidence: `eval/findings_2026-07-28.md`.

Still open from that section: M1, M2, M5, M6, M8, and hypotheses H1/H3/H4/H5.

### NEW — `other_pages` is mechanically impossible outside the raw tier (L, ROOT CAUSE)

*(Third and final diagnosis of this case. The first two — "corroborates the
wikipedia finding" and "the deferral chain bottoms out" — were both wrong. They
were readings of prompt text; this is a traceable code path, verified by probe
`scratchpad/probe_arxiv.py` plus the call chain below.)*

```
tier ∈ {browser, jina, zyte, firecrawl, archive} or ANY of the 9 site handlers
  → TierResult.pre_rendered = Rendered(content_md, title, byline, headings)
                                         ↑ dataclass has NO links field
  → fetcher._phase_extract copies those four and RETURNS  (fetcher.py:1270-1276)
  → fetcher.py:1318  `fc.links = extract_result.links`    NEVER RUNS
  → fc.links == []
  → _build_link_digest: `if not fc.links: return None`    (fetcher.py:2317)
  → no '## page links' block reaches the prompt
  → prompt: "If no '## page links' list is present, OMIT other_pages"
  → other_pages CANNOT be emitted. Not "is not" — cannot.
```

Only the `raw` tier runs trafilatura, and trafilatura is the sole producer of
`fc.links`. Every other retrieval path silently loses the page's anchors.

**One mechanism explains both failing eval cells**: `listing-answer-always-leaves-an-index`
(arXiv, browser tier) and `reddit-listing` (zyte tier). No coincidence needed.

Scope beyond those two: this affects **every** browser/handler/archive-served
page, which is the entire hard-fetch population — precisely the pages where a
caller most needs pointers. ADR-0014's handle-rehydration machinery is intact and
correct; it just never receives a digest to rehydrate from.

Probe evidence (`arxiv.org/list/cs.CL/recent`, browser tier, `include_links=True`):
50 arXiv ids in `content_md`, **0 links, 0 headings**, on a page that is nothing
but anchors.

Second, narrower gate worth reviewing at the same time: `_build_link_digest` also
requires a `json_synth`/`record_synth` candidate (`_DIGEST_GATE_SOURCES`), so even
on the raw tier a prose-shaped listing gets no digest. That one looks deliberate
("prose-only articles skip it and pay nothing") — the pre-rendered gap does not.

*Open:* whether `Rendered` should carry links, or whether the pre-rendered path
should run link extraction over the source HTML separately. That is a design call
for the change that fixes this, not a foregone conclusion.

NOT fixed here — orthogonal to the P1→P5 measurement chain, and now the
best-evidenced product change on the board.

### NEW — next_links quality is unmeasured-until-now, and mediocre (M)

Mean 3.17 over 6 scored cells per system; `pypi-httpx` 1–2, `gh-trending` 2.
**First observation ever on this axis** — no prior number exists, so this is a
baseline, not a regression. `gh-trending-best` scoring 5 on `a2web_detail` and 2
on `a2web_extract` for the same page is the sharpest single cell, since the
systems differ only in envelope shape. Worth one targeted look before reading
anything into the mean.


## RESOLVED — the digest gate blocks every pre-rendered page (2026-07-28)

Resolved, and the answer was neither option posed. The gate (`_DIGEST_GATE_SOURCES`)
was never the defect: it requires a structured candidate as a pre-LLM proxy for
product/listing shape, which is exactly what `link-affordances` requires so prose
articles pay no digest cost. The defect was that `_phase_extract`'s pre-rendered
early return skipped the structured ladder that PRODUCES those candidates —
`json_in_html` + `record_mine`, neither of which is the trafilatura pass the
`pre_rendered` optimisation exists to avoid. Fixed in
`narrow-the-pre-rendered-extraction-skip`. Do not reopen the gate.

## 2026-08-01 — `bound-every-unbounded-path` (§1–§4)

**Three unbounded waits and one unbounded recursion, all closed at a single seam
each.** The recurring lesson across all four: a bound that has to be
re-implemented at N sites is the bound that will be missing from the N+1th.

- **`hn.py` recursed on untrusted remote input with no cap.** Reproduced as
  `RecursionError` at depth 5000. Two shapes — plain nesting, and a chain of
  DELETED comments that recurses with `depth` unchanged and so defeats a depth
  cap entirely. `habr` and `discourse` had `_MAX_DEPTH` all along, which made
  this drift rather than a design gap. The change's task list said to fix the
  deleted path by advancing `depth`; that would re-indent every existing thread
  containing a deleted comment, so the shared comment budget bounds it instead
  with no rendering change. **The architecture guard's own first draft was
  vacuous** — it matched the substring `budget` anywhere in the function,
  including the parameter name, and stayed green with the bound deleted. Caught
  only by running the fix-reverted check against the guard, not just the
  witnesses.
- **No LLM timeout.** `anyllm` has no per-request bound, so a provider that
  never returns hung the fetch forever — the tool call never completes and the
  caller has nothing to act on, which is worse than a loud failure. Bounded by
  wrapping the PROVIDER at `select_provider`, covering all five `complete()`
  call sites and any added later. `LLMTimeout` subclasses `AnyLLMError` so it
  rides the existing degrade seam and keeps `packages/llm_extract/` free of a
  domain import. Filed as a shelf promotion under T7 — every anyllm consumer
  has this hole.
- **No per-fetch deadline.** Hops were bounded; their SUM was not. Default
  DERIVED (407s measured worst-case walk → 480s), not guessed, with the
  measurement recorded at the setting. Enforced at the dispatch site by
  `_within_budget`, checked BEFORE a hop starts rather than cancelling one
  mid-flight — a running hop has already paid its network cost. Expiry takes
  the ADR-0009 terminal path, and the hint says a2web ran out of budget, never
  that the site is slow.
- **Request bounds were frozen constants.** 14 of them, unreachable by any
  operator. Now a SCALE (`request_timeout_scale`), not 14 overrides and not one
  flat value: those numbers are individually tuned and their ratios carry the
  meaning — a paid render legitimately needs 6x an nitter probe. The guard
  immediately caught a github class-attribute default that would have silently
  ignored the setting; removed rather than allowlisted.

Two first-draft defects of my own, both caught by guards already in the suite
rather than by review: wrapping the provider unconditionally produced a truthy
`TimeoutProvider(inner=None)` that destroyed the `no provider → None` contract
the whole `ResourceUnavailable` seam rests on, and the new LLM doubles did not
declare `DOUBLES_ARM`.

## 2026-08-01 — `fix-cache-ttl-and-listing-sufficiency` (§1–§3, §4 partial)

- **`_ttl_for` cached almost everything for 7 days.** It read only the content
  type — `html` → 24h, everything else → 168h. Handlers serve upstream APIs, so
  every handler-served discussion thread, issue list and listing returned
  `application/json` or `application/atom+xml` and took the static TTL: the
  freshest surfaces in the product were held the longest. Fixed by having the
  PRODUCER declare (`TierResult.volatility`), with the heuristic surviving as
  the fallback for the generic HTTP tiers, which genuinely know no better. The
  content type cannot decide this — `application/json` from the GitHub issues
  API is a live discussion, the same header from a CDN may be a static asset.
- **`cache_ttl_live_m` was declared and read by nothing.** Not a duplicate of
  `is_live_only` (that BYPASSES the cache; this is a 5-minute TTL), so it was
  wired up rather than deleted — it turned out to be exactly the short TTL the
  volatility fix needed. Now guarded: `test_ttl_settings_are_read.py` fails on
  any declared TTL setting no code path reads. A dead setting is worse than a
  missing one — a missing one fails visibly, a dead one silently reports success.
- **`_ttl_for` masked a settings rename.** `getattr(settings_obj, "cache_ttl_article_h", 24)`
  duplicated every default and would have kept serving the literal through a
  rename. Now typed `AppSettings` with direct attribute access, pinned by an AST
  assertion that no defaulted `getattr` returns.
- **Listing sufficiency never ran on the handler path.** The check reads
  `record_count`, which only the DOM record-miner set — so a handler that
  renders its own listing (arXiv's "Showing 25 of 408") produced no record set,
  the phase returned at its first line, and the prose declared the view partial
  while the wire carried nothing. Both numbers were already computed for that
  sentence and discarded. Handlers now declare them and a prose/wire agreement
  test pins the two together.

**A witness caught itself being useless.** The first four listing tests called
`_phase_listing_completeness` with `record_count` already set, so the whole file
stayed GREEN with the wiring reverted — they proved the phase works given an
input, never that anything supplies it, which is precisely the defect. Found by
running the fix-reverted check; a fifth test now drives the real install.

**Left open, deliberately:** 4.7 (other listing handlers) — only arXiv holds an
advertised total; discourse/v2ex compute none, reddit's is a comment count
already wired, and HN's `nbHits` semantics are unverified, so declaring it risks
a FALSE `listing_partial`, which teaches callers to ignore the signal. Needs a
captured HN fixture. 5.3 (bench re-run) — live-network and spends LLM quota.

## 2026-08-01 — `close-guards-that-read-green` (§1-§3, §5.4-5.5, §7-§8)

Guards and citations that reported coverage they did not have.

- **The markup funnel matched only `re.compile`.** The rule said "never a
  regex"; the enforcement said "never a COMPILED regex", so a one-shot
  `re.search` over markup passed through. `reddit._atom_body_markdown` was
  parsing HTML with `re.sub` + `re.search` under a green build, and its own
  comment conceded the assumption it broke on. Replaced with a DOM after
  demonstrating the failing shape (a sibling `<div>` after the body makes the
  greedy match swallow site chrome into the author's words).
- **A guard named for a claim it never made.** `test_packages_boundary_frozen.py`
  was cited twice for freezing `__all__`, which it has never checked. Renamed;
  `__all__` recorded as unguarded.
- **A guard with zero adopters.** `test_transient_markers_not_stale` policed a
  marker convention with no instances anywhere in the tree. Retired.
- **Citations that do not resolve**, including two to a test that does not
  exist inside the document codifying the foreign-provenance rule — and that
  document's closing recommendation reasoned FROM that test's existence. The
  recommendation is re-derived in place; the self-failure is recorded in the
  document, not only in the fix.
- **A registry listing 10 of 34 guards**, because the "adding a rule" workflow
  had no step to register one. Filled, and completeness mechanized in both
  directions.
- **The ADR-0009 wire signals**: three of five asserted, severity asserted by
  nothing — the exact field the TSV column-union bug stripped. Lifted into a
  standalone test outside the golden mechanism.
- **`A2WEB_ACCEPT_WIRE_DELTA` accepted any truthy value**, so `=1` silently
  re-blessed all 12 goldens and recorded "1" as the justification.
- **`pytest-archon` was a dependency imported by nothing**, while its name stood
  in for the enforcement that actually existed as plain pytest + `ast`.
- **`firecrawl._TIMEOUT_S`** kept the value AND the comment that a measurement
  on its sibling (`zyte`, `2bf60ca`) had falsified.
- **Four capped renderers dropped their tails silently** (`hn`, `v2ex`,
  `discourse`, `habr`), each holding the total and discarding it — ADR-0009 on
  the sufficiency axis. arXiv's `N of M` declaration ported via one shared helper.

**The guard I wrote to catch stale citations was itself reading my machine.** It
passed locally and failed CI, because my working tree had `eval/runs/` (gitignored
bench output) and a `__pycache__` under a manifest surface with no tracked files.
CI was the foreign witness. It exposed a real finding in passing:
`_manifests/llm_providers/` has no tracked files at all — CLAUDE.md listed it as
a current plugin surface, naming plugins whose spellings were themselves retired.

Open, with reasons, in `BACKLOG.md`: §4 (playbook foreign witness), §5.1-5.3
(constants needing captured fixtures), §6 (corpus/bench).

---

## 2026-08-03 — the test suite writes to the developer's REAL cache (M, test hermeticity)

**The finding.** `tests/conftest.py` scrubs every `A2WEB_*` env var before the
first a2web import, deliberately, so a developer's real keys cannot register
paid tiers. That scrub also removes `A2WEB_CACHE_DIR`, and `cache.cache_dir()`
then falls back to `~/.a2web`. Exactly five test files set it back via a
per-file `monkeypatch` fixture; **every other cache-touching test writes into
the developer's own `cache.sqlite`.**

Observed on a dev machine 2026-08-03 (218MB real cache, 1028 rows):

```
  https://example.org/post        1 row   <- from test_fetcher.py
  https://blocked.example/page    1 row   <- from test_fetcher.py
```

**Two harms, and the second is why this is not cosmetic.**

1. Tests mutate real user data. Nothing else in the suite does this.
2. **It makes `make check` flaky in the worst possible shape.**
   `test_cache_hit_on_second_call` asserts its FIRST fetch is a `miss`. Once
   `example.org/post` is seeded in the real cache by an earlier run, that
   fetch is a `hit` and the test fails — intermittently, because whether the
   real cache is consulted depends on test ordering and on which
   `SqliteResource` was constructed first. Reproduced twice under coverage on
   2026-08-03; 8 consecutive clean runs without. **Invisible on a fresh
   checkout and on CI, semi-permanent once seeded locally** — a developer sees
   a failure CI cannot reproduce, which is the failure mode most likely to be
   dismissed as noise.

**The obvious fix does not work yet, and that is the real content of this
entry.** Setting `A2WEB_CACHE_DIR` to a temp dir at conftest module scope (one
line, same seam as the scrub) fixes both harms and turns two OTHER tests red:

```
  tests/eval_replay/test_regression_corpus.py::test_regression_replay[akakce-no-current-price]
  tests/eval_replay/test_regression_corpus.py::test_llm_egress_is_reproduced_byte_for_byte
      AssertionError: assert None == 'The page shows no current price...'
```

So the frozen-cassette replay suite — the one that exists to be deterministic —
**currently depends on state in the developer's home cache.** A cold-cache run
either serves no answer or reaches for the network (a cold-dir run of
`tests/eval_replay/` did not complete inside five minutes, where the warm-cache
run takes 18 seconds). Whatever it is reaching for is not in the cassette,
which is precisely what `test_llm_egress_is_reproduced_byte_for_byte` claims to
prove is impossible.

That is a second, larger defect wearing this one as a symptom, and it deserves
its own diagnosis rather than being bundled into a hermeticity fix.

> **DIAGNOSED 2026-08-03** — `eval/findings_2026-08-03-the-cassette-that-froze-a-304.md`.
> The cassette `akakce-no-current-price/inputs/raw.http` records a **`304 Not
> Modified` with a 13-byte body section**. A 304 carries no body by definition;
> it points at a copy the client already holds. So the suite's "frozen bytes"
> live in `~/.a2web/cache.sqlite`, not in the repo — and the URL is present in
> the real home cache on this machine. Cold, the replay yields `content_len: 0`,
> `extracted_answer: None`, and the LLM cassette is never called.
>
> It also surfaced a SECOND, product-side defect: a conditional-hit tier result
> with no cache row behind it gated as **`status: ok` with an empty
> `content_md`** and a cheerful `raw → ok (9ms)` narrative — the ADR-0009 harm
> in the pipeline, not the harness. Fix that one first; it is independent and
> unit-testable.
>
> Re-capture is NOT a drive-by: this case is a fabrication-trap specimen
> ("no current price"), so a refreeze against today's page can leave it green
> while testing nothing. Verify the page still has no price by reading the body
> before blessing.

**Scope.** M. Two steps, in order:

1. Diagnose what `replay_case` resolves out of the cache — extraction cache,
   HTTP cache, or both — and freeze it into the cassette. The suite cannot
   claim determinism while a warm home directory changes its result.
2. THEN set `A2WEB_CACHE_DIR` at conftest module scope (not a per-file
   fixture — five files remember and the sixth is the one that leaks), and
   delete the five per-file fixtures that become redundant.

**Do not do 2 before 1.** It turns a rare flake into two reliable failures and
buries the more serious finding under them.

**Evidence.** This session; the one-line conftest patch and its exact fallout
are reproducible by adding `os.environ["A2WEB_CACHE_DIR"] = tempfile.mkdtemp()`
immediately after the `A2WEB_CONFIG` line in `tests/conftest.py`.

---

### CLOSED 2026-08-03 — fixed in full, in the order the diagnosis required

The blocked half turned out to be a frozen `304`
(`eval/findings_2026-08-03-the-cassette-that-froze-a-304.md`): the cassette's
"frozen bytes" were a pointer into `~/.a2web/cache.sqlite`, so the replay
suite's determinism claim was false and the hermeticity fix could not land
without turning it red.

Shipped, in dependency order:

1. **`fix(tier-walk)`** — a `304` with no cached row behind it no longer falls
   through to `install()` as `status: ok` with an empty body. That was the
   ADR-0009 harm in the pipeline, independent of the harness, and it is the one
   defect here that could reach a real caller. Mutation-proven.
2. **`capture_case` is live-only for its target host** — the MECHANISM fix. A
   capture can no longer send a conditional request, so no future cassette can
   freeze a body-less 304. Done via `live_only_hosts` rather than a new
   `bypass_cache=` kwarg on `fetch()`: the mechanism already means exactly this,
   and a capture genuinely is a live-only fetch.
3. **Cassette guard** — a recorded `304` with an empty body raises on parse
   instead of replaying as an empty success.
4. **`load_case(..., with_inputs=False)`** — because (3) initially blocked its
   own fix: `eval-refresh` parsed the bad cassette before re-capturing, so the
   error message named a command that could not run. Refresh overwrites
   `inputs/` and never reads it.
5. **Re-captured `akakce-no-current-price`**, verified before blessing:
   `304`/13-byte body → `200`/124,030-byte body, and the case still tests what
   it was captured to test (independent raw fetch found zero TL price literals
   and the marker `fiyat bulunamadı`; the fresh answer still reports
   `offerCount=0`, `lowPrice=0`, "Fiyat Yok"). `steps`, `tier` and `status`
   unchanged.
6. **The conftest one-liner** — `A2WEB_CACHE_DIR` set at module scope, so the
   suite stops writing to the developer's real cache.

Verified with three consecutive full runs on a cold cache, 1631 passing each
time, plus `make check`.

**The lesson worth keeping:** the guard at `tier_walk` read
`if ... and fc.cached_row is not None and ...`, which LOOKS like protection. A
failed condition simply fell through to the success path. The check was present;
the protection was not. Prefer an explicit reject branch over a condition whose
failure mode is "carry on".

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

**SHIPPED 2026-08-03.** The append moved above the success check; the docstring
now records that the original justification had expired rather than repeating
it.

**The fix landed with all 1703 tests green**, though this entry predicted
`diagnostics_summary` deltas. That absence was the real finding: the only test
named for a failed archive dispatch fakes `_dispatch_archive` ITSELF, so the
real function never ran and the branch had no coverage at all. A behaviour
change with zero deltas is not reassurance — it is a question.

Covered now by `tests/capabilities/tier_pipeline/test_archive_attempt_is_visible.py`,
which fakes the archive TIER and lets the real dispatch execute. That is the
difference between testing a caller's handling of a result and testing the code
that produces it. Mutation-verified: moving the append back below the guard
fails 5 of its 6 tests.

The sixth is the one that would not have failed, and it is deliberate — a
successful dispatch must still record EXACTLY ONE row. Hoisting an append is a
two-line edit that could easily leave the original in place, and a duplicate row
per archive hit is something no other test would notice.

