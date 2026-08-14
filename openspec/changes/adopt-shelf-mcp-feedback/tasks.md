## 1. Wait for the shelf dependency

- [x] 1.1 Confirm shelf change `add-mcp-feedback-package` has shipped a
      real `mcp-feedback-vX.Y.Z` tag (not a local path) before starting
      the rest of this change — per D2, this blocks everything below.
      (`mcp-feedback-v0.1.0` tagged and pushed at shelf commit `64f2f7e`.)

## 2. Adopt the shelf package

- [x] 2.1 Add `mcp-feedback` to `pyproject.toml` pinned by tag (mirror the
      existing shelf-dependency comment style already used for other
      promoted packages).
- [x] 2.2 Rewrite `register_feedback_tools` in `routers.py` to call the
      shelf package's `register_feedback_tool(mcp, endpoint=...,
      api_key=..., extra_instructions="subject = the URL you fetched.")`
      instead of hand-registering the tool.
- [x] 2.3 Delete `record_agent_feedback` and `FeedbackReportResult` from
      `feedback_transport.py`.

## 3. Keep the mechanical reporter working

- [x] 3.1 Verify `_record_feedback` (`fetcher/pipeline.py`) does not call
      anything deleted in 2.3; if `post_feedback_logs` was shared, give
      `_record_feedback` its own copy of the POST helper per design D1.
      (Verified: `_record_feedback` only ever called `post_feedback_logs`,
      which was kept as-is — `record_agent_feedback`/`FeedbackReportResult`
      were the only deleted symbols, and nothing in `pipeline.py`
      referenced them.)

## 4. Update the nudge text and wire surface

- [x] 4.1 Update `_with_feedback_nudge` (`fetcher_response.py`) — nudge
      text references `report_feedback(url=..., note=...)`; change to
      `subject=`. (Also updated `report_feedback_available_hint()` in
      `hints.py` — the same nudge text is duplicated there for the
      standalone-hint case.)
- [x] 4.2 Accept the resulting wire deltas
      (`A2WEB_ACCEPT_WIRE_DELTA=adopt-shelf-mcp-feedback-subject-rename`)
      for `tests/contracts/wire/call/query_failure.json`,
      `query_heterogeneous_hints.json`, and `list_tools.json` (tool schema
      now shows `subject` not `url`).

## 5. Tests

- [x] 5.1 Rewrite `tests/capabilities/agent_invoked_feedback/` against the
      shelf package's public contract (mount it, call `report_feedback`
      with `subject`, assert on the delivered payload) instead of testing
      a2web-local internals that no longer exist.
- [x] 5.2 Confirm `tests/capabilities/feedback_telemetry/` (the mechanical
      reporter's own tests) pass unchanged.

## 6. Spec sync

- [x] 6.1 `make check` passes.
- [x] 6.2 Sync this change's delta spec into
      `openspec/specs/agent-invoked-feedback/spec.md`.
