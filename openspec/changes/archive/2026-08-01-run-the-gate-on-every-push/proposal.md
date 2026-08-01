## Why

**The quality gate does not run on push or on pull request.** The only workflow
in `.github/workflows/` is `release.yml`, and its trigger is:

```yaml
on:
  push:
    tags:
      - "v*"
```

So `make check` — lint, types, the full test suite, coverage ≥85%, and **every
architecture guard** — executes when someone cuts a release tag, and at no other
time. Between tags, a violation lands and stays landed.

This makes almost everything else in the backlog worth less than it reads.
a2web's architectural strategy is *encode the invariant as a test and let CI
fail the build* — it is stated that way in CLAUDE.md eleven times, including
"runs in `make check` and therefore on CI". That sentence is true only in the
sense that a release is CI. A guard that runs at tag time is not a guard against
landing a violation; it is a release-blocker that discovers violations in
batches, at the worst moment, attributed to whoever tagged.

Two supporting findings from the same inspection:

- **`.pre-commit-config.yaml` still runs `uv run a2kit lint rego`.** a2kit was
  retired on 2026-07-22 and CLAUDE.md records the Rego lint as "dropped — a real
  loss". That hook cannot be succeeding.
- **Pre-commit covers lint only** — ruff, format, markdown, actionlint. It does
  not run tests or architecture guards, and it is local-only: a fresh clone and
  any CI runner have no hooks installed at all. The `no-local-shelf-source`
  guard is described in CLAUDE.md as enforced by both a hook and `make check`;
  neither reaches a contributor who has not run the installer.

Why now: this is a prerequisite. Every change that adds a guard — and most of
the backlog does — is adding a guard to a system that will not run it until the
next release.

## What Changes

- **A `ci.yml` workflow running `make check` on push and on pull request.** The
  same gate `release.yml` already runs, moved to where it does work.
- **The release workflow keeps its own gate run.** It is not replaced by CI;
  a tag must still verify rather than trust that the commit was green.
- **The dead `a2kit lint rego` pre-commit hook is removed**, and the Rego lint's
  absence is recorded as an accepted gap rather than a hook that appears to run.
- **Branch protection is documented as an operator step.** A workflow that runs
  and reports is not a workflow that blocks; making the check required is a
  repository setting, not a file, and must be stated so it is not assumed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `enforcement-integrity`: the quality gate SHALL run on every push and pull
  request, not only on release; a declared enforcement mechanism SHALL either
  run or be recorded as absent.

## Impact

- `.github/workflows/ci.yml` — new
- `.github/workflows/release.yml` — unchanged behaviour, possibly refactored so
  the gate job is shared rather than duplicated
- `.pre-commit-config.yaml` — remove the a2kit hook
- `CLAUDE.md` — the "and therefore on CI" claims are accurate only after this
  lands; several need rewording either way
- `BACKLOG.md` — the Rego re-homing entry gains the note that its stand-in hook
  was dead
- No dependency changes. Runner cost increases: the gate runs per push instead
  of per tag.
