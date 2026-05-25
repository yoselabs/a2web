## Context

`ask` is the primary tool agents call against a2web. The server-side Haiku extractor already reads the entire page to answer a single question — yet the response surface tells the calling agent nothing about *what else* the page could answer. Agents must guess, re-ask, or escalate blindly.

Six spike rounds (v1 → v6) explored the space:

- **v1** (5 URLs, generic prompt): confirmed quality is high enough; identified `missed_sections` as hallucination-prone (arXiv abstract case).
- **v2 + v3** (30 URLs × 3 variants): locked the V_CTX context-aware prompt; ruled out `V_LEAN` as a standalone second call (page-content cost dominates).
- **v4** (calibration on 14 weak cases): single-axis `confidence` field was degenerate (always `high`, even on wrong labels).
- **v5** (two-axis rubric with hard cluster trigger): 0 envelope violations across 30 URLs, content_value well-distributed, 5/30 confidence dropped to medium — calibration finally honest.
- **v6** (4-name × 6-run benchmark): `affordances` scored highest behavioral grounding (2.67/5 vs 2.33 for `signals`/`hints`/`leads`). Cold-reading test showed the alternatives drag the model's mental model into wrong domains (`leads`→CRM, `hints`→RAG citations).

Spike artefacts live under `eval/spikes/affordances_v{1..6}*.py` and findings under `eval/findings_2026-05-24-affordances-*.md`. The implementation lifts the V_CTX_V3 prompt from `eval/spikes/affordances_v5_two_axes.py` verbatim into the production template.

## Goals / Non-Goals

**Goals:**

- Surface affordances on the `ask` wire shape by default; consumers decide whether to use them.
- Keep boundary-type discipline: package-side frozen dataclass (no domain imports), pydantic mirror at the API edge with typed Literal enums.
- Preserve byte-stable cache-prefix discipline (v0.19 invariant) — schema example MUST live in `tail`, not `cache_prefix`.
- Add an opt-out path (`include_affordances=False`) for high-volume callers wanting the lean v0.14 envelope shape — preserves the existing cost profile.
- Pre-ship: fix the v5-found Amazon miscalibration via a new `G_commerce` cluster.
- Honor a2web's existing `_prune_wire` envelope discipline — obstacle pages omit redundant fields.
- Bench-driven naming: `affordances` chosen over `signals`/`hints`/`leads` based on empirical model behavior.

**Non-Goals:**

- No content-value-driven escalation (auto-browser-tier on `content_value=low`) — deferred to BACKLOG.
- No affordances surface on `fetch_raw` — that tool stays minimal (no LLM step).
- No additional confidence-calibration tuning beyond adding `G_commerce` — further iterations need their own spike.
- No LDD telemetry surfacing of affordances field — deferred.
- No new external dependencies — pure prompt + parser + pydantic work.

## Decisions

### D1: Two prompt templates instead of one conditional template

`EXTRACT_CACHEABLE_V1` (existing) stays untouched. New `EXTRACT_WITH_AFFORDANCES_V1` is a sibling template — same `system`, same `cache_prefix_template` (byte-equal — load-bearing for cache invariance), different `tail_template`.

**Alternative considered:** single template with a conditional block. **Rejected** because the v0.19 cache-prefix invariant requires byte-identical prefixes across all `ask` values; varying the template structure complicates cache reasoning. Two named templates make the contract explicit.

### D2: AffordancesPayload boundary type lives in `packages/llm_extract/`

Package-side `AffordancesPayload` is a frozen `@dataclass(slots=True)` with string-typed fields. The pydantic mirror with closed `Literal` enums lives in `src/a2web/models.py` (domain side). Projection happens at the seam in `fetcher_response.build_ask_response`.

**Why split:** `tests/test_packages_independence.py` enforces no domain imports under `packages/`. Closed-enum `Literal` types would require importing pydantic into the package, which is fine, but keeping the package-side type a plain dataclass with string fields is consistent with the rest of `packages/llm_extract/`.

**Alternative considered:** pydantic both at boundary and inside the package. **Rejected** for consistency with existing patterns (`LlmNextLink` follows the same shape).

### D3: Default `include_affordances=True`

User decision: "a2web should not decide — consumer decides." The default-on shape ensures every `ask` call surfaces signal an agent could use. Callers wanting the lean v0.14 envelope (or wanting to shave the +18% completion-token cost) opt out via `include_affordances=False`.

**Alternative considered:** default off. **Rejected** because most agents calling `ask` would benefit from affordances and we don't want to gate value behind an opt-in.

### D4: Closed enums via typed Literal at the pydantic boundary

