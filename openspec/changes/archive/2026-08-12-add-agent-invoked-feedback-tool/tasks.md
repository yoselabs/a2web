## 1. Shared transport extraction (design.md D6)

- [x] 1.1 New module `src/a2web/feedback_transport.py`: a small async function taking `settings: AppSettings`, `scope_name: str`, `resource_attrs`, `log_records`, doing the gating check (`feedback_enabled`/`endpoint`/`api_key`), building the `resourceLogs` OTLP envelope, POSTing with `X-Api-Key` + 5s timeout, and swallowing `(httpx.HTTPError, OSError)` to `log_warning` — extracted verbatim from `_record_feedback`'s existing POST block
- [x] 1.2 Refactor `_record_feedback` (`fetcher/pipeline.py`) to build its payload pieces then call the new shared function, passing `scope_name="a2web.feedback"` — behavior unchanged, all 18 existing tests pass with zero edits

## 2. Nudge hint (design.md D1, spec: discovery requirements)

- [x] 2.1 Add `report_feedback_available` to `HINT_CODES` (`hints.py`) and a factory `report_feedback_available_hint()` — `severity="info"`, `fix` names `report_feedback` by name, following the `content_guidance_hint`-style minimal factory pattern
- [x] 2.2 New helper `_with_feedback_nudge` (`fetcher_response.py`) — appends to the first warning/critical hint's `fix` (via `model_copy`), or synthesizes `report_feedback_available_hint()` when `confidence == Confidence.low` and no hint present; idempotent (checks for the nudge marker already present) since `build_ask_response` re-derives from `build_response`'s already-nudged output
- [x] 2.3 Called in `build_response` (`fetch_raw` path), placed after ALL `op_hints` mutations, right before `FetchResponse(...)` is constructed
- [x] 2.4 Called in `build_ask_response` (`query` path), placed after `_index_loss_hint`'s extend (the last hint-mutating step in that function) and right before `AskResponse(...)` is constructed — confirmed this ordering matters: an earlier placement missed `index_lost_hint` (warning-severity, added by `_index_loss_hint`)
- [x] 2.5 Unit tests (`tests/capabilities/agent_invoked_feedback/test_feedback_nudge.py`, 9 tests): hint-fired → fix gains nudge, no new hint; no-fix hint → nudge becomes the whole fix; low-confidence-no-hint → one new info hint; high/medium confidence no-hint → untouched; info-only hint doesn't host the nudge but low confidence still synthesizes the standalone one; idempotent on an already-nudged fix and on an already-present standalone hint
- [x] 2.6 (found running the full suite) Two frozen wire-contract goldens (`call/query_failure.json`, `call/query_heterogeneous_hints.json`) drifted as expected — accepted via `A2WEB_ACCEPT_WIRE_DELTA=add-agent-invoked-feedback-tool-nudge`, recorded in `tests/contracts/DELTAS.md`

## 3. `report_feedback` tool (design.md D2, D3, D5)

- [x] 3.1 New function `record_agent_feedback` (`feedback_transport.py`) building an agent-feedback OTLP payload from `url`/`note`/`wanted`, calling the shared transport from §1 with `scope_name="a2web.feedback.agent"` — no redaction, no `feedback_include_content` gating (D5), gated only by the base triple. `url` sent under the attribute key `requested_url`, NOT `url` — caught during implementation (D5 addendum): `url` is itself one of the gateway's anchored redaction patterns and would arrive masked
- [x] 3.2 Registered `report_feedback(url: str, note: str, wanted: str | None = None)` as an MCP tool in `routers.py` via new `register_feedback_tools(mcp, components)` — reads `components.settings` directly, `@guard_tool`-wrapped, tagged `{"write"}`. Returns `FeedbackReportResult(sent: bool)` — `sent` reflects whether a send was attempted (config present), never actual delivery (invisible by design, same as the mechanical path)
- [x] 3.3 Wired into `server.py` alongside `register_web_tools`/`register_cookies_tools` — unconditional (no local-only gate, unlike cookies)
- [x] 3.4 Unit tests (`tests/capabilities/agent_invoked_feedback/test_report_feedback_tool.py`, 5 tests): flag off → no HTTP call, `sent=False`; flag on → one HTTP call, `scope.name: a2web.feedback.agent`, `requested_url`/`note`/`wanted` present regardless of `feedback_include_content`; regression guard that the key is `requested_url` not `url`; `wanted` omitted when not supplied; delivery failure swallowed, `sent=True` (attempted, not confirmed delivered)
- [x] 3.5 (found running the full suite) Two more real guards needed updates: `test_wire_list_tools`'s anti-vacuity assertion (hardcoded exactly `["fetch_raw", "query"]`) and `cli.py`'s `_TOOL_GROUPS` table (a tool absent from it fails loudly at CLI-build time rather than silently missing from the CLI) — both updated, `report_feedback` placed in a new `feedback` CLI group (`a2web feedback report`). Wire delta accepted via `A2WEB_ACCEPT_WIRE_DELTA=add-agent-invoked-feedback-tool-new-tool`

## 4. Verification

- [x] 4.1 `make lint` / `make ty` / full `uv run pytest tests/` — clean, 1881 passed, 2 deselected
- [x] 4.2 Real-payload capture (no network) for both the nudge-carrying response shape and the `report_feedback` outgoing payload — both confirmed reading as intended
- [x] 4.3 Added `report_feedback` to `README.md`'s tool table
- [x] 4.4 `openspec validate` clean

## 5. Explicitly deferred (design.md Non-Goals)

- [ ] 5.1 Behavioral cross-check against `uptake.py`-style re-fetch correlation for self-judgment reliability — not implemented in this change, tracked as a named future direction only
