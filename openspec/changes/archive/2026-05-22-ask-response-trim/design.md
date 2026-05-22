## Context

`ask-response-diet` (archived) gave `ask` the lean `AskResponse` envelope: empty-optional omission via a `@model_serializer(mode="wrap")`, failure-only `narrative`/`diagnostics_summary`, debug-only timing, a slim `extraction: {truncated}`, and `Heading` as a `[level, text]` tuple. This change is a small follow-up trimming three residual costs the user flagged on a real HN-front-page `ask` output.

The omit-empty serializer and the `build_ask_response` projection are the two seams that change. `fetch_raw` / `FetchResponse` are untouched.

## Goals / Non-Goals

**Goals:**
- `extraction: {truncated: false}` never appears; the truncation signal is preserved (as an operator hint) without the carrier object.
- `status` joins the failure-only tier — absence means success.
- `next_links` is tabular data, so it ships as TSV, not a JSON array of objects.

**Non-Goals:**
- No change to `fetch_raw` / `FetchResponse`, to the orchestrator, or to the tier cascade.
- No new tool parameters.
- No change to how `next_links` is *built* (handler + LLM composition is unchanged) — only its wire representation.

## Decisions

### Decision 1: `extraction` is debug-only; truncation becomes an operator hint

`build_ask_response` populates `AskResponse.extraction` only when `debug=True`. When `fr.extraction.truncated` is true, it appends an `OperatorHint(code="answer_truncated", message=..., fix=...)` to `operator_hints` — regardless of `debug`. So the actionable signal ("the answer may be incomplete — the page was truncated before extraction") always reaches the agent, while the metadata object is debug-only.

- **Why over keeping `extraction: {truncated}`:** when `truncated` is false (≈always), the object is zero information. An operator hint only materializes on the rare true case, and `operator_hints` is already the channel agents scan for actionable signals.
- `AskExtraction` stays as the debug-path model (full metadata). Its slim `truncated`-only shape is no longer used on the default path.

### Decision 2: `status` is failure-only via a serializer special-case

`status` is a `FetchStatus` enum — it is never "empty", so the existing omit-empty rule cannot drop it. The `AskResponse` `@model_serializer` gains one special case: drop the `status` key when its serialized value is `"ok"`. `status` also leaves `_ASK_REQUIRED_FIELDS` (the never-omit set). On `failed` / `partial` the value is a non-empty string not in the required set, so it is kept.

- **Why a serializer special-case, not builder logic:** `narrative`/`diagnostics_summary` go failure-only by the builder setting them to `""` (then omit-empty drops `""`). An enum has no empty sentinel, so the drop decision must live in the serializer.
- **Trade-off:** consumers doing `resp["status"]` break; the new contract is `resp.get("status", "ok")` or "key absent ⇒ ok". This is a deliberate, documented break — consistent with the failure-only tier `ask-response-diet` already established for `narrative`.

### Decision 3: `next_links` renders as a TSV block

The `AskResponse` serializer replaces the `next_links` value with a TSV string built from the typed `NextLink` list — reusing a2kit's `encode_tsv` (`a2kit.packages.formatter.tsv`) so escaping (tabs/newlines in `anchor`/`reason`) and column derivation match the framework's own TSV path.

- Columns: `anchor`, `url`, `reason`, and `kind` — but `kind` is omitted when every row's `kind` is `drilldown`. Mixed lists keep the `kind` column.
- Empty `next_links` is still omitted entirely (the omit-empty rule already covers the empty list — no TSV string is produced).
- The wire value of `next_links` becomes a `string`; the declared JSON schema still types it as an array. This schema/payload divergence is the same precedent `Heading` (tuple serializer) already set and is captured by the `tool_schemas` contract golden.

- **Why TSV:** a uniform `{anchor, url, reason, kind}` list is textbook tabular data; TSV collapses the repeated keys to a one-line header. a2kit dropped TOON for TSV on exactly this token-cost finding.
- **Alternative — keep JSON, just omit `kind` when `drilldown`:** smaller win (saves one key per row, not four); rejected in favor of TSV which subsumes it.

## Risks / Trade-offs

- **Three breaking wire changes at once** → all are marked BREAKING in the proposal + CHANGELOG; the contract goldens re-bless to the new shape, making the diff explicit and reviewable.
- **`next_links` as a string needs parsing** → for a multi-row list the token win outweighs the parse cost; for 0–1 rows it is a wash. Acceptable — `next_links` lists are typically 5–10 rows on aggregator pages, the exact case that motivated this.
- **TSV cell hygiene** → reusing a2kit's `encode_tsv` rather than hand-rolling means tab/newline escaping is the framework's tested behavior.
- **`status` removal surprises consumers** → highest-risk item; mitigated by CHANGELOG BREAKING note and the failure-only precedent. Absence-means-ok is a simple, learnable rule.

## Migration Plan

1. Land all three trims together (one serializer, one builder — same files).
2. Re-bless the contract goldens (`make bless-contracts`) and review the diff.
3. CHANGELOG `[0.12.0]` documents the three BREAKING wire changes.
4. Rollback: revert the change; `AskResponse` returns to the `ask-response-diet` shape. No persisted state depends on the envelope.

## Open Questions

- None. Scope is fixed by the four user-selected trims (the fourth — "omit `kind` when drilldown" — is folded into Decision 3 as the dropped TSV column).
