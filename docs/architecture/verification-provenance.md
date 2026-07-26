# Verification provenance — the witness rule, and where CI's authority ends

> Origin: a recurring "green that proves nothing" failure mode, diagnosed
> across the a2kit sunset + shelf sweep (2026-07) and pressure-tested by two
> Fable-5 council reviews. This is the honest map of what our automated gate
> can and cannot certify — written because the most dangerous guard is one that
> gives false comfort.

## The failure mode: oracle endogeneity

A check whose expected value is derived from the **same belief** as the thing it
checks cannot see the error they share. Its errors are correlated with the
artifact's, so the comparison is structurally blind to the shared bug — and it
stays green through the bug, forever. This bit us at least five times, each
found by accident rather than by a check:

- a wire golden froze a typo (`~95%%`) every agent reads, through 17 review rounds;
- a `/health` route 404'd and `__version__` sat stale by 47 releases — both outside Python, both invisible to 1200+ tests;
- three shelf-sweep "design questions" were authored from stale docstrings describing finished work in the present tense;
- the zendriver robust rung could not launch *at all* on the pinned version, and its unit test (a permissive fake) plus its skip-on-failure smoke were both green.

## Two mechanisms — and which we can defend against

| | Mechanism | Enforceable? | Our defenses |
|---|---|---|---|
| **B** | **Unknowns resolve to green** — skips, vacuous walks, absent surfaces. "Couldn't verify" silently becomes "verified." | **Yes** — vacuity is a property of the artifact (count the candidates). | `_walk.walked_files(minimum=…)` floors; `test_walk_is_not_vacuous`; accepted-delta liveness; the new browser-gate skip→fail flag; `test_transient_markers_not_stale`. |
| **A** | **Endogenous oracles** — goldens, hand-written fakes, docstrings. The oracle is a copy of the author's belief, so it agrees with the author's bug. | **Only partially.** You can mechanize the *existence* of a second path; you cannot mechanize its *independence*. | The three narrow guards below — and, past them, review discipline + an exogenous-witness budget. |

## The witness rule (the operational half)

