# Design — unified LLM contract-parsing discipline

## Context

Four LLM-output parsers exist in `src/a2web/`. Each guards a different boundary; each has different consequences for "the model dropped a field":

- `judge.py` — verdict (`scores`, `overall`, `reached`, `reasoning`).
- `extractor.py` — `_split_answer_and_routing` (answer + 7 router-shape fields) and `_split_answer_and_next_links` (answer + curated next-link candidates).
- `fetcher_response.py::_project_routing` — pydantic closed-enum validation of the package-side `RouterPayload`.
- `bench_judge.py` — bench-only clarity score + next_links score.

The cross-site invariant is that *every* boundary needs a policy for missing fields, that policy must be explicit, and the wobble must be observable. Today the policies are spread across docstrings, open-coded branches, and untyped log keys.

## Decisions

### Decision 1 — Discipline shape: a `WobbleTolerance` enum + per-field policy table

**Chosen:** A small enum + a per-boundary policy mapping + an `apply_policy` helper. Each parser declares a `dict[str, WobblePolicy]` and a `derive: Callable[[dict, str], object | None]` fallback.

```python
class WobbleTolerance(StrEnum):
    STRICT = "strict"      # raise — boundary cannot proceed
    DERIVE = "derive"      # compute from other already-parsed fields
    DEFAULT = "default"    # use a sentinel default
    SKIP = "skip"          # return None for the WHOLE boundary (not just this field)

@dataclass(slots=True, frozen=True)
class WobblePolicy:
    tolerance: WobbleTolerance
    default: object | None = None    # used by DEFAULT
    derive_from: tuple[str, ...] = ()  # documents which other fields DERIVE consults
```

**Alternatives considered:**

- **`LLMBoundary[T]` protocol** with `parse(raw: str) -> Result[T, ParseError]`. Too abstract: forces every site to re-implement the JSON-extraction step (`{...}` regex, fence-stripping, etc.) that today is duplicated but well-understood. The discipline we actually need is per-*field*, not per-*boundary*.
- **`ProjectWithDefaults[T]` helper** that takes a strict pydantic model + a defaults function. Cleaner for the router case but doesn't fit `judge.py` (no pydantic model — plain dataclass + manual JSON dict access). Forcing pydantic everywhere is a larger change with no payoff.
- **Pydantic `field_validator` + `pre=True`** with `pydantic.BaseModel.model_validate(..., context={"tolerance": ...})`. Concentrates the discipline inside pydantic and skips half the codebase (the dataclass-based parsers). Rejected for the same reason — heterogeneous parsers, need a discipline that works for both pydantic and raw-dict paths.

**Rationale.** The per-site policies have nothing in common *except* that each field has one of four fates. An enum is the smallest object that captures that. Helpers compose; the JSON-extraction step stays per-site (already-debugged code; no value in deduplicating).

### Decision 2 — Per-boundary policy table

| Site | Field | Tolerance | Rationale |
|---|---|---|---|
| `judge.py` | `scores` | STRICT | The judge axis is meaningless without per-criterion scores. |
| `judge.py` | `overall` | STRICT | Aggregate score; cannot be re-derived from `scores` alone (judge weights). |
| `judge.py` | `reached` | DERIVE (`overall >= 3`) | This is the wobble that motivated the proposal. `overall` already encodes pass/fail at the report-layer threshold; missing `reached` should never fail the cell. Matches the `harden-judge-parser` fix. |
| `judge.py` | `reasoning` | DEFAULT (`""`) | Reasoning is for human inspection; absence is annoying but not fatal. |
| `extractor.py::_split_answer_and_routing` | `answer` | STRICT | Without an answer the call has no product. Returns `(raw_text, None)` — the answer fallback is the raw text path, not a recovery within the JSON envelope. |
| `extractor.py::_split_answer_and_routing` | `structural_form`, `shape` | SKIP | When either is absent, drop the whole routing payload (the closed-enum mirror at `_project_routing` requires both). `answer` survives via the raw-text fallback. Today's behavior; codifies it. |
| `extractor.py::_split_answer_and_routing` | `genre`, `obstacle` | DEFAULT (`None`) | Documented optional fields. Today's behavior. |
| `extractor.py::_split_answer_and_routing` | `ask_here`, `try_url` | DEFAULT (`()`) | Documented optional collections. Today's behavior. |
| `extractor.py::_split_answer_and_next_links` | per-entry `anchor`/`url`/`reason`/`kind` | SKIP-entry | An invalid entry is dropped; the rest of the list survives. (SKIP applies per-list-entry here, not the whole list — a degenerate case the helper documents.) |
| `fetcher_response.py::_project_routing` | closed-enum violation on any field | SKIP | When pydantic rejects a value, drop the whole projected `RouterPayload`. `answer` already survived at the upstream boundary. Today's behavior; codifies it. |
| `bench_judge.py` clarity | `clarity` | STRICT | Bench axis is meaningless without the score. |
| `bench_judge.py` clarity | `reasoning` | DEFAULT (`""`) | Operator-readable but non-load-bearing. |
| `bench_judge.py` next_links | `next_links_score` | STRICT | Same as `clarity`. |
| `bench_judge.py` next_links | `reasoning` | DEFAULT (`""`) | Same. |

