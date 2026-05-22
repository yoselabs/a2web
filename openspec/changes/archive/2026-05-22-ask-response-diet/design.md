## Context

a2kit's formatter (`packages/formatter/__init__.py`) serializes every tool return with a plain `model_dump(mode="json")` — no `exclude_none`, no `exclude_defaults`. a2web has no serialization hook. So every field on `FetchResponse` reaches the wire: `byline:null`, `published:null`, `fit_md:null`, `meta:{}`, `links:[]`, `diagnostics:[]`, `operator_hints:[]`, `original_url:null`, `is_user_authored:false`, plus the always-present `content_md`.

`ask` and `fetch_raw` (`routers.py`) both return the shared `FetchResponse`; `ask` merely additionally fills `extracted_answer`. The `ask` premise is "small model extracts server-side, keeping caller context tiny" — but `content_md` ships the whole page anyway, dominating the payload (~70% on a HN front-page fetch).

`fit_md` has been unconditionally `None` since v0.3 (`fetcher_response.py:148`); the pruning filter it reserved space for never shipped and was superseded by JSON-synth (v0.11) and the LLM extractor.

Constraint from CLAUDE.md: changing the response envelope shape is breaking for MCP clients — flagged explicitly under "Ask First". This change accepts that break deliberately and documents it.

## Goals / Non-Goals

**Goals:**
- `ask` returns an answer-shaped envelope, not a page-shaped one. `content_md` is opt-in.
- Delete the dead `fit_md` / `TokenCounts.fit` carry-over.
- Empty/null optional fields are absent from the wire, not serialized as `null`/`[]`/`{}`.
- HN front-page stories expose both article and discussion URLs.
- `fetch_raw` stays a content-shaped tool — unchanged except `headings` tuple compression.

**Non-Goals:**
- No change to the tier cascade, gate, or extraction logic.
- No snippet-based grounding (the extractor returning supporting quotes instead of full `content_md`) — noted as a future fork, out of scope here.
- No rework of `confidence` semantics, even though `_confidence_for` derives from `len(content_md)` and is a weak signal on `ask`. Tracked as an open question.
- Not waiting on an a2kit release — the empty-omission mechanism ships in-repo now (Decision 3).

## Decisions

### Decision 1: Split the model — new `AskResponse`, keep `FetchResponse` for `fetch_raw`

`ask` returns a new `AskResponse` model; `fetch_raw` keeps `FetchResponse`. `AskResponse` simply does not declare `content_md`, `headings`, `tokens`, `fit_md`, or `is_user_authored` as default fields.

- **Why over a shared model with param gating:** a shared model still *declares* the heavy fields, so the output schema advertises them and a partial-fill is invisible to typed consumers. Two models give each tool an honest schema.
- **Alternative — `ask` returns `dict`:** full control, but loses the typed return annotation (schema discovery, in-process test client field-compare). Rejected — the typed model is worth keeping.
- `include_content: bool = False` on `ask` adds `content_md` (and `headings`) back when the caller explicitly wants grounding. When `True`, those fields are populated on `AskResponse`; when `False` they are absent.

### Decision 2: Delete `fit_md` and `TokenCounts.fit` outright

Not deprecate — delete. `fit_md` is removed from `FetchResponse`; `TokenCounts` collapses to a single `full: int` (or `tokens` is dropped from `AskResponse` entirely and kept debug-only on `FetchResponse`). The `fit-md` capability spec is removed.

- **Why delete vs keep-for-forward-compat:** CLAUDE.md's forward-compat note predates JSON-synth + LLM extraction. There is no pruning-filter roadmap. A field that is provably always `None` is pure noise and a standing "what is this?" tax on every reader.

### Decision 3: Empty-omission via a model-level serializer in a2web, plus an a2kit feedback ask

The clean long-term fix is a2kit formatter support for `exclude_none` / `exclude_defaults`. That needs an a2kit release. To ship now without waiting:

- `AskResponse` (and optionally `FetchResponse`) define a pydantic `@model_serializer(mode="wrap")` that drops keys whose value is `None`, `[]`, `{}`, or `""` for the designated optional fields. a2kit's `model_dump(mode="json")` runs the custom serializer, so the pruned shape reaches the wire with no a2kit change.
- Required fields (`url`, `status`, `tier`, `extracted_answer`, `confidence`) are never dropped, even if somehow falsy.
- A new entry in `docs/history/A2KIT_FEEDBACK_v0.*.md` requests first-class formatter `exclude_none` support so the custom serializer can later be retired.

- **Alternative — wait for a2kit:** rejected, blocks the whole token win on an external release.
- **Alternative — post-process the dict in the tool body:** can't — the tool returns a model and a2kit serializes downstream of the tool. The serializer must live on the model.

### Decision 4: Failure-only and debug-only field tiers on `AskResponse`

