# Tasks

Do this change before the others. Every guard the rest of the backlog adds is
inert until it lands.

## 1. Establish the baseline

- [ ] 1.1 Run `make check` on current `main` and record the result. If it is
      red, that is the finding this change predicted — record what landed since
      the last tag, and fix or file each item. Do NOT weaken the gate to reach
      green.

## 2. Run the gate on push and PR

- [ ] 2.1 Extract `release.yml`'s gate job into a reusable workflow invoked via
      `workflow_call`.
- [ ] 2.2 Add `.github/workflows/ci.yml` calling it on `push` and
      `pull_request`.
- [ ] 2.3 Decide branch scope (design Open Questions) and apply it.
- [ ] 2.4 Point `release.yml` at the same reusable workflow, so there is one
      definition of the gate.
- [ ] 2.5 Verify by pushing a commit that violates a known architecture guard on
      a scratch branch, and confirming CI goes red. A CI workflow that has never
      failed is not known to work.
- [ ] 2.6 Revert the deliberate violation.

## 3. Remove enforcement that cannot run

- [ ] 3.1 Delete the `a2kit-rego` hook from `.pre-commit-config.yaml`.
- [ ] 3.2 Note in `BACKLOG.md`, on the existing Rego re-homing entry, that its
      stand-in hook had been dead since the a2kit sunset.
- [ ] 3.3 Audit the remaining pre-commit hooks — confirm each invokes a tool
      that exists.

## 4. Stop overstating enforcement

- [ ] 4.1 Document branch protection as an operator step, stating plainly that
      the realistic protection is a gated push with immediate red, not a blocked
      merge (`fb:no-prs` means there is often no PR).
- [ ] 4.2 Correct CLAUDE.md's "runs in `make check` and therefore on CI"
      claims — accurate only after this change, and the
      `no-local-shelf-source` passage additionally overstates the hook.
- [ ] 4.3 State what the actual floor is for each mechanism described as a hard
      block.

## 5. Close out

- [ ] 5.1 `make check` green locally and in CI.
- [ ] 5.2 Confirm the CI badge / status reflects a real run on a real push.
- [ ] 5.3 Move the BACKLOG T4 CI entry to `BACKLOG-CLOSED.md`.
