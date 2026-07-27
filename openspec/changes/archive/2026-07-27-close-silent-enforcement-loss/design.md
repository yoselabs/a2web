## Context

Three invariants this repo states are not enforced over their stated scope. All
three were found by spiking on 2026-07-27, none by a failing test, and each was
confirmed empirically before being written down:

| # | Invariant | How it actually fails | Evidence |
|---|---|---|---|
| 1 | packages may not import domain code | an **unlisted** package has no contract | a temp package importing `a2web.settings` passed `tach check` clean |
| 2 | the architecture map is accurate | four citations do not resolve | `_plugin.py`, `tests/test_packages_independence.py`, `tools/hooks/install.py`, `ndjson_log` |
| 3 | never commit a local shelf source | the hook `exit 0`s without a shelf clone | read from `.git/hooks/pre-commit` |

The common shape is worth naming, because it is not the failure mode the repo
already defends against. `_walk.walked_files(minimum=…)` protects against a
guard that *scans nothing*. These three scan plenty — they simply do not scan
the subject. A guard with a floor can still be scoped away from the thing it
was written to catch.

Constraint that shapes every decision below: CI runs `make check`. A check in
the test suite is enforced on every push, on a machine with no shelf clone and
no git hooks. That is why all three fixes land as tests rather than as tooling
configuration or documentation.

## Goals / Non-Goals

**Goals**

- Make each of the three losses fail the gate, on CI, without developer setup.
- Keep each new guard non-vacuous, and verify each red-before-green against an
  injected violation — the failure being fixed is *precisely* a guard nobody
  watched fail.
- Correct the four stale citations and the one stale `tach.toml` entry.

**Non-Goals**

- **Not** replacing `tach`. It genuinely enforces the boundary for listed
  modules — verified by injection. The defect is list coverage, not the tool.
- **Not** changing the shelf's git hook. Its fail-open behaviour is correct
  *there*: a hook that hard-failed without the shelf would block every commit
  on a fresh clone of any consumer. The defect is relying on it alone and
  describing it as a hard block.
- **Not** auditing every document in the repo for stale paths. Scope is the
  agent-facing instruction file, because it is the one agents navigate by.
- **Not** generating `tach.toml` from the filesystem. See D1.

## Decisions

### D1 — Assert the module list matches the tree; do not generate it

`tach.toml` carries more than membership: dependency edges, and a grandfathered
exception (`block_detector` → `packages.escalation`) with a comment explaining
why. Generating the list would either discard that or require encoding the
exceptions somewhere else, which is the same hand-maintenance one level removed.

So the guard compares two sets and fails on either difference, leaving the
config hand-written. Adding a package stays a two-file edit — and the point is
that forgetting the second file is now loud.

*Alternative rejected:* a `tach sync` step in the Makefile. It would rewrite
dependency edges as a side effect of adding a module, silently widening
boundaries — the opposite of the invariant.

### D2 — Guard the manifest, not the lockfile, for local shelf sources

The violation is a `path =` or `editable = true` entry under the dependency
source table in `pyproject.toml`. That is what a developer edits to test an
unreleased shelf change, and what the shelf loop forbids committing.

Reading the manifest rather than the resolved environment keeps the check fast,
offline, and independent of whether anyone actually ran `uv sync` — and it
matches the artifact under version control, which is the thing that can be
committed.

*Alternative rejected:* inspecting installed distributions for editable
installs. It would flag a legitimately-editable local dev environment that was
never committed, punishing the workflow the hook is designed to allow.

### D3 — Historical citations get an explicit marker, not an allowlist

`CLAUDE.md` legitimately says things like "the extraction cache → shelf
`llm-cache`" and "was `packages/http_cache.py`". Those sentences are the record
of a promotion and must stay writable, with the path intact — the path is the
informative part.

Two mechanisms were considered:

- **An allowlist of known-dead paths in the test.** Rejected: it rots exactly
  like the citations do, and it puts the justification in a different file from
  the sentence it justifies.
- **A marker adjacent to the mention.** Chosen. The sentence carries its own
  status, a reader sees why the path is dead at the point of reading, and the
  diff that makes a path historical is the diff that marks it.

This mirrors the `# SPIKE-ARCHIVED:` convention landed the same day, and for
the same reason: an explicit, reviewable sentence beats silent rot, and the
escape hatch must be cheap or it will be worked around.

The concrete marker form is deliberately left to implementation — it must be
chosen against how `CLAUDE.md` actually reads today, and the file's existing
historical mentions are the test set. The requirement it must satisfy: the four
current dead citations either become correct or become marked, and no
present-day citation can be marked to silence it.

### D4 — Correct the map as part of this change, not after it

The four stale citations are not incidental cleanup. #2 is *how* #1 survived:
`CLAUDE.md` names `tests/test_packages_independence.py` as the enforcer of the
boundary invariant, so an agent checking whether packages are guarded finds a
confident answer, pointing at a file that was deleted. The correction and the
guard are one change because the map's inaccuracy is the mechanism.

## Risks / Trade-offs

- **The citation guard constrains the most-edited prose file in the repo.** →
  The escape hatch must be a single adjacent marker with no registration step
  (D3). If satisfying it ever takes more than one edit at the point of writing,
  it will be routed around, and a routed-around guard is worse than none
  because it still reads as coverage.
- **The `tach.toml` guard could be satisfied by adding a permissive entry.**
  Listing a package with wide-open dependencies passes the coverage check while
  granting no real protection. → Not solvable by this guard; the coverage check
  answers "is there a contract", not "is it tight". Noting the limit explicitly
  in the test docstring is the honest move, rather than implying more.
- **Three new gate checks on a suite already at ~1216 tests.** → All three are
  offline file reads; cost is negligible.
- **`ndjson_log`'s removal from `tach.toml` is load-bearing for the guard, not
  cosmetic.** → It must land in the same change, or the new guard fails on
  first run for a reason unrelated to the code under review.

## Migration Plan

No migration. No runtime code changes, no dependency changes, no wire or
signature changes. The change is additive to the gate plus two corrections;
rollback is reverting the commit.

Ordering within the change matters in one place: drop the stale `ndjson_log`
entry before or with the coverage guard, so the guard's first run reflects the
intended state.

## Open Questions

- **Does the citation guard extend to `CONSTITUTION.md` and `docs/adr/*.md`?**
  The ADR sweep is already a separate BACKLOG item (ADR re-evaluation triggers
  citing things that no longer run). Deliberately out of scope here; revisit
  once the marker convention has survived contact with `CLAUDE.md`.
- **Should the coverage guard also assert every listed module carries a
  dependency declaration?** That would catch the permissive-entry loophole
  above. Deferred — it needs a survey of what the current entries actually
  declare before a rule can be written that does not immediately need
  grandfathering.
