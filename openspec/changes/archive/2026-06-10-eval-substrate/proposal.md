## Why

The 2026-06-06 explore session committed a five-change program (`docs/architecture/extraction-fidelity-program.md`) to fix a *class* of extraction-fidelity bug, governed by ADR-0002 (real surface = ground truth; optimization ladder) and ADR-0003 (the coarse-select/LLM-interpret seam). Every change in that program is a hypothesis about extraction quality that **must be measured before it is cemented** — the explore session itself showed our intuitions can be wrong (the answerability signal may be redundant post-fix; the "menu" has cost cliffs). Today there is no instrument to measure this: the bench corpus (`eval/corpus.yaml`, `make bench`) is **live-network and non-deterministic**, capability tests use small hand-authored fixtures with a **faked** LLM, and there is **no VCR/replay layer**. We cannot validate a fidelity hypothesis, nor catch a regression in answer *shape*, without a repeatable substrate. This change builds that instrument first.

## What Changes

- **Deterministic replay mode** for the eval harness: fetch reads from frozen fixtures instead of the network at a defined injection seam, so a run is bit-reproducible.
- **Three-layer fixture capture** per corpus entry: (1) raw HTTP HTML, (2) rendered-DOM snapshot (post-JS, for the real-surface ground truth ADR-0002 names), (3) a pinned extracted-answer baseline. A `refresh` mode re-captures live to update snapshots / detect drift.
- **Multiple corpuses** with metadata + sync: a **happy-pass / real-problems regression** set (cases we've actually gotten stuck on — e.g. Hepsiburada; must keep passing; we observe answer-*shape* drift on it) and a **breaking / hypothesis-stress** set deliberately spanning the failure classes (A clean-schema, B source-omits/JS-only/bot-walled, C schema-lies/stale-price).
- **make-check vs make-bench split made explicit**: deterministic axes (data-contract conformance, token-cost accounting, answer-envelope *shape*) gate `make check` on frozen fixtures; LLM-judged axes (answer quality, clarity) stay informational under `make bench`. The judge model is pinned and recorded per run so quality deltas aren't confounded by judge drift.
- **Answer-shape drift observation**: a deterministic check that asserts the *structure* of the response envelope (which fields present, contract conformance) on the happy-pass set, robust to the non-deterministic prose.

Non-goals (deferred): the architectural changes themselves (typed boundary, menu, answerability, reconciliation — changes 2–5); full cross-source atomization; WebMCP. This change is the **instrument only**.

## Capabilities

### New Capabilities
- `eval-replay`: deterministic fixture-backed replay of the eval/extraction pipeline (capture, freeze, replay, refresh modes) — the repeatable substrate.
- `eval-corpus`: multi-corpus management (happy-pass regression + breaking-hypothesis sets) with metadata, sync, and the failure-class taxonomy (A/B/C/JS).

### Modified Capabilities
- `output-benchmark`: the bench gains a deterministic replay mode and an explicit make-check (deterministic axes, frozen) vs make-bench (LLM-judged, informational/live) split; judge-model pinning/recording.
- `test-layout`: records where fixtures, corpuses, and the replay seam live, and the deterministic-gates-only rule for `make check`.

## Impact

- Code: `src/a2web/llm_eval/` (corpus.py — multi-corpus + metadata; runner.py — replay/refresh modes; systems.py — fixture-intercept seam; report.py — judge-model recording; contract.py — deterministic shape/contract axis). A capture/refresh CLI under `llm_eval/`. A fixture store + index under `eval/` (gitignored large blobs vs committed small ones — TBD in design).
- The fetch injection seam: where replay intercepts (raw-tier response vs `JsonPayload` extraction vs `a2web_fetch`) — a design decision (the architecture agent flagged the raw tier as the cleanest seam).
- Tests: deterministic contract/token/shape axes wired into `make check` against frozen fixtures; the existing `tests/capabilities/output_benchmark/` harness-rot guards extended.
- No production runtime change, no wire/contract change, no new top-level dependency expected (snapshot storage uses stdlib/existing deps).
- Confirms no provisional ADR directly, but is the precondition that lets ADR-0004–0007 be confirmed by their changes.
