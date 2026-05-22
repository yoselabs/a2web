## Context

`AskResponse` already carries a `@model_serializer(mode="wrap")` that drops empty optionals, special-cases `status` (failure-only), and renders `next_links` as TSV. `FetchResponse` — returned by `fetch_raw` and, internally, by the shared `fetcher.fetch()` orchestrator — still serializes every declared field. A real `fetch_raw` payload is ~22 keys, the majority `null` / `[]` / `{}`.

Critically: the `@model_serializer` is **wire-only**. It changes `model_dump()` output, not attribute access. `fetch()`'s internal callers (the eval harness, unit tests, `build_ask_response`) read `FetchResponse` attributes directly and are completely unaffected — exactly as `ask-response-diet` proved for the `ask` path.

## Goals / Non-Goals

**Goals:**
- `FetchResponse` gets the same lean wire treatment as `AskResponse`: empty-omission, failure-only `status`/`narrative`, debug-only timing, TSV for link arrays.
- The omit-empty + TSV logic is written once and shared, not copy-pasted between the two envelopes.
- `fetch()` attribute-reading callers keep working with zero changes.

**Non-Goals:**
- No change to the orchestrator, tier cascade, gate, or extraction.
- No change to `AskResponse` behavior (its wire shape is already correct; only its *implementation* is refactored onto the shared helper).
- No new tool parameters.
- `content_md` stays — it is the whole point of `fetch_raw`; this is not an `ask`-style "drop the page" change.

## Decisions

### Decision 1: Extract a shared empty-omission serializer helper

`AskResponse._omit_empty` and the new `FetchResponse._omit_empty` are ~90% identical (drop `None`/`[]`/`{}`/`""`, never drop a required-field set, special-case `status`, render link fields as TSV). Extract a module-level helper — `_prune_wire(data, *, required, tsv_fields)` — that both serializers call.

- **Why:** two hand-maintained copies of subtle serialization logic drift. One helper, two thin `@model_serializer` methods.
- **Alternative — a shared base class:** rejected; pydantic model inheritance with a `@model_serializer` on the base is more surprising than a plain function the two serializers delegate to.

### Decision 2: `FetchResponse` field tiers mirror `AskResponse`

- **Always present:** `url`, `tier`, `confidence`. (`content_md` is kept by the empty-omission rule whenever non-empty — it does not need to be in the never-drop set; an empty `content_md` on a failed fetch *should* drop.)
- **Failure-only:** `status`, `narrative`, `diagnostics_summary` — dropped when the fetch succeeded.
- **Debug-only:** `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`. These are populated by `build_response` only when `debug=True`; the serializer then drops them as empties when absent.
- **Omitted when empty:** `title`, `byline`, `published`, `original_url`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, `extracted_answer`.

`extraction` / `extracted_answer` are always empty on a `fetch_raw` call (no LLM step) — no model change needed, the omit-empty rule simply removes them. They remain declared on `FetchResponse` because the shared `fetch()` orchestrator populates them when invoked with `ask=` by internal callers.

### Decision 3: `tokens` becomes debug-only

`tokens` is `{full: <char count of content_md>}`. The agent already has `content_md` and can measure it; the count is observability, not signal. `build_response` populates `tokens` only under `debug`. (`fetch_raw` exposes `debug` already.)

- **Alternative — keep `tokens` always:** rejected; it is redundant with the content the caller already holds.

### Decision 4: `links` and `next_links` render as TSV

Both are uniform lists of small records (`links`: `anchor`/`href`/`role`; `next_links`: `anchor`/`url`/`reason`/`kind`). The TSV treatment `ask` uses for `next_links` extends to both, via the shared helper's `tsv_fields` set. `next_links` keeps the "drop `kind` column when all-drilldown" rule. `links` is only ever populated when the caller passes `include_links=True`.

- **Why:** consistency with `ask`, and `links` on an aggregator page is the single largest array `fetch_raw` can emit — TSV is the biggest single win there.

## Risks / Trade-offs

- **Four breaking wire changes for `fetch_raw`** → `fetch_raw` is the documented fallback tool (~5% of reads), lower blast radius than `ask`. All marked BREAKING in proposal + CHANGELOG; the `fetch_raw_basic` contract golden re-blesses to make the diff explicit.
- **Shared helper must serve two slightly different required-sets / tsv-field-sets** → the helper takes them as parameters; each serializer passes its own. No hidden coupling.
- **`fetch()` internal callers** → unaffected (serializer is wire-only); covered by the existing eval + unit suites which read attributes.
- **`links`/`next_links` as strings vs declared array schema** → same schema/payload divergence `Heading` (tuple) and `ask`'s `next_links` already established; captured by the `tool_schemas` contract golden.

## Migration Plan

1. Land the shared helper + both serializers + `build_response` tier changes together.
2. Re-bless contract goldens (`make bless-contracts`); review the `fetch_raw_basic` + `tool_schemas` diff.
3. CHANGELOG `[0.13.0]` documents the `fetch_raw` BREAKING changes.
4. Rollback: revert; `FetchResponse` returns to the full-field wire shape. No persisted state depends on the envelope.

## Open Questions

- Should `fetch_raw` also gain an `AskResponse`-style hard split into its own model, or is the shared `FetchResponse` + wire-only serializer enough? Current lean: the serializer is enough — `FetchResponse` is already the right *shape*, it just over-serializes. A second model would duplicate ~20 fields for no behavioral gain. Resolve during specs review.
