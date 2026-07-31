# Findings — structural scan, 2026-07-31

Evidence for the 2026-07-31 backlog entries. Two scans in one session: an
openspec/verification drift sweep, then a large-files structural scan run by
five parallel agents on three axes (line count, responsibility count, change
coupling) plus an AST function census.

**This file is the evidence, not the queue.** The actionable list, its tracks,
and the dependency order live in [`BACKLOG.md`](../../BACKLOG.md). Every claim
below carries a `file:line` and was verified by execution, AST walk, or git
measurement at the time of writing — treat line numbers as of 2026-07-31 and
re-check before acting.

---
## the response contract is one concept in three files (L, structure — HIGHEST, T2 UMBRELLA)

**Source:** structural scan, 2026-07-31. Cross-confirmed by two independent
methods (git co-change; AST responsibility census). Verified.

`fetcher.py` + `fetcher_response.py` + `models.py` co-change in **17 commits** —
3× the next-largest triple. Pairwise, and **strengthening**, not decaying:

| pair | era A (05-09..06-15) | era B (06-16..07-31) | last 30d |
|---|---|---|---|
| `fetcher ↔ fetcher_response` | 5 (0.17/0.71) | **21 (0.53/0.84)** | 20 (0.56/0.83) |
| `fetcher ↔ models` | 9 (0.30/0.75) | **19 (0.47/0.86)** | 18 (0.50/0.90) |
| `fetcher_response ↔ models` | 4 (0.57/0.33) | **18 (0.72/0.82)** | 17 (0.71/0.85) |

Not a migration artifact — every commit subject is a product feature, and the
list reads as a single concept:

```
v0.14 envelope deviation trim · v0.21 router-shape envelope · ADR-0005 candidate
menu · v0.25 never-tolerate-any-unfetched-URL · honest partial-listing signal ·
structural "more exists" fallback · ADR-0015 withheld-body index · tier
truthfulness + classify_terminal + honest 404s · thin-not-wall · empty-vs-wall
discrimination · promote corroborated complete small pages to ok
```

Every ADR-0009/0012/0014/0015 tenet in CLAUDE.md lands as an edit to all three
files. **The invariants are documented as one concept and implemented as three.**
The 4-support extension with `packages/llm_extract/router_payload.py` says the
boundary type is a fourth fragment of the same thing.

Name it what its own commits name it: the **retrieval-completeness / response
contract**. That is the missing module. Every other seam below can be cut
without touching it, and none of them would make the remaining ~2100 lines of
`fetcher.py` any less coupled.

## listing sufficiency is OFF on the population it exists for (M, correctness — LIVE)

**Source:** structural scan, 2026-07-31. Verified by call-site count.

`_run_extraction_escalation` is called at **4** sites — `fetcher.py:1331`,
`:1377`, `:2150` (browser), `:2252` (paid). `_phase_listing_completeness` is
called at **2** — `:1332`, `:1378`. So a listing reached *by escalation*
recomputes `fc.record_count`/`fc.record_set` (`:1731-1732`) and never recomputes
`items_loaded` / `items_total` / `regex_oracle_total`.

**The population that escalates to a browser is the infinite-scroll listing —
the exact case the sufficiency machinery exists for.**

Second-order damage: `_apply_llm_listing_oracle:1500-1501` treats
`regex_oracle_total is None` as *"the regex found no numeric total"*. After an
escalation it actually means *"the phase never ran."* The two are
indistinguishable in the field, and the LLM oracle is muzzled on the first
reading.

`_phase_listing_render:2716-2722` already compensates by re-implementing the
assess-and-set inline — so the invariant lives in two places with no link
between them. Same failure shape as the `fetcher.py:1299-1323` incident (a
pre-rendered branch that returned before the ladder and starved four consumers
for months), one level out.

Related ordering hazards found in the same sweep, all unpinned:

- **`_phase_extract_answer` is re-entrant three times** (`:2324`, `:2658`,
  `:2724`) and is **not idempotent**. `fc.extraction_meta` (`:2554`) is
  overwritten wholesale, so token/cost accounting reports only the LAST call —
  **earlier LLM spend is invisible**. `fc.next_links_llm` (`:2536`) is assigned
  only inside `if request_next_links and result.next_links:`, so a second call
  returning nothing leaves the first call's links on the wire.
  `fc.link_digest` (`:2477`) is rebuilt against possibly-different `fc.links`,
  so the second pass rehydrates against a different closed set than the answer
  prose was rehydrated with (ADR-0014 surface).
- **The single paid budget is order-allocated.** `fc.paid_dispatches < 1` gates
  four competitors, resolved purely by call order in `_run_pipeline`:
  `:1827` → `_dispatch_action:1071` → `_obstacle_wants_render:2623` →
  `_listing_wants_render:2685`. Reordering `_phase_obstacle_render` (`:2330`)
  and `_phase_listing_render` (`:2335`) silently changes which product feature
  gets the render.
- **`fc.record_count` never resets** — `_escalate_via_records:1725-1732` sets it
  only on success, no `else: None`. A second ladder run finding no records
  leaves the pre-escalation count, which then feeds `:2716-2718`.
- **`_install_gate_archive` (`:982-996`) does not set `fc.status_code`** while
  `_install_archive_payload:978` does, though `_ArchiveOutcome` carries it
  (`:867`). Whether `status_code` reflects the archive depends on which region
  installed it — the same class of bug `_install_rendered_fields`'s docstring
  was written to prevent.
- **Five phases' ordering constraints are prose in docstrings only** (`:1955`,
  `:2315`, `:2337`, `:2344`). Nothing fails if the calls are reordered.

Fix the H1 call-site gap first — it is a live product defect, not a refactor
concern. The rest is the case for the entry below.

## the ADR-0009 floor is derived from the severity of an English sentence (M, structure — LIVE)

**Source:** structural scan, 2026-07-31. Verified.

`actions/terminal.py:29-66` defines `TerminalOutcome` — a closed 7-value
classification of what a failed fetch *means*. `fetcher.py:2009` computes it:

```python
outcome = classify_terminal(fc.observations, fc.resolved_verdict())
```

`:2010-2024` maps it to a hint code and **throws the value away**. `grep
TerminalOutcome src/` hits only `fetcher.py:46, 2010, 2013, 2019, 2022`. It is
not a `FetchContext` field and not on `FetchResponse`.

Then `fetcher_response.py:435, 442, 449` reconstructs the same classification by
string-matching the hints it just produced:

```python
if status == FetchStatus.failed and any(h.code == "try_user_browser" ...)          # outcome was `wall`
if ... any(h.code == "content_not_found" and h.severity == "warning" ...)          # `gone_unverified`
if ... any(h.code == "content_thin" ...)                                           # `thin_unverified`
```

The `severity == "warning"` test is the sharpest symptom: it reads back the
severity that `content_not_found_hint(verified=False)` (`models.py:187-198`)
chose, in order to recover the `verified` boolean that was passed **in**. A
round-trip through a message catalogue to recover a boolean.

`fetcher_response.py:427` calls the hint *"the SINGLE source of truth for
incompleteness"* — while `actions/terminal.py:8-16` exists precisely because the
previous design keyed on a projection instead of the observations.

**Six instances of the same shape** — a decision made upstream in a typed closed
vocabulary, erased at a boundary, reconstructed downstream from a string or a
constant:

1. `TerminalOutcome` → hint code → re-derived (above). **Touches ADR-0009.**
2. **`kind="structural"` at `fetcher_response.py:294`** discards every handler's
   own classification. Handlers set `drilldown` (`arxiv:323`, `hn:186`,
   `reddit:611`), `related` (`github:281,309`, `wikipedia:176`), `discussion`
   (`discourse:228`) — **none ever sets a structural-shaped one**. `NextLinkKind`
   (`models.py:371`) is a 4-value vocabulary with **no `structural` member**;
   `OtherPageKind` (`:448`) has 2. The fold relabels every handler entry to the
   one value its source vocabulary cannot express, and `models.py:456` defines
   `structural` as "deterministic continuation — pagination, page-order", a
   false claim for a Reddit post drilldown. Same line silently drops
   `NextLink.anchor`. And `models.py:729-734` says the `kind` column is dropped
   from the TSV "when every row is `drilldown` (the common handler-derived
   case)" — the authors know, in the same file where the fold calls them
   structural.
3. `empty_confirmed` — decided by `actions/empty.is_confirmed_empty`, set at
   `fetcher.py:1946`, read correctly at `fetcher_response.py:375`, then
   **re-derived at `:685`** from `any(h.code == "content_empty" ...)`, shadowing
   the imported name of the real predicate. Its sibling `small_page_confirmed`
   *is* carried across properly (`models.py:616`, set `:538`, read `:664`) — two
   adjacent promotions, two different mechanisms.
4. `_compose_next_links` (`:274-281`) drops `fc.next_links_handler` wholesale
   when the LLM list is non-empty, justified by "the LLM re-ranked handler
   candidates" — but `fetcher.py:2462` only passes them when
   `request_next_links`, so when it is False the LLM never saw them.
5. `retrieval_incomplete` and `confidence` are each decided twice, so neither
   `FetchResponse` field is final for `query` callers while both are final for
   `fetch_raw` callers. **The same field name means two different things
   depending on which tool you called.** (The confidence half is deliberate and
   documented at `:638-646` — a genuine two-phase decision. The fix is naming
   the phases, not merging the sites.)
