# What the tests caught, and what should have been substrate

**Date:** 2026-08-05 · **Scope:** the 22-commit session `3c4ad5d..9571f1d`
· **Method:** every defect below was found by mutation or by comparing a claim
against the code, never by reading code and thinking hard about it.

Two questions, answered separately:

1. **What worked** — which instruments found real defects, and why.
2. **What should be encapsulated** — where a defect existed *because* something
   was hand-rolled at the call site, and which of those are generic enough to
   promote to the shelf.

**The single largest finding is structural, and it is about the shelf itself:
the catalog holds 27 packages and every one is runtime substrate. There is no
test-time or verification-time package at all.** Yet this session's entire yield
came from verification instruments, each hand-rolled in-repo, several of them
now written two or three times with quietly diverging details. That is the gap.

---

## 1 · Every defect, and whether encapsulation would have prevented it

Read the last column as: *would the bug have been possible if this had been a
typed seam instead of code at the call site?*

| # | Defect | How it was found | Why it was possible | Encapsulation verdict |
|---|---|---|---|---|
| 1 | **`{{n}}` handle leaked to the caller** (ADR-0013/0014). A prose-only page has no link digest, so `_build_link_digest` returns `None` — but the prompt clause teaching the `{{n}}` convention ships unconditionally. That branch passed model-emitted handles through verbatim. | Reading CLAUDE.md's claim that the answer "is rehydrated in BOTH branches" and checking it | The digest owned `rehydrate_text`; **nobody owned the no-digest case**. `Optional[Digest]` put the decision at every call site. | **YES — null object.** An `EmptyDigest` whose `rehydrate_text` is `strip_handles` makes the leak unexpressible. `None` for "no digest" is the bug's enabling condition. |
| 2 | **`retrieval_incomplete: true` with zero operator hints** (ADR-0009). The loudest failure signal could ship silent. | Auditing ADR-0009's stated floor against `build_response` | The envelope permits an incoherent field combination; coherence lived in prose. | **YES — construction-time.** Three fields that must co-vary should be one constructor, not three assignments a builder is trusted to make together. |
| 3 | **A `304` with no cached row became an empty `ok`.** Body empty, `Verdict.ok`, narrative `raw → ok (9ms)` — the ADR-0009 harm exactly. | Cassette replay diverging from live | 304 semantics were inline in a 219-line loop, 80 lines from the validators that caused them. | **YES.** Now `retrieval/conditional.py`. Both branches live together because they answer one question. |
| 4 | **The eval cassette froze a 304.** The recording captured a conditional response and replayed it to a run that had no cache. | The above, chased upstream | Cassette record/replay is hand-rolled; nothing forbade recording a response meaningless without its request context. | **YES — shelf candidate (K).** A cassette that stores a 304 without its validators is a broken cassette; the mechanism should refuse at record time. |
| 5 | **A failed archive dispatch left no diagnostic row.** The caller saw a gap where an attempt was. | Backlog entry 1.3, verified | `diagnostics.append` sat *below* the success check. Ordinary statement-order bug. | Partly. A `with attempt(...)` scope that records on both exits removes the class. |
| 6 | **The never-cache-below-the-gate invariant had no test at all.** | Enumerating ADR invariants against test files | Nothing linked the invariant to a test. | No — coverage gap, not a seam gap. |
| 7 | **The deadline path had zero coverage**, and mutation showed deleting one `fc.observe(...)` kept every ADR-0009 signal firing while `resolved_verdict` silently degraded `timeout` → `other`. | Mutation, after writing the test | Observation and diagnostic are two calls that must agree; nothing paired them. | **YES.** Same fix as #5 — one `attempt` scope emitting both. |
| 8 | **A required-but-dead proxy could be bypassed** to a direct connection, silently violating operator policy. | Coverage hunt on `tier_walk.py` | Lease acquisition and its failure semantics were inline. | **YES.** Now `retrieval/proxy_lease.py`. |
| 9 | **The ADR-0014 drift validator was never proven wired.** The helper was tested; the call site was not. | Auditing the invariant→test map | Helper-tested, wiring-untested. **Found four separate times this session.** | No single seam — this is a *test-design* failure, addressed by proposal (C). |
| 10 | **The content-install chokepoint did not exist.** `_install_rendered_fields`'s docstring said "THE ONLY PLACE THIS COPY IS WRITTEN" — the sentence carrying the live `links` bug — while the guard written in response covered the *transport* half. | Comparing the designed tree to the shipped one | A claim in prose with no mechanism behind it. | **YES — shelf candidate (B).** The second instance of an identical AST guard. |
| 11 | **The proxy circuit breaker blamed the wrong party.** Replacing the egress-vs-origin verdict test with flat `success=False` — reporting every dispatch as a proxy failure — **passed all 1727 tests**. Three 404s would quarantine a healthy proxy for 10 minutes. | Mutation #5 of 5 on moved code | `tests/packages/test_proxy_routing.py` passes the boolean *literally*; which verdicts produce it is wiring, invisible from there. | **YES.** The classification is a parameter of a breaker, and had no owner. |
| 12 | **Three documents described three different container browsers**, all reading one `Dockerfile`. | Auditing checkable claims | Prose duplicated a build argument. | **YES.** The test now reads the default out of the `Dockerfile` and the override out of `release.yml`. |
| 13 | **`test_tools_return_pydantic_not_str` matched `@a2kit.read`** — a decorator that had not existed for weeks. Green while walking nothing. | The CLAUDE.md claim audit | No non-vacuity floor. | **YES — shelf candidate (A).** |
| 14 | **`_READS`, a 45-name AST ledger, could not distinguish two types with one spelling.** `fc.routing` is `llm_extract.RouterPayload`, not the `models.py` mirror. | `ty` rejected the annotation on the Protocol's first run | A ledger compares *names*. A type checker compares *types*. | **YES.** Protocol replaced ledger; the budget half survived as a ratchet (F). |
| 15 | **A hand-written fixture was the oracle for two dead parsers** (arXiv: 47 live entries → 0 rows; wikipedia: 1066 anchors → 0). Five green tests. | Pre-session, cited here because it is the same class | The fixture encoded the parser's assumption, authored by the same person at the same moment. | Structural: fixtures are now **captured**, and `dom-schema` exists to report *why* an extraction yielded nothing. |
| 16 | **A golden froze a typo.** `list_tools.json` preserved `~95%%` — in a description every agent reads — through 17 rounds of wire review. | Rendering the same string through `--help` | A golden proves a surface has not *changed*, never that it was right. | No seam. Design note: a golden needs a second, differently-shaped reader. |
| 17 | **TSV columns came from `rows[0]`**, deleting every key the first row elided — including `critical` on `try_user_browser`, ADR-0009's loudest hint. | `call_text` vs `call_wire` | Which fields are tables is a contract (literal); which columns a table has is a property of the rows (derived). Conflated. | **YES.** One `encode_rows` taking the union. Already fixed; the lesson is the *distinction*. |
| 18 | **30 of 32 architecture guards passed against an empty source tree.** | Pre-session; the fix is `_walk.walked_files(minimum=)` | Walk → collect → assert-empty is vacuous when the walk yields nothing. | **YES — shelf candidate (A).** The canonical sharp edge. |
| 19 | **A `sed` mutation applied 0 occurrences** and reported "All checks passed". Caught only because I printed the applied-count. | Doing it by hand, carefully | The mutation harness was `cp` + `sed` + eyeballing. | **YES — shelf candidate (C).** The highest-value proposal in this document. |

