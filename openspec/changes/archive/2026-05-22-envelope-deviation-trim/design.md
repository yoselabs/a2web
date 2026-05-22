## Context

After `ask-response-diet` / `fetch-response-diet`, the serializers drop *empty* optionals and apply failure-only / debug-only tiers field-by-field. Two residual problems: the debug fields are six scattered top-level keys, and `tier` / `url` / `original_url` are always-present fields that carry signal only on the non-default path. This change applies one rule consistently — *present only on deviation* — and packs the debug tier into a structural sub-object.

As established by the prior diets, the `@model_serializer` is **wire-only**: it changes `model_dump()`, not attribute access. The only attribute-level change here is the debug fields moving into a nested model and `url` becoming builder-gated — both call out internal-caller impact below.

## Goals / Non-Goals

**Goals:**
- Debug observability is one opt-in `debug` sub-object, not six conditionally-present keys.
- `tier` and `url` appear only when they deviate from the default; `original_url` is removed.
- The deviation rule is uniform and lives in the shared `_prune_wire` helper.

**Non-Goals:**
- No change to the orchestrator, tier cascade, or extraction.
- No change to `confidence` / `extracted_answer` / `content_md` presence rules.
- No change to failure-only `status` / `narrative` / `diagnostics_summary` semantics (only `status`'s *mechanism* is generalized).

## Decisions

### Decision 1: Debug fields move into a `DebugInfo` sub-object

The six debug fields (`started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, `extraction`) stay declared **flat** on `AskResponse` / `FetchResponse`; the `@model_serializer` **regroups them into a wire-only nested `debug` object**. There is no `DebugInfo` model and no `debug` field — the nesting exists only in `model_dump()` output, exactly like the TSV rendering of `links` and the `[level, text]` tuple of `Heading`.

- **Why wire-only, not a real `debug` field:** `FetchResponse` is dual-use — the `fetch_raw` wire model *and* the orchestrator's internal type. The eval harness reads `response.extraction` (`systems.py:245`) and other debug-tier attributes directly; collapsing them into a nested model would break attribute access. Wire-only regrouping keeps every internal `.cache` / `.tokens` / `.extraction` / `.diagnostics` read working with zero churn.
- **Mechanism:** `_prune_wire` takes a `debug_fields: frozenset[str]` parameter; matching keys are pruned of empties and collected under `out["debug"]` instead of staying top-level. When every debug field is empty (the `debug=False` path — the builder already gates timing/cache/tokens on `fc.debug`), no `debug` key is emitted.
- **Alternative — a `DebugInfo` model field:** rejected; breaks the eval harness's direct attribute reads on `FetchResponse`.

### Decision 2: `tier` deviation-only via a generalized `_prune_wire` rule

`_prune_wire` currently hardcodes `status == ok` → drop. Generalize it with a `deviation: dict[str, str]` parameter mapping a field name to the default value that triggers omission. Callers pass `{"status": "ok", "tier": "raw"}`. `tier` leaves the required-field set; absence on the wire means a plain `raw` fetch.

- **Why a map, not more hardcoding:** `status` and `tier` are the same pattern ("drop when value == default"); one parameter expresses both and absorbs the existing `status` special-case.

### Decision 3: `url` is redirect-only, builder-gated

The serializer cannot compare `url` to the URL the caller requested — it does not have it. The builder does: the requested URL is `fc.original_url or fc.url` (pre-captcha-rewrite input), the fetched URL is `fc.final_url`. `build_response` sets the `url` field to `fc.final_url` only when it differs from the requested URL, else to `""` — which the empty-omission rule then drops. `url` leaves the required-field set.

- **Covers both deviation sources:** HTTP redirects (`final_url` differs) and captcha-host rewrites (`original_url` on `FetchContext` set).
- **No internal `.url` reader:** verified by grep — the eval harness reads `FetchResponse.extraction` / `.tier` / `.status` / `.diagnostics_summary` (all stay flat) but never `.url`. Builder-gating `url` therefore breaks no internal caller; only unit tests that assert `result.url` on a non-deviated fetch need updating.
- **Alternative — carry the requested URL on the model for the serializer to compare:** rejected; adds a field purely to feed the serializer when the builder already has every input.

### Decision 4: `original_url` is deleted

`original_url` only ever told the caller "what you originally asked for" — information the caller already holds. With `url` now meaning "we ended up here instead," `original_url` is fully redundant. Removed from both envelopes and from `build_response` / `build_ask_response`.

## Risks / Trade-offs

- **Breaking for both tools** → all changes marked BREAKING in proposal + CHANGELOG; contract goldens re-blessed to make the diff explicit.
- **Three "absence means X" rules** (`status`, `tier`, `url`) → a parser must encode three defaults. This is the deliberate cost of a lean envelope; documented in the spec scenarios.
- **`url` attribute is builder-gated** → unlike the wire-only serializer changes, this changes `.url` for internal callers; the single non-test reader (`systems.py`) gets the `url or entry.url` reconstruction.

## Open Questions

- Resolved during implementation: a grep of `.url` / debug-tier attributes across `src/a2web/llm_eval/` + `tests/` found no internal reader of `FetchResponse.url`, but several `.extraction` / `.cache` / `.tokens` readers — which is why the debug fields stay flat on the model and the `debug` nesting is wire-only (Decision 1).

## Migration Plan

1. Land the wire-only `debug` regrouping, both serializers, the `_prune_wire` deviation param, and the builder changes together.
2. Re-bless contract goldens (`make bless-contracts`); review the `ask_*` / `fetch_raw_basic` / `tool_schemas` diff.
3. CHANGELOG `[0.14.0]` documents the BREAKING changes.
4. Rollback: revert; envelopes return to the flat shape. No persisted state depends on the envelope.