- `narrative`, `diagnostics_summary`: emitted only when `status != ok`. On success they restate `status` + `tier`.
- `started_at`, `total_ms`, `cache`, `diagnostics`: present only when `debug=True`.
- `extraction` on the wire is slimmed to `truncated` (the only field an agent branches on). `model`, `template_name`, token counts, `cost_usd`, `latency_ms`, `cache_hit` move to `debug` and remain on LDD events. Implemented as a slim `AskExtraction` projection, or by reusing the model-serializer to drop the observability keys outside `debug`.

### Decision 5: HN dual URLs in `content_md`, single URL in `next_links`

`_render_front_page` (`handlers/hn.py`) emits one line per story carrying both links:
`- **Title** (961 pts, 396 comments) — [article](url) · [discussion](https://news.ycombinator.com/item?id=<id>)`.

`next_links` keeps **one** `NextLink` per story (the article URL, `kind="drilldown"`) — emitting two entries per story would double an already token-sensitive array. The discussion URL lives in `content_md` for callers that opted into content.

- **Alternative — add `comments_url` to `NextLink`:** rejected — widens a shared boundary type for one handler's need.

### Decision 6: `headings` tuple compression on `fetch_raw`

`Heading` renders as `[level, text]` on the wire instead of `{"level": N, "text": "..."}`. Implemented via a `@model_serializer` on `Heading`. `ask` drops `headings` entirely (unless `include_content=True`), so this only affects `fetch_raw`.

### Decision 7: Golden contract tests guard the wire shape

The conditional field-presence logic (the model serializer dropping empties, failure-only fields, debug-only fields, `include_content` gating) is subtle and regresses silently — a broken serializer just drops a field, raising no error. Add scenario-based golden contract tests under `tests/contracts/`.

- Each scenario invokes `ask` / `fetch_raw` through the in-process test client (`a2kit.testing.client`) — the real production formatter wrapper chain — and compares the marshaled wire dict against a checked-in golden JSON. This catches both a2web serializer regressions and a2kit formatter changes (e.g. when a2kit later ships `exclude_none`, the golden diff surfaces it as a conscious bless, not a silent shift).
- Scenarios: `ask_success_minimal`, `ask_success_rich` (operator hints + next_links populated), `ask_failure`, `ask_include_content`, `ask_debug`, `fetch_raw_basic`.
- Non-determinism: the default `debug=False` goldens already omit `started_at` / `total_ms` / `cache`, so they are stable as-is. The single `ask_debug` golden normalizes timing fields to a fixed placeholder before compare.
- Bless mechanism: `A2WEB_BLESS_CONTRACTS=1` (or `make bless-contracts`) rewrites the goldens. On mismatch the failure message states "API contract changed — re-bless if intended, otherwise this is a regression."
- Complementary to — not a replacement for — the targeted assertions in task group 2: targeted tests check named invariants with clear messages ("required fields never dropped"); goldens catch full-shape drift including fields no one remembered to assert.
- **Out of scope:** snapshotting LDD event payloads or internal dataclasses — the contract guard covers the agent-facing wire only; internal types churn freely.

## Risks / Trade-offs

- **Breaking change for MCP clients** → The proposal marks it BREAKING; CHANGELOG + a version bump communicate it. `ask` consumers reading `content_md` must pass `include_content=True` or switch to `fetch_raw`. `fit_md` consumers have no replacement (the field was always `None` — no real data lost).
- **Two response models diverge over time** → Keep shared sub-types (`Verdict`, `Confidence`, `OperatorHint`, `NextLink`, `Diagnostic`) at module scope; only the envelope differs. A test asserts the shared fields stay name-compatible.
- **Custom `@model_serializer` is subtle** → It must never drop required fields and must round-trip through a2kit's `model_dump(mode="json")`. Covered by an in-process test client assertion on a real `ask` invocation (the wire path, not just `.model_dump()`).
- **`include_content=True` re-bloats the response** → Acceptable: it is an explicit, deliberate caller opt-in, and the default path stays lean.

## Migration Plan

1. Land `AskResponse` + the model serializer + `fit_md` deletion together (one change — they touch the same files).
2. Bump the minor version; CHANGELOG documents the `ask` envelope break and the `include_content` escape hatch.
3. No data migration — `fit_md` carried no data.
4. Rollback: revert the change; `ask` returns to `FetchResponse`. No persisted state depends on the envelope shape.

## Open Questions

- **`confidence` on `ask`** — `_confidence_for` derives confidence from `len(content_md)`. With `content_md` off the default path, should `ask` confidence reflect extraction signal (e.g. `extraction.truncated`, answer length) instead? Deferred, but the current value is semi-meaningless on `ask`.
- **Keep `tokens` at all?** `TokenCounts.full` is a *character* count, not tokens (misnamed). If `content_md` is off by default, `tokens` on `ask` is meaningless. Proposed: drop `tokens` from `AskResponse` entirely, keep a single `content_chars` on `FetchResponse` debug. Confirm during specs.
- **`cache` field** — drop from `ask` default or keep as a one-enum cheap field? Leaning debug-only per Decision 4.