6. **Two TSV field tables, three owners, one contract.** `wire._TSV_FIELDS` is
   literal *on purpose* (CLAUDE.md: "inference is how a field added to
   `AskResponse` silently changes the agent-facing wire"). But `models.py` holds
   a second implicit table in its serializer branches: `other_pages` is encoded
   at `models.py:921`, `links` at `:665`, `next_links` at `:667` — `wire.py`
   defers to all three via its ALREADY-TSV guard — while `operator_hints` /
   `refinement_axes` / `options` / `content_candidates` are encoded in
   `wire.encode_envelope`, and `headings` by **nobody** (`_is_tsv_shaped`
   rejects it). Nothing asserts the two tables describe the same set. The rule
   is honoured against *introspection* and defeated by *duplication* — the exact
   failure it names. `models.py:18` also imports `lean_wire.encode_tsv` directly
   rather than through `wire.py`, so the codec has two in-tree consumers.

Also found: **hint construction is spread across 5 modules** — 9 factories in
`models.py:141-368`, plus raw `OperatorHint(...)` at `fetcher_response.py:345,
600, 617, 668`, `fetcher.py:831, 1899, 2497`, `tiers/browser.py:129, 198`,
`handlers/reddit.py:730`. Seven codes (`answer_truncated`, `content_guidance`,
`retrieval_incomplete`, `index_lost`, `captcha_redirect`, `browser_unavailable`,
…) exist only as inline literals with no factory. The set of codes is a de-facto
closed enum that is **nowhere declared** — while four sites match on it by
string.

## no "install a fetch result" type; six fields written six ways (M, structure)

**Source:** structural scan, 2026-07-31. AST-measured (attribute stores/loads on
`fc`).

`FetchContext` has **69 declared fields** (`fetcher.py:271-539` — 269 lines, 10%
of the file is one dataclass). 73 distinct `fc.<field>` names are referenced
across the module; **`fetcher_response.py` reads 41 of them from outside.**

Six *transport* fields are each written by **six different functions across
three responsibility groups**:

| field | writers | readers |
|---|---|---|
| `body` | 6 | 4 |
| `content_type` | 6 | 3 |
| `final_url` | 6 | 6 |
| `tier_used` | 6 | 4 |
| `pre_rendered_payload` | 6 | 2 |
| `status_code` | 5 | 1 |

`_install_rendered_fields` (`:1262`) already unified the **content** half of
that copy — after it caused a live bug, and its docstring says so — and
explicitly excluded the transport half (`:1279-1281`), which is still hand-copied
six ways. That exclusion is the asymmetry `_install_gate_archive`'s missing
`status_code` (entry above) falls through.

**A `TierInstall` value type consumed by ONE `install(fc, result)` chokepoint is
the change that makes the extraction ladder / tier walk / escalators separable.**
It is exactly what `_install_rendered_fields`'s own docstring argues for, on the
half it did cut.

Cleanly extractable *without* touching that (≈640 lines, 23%, none carrying
`FetchContext` in the public surface):

- **`quality_gate.py`** (~132) — `js_heavy_hosts`, `evaluate`, `regate`. Highest
  value: `tiers/browser.py:111` already does `from ..fetcher import
  js_heavy_hosts`, an import inversion that exists *only* because the gate lives
  in the orchestrator.
- **`content_menu.py`** (~191) — `ContentCandidate`, `assemble_menu`,
  `wire_content_md`. Entirely pure, already the most test-exercised surface.
- **`next_link_derivation.py`** (~95) — `_records_to_next_links` is already
  labelled *"Domain seam"* at `:1789`.
- **`link_affordances.py`** (~52) — or fold into the existing `link_digest.py`.
- **`cookie_attach.py`** (~90), **`cache_policy.py`** (~41 — gives the `_ttl_for`
  defect a home), **`tier_telemetry.py`** (~36).

**Anti-seams — do not cut these**, each verified:

- `_phase_tier_loop` must not split from `_dispatch_action`: the `:1247`
  escalation-win check (`fc.tier_used != "none" and resolved_verdict() is ok`) is
  correct **only because** `_install_won_tier` at `:1254` has not run yet. Moving
  either statement changes which content wins.
- The three escalators cannot be unified without also moving the gate and the
  extraction ladder — `_escalate_browser:2150`, `_escalate_paid:2252` and
  `_dispatch_action:1058` all call into both. Extracting escalators alone leaves
  a three-way cycle.
- `_phase_empty_promotion` / `_phase_complete_small_page_promotion` /
  `_apply_terminal` are one unit — a mutually-exclusive chain expressed only by
  early returns across three functions, with `small_page_promoted()` reading a
  field written 460 lines away.
- `_phase_extract`'s pre-rendered branch is not liftable — `:1299-1323`
  documents that it previously returned *before* the ladder and starved four
  consumers for months.
- `FetchContext` itself: 69 fields, 41 read externally, ~19 test modules import
  it. Splitting it per-phase breaks the response builder's flat access.

Also: **13 private names whose only external consumer is the test suite**
(`_wire_content_md`, `_obstacle_wants_render`, `_apply_llm_listing_oracle`,
`_build_link_digest`, `_dispatch_action`, `_phase_extract`, …). That is the
shape of a module with no public API other than `fetch`.

Dead: `fetcher.py:1090`'s `_phase_resolve_cookies` call is a provable no-op given
the identical call at `:1095` and the host guard at `:777`.

## `domain.py` is 69% an undocumented renderer (M, structure)

**Source:** structural scan, 2026-07-31. AST-measured.

`domain.py` is 551 lines doing **three** jobs:

| job | lines | share |
|---|---|---|
| structured-data → markdown renderer (`:188-551` + `json_response_fallback`) | 381 | **69.1%** |
| URL policy (`is_search_shaped`, `rewrite_captcha_host`, `strip_reader_prefix`) | 107 | 19% |
| settings-coupled glue (`compute_profile_hash`, `is_live_only`) | **12** | **2.2%** |

CLAUDE.md and the module's own docstring (`:3`) both describe it as *"pure
functions reading `AppSettings` or models but too small to deserve their own
module."* That describes **12 of 551 lines**. The renderer reads neither
settings nor models; `rewrite_captcha_host` — one of the three functions CLAUDE.md
names — reads neither either. "Too small" against `_single_entity_md` at 36
lines and a 5-deep transitive call graph.

The renderer has **zero a2web imports** — it is already `tach.toml`-eligible for
`packages/` today — and **four test files already aim at it as a unit**
(`test_ld_json_itemlist.py`, `test_json_recipe_synthesis.py`,
`test_json_entity_render_is_default_keep.py`,
`test_json_entity_array_rendering.py`). The test tree treats it as a package;
only the source file disagrees. Consumers: `fetcher.py:1346`, `:1689`.

Anti-seams: `is_search_shaped` cannot follow the renderer — `:36-37` states it
exists to gate `actions.empty.is_confirmed_empty` (`empty.py:70`), so it is one
clause of the ADR-level empty→ok conjunction. And `_CAPTCHA_SEARCH_HOSTS`
(`:77-84`) is coupled to `packages/block_detector.py:186-190, 305-307` **by
comment only** — the two halves of one Google/Bing policy, in two modules, linked
in prose, with nothing testing the pair.

Dead public surface: `parse_query_params` is in `__all__` (`:30`), documented at
length, has 6 tests — and **zero call sites in `src/`**. Conversely
`strip_reader_prefix` is *not* in `__all__` yet is imported by `fetcher.py:56`.
`__all__` no longer describes the module.

## `models.py` is 25% prose and 12% wire projection (M, structure)

**Source:** structural scan, 2026-07-31. AST-measured.

| job | lines | share |
|---|---|---|
| type definitions (vocabulary + leaf models + envelopes) | 513 | 55% |
| **operator-hint message catalogue** (`:141-368`, 9 factories) | **228** | **25%** |
| **wire projection** (`:703-809`, 6 field-tier tables + `_prune_wire`) | **107** | **12%** |

Those 228 lines contain **no types**. They are agent-facing English — the
ADR-0009 never-silently-miss copy, severity calibration, remediation text.
`content_not_found_hint` (`:162-198`) is 37 lines of which 20 are literal message
strings encoding the verified/unverified severity policy.

**The ADR-0009 severity ladder — `critical` = wall, `warning` = unverified,
`info` = verified-dead — is discoverable only by reading nine docstrings
scattered through a type-definition file. There is no place where the ladder is
stated once.** That is what makes it re-derivable by string-match at
`fetcher_response.py:442` (entry above).

Wire projection is a separate job on three independent measurements: (1) it
already has a file — `wire.py` does the same job for the sibling channel; (2) its
parameters are field-name *tables about* the models, the shape `wire._TSV_FIELDS`
already uses; (3) `models.py` now contains **two omit-empty implementations that
do not know about each other** — `_prune_wire`'s inline `is_empty` (`:786`) and
`lean_wire.PruneEmpty` inherited by `AskExtraction` (`:678`). Import direction is
already clean: `models.py:29` imports from `.wire`; `wire.py` does not import
`models`.

The load-bearing anti-seam: the three `*_tsv` renderers **cannot** follow.
`_next_links_tsv` (`:733`) picks its column set by inspecting `lk.kind` across
*typed* rows; `_other_pages_tsv` (`:746`) the same on `p.off_domain`. Both need
model instances **before** `model_dump`, and `wire.encode_envelope` runs after
it. The pre-dump column decision is genuinely model-side; only the post-dump
rendering is wire-side.

## `fetcher_response.py` is 740 lines CLAUDE.md never mentions (M, structure + docs)

**Source:** structural scan, 2026-07-31.

**`fetcher_response.py` has no entry in CLAUDE.md's module table.** It appears
twice in passing — inside the `models.py` bullet, and in the LLM-contract note.
It owns the ADR-0009 `retrieval_incomplete` contract, the ADR-0015 index
composition, the obstacle→confidence reconciliation, and both response builders.

The two functions named "builders" are **~72 lines of construction wrapped in
~263 lines of policy**: `build_response` is 193 lines of which the
`FetchResponse(...)` call is 40; `build_ask_response` is 154 of which the
`AskResponse(...)` call is 32. The entire `retrieval_incomplete` contract is six
sequential `if` statements at `:393, :417-419, :424-425, :435-436, :442-443,
:449-450`.

The seam is already there, undeclared: **the two halves share exactly zero
helpers.** `_confidence_for` / `_wrap_content_md` / `_build_narrative` /
`_records_to_options` / `_compose_next_links` are `build_response`-only;
`_curate_ask_meta` / `_debug_extraction` / `_index_loss_hint` /
`_compose_other_pages` are `build_ask_response`-only. `build_response` never
touches `AskResponse` and vice versa.

Anti-seam: `build_response`'s policy is pure but **cannot** move to `actions/` —
its sole input is `FetchContext` (`fetcher.py:272`) and `fetcher.py` imports
`actions/`, so relocating inverts the dependency. `actions/terminal.py:18` states
the constraint. It is portable only once its input is `Sequence[Observation]` —
the exact substrate `terminal.py` and `empty.py` already stand on.

Docstring drift found in the same files, all verified:

- `fetcher_response.py:3` says **"Pure functions."** — `_project_routing` calls
  `log_warning` (`:98`); `build_response` calls `time.perf_counter()` (`:365`)
  and mutates its return value after construction (`:553-554`).
- `fetcher_response.py:7-9` states `include_links`/`link_roles` are applied
  **after** the builder. They are applied at `fetcher.py:692-695` — **before**.
  The stated ordering is backwards.
- `models.py:7-9` still describes a2kit's default formatter and "the custom
  renderer ships in a later PR"; a2kit was retired 2026-07-22 and the renderer is
  `wire.py`.
- `models.py:686-690` attributes `PruneEmpty` to "a2kit v0.40.1"; it comes from
  the shelf's `lean_wire`.
- `models.py:4-5` pins the shape to `v0.1-response-format.md` §2 — **not in the
  repo** — and the model has since gained 7+ fields.
- `AskResponse` and friends still say **"the `ask` tool"** (`:813`, `:678`,
  `:706`, `:721`) — renamed to `query` in v0.23. `wire._TSV_FIELDS` keys on
  `"query"`, so the two files disagree on the tool's name.
- `RouterPayload`'s docstring (`:517-522`) says **three** conditional fields;
  `fetcher_response.py:70-83` projects **seven** plus `item_total_seen`; CLAUDE.md
  says seven. Three counts of one thing, two wrong.

## `routers.py` is one function with a hole in it (S, structure)

**Source:** function census, 2026-07-31.

`register_web_tools` (`routers.py:57`) is **236 lines of a 355-line file** — 66%.
`query` (`:66`) is a 146-line closure nested inside it; `fetch_raw` (`:219`) is
74 more.

CLAUDE.md describes tools as *"plain closures over `Components`"*. A 146-line
closure inside a 236-line registrar is not plain, and the nesting makes both
untestable except through the MCP client seam. Note this is a genuine consequence
of design D1 (the parameter list IS the wire schema) — the signature must be
visible at the decoration site — so the fix is where the *body* lives, not where
the signature does.

Git says this one is **fading**, not live: `fetcher ↔ routers` was 11 in era A
and <3 in the last 30 days. Low priority; recorded so the size number is not
mistaken for urgency later.

## the Registry half of Strategy+Registry isolates nothing (S, structure)

**Source:** co-change analysis, 2026-07-31.

**`tiers/__init__.py` has never changed without `fetcher.py` — 12 of 12,
P(fetcher | tiers/__init__) = 1.00.** That is not layering; it is a registry
whose only consumer must be edited in lockstep.

Two more pure-function extractions with the same one-way leak, and both arrows
are **new** (era B, i.e. post-sunset):

- `domain.py → fetcher.py`: 0.71 overall, **0.89** in era B
- `actions/playbook.py → fetcher.py`: 0.64 overall, **0.86** in era B

Read: you cannot add a decision to the playbook without editing its interpreter,
while `fetcher.py` changes without the playbook ~85% of the time. The extraction
bought **testability, not independent evolvability**. Worth deciding explicitly
whether that was the goal — if it was, this entry is a no-op and should be
closed rather than left looking like a defect.

## `playbook.py` and its test are in 1.00/1.00 lockstep (S, verification)

**Source:** test-to-source co-change, 2026-07-31.

Recent era (since 2026-06-16): `actions/playbook.py ↔
tests/capabilities/cascade_decision_log/test_decide_next.py` — **6 commits,
P(test|src) = 1.00, P(src|test) = 1.00.** Total lockstep both ways. The table
cannot change without its test changing, and the test has no independent life.

For a pure function over enums that is arguably correct — the test *is* the
table. But it means **the test cannot catch a wrong table**: it and the playbook
were authored together, by the same author, at the same moment, and can only
confirm they agree. Same endogenous-oracle shape as the 2026-07-28
arXiv/wikipedia incident (five green tests over two dead parsers), one
abstraction level up.

What would make it a real witness: a corpus case or live probe where the
*outcome* of a routing decision is observed, not the decision itself. Note
`test_decide_next.py` is not naive — `:52` and `:59` are hypothesis property
tests, `:518` asserts rule-name uniqueness, `:526` asserts purity. Those four are
genuinely independent; the other 49 are the table restated.

Second instance in the same measurement: `handlers/reddit.py →
test_handlers.py` at **P(test|src) = 0.73**, the classic
fixture-encodes-implementation signature, on the handler with the largest churn
(2237 lines). Check whether those fixtures are under
`tests/fixtures/captured/` or hand-written.

Deliberately not actionable yet: `models.py → tests/contracts/tool_schemas.json`
measured 0.50/1.00, but that golden was **deleted** in the a2kit sunset
(`9bb4c37`). Its replacement `tests/contracts/wire/` has only 5 commits — not
enough history. **Re-measure in a month** rather than acting on the pre-sunset
number.

## a partial eval loss exits 0 (S, verification)

**Source:** structural scan, 2026-07-31. Verified.

`eval/findings_2026-07-28-full.md` recorded 2 quality cells lost to a judge parse
error (`int() argument … not 'list'`, from
`packages/llm_extract/judge.py:111-112`, bench twin `bench_judge.py:181-186`).

**The loss is no longer silent** — `runner.py:467-472` catches it, writes
`judge_raw.txt`, sets `AxisDisposition.UNSCORED` with `reason=f"parse_error:
{exc}"`, and it surfaces in three artifacts (`report.py:246-250`, `:255-263`,
`:435-449`). `close-silent-eval-loss` did its job.

**But nothing fails.** `broken_axes()` (`runner.py:247-262`) fires only when
`coverage.requested and coverage.scored == 0` → exit 4 (`__main__.py:243-252`).
A 2-of-N loss is exit 0, and the mean is over survivors (`_mean_opt`,
`report.py:217-221`; leaderboard `:193`; `stats_dict` `:482-491`). So an axis can
degrade from 20/20 to 3/20 across runs with no gate — honest denominators
(`_covered`, `:227`) are the only mitigation, and they require a human to read
them.

No test covers partial loss; `test_axis_disposition.py:165, 186, 221, 276` cover
the all-or-nothing case only. Wants a coverage floor (e.g. fail below X% scored
on a requested axis), which is a decision, not a bug fix.

## `llm_eval/systems.py` carries a second fetch stack (S, structure)

**Source:** structural scan, 2026-07-31.

`systems.py` is 375 lines: `WebFetchBaseline` (`:81-186`) plus its private HTTP
stack — `_FetchError:323`, `_http_get:327-360`, `_html_to_markdown:361-375`,
caps `:41-45` — is **~150 lines reproducing a competitor's fetch behaviour**,
sitting beside two ~50-line a2web adapters (`A2WebDetail:187`,
`A2WebExtract:239`). Purpose-named seam: `systems_webfetch.py`. It is a
reproduction of a competitor, not an a2web system, and that is the whole reason
it must not share a2web's stack.

`runner.py` (756) is 6 jobs. The one real mixing: **cell artifacts are written by
the driver** (`_run_one` writes at `:406, 407, 441, 466, 470, 481, 502`;
`_score_next_links` at `:589`) **while run artifacts are written by
`report.py`** — one concern, two owners. Cost accounting is smeared across
`:479, 558, 586`. Candidate seams: `axes.py` (the `AxisDisposition`/`*Axis`/
`AxisCoverage`/`broken_axes` block, `:77-277` — purpose already named in prose at
`:202-206` but not by structure), and moving `row_as_flat_dict`/`_row_to_json`
(`:694-745`, self-described as a write-boundary concern) to `report.py`.

`report.py` (499) is cohesive — 8 writers behind `write_all:64-77` with a stated
ordering invariant (`__main__.py:238-239`). The separable part is **not** the
writers: the run statistics are recomputed independently in **four** places
(`:193`, `:317-321`, `:393`, `:482-491`). One `stats(report)` the writers render.

Anti-seam worth keeping: `_CANDIDATE_FIELD` (`runner.py:660-666`) is literal on
purpose (`:648-659`) — extracting it without the systems list would reintroduce
the tolerant-lookup failure that cost five weeks of unscored `next_links`.

## test files that have drifted from their subject (S, structure)

**Source:** structural scan, 2026-07-31. Counts measured.

| file | tests | body lines | median | verdict |
|---|---|---|---|---|
| `site_handlers/test_handlers.py` | 57 | 736/972 | 13 | **(c)** four capabilities |
| `contracts/test_wire_contract.py` | 18 | 405/629 | 20 | **(a)** + one intruder |
| `output_benchmark/test_output_benchmark.py` | 23 | 322/572 | 9 | **(c)** five subjects |
| `tier_pipeline/test_fetcher.py` | 23 | 420/569 | 15 | (a) with a (c) tail |
| `cascade_decision_log/test_decide_next.py` | 53 | 314/533 | 5 | **(b)** repetition |

**`test_handlers.py` is an unsplit residue.** Its siblings already split per
handler (`test_handlers_arxiv.py`, `_discourse`, `_github`, `_habr`, `_v2ex`,
`_wikipedia`, `test_hn_front_page.py`, `test_reddit_html.py`). What is left is
registry dispatch `:27-66`, Reddit RSS `:74-155`, HN `:157-249`, old-Reddit
fallback `:261-396`, Twitter/nitter `:409-511`, challenge detection `:528-692`,
Reddit escalation `:698-945` — **and `test_playbook_*` at `:947-973`, which
exercises `actions/playbook.py:483`**. Nobody changing `decide_next` will grep a
file called `test_handlers.py`; `:959` does not even involve Reddit. The 6 other
handlers are *not* in the file despite its name. `test_hn_front_page.py` already
covers `_front_page_candidates`, which `:167` and `:186` cover again.

**`test_wire_contract.py` hides an architecture test.**
`test_a2web_matches_the_resolved_mcp_substrate` (`:439-520`) is 81 lines walking
every `src/a2web/**/*.py` with `ast`, resolving `fastmcp`/`mcp` imports and
comparing call-site keywords against `inspect.signature`. It captures no wire
bytes and opens no client. Its subject is every `ToolResult(...)` construction in
the tree; the filename says "wire contract goldens". Belongs in
`tests/architecture/`, beside its peers. Also `:34` imports **private symbols
from another test module** (`tests.capabilities.ask_response.test_ask_response`)
— a contract gate whose fixtures live in a capability test.

**`test_output_benchmark.py` re-implements shared doubles.** `_MockJudge:321` and
`_MockBenchJudge:338` are line-for-line re-implementations of `MockJudge`/
`MockBenchJudge` in `tests/capabilities/output_benchmark/_doubles.py:19,36` —
the module its sibling `test_axis_disposition.py:40` imports. It is the only file
in the directory not using it. `:484`
(`test_default_judge_model_denied_on_metered_anthropic`) asserts **only** on the
third-party `anyllm.DEFAULT_COST_POLICY` and touches no a2web code, while
`tests/packages/test_llm_cost_guard.py` exists. ADR-0016 coverage in a file
nobody changing cost policy will open.

**`test_decide_next.py` is genuine repetition** — 53 tests, median body 5 lines,
two shapes covering half the file (build a log, assert `decide_next(...) ==
Action`). Parameterizable with `id=` per rule. Except: `:321` and `:497` are
*precedence* tests needing two rules live at once, and cannot become rows.

**`test_fetcher.py:291-433`** tests `domain.py::rewrite_captcha_host` while
`test_domain.py` sits in the same directory.

Anti-seams that block the obvious splits: `_make_state` (`test_handlers.py:255`)
spans the fallback and escalation clusters; `_make_state_with_nitter` (`:402`)
and `_captured_interstitial` (`:518`) weld Twitter to the challenge catalogue;
`_StubSystem`/`_corpus` (`test_output_benchmark.py:278, 352`) are used by all
five suite-level tests and `_CountingJudge:530` subclasses the mocks in-test.
Promote the helpers first, split second.

## the markup-funnel guard misses `re.search`/`re.sub` (S, verification — LIVE)

**Source:** structural scan, 2026-07-31. Verified. **Supersedes and widens the
2026-07-28 "regex-over-markup OUTSIDE `handlers/`" entry below.**

`tests/architecture/test_handler_markup_funnel.py:90-96` matches **only
`ast.Call` where `node.func.attr == "compile"`.** Every inline `re.search` /
`re.sub` / `re.match` is invisible to it.

Full inline-regex inventory in `handlers/`:

| site | pattern | markup? |
|---|---|---|
| `reddit.py:502` | `<div class="md">(.*)</div>` | **YES — unguarded** |
| `reddit.py:497` | `<!--.*?-->` | **YES — unguarded** |
| `reddit.py:482` | `/r/([^/]+)/` | no (URL) |
| `arxiv.py:172` | `\s+` | no (whitespace) |

Both live in `_atom_body_markdown` (`:486-504`) — the exact failure surface the
guard was written for. Its own comment at `:500-501` admits *"Reddit's rendered
md never nests `<div>`, so the greedy match closes on the md div itself"* — a
spelling assumption, precisely what killed the arXiv and Parsoid parsers.

The guard's docstring claims *"all 18 legitimate patterns were anchored path
matchers and all 4 rotted ones were not — the split is clean."* **That census
counted only `re.compile`.** So the guard is a third instance of the pattern
CLAUDE.md already records twice (30 of 32 architecture tests passing against an
empty source tree; `test_tools_return_pydantic_not_str` matching a decorator
that no longer existed) — green while not covering the thing it names.

Two more guards in the same condition, found in the same sweep:

- **The prompt↔policy guard covers 8 of 86 rules.**
  `test_wobble_policies_match_prompts.py:36` imports `_ROUTER_SCHEMA_DOC` from
  `prompts.py` — so it is structurally blind to `extractor.py:391-424`'s
  `_next_links_suffix`, 34 lines of literal instruction text ("up to 10 links",
  "≤80 characters", the three `kind` definitions, a JSON exemplar). The
  next_links contract is ungoverned because the prompt text lives in the wrong
  module.
- **`_common.py` adoption has no guard at all** — `empty_result` 9/9,
  `map_non_ok` **4/9**, `challenge_verdict` **2 of 3 eligible**.

Fix the AST matcher first (widen to `search`/`sub`/`match`/`findall`), then the
two reddit patterns. Note `_ALLOWED_PREFIXES` (test `:54`) admits anything
starting `^(` / `^[` / `^/`, so `re.compile(r"^[<]div…")` would pass; low risk,
recorded for completeness.

## reddit's old.reddit channel can serve an interstitial as `ok` (S, correctness — LIVE)

**Source:** structural scan, 2026-07-31. Verified.

`wikipedia.py:87-96` argues in prose that the challenge check *"belongs on every
handler that extracts HTML, because one present only where a defect was already
observed is one nobody remembers to add to the next handler."* Three handlers
extract raw HTML — `wikipedia.py:81`, `twitter.py:202`, `reddit.py:889`. **Only
the first two call `_common.challenge_verdict`.**

So `reddit._fetch_old_reddit` (`:862-923`) can return a Reddit interstitial as
`Verdict.ok` with `pre_rendered` content. That is the empty-vs-wall invariant's
exact failure direction — a wall laundered into content — on the busiest
handler in the repo.

The argument for symmetry was written down and never mechanised. Fix the call
site; then decide whether the guard the wikipedia docstring implies is worth
writing (it would need to identify "extracts raw HTML" structurally).

## reddit.py is four retrieval channels behind one `matches()` (M, structure)

**Source:** structural scan, 2026-07-31. Section-measured.

`reddit.py` is 923 lines + `_reddit_html.py` 294 = **1,217 lines**. Every other
handler has exactly one retrieval channel (twitter has one channel over N
mirrors); the next-largest handler is `arxiv.py` at 326, median 247.

`fetch` (`:168-276`, **109 lines**) picks between four channels: eager
Zyte/old.reddit (`:198-201`), keyless `.rss` (`:203-276`), old.reddit HTML
fallback (`:221`, `:260` → `:850-923`), and archive/render escalation signals
(`:230`, `:233`, `:751`). **That ladder is the file's true centre and it has no
name.**

Of the 923, roughly **310 lines are not Reddit knowledge at all**:

- `:378-504` (127) — a general Atom/RSS feed client (`_AtomEntry`, `_AtomFeed`,
  `_parse_atom`, `_el_text`, `_iso_to_epoch`). Zero Reddit specificity except the
  `t1`/`t3` id-prefix convention on one line (`:433`). Shelf-shaped.
- `:318-375` (58) — a bespoke 429 retry loop honouring `x-ratelimit-reset`.
  Purely a `FetchOutcome` + header contract. **Habr, v2ex and discourse have no
  such policy at all** and would inherit one.
- `human_age` (`:681-692`), `_stub_line` (`:539-554`) — formatting, no domain.

**And ~136 lines are orchestrator policy that leaked down a layer.**
`_zyte_reddit_enabled` (`:770-777`) reads `settings.zyte_key` +
`settings.reddit_tier_policy` and **decides to spend money at tier 0** — the same
decision `playbook._decide_paid_last_resort` (`playbook.py:411`) exists to own,
documented at `playbook.py:61-67` as *"the last resort… must never preempt a free
recovery."* Reddit preempts it unconditionally.

**Two inert artefacts, measured:**

- **`_walled_signal` (`:700-717`) has exactly one occurrence in the entire repo:
  its own `def`.** Nothing calls it in `src/` or `tests/`. It is the sole reason
  `try_user_browser_hint` is imported at `:49`. And `twitter.py:137-147` names
  that shape as a **rejected** design — *"that shape was tried here and is
  wrong… the response carried 2204 characters of content under a klaxon saying
  it had none."*
- The hint codes `reddit_forbidden_try_archive` (`:235`) and
  `reddit_deleted_try_archive` (`:857`) are read by **no code in `src/`** — only
  two test assertions (`test_handlers.py:750, 766`). The archive dispatch
  actually fires off the *verdict*: `_archive_escalation_signal` returns
  `Verdict.not_found` (`:728`), `fetcher.py:1218` stamps `authoritative=True`,
  and `playbook._decide_reddit_comment_not_found_archive` (`:196-199`) matches
  on that. The docstring at `:721` describes an intent the string does not carry.
  **Side effect worth flagging:** the same authoritative `not_found` also
  suppresses the `content_not_found` hint at `fetcher.py:2016` — "try archive"
  and "definitively gone" are the same signal.

Anti-seams: `_to_rss_url` (`:284-315`) and `_url_shape` (`:105-115`) share
`_LISTING_PATH_RE` group semantics — splitting them re-parses the URL twice and
lets the two drift on sort-name changes. `_atom_body_markdown` (`:486-504`) looks
like generic HTML→md but the `<!-- SC_ON -->` split (`:496`) is Reddit's exact
render output; it must move *with* the renderer, not into `html_fragment` — but
it must stop being a regex. `_fetch_via_zyte_oldreddit` (`:780-832`) reads like
paid plumbing, but `:806-811` couples it to `content_expectations.assess` and the
fall-through-to-RSS on an oracle miss — **that fall-through is the Reddit-specific
value; the Zyte call around it is not.**

For contrast, `github.py` (483) is the healthiest of the large files: one
channel, one transport (`_CurlCffiGitHubAPI:120-153`), one classifier
(`_classify:84-104`), three pure renderers (`:387-483`). Its only duplication is
internal — `_fetch_repo_candidates:250-314` is 64 lines of near-identical
issue/PR loops (`:259-284` vs `:286-312`) differing only in endpoint, cap source
and `reason` prefix.

## cross-handler duplication: seven shapes, partial adoption (M, structure)

**Source:** structural scan, 2026-07-31. All 9 handlers + `_common.py` +
`_reddit_html.py`.

`_common.py` was created for three helpers and **stalled at partial adoption on
all three**, with nothing testing or enforcing it:

- **D1 — non-ok `FetchOutcome` → `Verdict` mapping.** `map_non_ok` used by 4/9
  (arxiv `:90,132`, hn `:91`, discourse `:73`, wikipedia `:69`). Carrying the
  table inline instead: `reddit.py:206-239` + `:875-882`, `twitter.py:187-195`,
  `github.py:191-209` (as a gidgethub exception ladder). `habr.py:124` and
  `v2ex.py:107` collapse it to `verdict is not ok → None`, **silently losing the
  timeout/404/429 distinction**. 4/9 with 5 divergent variants — the extraction
  happened and then stopped.
- **D2 — the never-raises JSON GET.** `habr._fetch_json:115-130` and
  `v2ex._fetch_json:99-112` are near-identical, same docstring, each paired with
  an identical `anyio.create_task_group` fan-out (`habr:87-95`, `v2ex:70-78`).
- **D3 — depth-indented blockquote comment renderer. Five sites, four
  implementations:** `hn._render_kid:233-247`, `habr._render_comment:198-227`,
  `discourse._render_post:179-193`, `_reddit_html._render_comment:271-276`
  (`"> " * (depth+1)`, note the differing spacing), `reddit.py:666` inline. All
  produce the same `{quote} body / {quote} / {quote} — {author}`. habr and
  discourse are byte-level near-twins. **Depth caps diverge unjustifiedly** —
  `_MAX_DEPTH = 20` in habr (`:48`) and discourse (`:41`); hn and `_reddit_html`
  have **none**.
- **D4 — an untyped render bag the guard cannot see.** 7 handlers return
  `{"content_md","title","byline","headings"}` as a dict and hand it to
  `Rendered.from_dict`; 3 construct `Rendered(...)` directly. This is a
  `dict[str, Any]` bag that `test_no_dict_str_any_on_dataclasses.py` misses —
  **it walks dataclass fields, not function returns.** Worse,
  `discourse._render_index:238-243` smuggles a **fifth key `next_links`** through
  the same bag and unpacks it at `:95` — a second, undeclared contract on an
  untyped dict.
- **D5 — `NextLink` builders with unexplained cap divergence.** arxiv `:311-326`
  cap 10, hn `:160-189` cap 10, wikipedia `:152-179` cap 10, reddit `:610-614`
  cap 10, github `:250-314` 5+5, **discourse `:227-229` up to `_MAX_TOPICS`=50,
  effectively uncapped.** And `kind=` values diverge with no shared vocabulary
  check: `drilldown` (arxiv/hn/reddit), `related` (github/wikipedia),
  **`discussion` (discourse:228) — which is not in `extractor._VALID_KINDS`**
  (`{"drilldown","related","source"}`, `extractor.py:388`).
- **D6 — listing stub line.** `- **Title** (meta)\n  <url>` produced
  independently four times: reddit `:539-554`, arxiv `:298`, hn `:146`,
  discourse `:226`.
- **D7 — the H1-from-title / H2-from-section headings idiom.** Mechanically
  identical in all 9.

**Do NOT merge** (coincidental similarity): the `matches()` bodies — each is one
call to a site-specific classifier and the shared shape is already the `Handler`
protocol; the anchored path regexes — each encodes a different site's URL
grammar and sharing them creates false coupling; `github._CurlCffiGitHubAPI` — a
genuine one-off; `twitter`'s instance rotation — unique to a mirror farm.

## 45 of 86 prompt rules have neither code nor test (L, verification)

**Source:** structural scan, 2026-07-31. Independent census. **Supersedes the
"21 behavioural rules live only as prompt English" entry below** — that count was
a subset (it counted only the `_ROUTER_SCHEMA_DOC` field-description clauses).

86 distinct behavioural instructions across the 5 templates in `prompts.py`:

| enforcement | count |
|---|---|
| has a **code implementer** | 24 |
| has a test of any kind | 33 — of which **13 assert only that the sentence is in the prompt string**, and 3 are live-network corpus proxies |
| **NEITHER code nor test** | **45** |
| covered by the one structural guard (field presence) | **8** |

**Largest untested cluster: the `also_here` query grammar — 11 consecutive rules
with zero enforcement** (`prompts.py:256-273`): drop-the-verb-frame, ≤1 operator
from `, / vs / /`, CAPS at most one token, trailing `?` only for DECIDE items,
split `and`-joined items, listing-orthogonality, "COVERED means everything the
page holds", count guidance 3/5/5+. `extractor.py:546-552` only filters
non-strings. **v0.23 and v0.25 both revised this cluster** (module comments
`:161-186`) — two tuning rounds against an unmeasured surface.

**Three places where the prompt and the code actively disagree, verified:**

1. **`prompts.py:291-294` "put that continuation FIRST" is overridden.**
   `fetcher_response._compose_other_pages:284-299` re-sorts to
   `handler-structural + llm-structural + llm-drilldown` and truncates to
   `_NEXT_LINKS_CAP`. A drilldown the model deliberately placed first lands last
   — or off the end. The prompt asks for an ordering the pipeline structurally
   cannot honour.
2. **`prompts.py:277-280` "NEVER type a raw URL" has a sanctioned escape hatch.**
   `extractor.py:576-578` accepts any model-supplied `url` string unchecked, and
   `tests/capabilities/link_affordances/test_rehydration_seam.py:55`
   (`test_legacy_url_entry_passes_through`) **pins** that. The ADR-0014
   closed-set guarantee holds only on the `{{n}}` handle path; the legacy `url`
   path is a hole with a test defending it. (Already recorded separately; this is
   the prompt-side view of the same hole.)
3. **`prompts.py:305-306` gates `refinement_axes` on "listing AND SELECTION
   question"; `fetcher_response.py:628, 636` gates on `is_listing` alone.** Axes
   reach the wire for a non-selection listing question.

Unenforced by explicit admission in the source: `router_payload.py:43-44`
("≤120 chars per prompt instruction; the pydantic mirror does not truncate" —
and `models.py:466` has no `max_length` on `OtherPage.reason` while `:382` *does*
cap `anchor` at 120), and `router_payload.py:61-63` ("dimensional-not-value
discipline is a prompt instruction; the boundary type stays loose").

The only behavioural check on the ADR-0012/0014/0015 prompt clauses is
`eval/corpus.yaml` — 38 entries, live-network, quota-spending, deliberately
outside `make check`.

**The missing structure, named:** *"this behavioural clause is claimed by X"* —
where X is a code implementer (24), a corpus entry (3), an assertion (13
wording-only), or nothing (45). Today there is one guard and it verifies field
presence for 8.

Anti-seam: the four worked examples (`prompts.py:321-363`) look like fixtures
that could move to a test file. **They cannot** — they are inside the cached
`system` bucket, and the v0.19 cache-prefix invariant (`:400-401`, guarded by
`test_prompt_cache_stability.py`) makes their bytes part of the contract.
`WEBFETCH_DEFAULT_V1` (`:85-99`) is likewise immovable by design — a byte-equality
eval anchor.

## `extractor.py` holds ~200 lines its siblings are named for (M, structure)

**Source:** structural scan, 2026-07-31.

`extractor.py` is 649 lines doing nine jobs, in a package whose siblings are
literally named `prompts` and `router_payload`:

| lines | job | sibling that owns the concern |
|---|---|---|
| `:179-368` | `Extractor.extract` — 190 lines: template swap, truncation, cache read, **prompt assembly (`:243-269`)**, provider call + degrade, routing classification, cache write | prompt half → `prompts.py` |
| `:384-437` | **prompt English** — `_next_links_suffix` is 34 lines of literal instruction text | `prompts.py` |
| `:440-481` | next_links response parsing | wobble / a parse module |
| `:489-646` | **router-envelope parsing**, incl. `_build_router_payload` (88 lines) | `router_payload.py` owns every type it builds |
| `:90-103` | `LlmNextLink` boundary type | `router_payload.py` |

`judge.py` is the counter-precedent — it keeps its policy table and parse
adjacent to its consumer — but `judge.py` is 238 lines total, **smaller than
`extractor.py`'s parse block alone.**

The split is not aesthetic: it is why the prompt↔policy guard cannot see the
next_links contract (entry above). Seams, named by purpose: `build_parts(...)`
(absorbs `:243-269`, `:384-437`, and the flag-precedence rule at `:257`),
`parse_router(...)` (`:489-646`), `parse_next_links(...)` (`:384-388` +
`:440-481`), and the never-raises provider call (`:271-310`).

Anti-seams: the extraction **cache** (`:224-241`, `:341-351`) looks liftable but
its skip predicates are entangled with `request_routing`/`request_next_links` —
cache and prompt shape are one decision. And `RoutingOutcome` (`:63-87`) reads
free-standing but its four arms are only distinguishable *at* `:314-329`, where
`provider_error` and `routing_payload is None` are both in scope.

Also: `Extractor.extract` carries a precedence rule between two independent flags
(`:257`, documented over 8 lines at `:249-256` **as a shipped bug**) — a policy
the signature says is caller-controlled and the body says is not.

## five escalation decisions live outside the "single policy function" (M, structure)

**Source:** structural scan, 2026-07-31. The module says so itself.

`playbook.py:10-15`: *"the post-extraction completeness escalations — the
obstacle-driven render, the listing scroll render, and the handler
`escalate_to_render` ladder — are NOT yet planner rules; their policy still lives
in dedicated fetcher phases."*

Measured, that policy is at `fetcher.py:1204` (`escalate_to_render`), `:1828`
(forced paid render), `:2331` + `:2662-2713` (listing scroll), plus
`reddit.py:198` (eager Zyte). **A rule added to `_RULES` and a rule added to a
fetcher phase are indistinguishable to a reader** — but only `decide_next` has
the priority lattice, the caps, and the 53-test gate.

**`playbook.py` itself is not the problem, and its 513 lines are not bloat.** All
14 rules in `_RULES` (`:435-476`) are exercised, including the four whose *names*
never appear in tests. Rule uniqueness is asserted (`:518`), purity (`:526`),
totality is property-tested (`:52`). `RulePriority` (`:95-117`) is closed,
`_RuleContext` (`:120-128`) frozen, `decide_next` (`:483-499`) the sole entry.
Roughly 200 lines code / 300 comment, and the comments carry live incident
history (`:342-362` documents the jina-stripped-markdown hole). **This is what
the earlier `playbook → fetcher` co-change entry is measuring: the leak is
outward, not inward.**

Anti-seam: the seven transport rules (`:265-339`) look like a table that could
be data. They cannot — `_decide_other_4xx_escalate` (`:281`) carves 403 out
because 403 has its own rule, `_decide_uncorroborated_404_escalate` (`:315`)
inverts on `authoritative`, and `_decide_network_drop_escalate` (`:301`) depends
on which verdicts *aren't* `connection_error`. **The exclusions are the content;
a table would hide them.**

## `endpoint-auth` spec yields an UNAUTHENTICATED endpoint if followed (S, SECURITY)

**Source:** openspec drift sweep, 2026-07-31. Verified.

`openspec/specs/endpoint-auth/spec.md` writes its OAuth variables bare —
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_BASE_URL`,
`GOOGLE_REQUIRED_SCOPES`, `GOOGLE_REDIRECT_PATH` — in 8 places (`:8`, `:12`,
`:17`, `:33-34`, `:41`, `:58`, `:64`).

`settings.py:92` sets `env_prefix="A2WEB_"` and the fields are `google_client_id`
/ `google_client_secret` / `google_base_url`, so the real variables are
**`A2WEB_GOOGLE_*`**.

**Failure mode:** an operator follows the spec, sets `GOOGLE_CLIENT_ID`, the
settings field stays `""`, a2web reads that as "not configured", and the spec's
own branch — *"When it is not configured, no auth provider SHALL be passed and
behavior SHALL be unchanged"* — makes a **publicly reachable, unauthenticated
MCP endpoint** look like correct intended behaviour. Silent, and the spec
explains away its own symptom.

Deploy-time security consequence, not documentation drift. Fix the spec; and
consider making `serve_http_main()` fail loudly when it finds bare `GOOGLE_*`
set in the environment while its own `A2WEB_GOOGLE_*` are empty — the
misconfiguration is detectable at boot.

---

## `_ttl_for` caches almost everything for 7 days (S, correctness — LIVE)

**Source:** threshold audit, 2026-07-31. Measured against `AppSettings()`:

```
text/html             ->   24 h
application/json      ->  168 h
text/markdown         ->  168 h
application/atom+xml  ->  168 h
""  /  None           ->  168 h
```

`fetcher.py:263 _ttl_for` routes everything non-HTML — **including an absent
content-type** — to the 7-day static TTL. The jina tier sets
`content_type="text/markdown"` (`jina.py:119-192`), so **every jina-served page
is cached for a week.** `handlers/_common.py:46` and `reddit.py:181` set `""`;
discourse/github/habr/hn/v2ex set `application/json`; `arxiv.py:107` sets
`application/atom+xml`. **Only wikipedia gets the 24h article TTL.** Reddit and
HN escape only because `live_only_hosts` bypasses cache entirely — GitHub issue
lists, Discourse forums, Habr threads, arXiv listings and firecrawl renders do
not.

Fail-unsafe by default: an unknown content-type gets the LONGEST TTL.

`_ttl_for` has **zero tests** — every TTL test (`tests/capabilities/cache/test_cache.py:48,75,99`)
hard-codes `ttl_s=3600`, exercising storage and never policy. Perturbation:
`cache_ttl_static_h` 168→336 = 0 failures; `cache_ttl_article_h` 24→48 = 0.

While here: **`cache_ttl_live_m = 5` is dead code** — read nowhere (`is_live_only`
does a full cache bypass). An operator setting `A2WEB_CACHE_TTL_LIVE_M` gets
nothing. Delete or wire it.

Also `fetcher.py:267-268` uses `getattr(settings_obj, "cache_ttl_article_h", 24)` —
renaming the setting silently falls back to a hard-coded default instead of
failing.

---

## `_MAX_RECORDS` × `DEFAULT_TOLERANCE` dead zone (S, correctness — ADR-0009 LIVE)

**Source:** threshold audit, 2026-07-31. Measured:

```
total 50 -> ready     total 55 -> ready     total 56 -> partial
```

`fc.record_count = len(record_set.records)` (`fetcher.py:1731`) is the
**post-cap** count. For any listing advertising **51-55 items**, `_MAX_RECORDS=50`
truncates `loaded` to 50, `DEFAULT_TOLERANCE=0.9` clears it as `ready`, and
`listing_partial` never fires — **the caller is told the listing is complete
while 1-5 items were dropped.**

Shelf ledger 0074 admits the reported shortfall is IMPRECISE above 50. It does
not admit the shortfall can VANISH. A silent miss produced by two independently
ASSERTED constants interacting — neither wrong alone. `_MAX_RECORDS` is
INHERITED from a2web's own unexplained `domain.py:285,439` `[:50]`;
`DEFAULT_TOLERANCE`'s cited validation was a 489/7899 read (6%), which never
exercises the 90% boundary.

Witness: `_MAX_RECORDS` 50→100 = **0 failures** — the direction that would fix
the ledger bug is unwitnessed. `DEFAULT_TOLERANCE` is witnessed (9 failures at
0.45) but every test case uses loaded values far below 50, so the dead zone is
untested. Add the boundary test first, then decide whether the cap or the
tolerance moves.

---

## 22 constants can be doubled with zero test failures (M, verification)

**Source:** threshold audit, 2026-07-31. Method: rewrote each constant's SOURCE
LITERAL through a `sys.meta_path` loader (catches `from x import CONST` bindings
that attribute monkeypatching misses), 50 perturbations, full suite each.
Baseline 1274 passed.

**29 of 50 perturbations changed nothing.** Of ~60 audited constants, **three**
are genuinely measurement-derived (`zyte._TIMEOUT_S=60.0`,
`_RENDER_CONTENT_CEILING=2000`, `BLANK_HTML_THRESHOLD=32`); one is externally
sourced (`WEBFETCH_HTTP_TIMEOUT_S`); two are weakly corpus-tuned. Everything
else is ASSERTED or INHERITED.

**Worst: `_HEADING_FRAC_MIN = 0.50`** (record-mine `detector.py:62`) —
**unwitnessed in BOTH directions** (0.25 = 0 failures, 1.00 = 0 failures). At
1.0 every record must carry an `h1`-`h6`, so record detection dies on any
listing using `<div>`/`<span>` titles — most e-commerce grids. Silent:
`record_count` stays `None`, removing the ADR-0015 index AND the ADR-0009
completeness signal at once, with no diagnostic. Its own design doc
(`2026-05-22-structural-record-detection`) says *"corpus-tuned (10 pages) —
widen the benchmark corpus and retune if a real miss appears."* Never retuned.
Related: the shelf implementation dropped `[role=heading]`, a silent divergence
from the normative text in `openspec/specs/record-extraction/spec.md`.

`_CONSISTENCY_MIN = 0.70`: 0.95 = 0 failures, 0.35 = 1. Same capability-off
shape — 0.95 kills detection on any listing with mixed card types (sponsored /
promoted rows).

**`LENGTH_FLOOR = 500`'s test is endogenous.** `tests/capabilities/extraction/test_wire_content_md.py:17`
is `assert len(_PROSE) >= LENGTH_FLOOR` — a fixture sized FROM the constant. It
can only confirm the fixture agrees with it. This is the single most
load-bearing number in the product (gates quality-gate, extraction,
retrieval-completeness, browser escalation, empty-vs-wall) and it is ASSERTED,
day-one, with no comment.

**Every timeout is unwitnessed** — raw 10→20, jina 15→30, archive 12→24 all = 0
failures. Archive's 12 applies to THREE sequential fetches (CDX → wayback →
archive.ph), so the real worst case is ~36s.

**`firecrawl._TIMEOUT_S = 40.0` is a stale twin of a disproven number.** Zyte's
identical 40.0 was MEASURED to fail under concurrent load (`2bf60ca`: *"one
Reddit cell got zyte ok in 7.9s, a concurrent one timed out at 40.3s and fell to
a weaker fallback"*) and raised to 60. Firecrawl renders server-side the same
way, kept 40, and still carries the "generous headroom" comment that was
falsified for its sibling. Propagate the correction.

**Silent truncation with no shortfall signal.** `arxiv.py:297 entries[:25]` is
the ONLY cap in the codebase that reports its own truncation (`Papers (25 of
408)` + a partial-view note), and its docstring cites the bench measurement that
forced it. The same failure is live one file over:

| constant | reports shortfall? | witness |
|---|---|---|
| `habr._MAX_COMMENTS = 400` | **no — stops mid-tree, no count, no total** | 0 failures |
| `hn._ALGOLIA_SEARCH_HITS_PER_PAGE = 30` | **no — Algolia returns `nbHits`, ignored** | 1 |
| `v2ex._MAX_REPLIES = 200` | post-truncation count only (full `replies` in hand, discarded) | 0 |
| `discourse._MAX_TOPICS = 50` | post-cap count only | 0 |

All four landed in one commit (`7b1abdd`) with no openspec, ADR, findings or
CHANGELOG derivation. Port the arXiv `N of M` pattern; `hn` and `v2ex` already
hold the total.

**Cross-cutting:** `listing_scroll_cap = 8` and
`any_browser.playwright._SCROLL_STABLE_MAX_PASSES = 8` are two independent 8s
for one concept; `_THIN_BROWSER_MAX_BODY = 1_024` and
`any_browser.playwright._THIN_FLOOR = 4_096` are two browser-thinness floors
**4x apart in the same render path**; four unrelated 500s
(`LENGTH_FLOOR`, `_MAX_RECORD_CHARS`, `_ENTITY_VALUE_CAP`,
`extractor._PROVIDER_ERROR_MAX`) with no stated linkage; and
`openspec/specs/link-discovery/spec.md:37`'s single "capped at 10" invariant is
implemented as four hardcoded literals (`arxiv.py:317`, `hn.py:169`,
`reddit.py:612`, only `wikipedia._WIKILINK_CAP` named), so the spec's cap cannot
be changed in one place.

**Two self-declared soft values worth acting on:** `_ENTITY_ARRAY_CAP = 10` is
documented as *"a starting guess… adjust at implementation time if a real
fixture suggests otherwise"* — no fixture ever revisited it. And
`_CORROBORATION_THRESHOLD = 2` is already known-wrong at `BACKLOG.md:428` (counts
OBSERVATIONS, not INDEPENDENT EGRESSES), which **directly contradicts the word
"independent" in the code comment at `terminal.py:72`**.

**Doc drift found here:** CLAUDE.md:73 says browser is "capped at 1/fetch";
`playbook.py:156,172,260` caps at `< 2` (fast → robust rungs).

---

## there is no CI on push or PR (S to fix, L in consequence — READ FIRST)

**Source:** doc-drift sweep, 2026-07-31. Verified: `.github/workflows/` contains
exactly one file, `release.yml`, and its trigger is:

```yaml
on:
  push:
    tags:
      - "v*"
```

**Every guard in this backlog runs only when a version tag is pushed.** Not on a
branch, not on a PR, not on a merge to main. CLAUDE.md:20 states the shelf guard
"runs in `make check` and therefore on CI" — it does not, on the events where
regressions actually arrive.

This reframes every other verification entry below: the goldens, the endogenous
fixtures, the missing wire witnesses are all weaker than they look, because the
gate they hang from does not fire. **Fix this before investing in any individual
guard** — a stronger assertion on an ungated pipeline buys nothing.

---

## two named guards answer a different question than advertised (S, verification)

**Source:** doc-drift sweep, 2026-07-31. Both verified by reading the tests.

1. **`test_packages_boundary_frozen.py`.** CLAUDE.md:249 and
   `docs/architecture/README.md:73` both state it pins `packages/*/__init__.py`
   `__all__`. It asserts `@dataclass(frozen=True)` + slots on `BlockResult` and
   `EscalationSignal`. **The word "frozen" is doing double duty across two
   unrelated invariants.** Only one package has an `__all__`
   (`packages/llm_extract/__init__.py:55`) and it is unguarded. Precisely the
   shape `close-silent-enforcement-loss` was created to kill.

2. **`test_transient_markers_not_stale`.** `grep -rn "TRANSIENT ("` over `src/`
   and `tests/` returns **0** outside the guard itself. The population is empty,
   so the guard cannot fire — while `verification-provenance.md:26` lists it as
   one of three mechanizable remedies for mechanism-B rot. Its non-vacuity test
   proves the archive LOOKUP resolves, not that any marker exists. A guard
   reporting "0 violations in 0 candidates", named as coverage, inside the very
   doc that names that pathology.

Adjacent: **`pytest-archon` is a declared dependency used by zero tests**
(`pyproject.toml:223-226`, ADR-0001:60, CLAUDE.md:243 — "the pytest-archon
`json.loads`-ban will close this loop"). Every architecture guard is hand-rolled
`ast`. An auditor sees an installed library plus a promise.

And **the rules registry is 10 of 33.** `docs/architecture/README.md` omits 23
existing guards including `test_one_composition_root`, `test_cold_start_laziness`,
`test_trafilatura_funnel`, `test_handler_markup_funnel`,
`test_tach_covers_every_package`. The documented "adding a rule" workflow has a
step for CLAUDE.md and none for this table — which is why it rotted.

**`json.loads` scope gap, corrected.** The handler sites
(`discourse.py:78`, `habr.py:127`, `v2ex.py:110`, `hn.py:100`,
`tiers/archive.py:82`) parse SITE API JSON and are benign. The real hole is that
CLAUDE.md names five LLM-contract-parsing sites and **two live outside the
walked root** (`test_json_loads_funnel.py:30` walks only
`src/a2web/packages/llm_extract/`): `llm_eval/bench_judge.py` and
`fetcher_response.py::_project_routing`. A future LLM-JSON parse at either
bypasses the funnel with the guard green.

---

## openspec canonical specs contradict shipped code (M, docs — 4 load-bearing)

**Source:** doc-drift sweep, 2026-07-31.

Dominant cause: two structural migrations landed with no spec sync — the
`anyllm` adoption (`ee2452c`, shipped BREAKING, updated no spec) and the shelf
promotions that emptied `packages/`.

| spec | asserts | code |
|---|---|---|
| `provider-selection:22,34-37,100-107` | `openai_compatible` is LAST in auto order so it "can never shadow a working Claude/Anthropic path" | `llm_resource.py:71-74` `_GATEWAY_FIRST_ORDER` puts it **FIRST** when `OPENAI_API_KEY`+`OPENAI_BASE_URL` are both set — **a live routing invariant inverted** |
| `endpoint-auth` | writes every env var bare (`GOOGLE_CLIENT_ID`) | `env_prefix="A2WEB_"` applies — **an operator following it literally gets an UNAUTHENTICATED endpoint** |
| `browser-tier:180,192-195` | the smoke check SHALL auto-skip when the binary is unavailable | `test_browser_smoke.py` hard-FAILS under `A2WEB_REQUIRE_BROWSER=1`; following the spec re-opens the dead-rung hole the guard closes |
| `tier-pipeline:8,84-96` (+ `site-handlers`, `raw-tier`) | requires `tier_extras: dict[str, Any]` | CLAUDE.md says never reintroduce it; `test_no_dict_str_any_on_dataclasses.py` fails on it |
| `extraction:103-152` vs `content-expectations:48` | contradict EACH OTHER on candidate selection | and both contradict `fetcher.py:1541-1586` |
| `output-benchmark`, `openai-compatible-provider` | prescribe the invalid provider ids as normative config | see the provider-ids entry |

Nine `openspec/specs/` sites still cite the deleted
`tests/test_packages_independence.py` — `close-silent-enforcement-loss` fixed
that citation in CLAUDE.md only, because the guard it built reads CLAUDE.md
alone.

**Cheapest high-value fix:** two fully-implemented changes were never archived —
`narrow-the-pre-rendered-extraction-skip` (27/27) and
`restore-links-on-pre-rendered-tiers` (25/25). Their delta specs already contain
corrected text for `tier-pipeline`, `extraction`, `link-affordances`,
`listing-completeness`, `link-discovery` — including the `tier_extras` fix.
Sync those, then sync `provider-selection` + `openai-compatible-provider` +
`output-benchmark` for `ee2452c`.

**Refuted hypothesis, recorded so it is not re-checked:** `handler-live-probe/spec.md`
is one of the MOST current specs in the tree (rewritten by
`2026-07-28-probe-asserts-yield-not-reachability`, matches `handler_probe.py`
requirement-for-requirement). Its only defect is a `_HANDLERS` registry name with
zero hits.

---

## CLAUDE.md describes a different system than the one shipped (S, docs)

**Source:** doc-drift sweep, 2026-07-31. CLAUDE.md is the map every agent reads
first; each of these sends a reader somewhere wrong.

**Load-bearing:** CLAUDE.md:119,125 — *"The container is deliberately slimmed —
no `[browser]`/`[cookies]`/`[claude-code]` extras — so a served a2web has no
local browser."* `release.yml:92-94` builds and pushes with
`INSTALL_BROWSER=true`; `Dockerfile:9-13` and `README.md:332-334` both describe
the published image as browser-baked (~1.9 GB). Three sources agree against
CLAUDE.md. An agent reasoning "the served instance cannot browser-escalate"
routes wrong. (`openspec/specs/container-image:20-27` errs the OPPOSITE way,
asserting Chromium unconditionally while a default `docker build` ships none.)

**Structural, misleads anyone reasoning about ordering:** CLAUDE.md:72 says
`_run_pipeline` is "a 12-line coordinator calling six named phases". It is **47
lines calling twelve**, and `_phase_cache_write` is NOT terminal — three
promotion/terminal steps run after it.

**Inventory drift:** 9 site handlers documented as 5 (`:69`); the **zyte tier and
the `browser_robust` rung are absent entirely** while `_PAID_TIER_ORDER =
("zyte", "firecrawl")` puts zyte first (`:70` says only "`paid.py` (Firecrawl
env-gated)"; the files are `_paid.py`, `firecrawl.py`, `zyte.py`); 8 tier
manifests documented as 5; `_manifests/llm_providers/` listed as a live plugin
surface (`:85`) but the directory is empty with no `load_surface` targeting it;
`domain.py` described as "pure functions too small for their own files" (`:75`)
when ~370 of 551 lines are a structured-data renderer.

**Dead/renamed symbols:** `_apply_after_tier_action` / `_AfterTier` (now
`_dispatch_action` / `_Exec`; survive in test comments at
`test_fetcher.py:360,384`, the latter claiming to test "the
`_apply_after_tier_action` contract"); `next_action_after_gate` /
`next_action_after_tier` (now `decide_next(log, *, url, caps)`);
`ExtractionCache` (now `LlmCache`); the tool registered as `refresh` but called
`cookies_refresh` in CLAUDE.md:119, `settings.py:239,253`, `README.md:367-368`.

**Why the citation guard missed these:** `test_claude_md_citations_resolve.py:61`
requires a file suffix, so it checks 43 of 78 path-shaped citations and **no
directory citation at all** — which is why CLAUDE.md:29,81 can cite
`openspec/changes/sunset-a2kit-dependency/` and `.../shelf-sweep-promotions/` as
read-this-first gates when both moved under `archive/` with date prefixes.
Widening that regex is the cheapest fix in this entry.

Also `CLAUDE.md:31` names `a2kit-v043-migration/` as the most recent archived
change; it is one of ~55 older ones (latest is `2026-06-19-a2kit-v044-migration`).
And `CLAUDE.md:249`'s "aiosqlite worker thread doesn't leak" — the test asserts
the conftest TEST-ONLY daemon patch is applied and says nothing about production.

---

## stale provider ids break a documented boot (S, correctness — LIVE)

**Source:** doc-drift sweep, 2026-07-31.

`ee2452c` (HEAD, 2026-07-27) adopted `anyllm.ProviderName` and its own commit
body says the old ids no longer validate. The sweep reached `Makefile` and
CLAUDE.md; it missed four places, three of which are copy-pasteable:

| site | says | truth |
|---|---|---|
| `README.md:305` | `A2WEB_LLM_PROVIDER` accepts `anthropic` / `claude-code` / `openai_compatible` | all three `ValidationError` at settings load |
| `README.md:429` | `A2WEB_BENCH_PROVIDER=anthropic make bench` | `anthropic-api` |
| `settings.py:205-206`, `:223` | same three ids, as the documented menu | contradicts `settings.py:37` 170 lines above |
| `eval/model_benchmark/run.py:96` | sets `"openai_compatible"` — **live code, not a doc** | `openai-compatible` |
| `llm_resource.py:11-21`, `:56` | same menu + a `claude-code`→SDK mapping | no such id to map from |

Measured: `AppSettings(llm_provider="anthropic")` → `ValidationError`.
Mitigating for ADR-0016: it fails LOUD at resolution rather than silently
falling through to metered billing. Note README is clean on env var NAMES —
every `A2WEB_*` in its deployment matrix resolves to a real `AppSettings` field;
it is the documented VALUES that are dead.

Second-order: **ADR-0016 and CLAUDE.md now contradict each other in front of the
reader.** ADR-0016:22,33 carries `claude-code` / `anthropic` /
`packages/llm_cost_guard.py`; CLAUDE.md carries the corrected
`claude-code-sdk` / `anthropic-api` / shelf `anyllm.cost`. Both are
correctly-dated records, so neither is drift by the stated rule — but ADR-0016
is cited as LIVE doctrine from CLAUDE.md and `verification-provenance.md:131`.
Same shape at ADR-0014:21,45 (`NextUrl.off_domain` → `OtherPage.off_domain`,
folded by ADR-0015, with no "superseded by" pointer on 0014). The underlying
symbols all survive: `assert_within_budget`, `CostPolicy`, `CostViolation`,
`with_cost_guard` are exported by `anyllm.cost`. Suggests ADRs cited as live
doctrine need a superseded-identifier pointer, not a rewrite.

---

## two cited architecture guards do not exist (S, verification)

**Source:** doc-drift sweep, 2026-07-31.

1. `docs/architecture/README.md:66` lists **`tests/architecture/test_no_lambdas_in_app_provide.py`** in the LIVE "current rules" table (repeated at `:15`). The file does not exist; `app.provide` died with a2kit on 2026-07-22. The manual's own "Removing a rule" section requires deleting the file AND the docs — half was done. A reader adding a lambda believes CI catches it. This is precisely the "rule that reads as coverage while providing none" pathology, inside the document that warns about it.

2. `docs/architecture/README.md:74` and `docs/architecture/verification-provenance.md:70-71` cite **`tests/packages/test_zendriver_backend.py::test_fake_config_matches_real_add_argument`** as the standing fake-fidelity contract AND as the reference implementation of mechanizable guard #1. Neither file nor function exists — promoted to the shelf with `any_browser`, no a2web-side successor.

(2) is the higher consequence and the sharper lesson: `verification-provenance.md`
lists exactly three mechanizable guards, and then reasons FROM the existence of
this one — *"H1 + the wire golden gate + the standing fake-fidelity contract
already bought most of the endogenous-oracle risk down"* — to advise spending
marginal effort elsewhere. A live budget recommendation resting on a guard that
is not there, and the failure it was built to catch (the dead `--no-sandbox`
rung, cited twice in the same file) is exactly the class now unguarded.

**The doc that codifies the foreign-provenance rule fails it.** Worth an entry
in that doc itself, not just a fix.

The two SURVIVING guards were verified real and correct: `_walk.walked_files(minimum=…)`,
`test_transient_markers_not_stale` (which carries its own non-vacuity test), and
the `browser-gate` CI job (`publish` genuinely `needs: [gate, browser-gate]`;
the smoke test `pytest.fail`s rather than skips under `A2WEB_REQUIRE_BROWSER=1`).

---

## naming rot: `_prescribe_browser_on_wall` (XS, cosmetic)

Cited in present tense at `fetcher.py:1839,1919` and `fetcher_response.py:388,429`
as the live emitter of the `try_user_browser` floor. The symbol does not exist.

**Behaviour is intact** — `_apply_terminal` (`fetcher.py:1973`, called at `:2349`,
second-to-last statement of `_run_pipeline`) runs the floor, and
`fetcher_response.py:435` reads the resulting hint. Renamed by
`2026-07-15-fetch-failure-semantics`, which updated `terminal.py`'s history
docstring and missed four consumer comments.

Cost is navigational: four comments name a grep target that returns zero hits.
Recorded explicitly because an earlier reading of this session blamed it for the
`paid_auth_error` hole; it is not the cause.

**Worst of this group is not that rename.** `state.py:144` claims, present
tense: *"Registered in `server.py` as `app.provide(Provider, build_selected_provider)`."*
`server.py` has no `provide`; the factory is wired in
`components.build_components()`. The docstring names the WRONG FILE and the
WRONG API for the composition root — pointing a reader at exactly the
parallel-root violation `test_one_composition_root.py` exists to prevent.
`cookie_jar.py:9` is the same shape one file off. Eleven a2kit-API comment sites
survive in `src/`; the four in `components.py`/`server.py` are explicitly
past-tense migration tables and are fine.

Same class, same fix pass: `twitter.py:144` `_attach_failure_floor`;
`log.py:251` `build_app()` (→ `server.build_mcp_server`); `_policies.py:4`
`JUDGE_VERDICT_POLICY` (→ `_JUDGE_POLICY`); `settings.py:242` `CookiesRouter`;
`fetcher_response.py:408` `_extract_answer` (→ `_phase_extract_answer`);
`content_expectations.py:29` `TOLERANCE` (→ `DEFAULT_TOLERANCE`).
Also `CONSTITUTION.md:427` / ADR-0001:61 cite `tests/test_packages_independence.py`
(replaced by Tach); `CONSTITUTION.md:488,491` cite `AGENTS.md` and
`docs/PROMOTION_AUDIT.md` (neither exists) — but that file is a declared verbatim
a2kit copy, so the fix belongs upstream.
`BACKLOG.md:539-543` names `make bless-contracts` / `test_contracts.py` /
`tool_schemas.json` / `ask_success_rich.json` — all four nouns stale.
`docs/architecture/cloudflare-handling.md` is present-tense and turn-key-framed
over `packages/browser_pool.py` (gone), Camoufox-as-default (gated off
unconditionally), `tiers/paid.py` (never existed), and an `assets/` specimen with
no `assets/` dir; its Layer-2 half verifies clean, which makes the rotted half
more likely to be trusted.

---

## `paid_auth_error` has no operator hint (S, correctness — LIVE DEFECT)

**Source:** encapsulation scan, 2026-07-31.

Not a rot risk. Already broken. A keyed paid tier rejecting our key today ships
`status: failed` + `retrieval_incomplete: true` + narrative + diagnostics and
**zero operator hints** — the one signal that would say "fix your key" does not
exist.

`grep -n 'code="' src/a2web/models.py` returns 10 hint factories; none is
`paid_auth_error`. Two chokepoints each stand down believing the other covers
it:

- `fetcher.py:1994` — *"`operator_error` / `unreachable` → no hint here
  (paid_auth_error carries its own)"*
- `fetcher_response.py:390` — *"Only `paid_auth_error` is special: it keeps its
  OWN dedicated hint... instead of `try_user_browser`"*

CLAUDE.md's Never clause requires it verbatim: *"a critical `try_user_browser`
operator hint (**or `paid_auth_error` when a keyed paid tier's key is bad**)"*.

`test_paid_escalation.py:183-200` asserts the verdict and diagnostics, never a
hint; `test_never_silent_miss.py:104` asserts exactly-one `try_user_browser`,
which this branch deliberately does not emit. So both witnesses pass.

Fix is small (one factory + one emission site). The lesson is not: this is the
same shape as the listing oracle — a capability whose only description was a
comment referring to something that was never written.

Also waived by a guard: `tests/architecture/test_terminal_hint_coherence.py:33`
declares `operator_error: frozenset({None})` with the comment "emitted at the
paid tier". That file declares `_COHERENCE` inside itself and asserts properties
OF THAT LITERAL — it never reads `fetcher._apply_terminal`. A spec-consistency
test wearing an enforcement test's clothes.

**Not** caused by the `_prescribe_browser_on_wall` naming rot (logged separately
below) — that drift is cosmetic and the wall floor it describes is intact.

---

## invariants with no code implementer (M-L, structure)

**Source:** encapsulation scan, 2026-07-31. Ranked by exposure.

Each is a stated first-class invariant whose enforcement is prose, or whose
test asserts the fixture rather than the behaviour.

| # | invariant | where it "lives" | why it can die silently |
|---|---|---|---|
| 1 | **ADR-0012** never manufacture a selection | `prompts.py:202-209` — English only | sole `make check` assertion is that a corpus entry EXISTS (`test_corpus_subset_and_selection.py:52`). Delete the paragraph, suite stays green. Behaviour judged only under `make bench`, which is not run by default. |
| 2 | **ADR-0014** never surface an ungrounded URL | `link_digest.py` + a second, unrelated substring check at `fetcher.py:2536` | no end-to-end witness. The one wire test (`test_router_wire.py:122`) feeds a raw model-typed URL and asserts it REACHES the wire — pinning the escape hatch open. Its stub page is prose-only, so no digest is built and both rehydration sites are inert: the capability can be entirely off, green suite. |
| 3 | `structural_form` — the unnamed master switch | six independent proxies (`extractor.py:538`, `fetcher_response.py:628`, `fetcher.py:2355`, `domain.py:41`, `block_detector.py:249`, `fetcher_response.py:234`) | `wobble/_policies.py:34` defaults it to `None` BY POLICY. Model stops emitting it → `options` and `refinement_axes` permanently empty, silently. Every listing test hand-feeds the value. This switch also gates #1's only visible artifact. |
| 4 | **ADR-0015** index loss | `fetcher_response.py:311-355` `_index_loss_hint` | the docstring (`:326-333`) argues the gate must be on the DELIVERED index; `:341` then returns early unless routing was unparsable, making that check unreachable on the OK path. A clean envelope with `also_here: []` fires nothing — and `prompts.py:181-184` records that harm already happening live. A named guard that reads as coverage and does not cover the failure that occurred. |
| 5 | handler wall check | `handlers/_common.py:80` `challenge_verdict` | adopted by 2 of 9 handlers (`twitter`, `wikipedia`). JSON-API handlers are genuinely N/A. **Real gap: `arxiv.py:136-165`** decodes HTML, parses it, returns `Verdict.ok`, no challenge check — a Cloudflare interstitial renders "Papers (0)" as success, in the same handler that already shipped a silently-dead parser. No AST guard asserts adoption. |
| 6 | breakers / proxy routing | `fetcher.py:1086-1140`, `tiers/raw.py:92` | answered only inside the tier loop. Browser (`:2111`), paid (`:2216`), archive (`:905`), jina (own client) and 8 of 9 handlers bypass both. No test asserts a breaker ever opens or that a configured proxy is applied. Silent death = proxies stop applying and the resulting blocks get blamed on anti-bot. |
| 7 | `domain.py` (inverse case) | ~370 of 551 lines are a complete structured-data→markdown renderer (the `json_synth` rung) | CLAUDE.md:75 describes the module as "pure functions too small for their own files". Mis-documented and un-findable, but genuinely WITNESSED (`tests/capabilities/json_extract/`, two architecture tests) — so low severity. |

**The template for fixing all of them already exists in-repo.** ADR-0009 is the
counter-example: `actions/terminal.py::classify_terminal` is named after the
QUESTION, pure, total over a closed enum, one chokepoint (`_apply_terminal`),
six test files. The archived `2026-07-11-prescribe-browser-on-any-wall` change
is the record of collapsing three scattered emission sites into it. This smear
was found and fixed once; it was not reapplied elsewhere.

Caveat on that counter-example: the ADR-0009 four-signal conjunction is itself
never asserted as executable code — only byte-equality against a re-blessable
golden (`A2WEB_ACCEPT_WIRE_DELTA`), with `test_no_golden_is_degenerate` checking
only non-emptiness and `len(text) > 20`. That gap is exactly how the
`paid_auth_error` hole got through.

---

## the corpus cannot see the envelope (L, verification — HIGHEST LEVERAGE)

**Source:** corpus negative-space scan, 2026-07-31.

`JUDGE_V1` (`prompts.py:409`) has three slots: `{ask}`, `{content}` (= the
criteria list), `{answer}`. **The page is never in the prompt.** The instruction
says "penalize fabrication" to a judge with no ground truth.

Axes and what each can read: quality → answer prose; clarity → answer prose;
next_links → the `other_pages` TSV block only; contract → the full envelope, but
asserts exactly 5 SHAPE rules, never semantics. Nothing reads `also_here`,
`options`, `refinement_axes`, `obstacle`, `operator_hints`, `diagnostics`,
`confidence`, or `status` semantics.

**33 of 115 criteria are addressed to a reader that does not exist.**

Invariants with ZERO catching cells: ADR-0009 wire half (1 offline only),
ADR-0014, ADR-0015, ADR-0017, empty-vs-wall, tier-truthfulness wire half,
listing `options` shape, never-cache-below-the-gate, ADR-0013 handles. **Nine of
twelve.** ADR-0012 is the one healthy invariant (4 cells, prose-level,
genuinely catchable) — and it is the one with no code implementer, so it is
witnessed exactly where it is not enforced.

The 21 anti-fabrication criteria are decorative, and `_NEXT_LINKS_TEMPLATE`
explicitly instructs *"never penalize an entry for being unfamiliar or assume it
is fabricated"* — the one axis that reads URLs is told not to suspect them.

**The fix is mostly wiring that already exists.** `tests/eval_replay/replay.py::assert_contract`
already supports `status`, exact `operator_hints`, `tier`, `next_links_min`,
`content_includes/excludes`, `input_menu_includes/excludes`. It is used on 7
offline cases, 5 of which assert `status: ok` — the failure taxonomy has ONE
frozen witness in the repo. Wire that vocabulary into the live bench as a
per-cell deterministic assertion block and 33 dead criteria become live.
Second: pass the fetched page to the quality judge so "does not fabricate"
becomes checkable.

Also add `retrieval_incomplete` + `narrative` to `replay.py::observe()` — they
are not in the projection, so the akakce wall baseline can never regress on them
and is not the second witness it appears to be.

**Language over-fit, measured:** English 26 / Turkish 9 / Russian 1 / Chinese 1.
**Every commerce, wall, empty-vs-wall and 404 case is Turkish.** No non-English
listing, no non-English wall, no non-English 404. Zero RTL, JP/KR, or
non-English-European. Archetypes with zero coverage: PDF, login-wall, metered
paywall, geo-block/451, cookie-consent interstitial, JSON content-type,
data-table page, infinite-scroll feed, redirect chain, video/transcript.

---

## a wire regression on ADR-0009 is one re-bless from green (M, verification)

**Source:** golden-witness scan, 2026-07-31. Measured, not reasoned.

Simulated wire-only regressions (monkeypatching `_prune_wire`, so object
attributes stay correct — the shape of a serializer bug). Baseline 1274 passed.

| regression | failures |
|---|---|
| drop `narrative` | 3 |
| drop `diagnostics_summary` | 3 |
| drop `retrieval_incomplete` | **1** |
| drop the critical hint | **1** |
| **downgrade hint `critical` → `info`** | **1** — the golden's BYTE-COMPARE, nothing else |

Turning the ADR-0009 klaxon into an informational note for every agent in the
field is one `make bless-wire SLUG=whatever` away from green.
`wire_harness.py:169` is `if ACCEPT_SLUG: path.write_text(actual)` — the slug is
never validated, and it rewrites all 12 goldens in one run.

Cause is structural: 55 `retrieval_incomplete` assertions exist and
`test_never_silent_miss.py:103-105` does assert `severity == "critical"` — but
every one reads `result.<attr>` from `fetcher.fetch()`. **None exercises the wire
projection**, the layer agents actually consume.

`test_no_golden_is_degenerate` bars only `len(text) > 20`; the real coverage is
the inline per-scenario asserts, which are good. `test_every_accepted_delta_is_real`
proves A difference persists, never THE described one (all 9 slugs currently
pass; nothing stale today).

**Fix:** lift the three inline asserts out of `test_wire_query_failure` into a
standalone wire capability test asserting all five signals PLUS
`severity == "critical"` — removing the golden from the enforcement path.

---

## the sufficiency question has no name (M, structure — ANSWERED by T1)

> **The naming half is answered by *decompose `fetcher.py` into single-purpose
> files*:** `sufficiency/` is a directory in that tree, which is what gives the
> question a structural home. What remains open here is the *contract* — what
> that node promises and how it is witnessed — which the decomposition does not
> settle. Read this entry for the contract question; take the name from T1.

**Source:** listing-machinery reflection, 2026-07-30/31 (five-agent audit).

The question *"did this fetch retrieve the whole thing, or a slice?"* is
implemented in seven places across three files and is named in none of them:

| piece | where |
|---|---|
| advertised total | `listing_oracle.py::listing_oracle` |
| "more exists" affordance | `listing_oracle.py::listing_has_more` |
| loaded-vs-total verdict | `content_expectations.py::assess` |
| wire the verdict | `fetcher.py::_phase_listing_completeness` |
| LLM fallback total | `fetcher.py::_apply_llm_listing_oracle` |
| act on it | `fetcher.py::_phase_listing_render` |
| report it | `fetcher_response.py`, `models.py` (`items_*`) |

`listing_oracle` names the **trick** (an oracle, a regex), not the purpose.
That is the whole defect: nobody could see the capability was dead because
there was no single thing to look at. It fired 4 times in the project's
history, on 1 URL, which was not a listing — and the module name gave no
surface on which that could be noticed.

**Proposed shape:** `packages/sufficiency/` owning the VERDICT only —
`assess(rendered, advertised, has_more) -> Ready | Partial | Unknown`.
Extraction stays outside (LLM `item_total_seen`, parsed JSON-LD,
`listing_has_more`): verdicts are pure, extraction is web- and site-shaped.
The abstraction is already proven — `content_expectations.assess` is shared
with Reddit comment counts, the same question with a different noun.

**Not** "page completeness loading detection": "loading" imports a
browser-mechanics assumption. jina truncating and infinite-scroll not firing
are the same verdict. `sufficiency` is the word the ADR and the phase
docstrings already use — just never a filename.

**Order is load-bearing: delete first, then name.** Encapsulating the current
pile would make broken machinery legible instead of gone. Ships after the
`_VISIBLE_COUNT_RE` deletion + the `fetcher.py:1466` ordering fix; what
survives is a verdict function and two honest signals.

---