> **Every load-bearing claim needs at least one witness of independent
> provenance.** A golden is never a witness (it is a snapshot of the artifact).
> A fake is never a witness (it is the author's belief about the dependency). A
> docstring is anti-witness. A witness is: a second **mechanical** renderer of
> the same source; the **real substrate** in an environment obligated to run
> it; or a **second consumer**. "Found by accident" is the system reporting
> where detection actually comes from — provenance diversity, not test volume.

## Where CI's authority ends (say it out loud)

You cannot certify independence with a guard, because the guard is something you
authored too — a guard against endogeneity can itself be endogenous (one level
up). Two concrete proofs from this repo:

- The `~95%%` typo did **not** die because a mechanically independent renderer
  disagreed. The CLI is *derived from the same tool-registration strings*. It
  died because a different rendering frame triggered a **fresh human read**. Our
  best documented mechanism-A kill was a human-attention event, not a mechanical
  one. Build a "witness registry", call a surface covered, and you mechanize
  away the thing that actually worked.
- The lean-wire shape guard exists because the *shelf* codec raises the same
  `TypeError` the old vendored one did. Two renderers through a shared library
  agree on the shared library's bug, greenly, forever.

So the honest posture is: **CI can enforce that a second path exists and ran on
N>0 inputs. It cannot certify the second path is independent.** Above that line,
provenance diversity is a review-discipline and exogenous-budget problem, not a
CI one. Everything you author yourself — including this doc's guards — is at best
*decorrelated*, never independent. The only truly exogenous witnesses we have:
live reality (`make bench` against the real web with real LLMs), an upstream
library's own behavior, a genuinely foreign consumer, and production telemetry.

## The three narrow guards (what IS mechanizable)

1. **Standing fake-fidelity contract.** A hand-written fake of an external
   dependency must be re-checked against the *real installed library* on every
   commit, so it cannot drift laxer than reality (the exact failure that shipped
   the dead `--no-sandbox` rung). Pattern: run the same battery through the fake
   and the real object; assert identical accept/reject. The real library is the
   exogenous half. Reference: `test_fake_config_matches_real_add_argument` in
   `tests/packages/test_zendriver_backend.py`. Extend to any fake whose real
   counterpart validates, raises, or enforces ordering.

2. **Real-substrate lane with skips forbidden.** Any capability whose real
   behavior is expensive to reach (a browser launch, a container boot) gets a CI
   lane that reaches it, in which a missing dependency is a **failure**, not a
   skip. A skip in the one environment you control is a dead rung wearing a green
   coat. Reference: the `browser-gate` job + `A2WEB_REQUIRE_BROWSER=1` policy
   (`test_browser_smoke.py`), with the fail-branch pinned in the default gate by
   `test_browser_gate_policy.py` (a branch a *working* browser can never reach).

3. **Expiry-carrying transient markers.** Provisional code kept only until a
   change lands carries `TRANSIENT (<change-id>)`; the marker is stale (guard
   fails) once that change is archived. The archive directory is the exogenous
   witness — "the change shipped" is a fact on disk, not a judgement. Reference:
   `test_transient_markers_not_stale`. We deliberately do **not** ban temporal
   words: that fires on legitimate corrective narration ("a2kit *used to* own
   this, now this module does") and trains docstrings to lie fluently. Semantic
   staleness is not lintable; only the pinned-lifecycle-claim slice is.

## Promotion to the shelf — the boundary invariants

Promoting to a shared registry means our blind spots propagate to consumers we
don't control, pinned by tag and hard to unship. Expected-loss ranking (the
thing most likely to hurt a consumer first is NOT an endogenous golden — it is a
package that installs clean on our machine and nowhere else):

1. **Foreign-soil install-and-run at tag time (THE gate).** Before a tag is
   published: install the package from the tag into a clean environment with no
   repo checkout and none of a2web's incidental dependencies, then run its
   acceptance suite against the *installed artifact*. Kills the largest
   propagation class — works-in-monorepo / broken-as-artifact: undeclared deps,
   missing `py.typed`, packaging holes, and especially graceful-degradation
   paths (which never execute on home soil, because home soil has everything).
2. **Pin, never `path=`.** The promotion is not done until a2web's full gate is
   green while pinned to the *published tag*, not the worktree. (The commit guard
   already blocks committing editable shelf sources; this extends the
   discipline.) It is the closest available second-consumer proxy.
3. **Tag lifecycle is immutable.** Decide before the first bad tag, not after: a
   bad tag gets a ledger row + a superseding tag, never a deletion or
   force-push. Consumers pin by tag; a mutable tag is a supply-chain hole in our
   own house. (Mirrors the shelf's "never delete an old tag.")
4. **Boundary enums get an exhaustive match in the consumer.** Type drift across
   the boundary has already happened (`ProviderMode` vs `anyllm.ProviderName` —
   different string sets). Every shelf boundary enum resolves to the consumer's
   type at the seam with an exhaustive `match` + `assert_never`, so drift breaks
   at type-check — the cheapest independent provenance there is, a compile-time
   witness.

## The exogenous-witness budget (the meta-risk)

Every anti-A asset touches reality, and reality flakes: the browser lane, the
live bench, foreign-soil installs. Without a **separate lane, separate signal,
and an explicit triage SLA**, the team retrains itself to ignore red within a
month — and *a red that's ignorable is mechanism A wearing mechanism B's coat*.
A flaky exogenous witness is worse than none. Corollary, and the single highest-
value standing action against mechanism A: **schedule `make bench`.** It is the
one oracle that cannot agree with our beliefs, because it does not know them —
worth more than any amount of H4/H5 golden/docstring machinery. It is currently
manual; a scheduled run with diffed findings is the goal (gated on the ADR-0016
subscription-only rule — never metered).

## Don't over-index

The witness rule is right, but it is fourth on the promotion's expected-loss
list, behind packaging/foreign-soil, semver/compat discipline, and tag
lifecycle. H1 (the browser gate) + the wire golden gate + the standing
fake-fidelity contract already bought most of the endogenous-oracle risk down.
Spend the marginal effort on the boundary mechanics above, not on a fourth
oracle guard.