`page_kind`, `page_kind_confidence`, `content_value`, and `shape.label` are all typed `Literal` enums on the pydantic side. Values outside the closed set raise validation errors and fall through to `affordances=None`.

**Why closed enums:** the v5 spike confirmed the model adheres to closed vocabularies reliably (0 free-text drift across 30 URLs × 3 variants). Open enums would let prompt drift introduce vocabulary creep that downstream agents can't depend on.

**Alternative considered:** open string with a documented closed-set hint. **Rejected** — agents over MCP need a contract.

### D5: Envelope discipline matches a2web's `_prune_wire` pattern

When `page_kind` is `paywalled`/`error`/`empty`/`blocked`, the wire-side serializer omits `content_value`, `shapes`, `follow_up_questions`. Their absence carries meaning. This matches the existing `AskResponse` envelope discipline (omit `narrative`/`diagnostics_summary` on success, omit empty optionals).

### D6: G_commerce cluster as a pre-ship fix, not a follow-up

v5 found `product-amazon → listing` claimed `high` confidence — the cluster trigger didn't fire because `listing` and `product-page` weren't in a shared cluster. Adding `G_commerce: {listing, product-page, package-page}` before shipping costs nothing (prompt-only change) and patches the one production-relevant miscalibration the spike surfaced.

### D7: Affordances JSON addendum lives at the end of the tail

Existing pattern: `request_next_links=True` appends a fenced JSON request to `tail`. Affordances follows the same shape — a fenced JSON request appended after the answer, parsed by a fence-tolerant parser. The two can coexist (next_links + affordances both opt-in) without competing for the same tail slot.

**Cache invariance:** the affordances request is part of `tail`, which is per-call variable already. `cache_prefix` remains byte-stable across all `(content, ask, include_affordances, request_next_links)` combinations for a given `content`.

### D8: Failure modes degrade gracefully to `affordances=None`

Three failure paths, all degrade silently to `affordances=None` while preserving `extracted_answer`:

1. Model returns malformed JSON → fence-tolerant parser fails → `affordances=None`.
2. Pydantic validation fails on closed enums (e.g. `page_kind="diagram"`) → `affordances=None`.
3. LLM unavailable / fetch failed → no extraction step ran → `affordances=None` (existing path).

In all three, `extracted_answer` and any next_links are unaffected. An operator hint records the parse-failure case so callers can detect schema drift.

## Risks / Trade-offs

[Risk: Default-on bloats every response, increasing context for high-volume callers] → Mitigation: opt-out via `include_affordances=False`; documented in tool description.

[Risk: Model drifts on the page_kind enum over time (new content types appear, schema doesn't capture them)] → Mitigation: closed enum + `other` catch-all; the parser drops to `affordances=None` on enum mismatch (no crash, no silent vocabulary creep). Drift visible in production logs.

[Risk: Marginal cost is genuinely +18% per `ask` call on long pages] → Mitigation: actual cost is dominated by prompt tokens (page content); completion tokens are ~500 of ~20k total. v5 spike confirmed the math holds at 30-URL scale. High-volume callers can opt out.

[Risk: Adding fields to `AskResponse` is technically breaking for clients with strict field enumeration] → Mitigation: additive change, documented in CHANGELOG; existing test client validates wire compatibility.

[Risk: Cache-prefix byte-equality could be accidentally violated by future edits to `EXTRACT_WITH_AFFORDANCES_V1`] → Mitigation: a spec scenario asserts cache-prefix byte-equality for any `(X, Y1)` vs `(X, Y2)`; covered by a unit test in `tests/packages/llm_extract/test_prompt_cache_stability.py`.

[Risk: Affordances quality regresses silently on a particular content class not in the 30-URL bench corpus] → Mitigation: output-benchmark gate (`make bench`) before merge; failures land as findings file with reproducer.

## Migration Plan

1. **Land the change** behind the default-on flag. Existing callers see new field; field is small (~250 bytes typical).
2. **CHANGELOG documentation** — call out the field as additive, document the opt-out kwarg.
3. **Output-benchmark gate** — run `make bench` before merge. Compare answer-quality axes with affordances on vs off; expect parity (the prompt change is local to the tail).
4. **No rollback path needed** — purely additive. If quality regresses, flip default to `False` in a follow-up (`include_affordances=False`).

## Open Questions

- None blocking ship. Two questions deferred to BACKLOG:
  - Should `content_value=low` on a content-kind page auto-trigger browser-tier escalation? (Telemetry-first.)
  - Should we surface affordances on LDD events for in-process observability? (Telemetry-first.)
