# Tasks

Do this change before the others. Every guard the rest of the backlog adds is
inert until it lands.

## 1. Establish the baseline

- [x] 1.1 Run `make check` on current `main` and record the result. If it is
      red, that is the finding this change predicted — record what landed since
      the last tag, and fix or file each item. Do NOT weaken the gate to reach
      green.
      **Result 2026-07-31 at `469ca5c`: GREEN.** 1274 passed, 2 deselected,
      coverage 90.96% (floor 85%), tach 69/69, `validate_manifests` OK. The
      predicted red run did not materialise — nothing had rotted between tags.
      Worth recording as a negative result: the gate's absence had not yet cost
      a landed violation, so this change is prevention, not cleanup.

## 2. Run the gate on push and PR

- [x] 2.1 Extract `release.yml`'s gate job into a reusable workflow invoked via
      `workflow_call`.
- [x] 2.2 Add `.github/workflows/ci.yml` calling it on `push` and
      `pull_request`.
- [x] 2.3 Decide branch scope (design Open Questions) and apply it.
- [x] 2.4 Point `release.yml` at the same reusable workflow, so there is one
      definition of the gate.
- [x] 2.5 Verify by pushing a commit that violates a known architecture guard on
      a scratch branch, and confirming CI goes red. A CI workflow that has never
      failed is not known to work.
      **Done 2026-07-31.** Branch `ci-verify-red`, a deliberate `json.loads`
      call in `packages/llm_extract/errors.py`. Run `30662476447` → **failure**
      in 1m30s at `test_no_json_loads_outside_wobble` — confirmed it failed for
      the intended reason, not incidentally.
- [x] 2.6 Revert the deliberate violation.

## 3. Remove enforcement that cannot run

- [x] 3.1 Delete the `a2kit-rego` hook from `.pre-commit-config.yaml`.
- [x] 3.2 Note in `BACKLOG.md`, on the existing Rego re-homing entry, that its
      stand-in hook had been dead since the a2kit sunset.
- [x] 3.3 Audit the remaining pre-commit hooks — confirm each invokes a tool
      that exists.

## 4. Stop overstating enforcement

- [x] 4.1 Document branch protection as an operator step, stating plainly that
      the realistic protection is a gated push with immediate red, not a blocked
      merge (`fb:no-prs` means there is often no PR).
- [x] 4.2 Correct CLAUDE.md's "runs in `make check` and therefore on CI"
      claims — accurate only after this change, and the
      `no-local-shelf-source` passage additionally overstates the hook.
- [x] 4.3 State what the actual floor is for each mechanism described as a hard
      block.

## 5. Close out

- [x] 5.1 `make check` green locally and in CI. Local: 1274 passed, 90.96%.
      CI on `main`: run `30662423192`, **success** in 1m38s.
- [x] 5.2 Confirm the CI badge / status reflects a real run on a real push.
      Both polarities observed on real pushes: green on `main`, red on the
      scratch branch. No badge is rendered anywhere yet — noted, not added.
- [x] 5.3 Move the BACKLOG T4 CI entry to `BACKLOG-CLOSED.md`.
