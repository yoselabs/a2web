# Tasks

## 1. Contract-impact check (before touching code)

- [x] 1.1 Confirm `partial` appears in no CLI contract capture under `tests/contracts/cli/`. `grep -rn partial tests/contracts/` → no matches.
- [x] 1.2 Confirm `partial` appears in no wire golden under `tests/contracts/wire/`, including a parsed search of `list_tools.json` for an inlined status enum. Both `partial` and `FetchStatus` absent — the served schema does not inline the enum.
- [x] 1.3 Census `FetchStatus` producers across `src/` and confirm no assignment or return writes `partial`. Producers are `fetcher_response.py:871,878,887,930` (`ok`, `failed`) and `models.py:670` (`ok`, in `_WIRE_DEVIATION`); `partial` has none.

## 2. Remove the member

- [x] 2.1 Delete `partial = "partial"` from `FetchStatus` in `src/a2web/models.py`.

## 3. Guard the class of defect

- [x] 3.1 Add `tests/architecture/test_every_fetch_status_has_a_producer.py`, walking `SRC_ROOT` for `FetchStatus.<member>` producer sites (assignment / annotated assignment / return), excluding comparisons.
- [x] 3.2 Open with a not-vacuous assertion — a walk finding zero producers must fail rather than pass every check below it.
- [x] 3.3 Assert every declared member has a producer, failing with the member names.
- [x] 3.4 Assert the guard actually catches the regression: a member with only a comparison site is reported unproduced (`test_a_comparison_alone_does_not_count_as_a_producer`), plus `test_a_return_counts_as_a_producer` for the other direction.
- [x] 3.5 Tag with `@pytest.mark.protects` citing the modified `app-composition` requirement. Cited as `spec:app-composition` + the requirement heading rather than `change:` — the heading is unchanged by the delta, so the marker resolves both before and after archive.

## 4. Verification

- [x] 4.1 Run the new guard file alone; confirm it passes and that the not-vacuous check is doing work. 4 passed.
- [x] 4.2 `make check` (lint + ty + test-cov + arch) green, with no wire-golden re-bless. **1890 passed, 92.15% coverage, tach clean, 186 architecture tests passed.**
- [x] 4.3 No live-network or metered run needed — this change touches no external system, so workflow-a's `cost-approval` suspension does not fire (`make bench` is not required and is not run).
- [x] 4.4 **The guard was proven red before it was trusted green.** `partial` was reinstated in `models.py`, the guard run (`1 failed` — *"declared `FetchStatus` members that no code path in src/ emits: partial"*), and the file restored. A census guard that has never failed is indistinguishable from one that cannot.

## 5. Unanticipated: the architecture registry

- [x] 5.1 **Not in the original plan.** `make check` failed on `test_architecture_registry_is_complete.py`: `docs/architecture/README.md` lists every guard, and a new guard file must be registered — *"a registry that lists some of the guards is worse than none: a reader takes it as the enforced set."* Added the one-line entry. Mechanical, correctly caught by the repo's own structure, and resolved in-session rather than escalated.

## 6. Ship

- [x] 6.1 `openspec archive retire-unproduced-fetch-status`. One requirement modified in `openspec/specs/app-composition/spec.md`; no spec added or removed.
- [x] 6.2 Commit `feat(models)` (`11f5b84`) + `chore(openspec): archive` (this commit), citing `a2web-0br`.
- [x] 6.3 Close `a2web-0br`.
