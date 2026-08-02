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

- [ ] 5.1 Pipeline: `_run_pipeline` is documented as "a 12-line coordinator
      calling six named phases" (`:72`). It is **47 lines calling twelve**, and
      `_phase_cache_write` is **not terminal** — three promotion/terminal steps
      run after it.
- [ ] 5.2 Handlers: 9 documented as 5 (`:69`).
- [ ] 5.3 Tiers: the zyte tier and the `browser_robust` rung are absent
      entirely, while `_PAID_TIER_ORDER = ("zyte", "firecrawl")` puts zyte
      **first**. The files are `_paid.py`, `firecrawl.py`, `zyte.py`.
- [ ] 5.4 Tier manifests: 8 documented as 5.
- [ ] 5.5 Browser cap: `:73` says "capped at 1/fetch"; `playbook.py:156,172,260`
      caps at `< 2` (fast → robust rungs).
- [ ] 5.6 `domain.py`: described as "pure functions too small for their own
      files" (`:75`) when ~370 of 551 lines are a renderer. **Coordinate with
      `lift-the-item-set-and-renderer`**, which changes this.
- [ ] 5.7 Add `fetcher_response.py` — 740 lines CLAUDE.md never mentions.
- [ ] 5.8 `_manifests/llm_providers/` is listed as a live plugin surface (`:85`)
      but holds only `__pycache__`. **Verify the loader cannot resurrect it**
      before deleting the directory.
- [ ] 5.9 Consider asserting the inventory counts mechanically rather than
      restating numbers that rot (design Open Questions).

## 6. Dead and renamed symbols

- [ ] 6.1 `_prescribe_browser_on_wall` — cited in present tense at
      `fetcher.py:1839,1919` and `fetcher_response.py:388,429` as the live
      emitter of the `try_user_browser` floor. The symbol does not exist; the
      behaviour lives in `_apply_terminal`. **Repoint the comments, do not strip
      them** — they explain an ADR-0009 mechanism.
- [ ] 6.2 `_apply_after_tier_action` / `_AfterTier` → `_dispatch_action` /
      `_Exec`. They survive in `test_fetcher.py:360,384`; `:384` claims to test
      "the `_apply_after_tier_action` contract" — read that test rather than only
      renaming it.
- [ ] 6.3 `next_action_after_gate` / `next_action_after_tier` →
      `decide_next(log, *, url, caps)`.
- [ ] 6.4 `ExtractionCache` → `LlmCache`.
- [ ] 6.5 The cookies tool is registered as `refresh` but called
      `cookies_refresh` in CLAUDE.md:119, `settings.py:239,253`,
      `README.md:367-368`. Pick one.

## 7. The citation guard

- [ ] 7.1 Widen `test_claude_md_citations_resolve.py:61`'s file-suffix regex to
      accept directory citations. It currently checks 43 of 78 path-shaped
      citations and no directory citation at all.
- [ ] 7.2 Observe it go red before fixing anything — expect CLAUDE.md:29 and :81,
      which cite `sunset-a2kit-dependency/` and `shelf-sweep-promotions/` as
      read-this-first gates when both moved under `archive/` with date prefixes.
- [ ] 7.3 Fix CLAUDE.md:31, which names `a2kit-v043-migration/` as the most
      recent archived change; it is one of ~55 older ones (latest is
      `2026-06-19-a2kit-v044-migration`).
- [ ] 7.4 Extend the guard past CLAUDE.md to `openspec/specs/` and `docs/`. The
      nine stale independence-test citations survived because
      `close-silent-enforcement-loss` built a guard that reads CLAUDE.md alone.
- [ ] 7.5 Record that lesson in `verification-provenance.md`: **a guard's scope is
      not the fix's scope.** When a guard is built for a class of defect, the
      repair covers the class, not the guard's window.

## 8. Close out

- [ ] 8.1 Fix `docs/architecture/README.md`'s rules registry — 10 of 33 guards
      listed. Note `close-guards-that-read-green` also touches this; coordinate.
- [ ] 8.2 Correct CLAUDE.md:249's "aiosqlite worker thread doesn't leak" — the
      test asserts the conftest TEST-ONLY daemon patch is applied and says
      nothing about production.
- [ ] 8.3 `make check` green. No application logic changed in this change.
- [ ] 8.4 Record the refuted hypothesis so it is not re-checked:
      `handler-live-probe/spec.md` is one of the most current specs in the tree.
      Its only defect is a `_HANDLERS` registry name with zero hits.
- [ ] 8.5 Move the T6 entries to `BACKLOG-CLOSED.md`.