---

## 2 · Shelf proposals

Checked against the catalog (`<shelf>/catalog/README.md`, 27 packages). **None of
these overlap an existing package.** Ranked by evidence, not by appeal.

| Rank | Proposed package | Capability sentence | Evidence in this repo | Genericity |
|---|---|---|---|---|
| **1** | **`mutation-probe`** | *Stop trusting a green suite — apply a mutation to real source, assert it applied, run a command, assert it failed, restore.* | ~20 mutations run by hand this session; one silently applied zero and produced a meaningless pass (#19). Four defects (#7, #10, #11, #14) were found only because a mutation was run. | Total. Nothing about it is a2web. |
| **2** | **`guard-walk`** | *Stop writing architecture guards that pass vacuously — walk a source tree with a declared floor, so a moved root goes red instead of green.* | #13, #18. Currently `tests/architecture/_walk.py`, 40 lines, with a self-check test beside it. | Total. Every repo with AST guards needs it. |
| **3** | **`chokepoint-guard`** | *Stop letting a field group acquire a second writer — declare the set and its allowed writers, and fail when a new function assigns one.* | Written **twice** (`test_transport_install_chokepoint`, `test_content_install_chokepoint`), already diverged: one scopes assignments by receiver name, one does not. Both exist because a duplicated writer caused a live bug. | High. Any codebase with a mutable context/state object. |
| **4** | **`exemption-table`** | *Stop letting a suppression entry outlive its reason — every allowlisted item must still describe a real thing, or the table fails.* | Three instances here: `_ALLOWED_WRITERS`, the CLI contract's `_ACCEPTED`, and `test_terminal_hint_coherence` — whose `frozenset({None})` was justified by a hint that **did not exist**, and would have stayed green through its deletion. | High. Every lint/type suppression list has this failure. |
| **5** | **`registry-completeness`** | *Stop maintaining a docs index by hand — assert both directions between a document's citations and the filesystem.* | `docs/architecture/README.md` listed **10 of 34** guards. Also `test_claude_md_citations_resolve`, `test_no_a2kit_in_specs`. | High, with a thin config surface (path, pattern, direction). |
| **6** | **`cassette`** | *Stop recording HTTP interactions that cannot be replayed — refuse a conditional response whose validators are not part of its key.* | #4. Cost a full defect-chase before the mechanism was fixed ahead of the instance. | Medium-high. Real overlap with `http-cache` to reconcile at SEAM. |
| **7** | **`budget-ratchet`** | *Stop letting "reads a bit of it" become "reads most of it" — a ceiling plus a ratio, lowered whenever work earns it.* | `test_response_context_slice.py`, ratcheted 45 → 39 this session. 45-of-79 is a slice; 45-of-50 is not, at the same count — which is why a bare ceiling is insufficient. | Medium. Small package, but I have re-derived it twice. |
| **8** | **`proxy-routing`** *(evolve, not create)* | The existing a2web package plus the **egress-vs-origin classification as an explicit parameter**. | #11 — the classification lived in a call-site tuple, untested, and inverting it passed 1727 tests. | Medium. Breaker + route table is generic; the verdict vocabulary is the seam to parameterize. |

**Dependency note:** (1) is a prerequisite for the trustworthiness of (2)–(5).
A guard package's own verification lane *is* "plant a violation, assert red" —
so promoting guards without a mutation harness ships exactly the blind spot the
shelf loop's resolution 0013 forbids.

---

## 3 · Developer experience — three concrete proposals for the shelf

**3.1 · The SEAM trigger enumerates only runtime substrate, and the catalog
matches it exactly.** `docs/agent-loop.md` fires SEAM on "a helper, wrapper,
adapter, or any substrate glue — LLM / DB / embedding / git / file / format /
config / datetime / collections". Test infrastructure is not in that list, and
27 of 27 catalog entries are runtime. That is unlikely to be coincidence: the
trigger describes what gets noticed. **Proposal: add a verification category to
the SEAM trigger** — "a guard, fixture harness, golden mechanism, or anything
whose job is to make a test fail." Without it, the highest-leverage code in a
session like this one is invisible to the loop that exists to catch it.

**3.2 · The bugfix trigger's own test says these should already have promoted.**
The loop asks: *did we learn this from a bug, or from the docs?* Non-vacuous
walking (#18) was learned when 30 guards passed against an empty tree. The
mutation-applied assertion (#19) was learned when `sed` matched nothing. Neither
is derivable from any document. Both are textbook sharp edges — and both are
still sitting in `tests/architecture/` as local files, because the trigger's
examples do not look like them.

**3.3 · Provenance comments are hand-maintained prose, 27 times over.** Every
shelf pin in `pyproject.toml` carries a hand-written comment ("promoted to the
shelf and adopted back (was `packages/http_fetch`)"). That is genuinely useful
history and exactly the kind of prose this session found wrong in three
documents at once (#12). **Proposal: generate it.** The catalog already knows
each package's origin; a consumer's pin block can be a managed region — the
shelf has `managed-region` for precisely this, and does not use it on itself.

---

## 4 · What worked, and should not be changed

- **Mutation over review.** Every defect in §1 came from breaking working code
  and watching the suite stay green, or from checking a written claim against
  the code. Zero came from reading code attentively.
- **Writing the guard BEFORE the refactor.** `test_fetch_context_request_is_frozen`
  was written while the 18 fields were still mutable. A guard written after
  proves the refactor happened; written before, it proves it is still possible —
  and goes red the moment someone makes it impossible.
- **Letting the type checker drive a migration.** `ty` named every one of ~60
  call sites in the §7.2 lift and caught two of my own errors. The `_READS`
  ledger it replaced could not have caught either.
- **Guards that predict their own future.** The transport chokepoint's exemption
  comment named `retrieval/conditional.py` before that file existed; when it
  landed, the guard went red on the stale exemption before any behavioural test
  had an opinion.
- **Declining work with the reasoning recorded.** §7.2's per-node split was
  stopped short and the reopen condition written down (`tasks.md` §7.2d). A
  refactor declined without a recorded reason is re-proposed every quarter.

## 5 · What is still unverified

`make bench` has not run. Nothing in this session is evidence that a2web
*answers* better — only that it fails more loudly, and describes itself more
accurately.
