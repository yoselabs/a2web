## Why

The `ask` tool ships the full page markdown (`content_md`) on every call even though its entire premise is "small model extracts server-side, keeping your context tiny." On a typical Hacker News front-page fetch that is ~900-1000 tokens of a ~1400-token response — roughly 70% waste — plus a tail of `null` / `[]` / `{}` fields that a2kit's formatter serializes verbatim (it calls `model_dump(mode="json")` with no `exclude_none`). The `ask` response should carry the answer, not the page.

## What Changes

- **BREAKING** — `ask` returns a new lean envelope (`AskResponse`) instead of the shared `FetchResponse`. `content_md`, `headings`, `tokens`, and `is_user_authored` are dropped from the `ask` surface; `content_md` (+ `headings`) returns only behind a new opt-in `include_content` param (default `False`).
- **BREAKING** — `fit_md` and `TokenCounts.fit` are deleted from the model entirely. `fit_md` has been unconditionally `None` since v0.3; the "pruning filter" it reserved space for was superseded by JSON-synth (v0.11) and the LLM extractor. The `fit-md` spec is removed.
- On an `ask` success, `narrative` and `diagnostics_summary` are emitted only when `status != ok` (on success they merely restate `status` + `tier`). `started_at`, `total_ms`, and `cache` move to `debug`-only.
- Genuinely-optional fields (`byline`, `published`, `operator_hints`, `next_links`, `original_url`, `meta`) are omitted from the wire when empty/null rather than serialized as `null` / `[]` / `{}`.
- `extraction` metadata on the wire is slimmed to the agent-relevant signal (`truncated`); cost/latency/model/template fields move to debug + LDD.
- The HN handler emits **both** the article URL and the `news.ycombinator.com/item?id=` discussion URL for external-link stories in `content_md`.
- `fetch_raw` keeps the content-shaped envelope; `headings` on it compress to `[level, text]` tuples.
- An a2kit feedback-doc item records the request for formatter-level `exclude_none` / `exclude_defaults` support (the clean long-term mechanism for empty-omission).

## Capabilities

### New Capabilities
- `ask-response`: the lean `ask`-tool response envelope — required fields, opt-in `content_md`, failure-only fields, empty-field omission, and slimmed `extraction` metadata.

### Modified Capabilities
- `fit-md`: removed — `fit_md` and `TokenCounts.fit` are deleted; the capability no longer exists.
- `site-handlers`: HN front-page rendering emits both article and discussion URLs.

## Impact

- `src/a2web/models.py` — new `AskResponse` model; delete `fit_md`, `is_user_authored`, `TokenCounts.fit`.
- `src/a2web/fetcher_response.py` — new `build_ask_response` builder; failure-only field logic.
- `src/a2web/fetcher.py` / `src/a2web/routers.py` — `ask` returns `AskResponse`; new `include_content` param.
- `src/a2web/handlers/hn.py` — dual-URL front-page rendering.
- BREAKING for MCP clients parsing `ask` results (`content_md`, `fit_md`, `tokens`, `is_user_authored` no longer present by default) and for any consumer reading `FetchResponse.fit_md`.
- `docs/history/A2KIT_FEEDBACK_v0.*.md` — new entry requesting formatter `exclude_none` support.
