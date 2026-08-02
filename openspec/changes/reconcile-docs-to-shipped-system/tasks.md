# Tasks

**Do this last.** `unify-the-response-contract` and
`decompose-fetcher-into-files` will re-invalidate the pipeline description, the
module inventory, and parts of `tier-pipeline`.

**Section 1 does not wait.** Both items are live harm, not drift. Lift them out
and ship them immediately if this change slips.

## 1. Ship now, regardless of everything else

**SHIPPED 2026-08-01, ahead of the rest of this change** (commit trailer
`fix(auth)`). Both items were live harm, so they were lifted out as the design
said to. Two things the spiking changed vs the task text below:

- 1.1/1.2 grew a CODE half. Rewriting the prose alone leaves every operator who
  already deployed on the bare spelling silently unauthenticated, so
  `server._reject_unprefixed_auth_env` now refuses to boot when auth vars are
  set without the `A2WEB_` prefix and no prefixed one is. 1.2's fail-closed
  behaviour for *partial* config already existed; it could not catch the bare
  case, because from inside `AppSettings` nothing was configured at all.
- 1.4 was NOT confined to specs. `README.md` offered the same three retired ids
  for `A2WEB_LLM_PROVIDER`, all of which raise a pydantic `literal_error` at
  settings construction — verified, not assumed. Both doc defects are now
  pinned by `tests/architecture/test_documented_env_is_real.py`.

- [x] 1.1 **`endpoint-auth` (SECURITY).** The spec writes every env var bare
      (`GOOGLE_CLIENT_ID`) while `env_prefix="A2WEB_"` applies. An operator
      following it literally gets an UNAUTHENTICATED endpoint. Rewrite with the
      prefix.
- [x] 1.2 Add the fail-closed behaviour: incomplete auth configuration must fail
      startup rather than serve unauthenticated.
- [x] 1.3 **`provider-selection`.** `:22,34-37,100-107` state
      `openai_compatible` is last so it "can never shadow a working
      Claude/Anthropic path"; `llm_resource.py:71-74`'s `_GATEWAY_FIRST_ORDER`
      puts it **first** when `OPENAI_API_KEY`+`OPENAI_BASE_URL` are both set.
      Document the promotion and its condition.
- [x] 1.4 Fix the retired provider ids in `provider-selection`,
      `openai-compatible-provider` and `output-benchmark` — the pre-rename
      spellings fail at resolution, so a documented boot is broken. Under
      ADR-0016 this is the area where a wrong belief costs money.

## 2. Sync work already done, before writing anything new

**Done 2026-08-02. The premise of this section was half wrong, and the wrong
half is the interesting one.** Both changes had been ARCHIVED on 2026-07-30 —
but archived is not synced. `openspec archive` moves the change directory; it
does not apply the delta. So the two changes sat in `archive/` looking closed
while `openspec/specs/` still carried the pre-change text, and the tasks below
read as pending work when 2.1/2.2 were the only part already finished.

That is a trap worth naming: **an archived change is evidence that work
shipped, never evidence that the spec says so.** Anyone auditing drift by
listing `archive/` gets a wrong answer with authority.

- [x] 2.1 Sync and archive `narrow-the-pre-rendered-extraction-skip` (27/27).
      Archived 2026-07-30; delta applied 2026-08-02 (1 MODIFIED requirement in
      `tier-pipeline`, 3 ADDED across `extraction` / `link-affordances` /
      `listing-completeness`).
- [x] 2.2 Sync and archive `restore-links-on-pre-rendered-tiers` (25/25).
      Archived 2026-07-30; delta applied 2026-08-02 (5 ADDED across
      `link-affordances` / `link-discovery`).