Two patterns to call out:

- **STRICT survives.** This is not a "make everything graceful" proposal. Three of the four sites have at least one field whose absence still raises.
- **The fallthrough for `SKIP` differs by site.** For `_project_routing`, SKIP drops `routing`; the answer survived upstream. For `_split_answer_and_routing`, SKIP returns `(text, None)`; the answer is the raw response text. The discipline names the policy; the fallthrough lives at each call site.

### Decision 3 — Where the helper lives

`src/a2web/packages/llm_extract/wobble.py`.

The package is the natural home: it already owns `Judge`, `Extractor`, `RouterPayload`, and `JudgeParseError`. The packages-independence rule (`tests/test_packages_independence.py`) requires `wobble.py` to have **zero imports from `a2web.<domain>`**. The shape of the discipline (enum, dataclass, structured log via `structlog.get_logger`) does not need any domain knowledge.

The two non-package call sites (`fetcher_response.py::_project_routing` and `llm_eval/bench_judge.py`) import the discipline from the package — same direction the import dependency already runs.

### Decision 4 — Observability

Every wobble fires a single structured log event with a stable schema:

```python
_LOG.warning(
    "llm_wobble",
    boundary="judge",                # the per-site name
    field="reached",                  # the wobbling field
    policy_applied="derive",          # which enum value handled it
    model="claude-haiku-4-5-20251001",
    raw_excerpt=text[:200],           # bounded; never the full response
)
```

The key is **always** `llm_wobble`. The five legacy keys (`routing_validation_failed`, `judge_failed`, `clarity_judge_failed`, `next_links_judge_failed`, plus the silent paths in `_split_answer_and_next_links`) collapse to a single searchable event. The `boundary` + `field` pair gives the same drill-down today's prefixed keys give, without operators having to know every prefix.

Bench artefacts (`eval/runs/.../wobble.jsonl`) can `grep "llm_wobble"` to compute per-axis wobble rates. The product judge case (`boundary=judge field=reached policy_applied=derive`) becomes a first-class signal instead of a `judge_failed` casualty.

### Decision 5 — Relationship to `harden-judge-parser`

`harden-judge-parser` lands the single most-painful symptom (judge `reached` missing → `judge_failed`) with a single-file fix and zero new abstractions. It is the **right** ship-first move; the regression is live and we shouldn't gate the fix on a cross-cutting discipline.

This proposal layers on top:

- If `harden-judge-parser` ships first (likely), this proposal swaps the open-coded derivation in `judge.py` for the shared `WobblePolicy.DERIVE` path. Same external behavior; same regression fix; the policy is now explicit and visible to the other three sites.
- If this proposal ships first (unlikely), `harden-judge-parser` is absorbed — its scenarios live in this proposal's spec delta. Drop `harden-judge-parser` from the queue.

Either order is safe. The two proposals do not need to be merged.

## Risks / Trade-offs

- **Risk:** Codifying today's `SKIP` policies hides legitimate breakage. *Mitigation:* every SKIP emits `llm_wobble`. A spike in `boundary=extractor field=structural_form policy_applied=skip` is a model regression we can now graph instead of swallow.
- **Trade-off:** A `dict[str, WobblePolicy]` per parser is more verbose than today's open-coded `parsed.get("genre")` branches. Verbosity is the point: the verbosity is the documentation.
- **Trade-off:** The discipline does not (yet) cover provider-level retries. A `JudgeParseError` on STRICT is still a hard fail; we are not adding "retry the LLM call with a stricter system prompt." That is a separate proposal if we ever want it.
