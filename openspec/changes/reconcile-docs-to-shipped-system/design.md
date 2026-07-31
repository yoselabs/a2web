## Context

Doc-drift sweep, 2026-07-31. Evidence in
`docs/findings/2026-07-31-structural-scan.md`.

The dominant cause is identifiable: **two structural migrations landed with no
spec sync** — the `anyllm` adoption (`ee2452c`, shipped BREAKING, updated no
spec) and the shelf promotions that emptied `packages/`. Most of the drift is
downstream of those two events, not of general neglect.

The second cause is narrower and more interesting: **`close-silent-enforcement-loss`
built a citation guard that reads CLAUDE.md alone.** It fixed the
`test_packages_independence.py` citation in CLAUDE.md and left the same citation
in nine `openspec/specs/` files, because the guard's scope defined the fix's
scope. A guard's coverage silently becomes the definition of "done".

## Goals / Non-Goals

**Goals**

- An agent reading CLAUDE.md reasons about the shipped system.
- An operator following a spec gets a working, authenticated deployment.
- The specs do not contradict each other.
- The citation guard covers the citations that actually exist.

**Non-Goals**

- Any application behaviour change. This change writes no logic.
- Rewriting specs that are current. `handler-live-probe` is explicitly out —
  refuted, and recorded so it is not re-checked.
- Documenting the systems that `unify-the-response-contract` and
  `decompose-fetcher-into-files` are about to change. That is why this is last.

## Decisions

### D1 — Do this last, with two exceptions lifted out

`unify-the-response-contract` and `decompose-fetcher-into-files` will
re-invalidate the pipeline description, the module inventory, and parts of
`tier-pipeline`. Reconciling first means doing it twice, and the second pass is
the one that gets skipped.

**Two items must not wait**, because they are live harm rather than drift:

- **`endpoint-auth`.** The spec writes every environment variable bare
  (`GOOGLE_CLIENT_ID`) while `env_prefix="A2WEB_"` applies. An operator following
  it literally gets an **unauthenticated endpoint**. That is a security defect
  wearing a documentation defect's clothes.
- **`provider-selection`.** The spec states `openai_compatible` is last in auto
  order so it "can never shadow a working Claude/Anthropic path". The shipped
  `_GATEWAY_FIRST_ORDER` puts it **first** when both `OPENAI_API_KEY` and
  `OPENAI_BASE_URL` are set. A live routing invariant documented inverted — and
  under ADR-0016, provider routing is exactly where a wrong belief costs money.

Ship those two on their own if this change slips.

### D2 — Sync the two unarchived changes before writing anything new

`narrow-the-pre-rendered-extraction-skip` (27/27) and
`restore-links-on-pre-rendered-tiers` (25/25) are fully implemented and never
archived. Their delta specs already contain corrected text for `tier-pipeline`,
`extraction`, `link-affordances`, `listing-completeness`, `link-discovery` —
including the `tier_extras` fix that three specs currently require and an
architecture test currently forbids.

A large fraction of the spec drift closes by syncing work already done. Do it
first; anything hand-written before that risks conflicting with a delta already
in the tree.

### D3 — Resolve the container-browser fact, don't pick a document

CLAUDE.md says the image has no browser. `release.yml:92-94`, `Dockerfile:9-13`
and `README.md:332-334` say the published image is browser-baked (~1.9 GB).
`openspec/specs/container-image:20-27` asserts Chromium **unconditionally**,
while a default `docker build` ships none.

So: two documents, wrong in opposite directions, about one fact that depends on a
build argument. The fix is not to align the docs to each other — it is to state
the actual rule (**default build: no browser; published release image:
browser-baked**) once, and have both documents say that.

This matters beyond tidiness: an agent that believes the served instance cannot
browser-escalate will route around a capability it has.

### D4 — Widen the citation guard, then fix what it exposes

`test_claude_md_citations_resolve.py:61` requires a file suffix. It therefore
checks 43 of 78 path-shaped citations and no directory citation at all.

Widen it to accept directory citations. Expect it to go red on CLAUDE.md:29 and
:81 — two `read-this-first` gates pointing at changes that moved under
`archive/`. That red is the guard working.

Same discipline as elsewhere in this backlog: widen, observe the failure, then
fix. A widened matcher that was never seen to fail is not known to match.

### D5 — The guard's scope is not the fix's scope

`close-silent-enforcement-loss` fixed one citation and left nine identical ones,
because its guard read one file.

Record this as the lesson, in `verification-provenance.md`: when a guard is built
to catch a class of defect, the *repair* covers the class, not the guard's
window. Then extend the citation guard past CLAUDE.md to `openspec/specs/` and
`docs/`, so the scope and the class match.

### D6 — Dead symbols get renamed, not deleted from the prose

`_prescribe_browser_on_wall` is cited in present tense at four sites as the live
emitter of the `try_user_browser` floor. **The behaviour is intact** — it lives
in `_apply_terminal`. The comments are load-bearing explanation of an ADR-0009
mechanism; the fix is to repoint them, not to strip them.

Same for `_apply_after_tier_action` / `_AfterTier` and `next_action_after_gate` /
`next_action_after_tier`. Note `test_fetcher.py:384` claims to test "the
`_apply_after_tier_action` contract" — a test whose stated subject no longer
exists is worth reading rather than just renaming.

## Risks / Trade-offs

- **This change is worth less if done early**, and there is a real temptation to
  do it early because it is cheap. D1's two exceptions are the release valve;
  everything else waits.
- **Correcting `tier_extras` in three specs conflicts with the two unarchived
  changes** if done by hand. D2's ordering exists for this.
- **Widening the citation guard will turn the docs red** in places nobody has
  budget for. Fix the citations; do not narrow the guard back.
- **A doc-only change has no test that proves it right.** The citation guard
  covers existence, not accuracy. The inventory counts (9 handlers, 8 tier
  manifests, 12 phases) are the parts a guard *could* check — consider counting
  them mechanically rather than restating numbers that will rot again.

## Open Questions

- Should the handler/tier/manifest inventory in CLAUDE.md be generated or
  asserted? A count in prose rots by construction; a test asserting "CLAUDE.md
  says N and there are N" is cheap and non-vacuous. Leaning assert.
- `extraction:103-152` vs `content-expectations:48` contradict each other **and**
  both contradict `fetcher.py:1541-1586`. Which is intended? This is the one item
  here that needs a product decision rather than a transcription.
- Does `container-image` need the build-argument distinction as a spec
  requirement, or is it a README fact? Leaning requirement — the deployed
  capability set depends on it.
- `_manifests/llm_providers/` holds only `__pycache__`. Documented as a live
  plugin surface with no `load_surface` targeting it. Verify the loader cannot
  resurrect it before deleting the directory.