- [x] 2.3 Confirm their deltas closed `tier-pipeline`, `extraction`,
      `link-affordances`, `listing-completeness`, `link-discovery` — including
      the `tier_extras` fix that three specs require and
      `test_no_dict_str_any_on_dataclasses.py` forbids.

      **They did not, and could not.** The deltas covered ONE of ten
      `tier_extras` sites (`tier-pipeline`'s pre-rendered requirement). The
      other nine were never in scope of either change and were fixed here
      against the real field names on `TierResult`:

      | spec | was | now |
      |---|---|---|
      | `tier-pipeline` §Tier protocol | `tier_extras: dict[str, Any]` in the required field list | the named typed fields + an explicit "there SHALL be no `dict[str, Any]` bag" |
      | `tier-pipeline` §registry | `tier_extras["no_match"] = True` | `no_match=True` |
      | `tier-pipeline` §browser cache (×3) | `tier_extras["from_archive"/"from_browser"]` | `from_archive=True` / `from_browser is True` |
      | `site-handlers` (×3) | `TierResult.tier_extras["pre_rendered"]` | `TierResult.pre_rendered` (a `Rendered`) |
      | `raw-tier` §conditional | `tier_extras["conditional_hit"] == True` | `conditional_hit is True` |
      | `raw-tier` §proxy failure | `tier_extras["proxy_url"]` populated for diagnostics | `Diagnostic.proxy` — the proxy **id**, not the URL |

      Two of these were worse than stale. The Tier-protocol entry **mandated**
      the bag that `test_no_dict_str_any_on_dataclasses.py` forbids and
      CLAUDE.md's `Never` list bans, so the spec and the guard were in direct
      opposition and the spec was losing silently. And `tier_extras["proxy_url"]`
      named a field that has never existed in ANY form — `proxy_url` is a
      `fetch()` parameter — while the real diagnostic carries `proxy_id`
      deliberately, because a proxy URL can embed credentials. A reader
      implementing that line as written would have logged secrets.

      Meanwhile `retrieval-completeness:237` and `browser-backend:106` already
      said "a typed field, never a `tier_extras` bag". The spec set contradicted
      itself on the exact point, in the exact vocabulary, and nothing noticed.
- [x] 2.4 Re-inventory what drift remains. A large fraction should be gone.
      Every `tier_extras` occurrence in `openspec/specs/` is now negative
      commentary (three sites, all saying "never a bag"). `openspec validate
      --all`: 49 passed, 0 failed.

## 3. The remaining spec contradictions

- [x] 3.1 **Done 2026-08-02, and the citation held** — first of this change's
      §3 to survive its own check.

      Corrected to the shipped rule, which is not "skip" or "fail" but
      *environment-conditional*: skip where the engine is absent because the
      machine has none (punishing a contributor's inner loop for a fact about
      their laptop is wrong), FAIL under `A2WEB_REQUIRE_BROWSER=1`, which is the
      switch asserting "a browser was provisioned here" and which the release
      lane sets. Wrote the reasoning in, not just the behaviour: an
      unconditional auto-skip means a rung that launches nothing skips
      everywhere, reports green through a full release gate, and is
      indistinguishable from a rung that works.

      **Unplanned, found en route and NOT silently absorbed:** the requirement
      named **Camoufox**, which is gated off (`_manifests/browser_backends/camoufox.py`)
      — a spec-literal reader would have written the check against a binary the
      project deliberately does not ship. De-named it here. But the same defect
      runs through the WHOLE `browser-tier` spec at eight more sites, including
      requirement titles ("executes JS via Camoufox pool", "degrades gracefully
      without Camoufox") and a requirement whose trigger is
      `from camoufox.async_api import AsyncCamoufox` raising `ImportError`.
      That is a bigger correction than §3.1 and is filed as 3.1b rather than
      folded in, because quietly widening a task is how its verification stops
      being checkable.
- [ ] 3.1b `browser-tier` is written against Camoufox throughout — 8 sites
      beyond the smoke check, including two requirement titles and one whose
      trigger condition is a Camoufox import. The shipped engines are
      patchright / zendriver via the shelf `any_browser`; Camoufox is
      manifest-gated OFF. Re-point the spec at the `BrowserBackend` interface.
- [ ] 3.2 `extraction:103-152` and `content-expectations:48` contradict each
      other on candidate selection, and both contradict `fetcher.py:1541-1586`.
      **This one needs a product decision**, not a transcription — decide which
      is intended.
- [x] 3.3 **The citation was wrong — there are ZERO such sites in
      `openspec/specs/`.** Measured 2026-08-02: 79 repo-wide occurrences, none
      under `openspec/specs/`. They were fixed by
      `archive/2026-07-27-close-silent-enforcement-loss`, and this task was
      never updated — the fifth task this week to describe a real problem at a
      location that had already moved.

      What the survey actually found, sorted by whether the text makes a
      PRESENT-TENSE claim:

      | site | verdict |
      |---|---|
      | `src/a2web/packages/README.md:29` | **fixed** — said the invariant test "gates" the contract. It is `tach.toml`; repointed, and named `test_tach_covers_every_package.py`, since an unlisted package silently gets no contract at all. |
      | `src/a2web/packages/llm_extract/router_payload.py:7` | **fixed** — "preserves the `test_packages_independence` invariant", present tense. |
      | `BACKLOG.md:2244` | **fixed** — an OPEN entry, so it is guidance for future work, not a record. |
      | `BACKLOG.md:1784,1794` | left — inside `✅` shipped-stage entries. |
      | `CHANGELOG.md` ×8, `archive/**` ×~40, `docs/history/`, `docs/findings/` | left — historical records. A record of what was true then is not drift; rewriting it would destroy the evidence. |
      | `tach.toml:6`, `docs/adr/0001:61`, `test_claude_md_citations_resolve.py` | left — already correct, each naming it as REPLACED or `<!-- gone -->`. |
      | `CONSTITUTION.md:68,427` | **NOT fixed — needs a human.** `:427` claims "a2web has the test", which is false. Phase A requires confirmation for a Constitution-touching change, so it is raised rather than edited. |

      The distinction that made this tractable: a dead citation in a historical
      record is correct, and a dead citation in a present-tense sentence is a
      defect. Bulk-replacing all 79 would have corrupted the record.

## 4. The container-browser fact

- [ ] 4.1 Establish the actual rule: default `docker build` vs the published
      release image (`release.yml:92-94` sets `INSTALL_BROWSER=true`).
- [ ] 4.2 Correct CLAUDE.md:119,125 — it says the container has no browser, while
      `Dockerfile:9-13` and `README.md:332-334` describe a browser-baked ~1.9 GB
      image.
- [ ] 4.3 Correct `openspec/specs/container-image:20-27`, which errs the opposite
      way by asserting Chromium unconditionally.
- [ ] 4.4 State it once, with the build argument named, and have both documents
      cite that.

## 5. CLAUDE.md — inventory and structure

**Four of nine were already fixed by earlier changes; four were real; one became
a guard.** Censused before editing.

- [x] 5.1 **Stale — CLAUDE.md contains no `_run_pipeline` or "coordinator"
      claim.** The fetcher section was rewritten when the module became a
      package (`decompose-fetcher-into-files`). Nothing to correct.
- [x] 5.2 **Real.** Five handlers named, nine on disk — and the four unnamed
      (`discourse`, `habr`, `twitter`, `v2ex`) were invisible to any reader who
      counted the names and found them self-consistent. All nine now listed.
- [x] 5.3 **Real, and worse than stated.** The tiers line named `paid.py`
      (the file is `_paid.py`), never mentioned `zyte.py` or `firecrawl.py` as
      separate tiers, never mentioned `site_handler.py`, and omitted the
      `browser_robust` rung entirely. `_PAID_TIER_ORDER = ("zyte", "firecrawl")`
      — zyte FIRST — is now stated, because "Firecrawl env-gated" implied
      Firecrawl was the paid tier.
- [x] 5.4 **Real.** `tiers/ (5 tiers)` → 8, now enumerated rather than counted,
      so the omission cannot recur silently.
- [x] 5.5 **Real.** "capped at 1/fetch" → `playbook.BROWSER_DISPATCH_CAP = 2`,
      with what the two dispatches ARE (fast Chromium, then robust CDP) — the
      number alone reads as a typo; the reason is the fast→robust ladder.
- [x] 5.6 Already done — CLAUDE.md documents `domain.py` at 149 lines and
      records that the 381-line renderer moved to `packages/structured_render.py`.
      `lift-the-item-set-and-renderer` shipped.
- [x] 5.7 Already done — `fetcher_response.py` has its own CLAUDE.md entry,
      including the note that it was undocumented until 2026-08-01.
- [x] 5.8 Already done — `_manifests/llm_providers/` is marked GONE with the
      reason (promoted to shelf `anyllm`; `select_provider` calls
      `resolve_provider` directly).
- [x] 5.9 **Done — and this is the part that stops §5 recurring.**
      `tests/architecture/test_claude_md_inventory_counts.py` asserts the two
      stated counts against the tree AND that every handler / tier manifest is
      NAMED, since a correct count beside an incomplete list is the worse half
      of the defect: a reader who counts the names and finds them consistent has
      no signal that four are missing.

      Mutation-verified in four directions, and the fourth is why the guard is
      trustworthy: dropping `browser_robust` from the manifest list initially
      **PASSED**, because the name also appears in the tiers paragraph and in
      `browser_robust_backend`. A whole-document substring search is satisfied by
      any incidental mention. Scoped to the parenthesised list; now fails.

## 6. Dead and renamed symbols

**Half this section was already true when it was written.** Censused first,
per the `enforcement-integrity` rule this repo added on 2026-08-02: of the nine
symbols named, three have zero occurrences anywhere and needed nothing.

- [x] 6.1 **Done 2026-08-02.** Four sites named `_prescribe_browser_on_wall`.
      Three make a PRESENT-TENSE claim and were repointed to
      `fetcher.verdict.terminal._apply_terminal` — repointed, not stripped, as
      the task correctly insisted: they explain the ADR-0009 single-systematic-
      floor mechanism and deleting them loses the reasoning.
      `actions/terminal.py:9` was left: it names the symbol in the PAST tense as
      one of the two inverse whitelist predicates the classifier replaced, which
      is exactly right and is the record of why the classifier exists.
- [x] 6.2 **Done, and reading the test was the point — it was wrong in a second
      way.** `test_fetcher.py:360,384` described "`_apply_after_tier_action`
      gates further URL rewrites on `fc.url_rewrites < 1`". Both halves are
      dead: the symbol is `_dispatch_action`, AND the gate is no longer an
      inline `< 1` in the orchestrator — it moved to the planner as
      `ctx.caps.url_rewrites >= URL_REWRITE_CAP` (`playbook.py:88,160`).
      `_AfterTier` has ZERO occurrences repo-wide; nothing to rename.

      Also corrected an overclaim found while reading: the comment implied the
      assertion below it verified the budget rule. It does not — it asserts the
      rewrite happened and the tier was dispatched once. Said so plainly rather
      than leaving prose that reads as coverage.
- [x] 6.3 `next_action_after_gate` has ZERO occurrences; `next_action_after_tier`
      had one, a test docstring, now `playbook.decide_next` with a line naming
      the unification (the after-gate and after-tier planners became one
      `decide_next(log, *, url, caps)` over the decision log).
- [x] 6.4 **Nothing to do — `ExtractionCache` has ZERO occurrences repo-wide.**
      Renamed to `LlmCache` when the extraction cache was promoted to the shelf;
      this task outlived the work.
- [ ] 6.5 **Raised, not decided — this is an Ask First item.** The tool is
      registered on the wire as bare `refresh` (`routers.py:299`) while
      `settings.py:282,296`, `README.md:374-375` and `CLAUDE.md:148` all call it
      `cookies_refresh`, and the CLI already groups it as
      `a2web cookies refresh` (`cli.py:72`).

      Recommend renaming the WIRE name to `cookies_refresh`: bare `refresh`
      sits in the same flat MCP namespace as `query` and `fetch_raw` and tells
      an agent nothing about what it refreshes. Blast radius is near-zero — the
      tool is default-OFF (`expose_cookies_tool`), local-only, and absent from
      the published container. But it IS a tool-signature change, which CLAUDE.md
      lists under Ask First, so it waits for a human rather than being decided
      by whoever happened to be editing docs.

## 7. The citation guard

**Done before this change reached it, except 7.3.** Verified 2026-08-02.

- [x] 7.1 `_CITATION_DIR` exists at
      `test_claude_md_citations_resolve.py:75` and is used at `:293`.
      Directory citations are checked.
- [x] 7.2 Already fixed: CLAUDE.md:31 and :84 cite
      `archive/2026-07-26-sunset-a2kit-dependency/` and
      `archive/2026-07-27-shelf-sweep-promotions/` with their date prefixes, and
      the guard is green over them. The "observe it go red first" step cannot be
      re-run — the fix landed with the widening, in
      `archive/2026-07-27-close-silent-enforcement-loss`.
- [x] 7.3 **Real, and fixed 2026-08-02.** CLAUDE.md:33 named
      `2026-06-11-a2kit-v043-migration` as the most recent; the newest is
      `2026-06-19-a2kit-v044-migration`. Rather than swap the name, the line now
      says both and says which to READ: v0.44 was a clean pin bump that touched
      nothing a2web consumed, so v0.43 remains where the surface actually moved.
      A bare swap would have sent every reader to the less useful document while
      being technically accurate — which is how the line got wrong in the first
      place.
