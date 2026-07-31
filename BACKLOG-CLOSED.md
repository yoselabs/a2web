# Backlog — closed

Shipped, resolved, and superseded entries moved out of `BACKLOG.md`. Kept
because the *reasoning* in a closed entry is often the reason a later change is
correct — several of these record incidents (a dead parser behind green tests, a
silently-lost eval cell) that the surviving invariants exist to prevent.

Nothing here is actionable. If an entry looks live again, move it back rather
than re-deriving it.

---
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
