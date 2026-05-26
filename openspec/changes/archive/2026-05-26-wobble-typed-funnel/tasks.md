# Tasks — wobble-typed-funnel

Step ordering is load-bearing. See `design.md` "Migration order".

---

## Step 0 — Verify the type-check gate

- [ ] 0a. **Confirm `ty` flags `NewType` mismatch.** Write a 5-line scratch test: `Foo = NewType("Foo", str)`; `def f(x: Foo): ...`; `f("bare string")` — confirm `ty` errors. If `ty` doesn't flag, fall back to `pyright` for the gate and update `make check` accordingly (record decision in design D8).
- [ ] 0b. **Read** `scripts/spike_typed_funnel_wobble.py` (kept from explore session 2026-05-26) — the API shape was validated there.

## Step 1 — Build `wobble/` folder side-by-side

- [ ] 1a. Create `src/a2web/packages/llm_extract/wobble/__init__.py` with the new surface (Wobbled, parse_with_policy, unwrap, plus re-exports of WobblePolicy / WobbleTolerance / WobbleSkip / emit_wobble for back-compat during migration).
- [ ] 1b. Create `wobble/_internal.py` — move `_Parsed[T]` (new), `_apply_field` (relocated from old `apply_policy` body), `_strip_fences` (new, lifted from extractor.py).
- [ ] 1c. Create `wobble/_policies.py` — define `EXTRACTOR_ROUTING_POLICY`, `EXTRACTOR_NEXT_LINKS_POLICY`, `JUDGE_VERDICT_POLICY`, `BENCH_CLARITY_POLICY`, `BENCH_NEXT_LINKS_POLICY`. Start with the policies currently inline in each consumer.
- [ ] 1d. Keep the old `wobble.py` intact for now — both surfaces coexist. The old module re-exports from the new folder (`from .wobble import *`) so existing imports keep working.
- [ ] 1e. `make check` — green. Both surfaces resolve.

## Step 2 — Migrate `_split_answer_and_routing`

- [ ] 2a. Rewrite `extractor._split_answer_and_routing` to call `parse_with_policy(raw, policies=EXTRACTOR_ROUTING_POLICY, into=RouterPayload, boundary="extractor.router_shape", model=...)`. Catch `ParseError` and return `(text, None)`.
- [ ] 2b. Confirm `_split_answer_and_routing` return type is now `tuple[str, Wobbled | None]`.
- [ ] 2c. Update one immediate caller in `extractor.Extractor.extract` to unwrap once at the seam.
- [ ] 2d. Run targeted test: `tests/packages/llm_extract/test_extractor_router_parse.py` — shape parity required.
- [ ] 2e. `make check` — green.

## Step 3 — Migrate `_split_answer_and_next_links`

- [ ] 3a. Same pattern as step 2 with `EXTRACTOR_NEXT_LINKS_POLICY` and `into=` a small dataclass holding `(answer, next_links)`.
- [ ] 3b. `make check` — green.

## Step 4 — Migrate `judge.parse_verdict`

- [ ] 4a. Rewrite to use `parse_with_policy(..., into=JudgeVerdict, policies=JUDGE_VERDICT_POLICY)`.
- [ ] 4b. Drop the now-redundant local `_JUDGE_POLICY` table (moved to `_policies.py` in step 1c).
- [ ] 4c. Run `tests/packages/llm_extract/test_judge*.py`. `make check` — green.

## Step 5 — Migrate `bench_judge._parse_clarity` and `_parse_next_links`

- [ ] 5a. Same pattern as step 4 with `BENCH_CLARITY_POLICY` and `BENCH_NEXT_LINKS_POLICY`.
- [ ] 5b. Drop the local `_CLARITY_POLICY` / `_NEXT_LINKS_POLICY` tables.
- [ ] 5c. `make check` — green.

## Step 6 — Adapt `fetcher_response._project_routing`

- [ ] 6a. Resolve design D7's open question: stress-test fitting pydantic-validate as a policy. Pick: (i) funnel through `parse_with_policy` if shape fits, OR (ii) keep `_project_routing`'s bespoke `apply_policy` call but accept `Wobbled[RouterPayload]` as input.
- [ ] 6b. Implement chosen shape. Confirm `_project_routing` no longer calls `json.loads`.
- [ ] 6c. Run `tests/test_fetcher_response*.py`. `make check` — green.

## Step 7 — Retire the old surface

- [ ] 7a. Delete `src/a2web/packages/llm_extract/wobble.py` (the flat module).
- [ ] 7b. Update `packages/llm_extract/__init__.py`: keep `Wobbled`, `parse_with_policy`, `unwrap`, `WobblePolicy`, `WobbleTolerance`, `WobbleSkip` in `__all__`. Decide whether `apply_policy` and `emit_wobble` remain public (audit consumers; retire if zero).
- [ ] 7c. Grep for `from a2web.packages.llm_extract import apply_policy` — should be zero hits.
- [ ] 7d. `make check` — green.

## Step 8 — Document and snapshot

- [ ] 8a. Update CLAUDE.md "LLM contract parsing" section: replace "every site declares a per-field `WobblePolicy`" with "every site funnels through `wobble.parse_with_policy`; policy tables live centrally in `wobble/_policies.py`."
- [ ] 8b. Update CLAUDE.md "Never" list: add "Never call `json.loads` inside `packages/llm_extract/` outside `wobble/`." (Lands ahead of the archon rule from `arch-fitness-functions-bootstrap`.)
- [ ] 8c. Capability test: write or extend `tests/capabilities/wobble_funnel/` confirming every consumer site receives a `Wobbled` and that `llm_wobble` events fire on optional-field misses for each of the five policies.

## Step 9 — Verify against the bench

- [ ] 9a. Run `make bench` (single-URL smoke or 5-URL subset — full bench is expensive). Confirm output envelopes are byte-stable and `llm_wobble` events appear on stdout for any optional field the model drops.
- [ ] 9b. Compare against the v0.23 bench artefacts under `eval/runs/` for shape parity.

---

## Done definition

- [ ] All four canonical sites route through `parse_with_policy`.
- [ ] `packages/llm_extract/wobble.py` (flat module) deleted; replaced by `wobble/` folder.
- [ ] `make check` green (lint + ty + test + 85% coverage).
- [ ] `llm_wobble` events fire for *every* recovered optional field at the four sites.
- [ ] CLAUDE.md updated.
- [ ] The `arch-fitness-functions-bootstrap` change can be picked up next without merge conflicts.
