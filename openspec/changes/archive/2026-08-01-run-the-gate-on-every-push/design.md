## Context

Verified 2026-07-31: `.github/workflows/` contains exactly one file,
`release.yml`, triggered on `v*` tags. `make check` therefore runs at tag time
and at no other time.

This is the highest-leverage item in the backlog's T4 track, and it is
upstream of most of the rest of the backlog — nearly every proposed change adds
a guard, and guards are the thing not currently running.

## Goals / Non-Goals

**Goals**

- `make check` runs on push and on pull request.
- Nothing that claims to be enforcement is left running-but-dead.

**Non-Goals**

- Changing what `make check` contains. The gate is good; it is just not
  invoked.
- Adding the live-network targets (`make bench`, `make handler-probe`) to CI.
  They spend quota and hit real hosts; they are deliberately outside the gate
  and stay outside.
- Re-homing the Rego lint. Removing the dead hook is in scope; replacing the
  capability is a separate backlog entry.

## Decisions

### D1 — A separate `ci.yml`, with the gate job shared

`release.yml`'s gate job and CI's gate job are the same work. Duplicating the
YAML means they drift, and the one that drifts is the one nobody watches.

Prefer a reusable workflow (`workflow_call`) that both invoke, so there is one
definition of "the gate". If that adds more moving parts than it saves for two
callers, duplicate it and add a test that the two job definitions match — but
prefer the reusable workflow.

### D2 — Release keeps running the gate

Tempting to skip it on the grounds that CI already passed on that commit. Do not:
a tag can point at any commit, CI can have been skipped or its result stale, and
the release path publishes a public image. The release gate is cheap relative to
what it protects.

### D3 — Branch protection is documented, not assumed

A workflow that runs and reports red does not prevent a merge. Making the check
required is a GitHub repository setting.

This matters more here than usual: `fb:no-prs` means this repo merges to main
directly, so there is often no PR for a check to block. The realistic protection
is *the push is gated and the author sees red immediately*, not *the merge is
blocked*. Say that plainly rather than implying a block that does not exist —
overstating enforcement is the exact failure this change exists to fix.

### D4 — Remove the dead hook rather than repairing it

`a2kit lint rego` cannot run; a2kit is gone. Repairing it means re-homing the
Rego lint, which is real work already tracked. Removing it makes the gap
visible, which is the honest state.

## Risks / Trade-offs

- **Runner cost rises** from per-tag to per-push. The gate is offline and
  deterministic by design, so it is minutes, not hours. Acceptable, and the
  alternative is what we have.
- **The first CI run may be red.** Violations may have landed since the last
  tag — that is the hypothesis motivating this change. If so, that is the change
  discovering exactly what it was built to discover; fix or record each, do not
  weaken the gate to get green.
- **A reusable workflow is one more indirection** for two callers. Judged worth
  it because a drifted gate is silent, and a silent gate is what this change is
  about.

## Open Questions

- Should CI run on all branches or only `main` plus PRs? Pushing to a scratch
  branch and getting a red mail is noise; not gating it means a violation can
  sit. Probably all branches, since the repo merges to main directly and a
  scratch branch is often what becomes main.
- Should the browser gate (`make test-browser`, real Chromium launch) run on
  push too, or stay release-only? It is slow and network-dependent. Leaning
  release-only, with the note that it therefore does not guard a push.
