## Why

**CLAUDE.md is the map every agent reads first, and it describes a system that is
not the one shipped.** Each item below sends a reader somewhere wrong.

### Load-bearing: the container's browser

CLAUDE.md:119,125 — *"The container is deliberately slimmed — no
`[browser]`/`[cookies]`/`[claude-code]` extras — so a served a2web has no local
browser."* But `release.yml:92-94` builds and pushes with `INSTALL_BROWSER=true`,
and `Dockerfile:9-13` and `README.md:332-334` both describe the published image
as browser-baked (~1.9 GB). **Three sources agree against CLAUDE.md.** An agent
reasoning "the served instance cannot browser-escalate" routes wrong.

`openspec/specs/container-image:20-27` errs the *opposite* way, asserting
Chromium unconditionally while a default `docker build` ships none. So the two
documents are wrong in opposite directions about the same fact.

### Structural: the pipeline

CLAUDE.md:72 says `_run_pipeline` is "a 12-line coordinator calling six named
phases". It is **47 lines calling twelve**, and `_phase_cache_write` is **not
terminal** — three promotion/terminal steps run after it. Anyone reasoning about
ordering from this is reasoning about a different pipeline.

### Inventory drift

- 9 site handlers documented as 5 (`:69`)
- **the zyte tier and the `browser_robust` rung are absent entirely**, while
  `_PAID_TIER_ORDER = ("zyte", "firecrawl")` puts zyte first — `:70` says only
  "`paid.py` (Firecrawl env-gated)", and the files are `_paid.py`,
  `firecrawl.py`, `zyte.py`
- 8 tier manifests documented as 5
- `_manifests/llm_providers/` listed as a live plugin surface (`:85`), but the
  directory is empty with no `load_surface` targeting it
- `domain.py` described as "pure functions too small for their own files" (`:75`)
  when ~370 of 551 lines are a structured-data renderer
- `fetcher_response.py` — 740 lines CLAUDE.md never mentions at all
- browser "capped at 1/fetch" (`:73`) vs `playbook.py:156,172,260` capping at
  `< 2` (fast → robust rungs)

### Dead and renamed symbols

`_apply_after_tier_action` / `_AfterTier` (now `_dispatch_action` / `_Exec`;
they survive in test comments at `test_fetcher.py:360,384`, the latter claiming
to test "the `_apply_after_tier_action` contract");
`next_action_after_gate` / `next_action_after_tier` (now
`decide_next(log, *, url, caps)`); `ExtractionCache` (now `LlmCache`); the tool
registered as `refresh` but called `cookies_refresh` in CLAUDE.md:119,
`settings.py:239,253`, `README.md:367-368`. And `_prescribe_browser_on_wall`,
cited in present tense at `fetcher.py:1839,1919` and
`fetcher_response.py:388,429` as the live emitter of the `try_user_browser`
floor — **the symbol does not exist** (the behaviour is intact, in
`_apply_terminal`).

### Why the citation guard missed all of it

`test_claude_md_citations_resolve.py:61` requires a file suffix, so it checks
**43 of 78** path-shaped citations and **no directory citation at all** — which
is why CLAUDE.md:29 and :81 can cite `openspec/changes/sunset-a2kit-dependency/`
and `.../shelf-sweep-promotions/` as read-this-first gates when both moved under
`archive/` with date prefixes. CLAUDE.md:31 also names `a2kit-v043-migration/` as
the most recent archived change; it is one of ~55 older ones.

### The specs contradict the code, and four are load-bearing

| spec | asserts | code |
|---|---|---|
| `provider-selection:22,34-37,100-107` | `openai_compatible` is LAST in auto order so it "can never shadow a working Claude/Anthropic path" | `llm_resource.py:71-74`'s `_GATEWAY_FIRST_ORDER` puts it **FIRST** when `OPENAI_API_KEY`+`OPENAI_BASE_URL` are both set — **a live routing invariant inverted** |
| `endpoint-auth` | writes every env var bare (`GOOGLE_CLIENT_ID`) | `env_prefix="A2WEB_"` applies — **an operator following it literally gets an UNAUTHENTICATED endpoint** (SECURITY) |
| `browser-tier:180,192-195` | the smoke check SHALL auto-skip when the binary is unavailable | `test_browser_smoke.py` hard-FAILS under `A2WEB_REQUIRE_BROWSER=1`; following the spec re-opens the dead-rung hole the guard closes |
| `tier-pipeline:8,84-96` (+ `site-handlers`, `raw-tier`) | requires `tier_extras: dict[str, Any]` | CLAUDE.md says never reintroduce it, and `test_no_dict_str_any_on_dataclasses.py` fails on it |

Plus: `extraction:103-152` and `content-expectations:48` contradict **each
other** on candidate selection, and both contradict `fetcher.py:1541-1586`.
`output-benchmark` and `openai-compatible-provider` prescribe the retired
provider ids as normative config — the pre-rename spellings fail at resolution,
so a documented boot is broken.

**Nine `openspec/specs/` sites still cite the deleted
`tests/test_packages_independence.py`.** `close-silent-enforcement-loss` fixed
that citation in CLAUDE.md only, because the guard it built reads CLAUDE.md
alone.

### The cheapest high-value fix

**Two fully-implemented changes were never archived** —
`narrow-the-pre-rendered-extraction-skip` (27/27) and
`restore-links-on-pre-rendered-tiers` (25/25). Their delta specs already contain
corrected text for `tier-pipeline`, `extraction`, `link-affordances`,
`listing-completeness`, `link-discovery` — including the `tier_extras` fix. Sync
those first; a large fraction of the spec drift closes with no new writing.

## What Changes

- **Sync and archive the two completed changes.** Their deltas already carry the
  corrections.
- **Correct the four load-bearing spec contradictions**, starting with
  `endpoint-auth` (security) and `provider-selection` (inverted routing
  invariant).
- **Reconcile the container-browser fact.** CLAUDE.md and
  `openspec/specs/container-image` are wrong in opposite directions; decide what
  the published image actually is and say it once.
- **Correct CLAUDE.md's inventory, pipeline description, and dead symbols.**
- **Widen the citation guard** to accept directory citations, and fix what it
  then exposes.
- **Sync the nine `openspec/specs/` sites** citing the deleted independence test.
- **Rename `_prescribe_browser_on_wall`'s four citations** to the surviving
  `_apply_terminal`.
- **Sync `provider-selection` / `openai-compatible-provider` / `output-benchmark`
  for the `anyllm` rename** (`ee2452c` shipped BREAKING and updated no spec).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `endpoint-auth`: environment variables SHALL be documented with the prefix that
  actually applies.
- `provider-selection`: the documented auto order SHALL match the shipped order.
- `browser-tier`: the smoke check SHALL be documented as failing, not skipping,
  when required.
- `container-image`: the published image's browser contents SHALL be stated once
  and consistently.

## Impact

- `CLAUDE.md` — inventory, pipeline, symbols, container, cookie tool name
- `openspec/specs/` — `endpoint-auth`, `provider-selection`, `browser-tier`,
  `tier-pipeline`, `site-handlers`, `raw-tier`, `extraction`,
  `content-expectations`, `container-image`, `output-benchmark`,
  `openai-compatible-provider`, plus nine independence-test citations
- `openspec/changes/` — two completed changes synced and archived
- `docs/architecture/README.md` — the rules registry is 10 of 33
- `tests/architecture/test_claude_md_citations_resolve.py:61` — the regex
- `src/a2web/fetcher.py`, `fetcher_response.py` — comment citations only
- No behaviour change. This change writes no application logic.

## Ordering

**Do this last.** `unify-the-response-contract` and
`decompose-fetcher-into-files` will re-invalidate the pipeline description, the
module inventory, and parts of `tier-pipeline` — so reconciling before them means
doing it twice.

**Two exceptions that should not wait:** `endpoint-auth` (an operator following
it literally gets an unauthenticated endpoint) and `provider-selection` (a live
routing invariant documented inverted). Lift both out and ship them immediately
if this change slips.

## Out of Scope

- The `_MAX_RECORDS` × `DEFAULT_TOLERANCE` interaction. Still unverified; it
  stays in `BACKLOG.md`, not in a spec.
- `handler-live-probe/spec.md` — **refuted, recorded so it is not re-checked.**
  It is one of the most current specs in the tree, rewritten by
  `2026-07-28-probe-asserts-yield-not-reachability` and matching `handler_probe.py`
  requirement-for-requirement. Its only defect is a `_HANDLERS` registry name
  with zero hits.
