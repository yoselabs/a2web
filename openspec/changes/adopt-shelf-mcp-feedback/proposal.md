## Why

a2web's `report_feedback` tool (archived change
`add-agent-invoked-feedback-tool`) was built a2web-only, scoped around a
`url` parameter tied to its own fetch domain. A generic, FastMCP-mountable
version of the same mechanism is being built on the shelf
(`mcp-feedback` package, shelf change `add-mcp-feedback-package`) so any
MCP project can reuse it verbatim. a2web should be the first real consumer
of that shelf package rather than keep maintaining a parallel, fetch-only
copy of a mechanism the shelf now owns generically — this is the adopt
side of "reach for the shelf first" (`AGENTS.md`), and DEEP · STABLE ·
WINS applies directly: the shelf package's schema and transport are
already validated against a2web's own prior drift data.

## What Changes

- **BREAKING**: `report_feedback`'s `url: str` parameter is replaced by
  `subject: str` (same slot, renamed — callers pass the URL they fetched,
  same as before, but the field itself is no longer fetch-specific by
  name). `note`/`wanted` are unchanged.
- `src/a2web/feedback_transport.py`'s `record_agent_feedback`/
  `FeedbackReportResult`/`post_feedback_logs` (the agent-invoked half) are
  deleted; `register_feedback_tools` in `routers.py` now calls the shelf
  package's `register_feedback_tool(mcp, endpoint=..., api_key=...,
  extra_instructions=...)` instead of hand-registering the tool.
- a2web supplies `extra_instructions` naming its own convention: "subject
  = the URL you fetched."
- `A2WEB_FEEDBACK_ENDPOINT`/`A2WEB_FEEDBACK_API_KEY` settings are passed
  through unchanged as the shelf package's `endpoint`/`api_key` — no
  settings/env var renaming.
- `_record_feedback` in `fetcher/pipeline.py` (the mechanical,
  pipeline-triggered reporter) is explicitly **unaffected** — it stays
  a2web-local, per the shelf proposal's own scope boundary, and keeps
  using its own POST mechanics (not this package, which covers only the
  agent-invoked case).
- Wire contract goldens (`tests/contracts/wire/*.json`) and the
  `report_feedback` tool's advertised schema update to reflect
  `subject` instead of `url`.

## Capabilities

### Modified Capabilities
- `agent-invoked-feedback`: the `report_feedback` tool's correlation field
  is renamed `url` → `subject`, and its implementation is delegated to the
  shelf `mcp-feedback` package instead of a2web-local code.

## Impact

- `pyproject.toml`: new pinned dependency `mcp-feedback = { git =
  "https://github.com/yoselabs/shelf", subdirectory =
  "packages/mcp-feedback", tag = "mcp-feedback-v0.1.0" }` (tag TBD until
  the shelf package ships).
- `src/a2web/feedback_transport.py`: `record_agent_feedback`,
  `FeedbackReportResult`, and the agent-feedback-specific parts of
  `post_feedback_logs` are deleted. `_record_feedback`'s own transport use
  in `fetcher/pipeline.py` is unaffected (it doesn't call any of the
  deleted functions — verify during implementation).
- `src/a2web/routers.py`: `register_feedback_tools` rewritten to a thin
  call into the shelf package.
- `tests/capabilities/agent_invoked_feedback/`: rewritten against the
  shelf package's public contract instead of a2web-local internals.
- `tests/contracts/wire/*.json`, `tests/contracts/DELTAS.md`: new wire
  delta for the `url`→`subject` rename (`A2WEB_ACCEPT_WIRE_DELTA`).
- `openspec/specs/agent-invoked-feedback/spec.md`: requirements updated for
  the field rename.
- Depends on the shelf change `add-mcp-feedback-package` reaching a
  usable, tagged state before this change can be applied — this proposal
  can be written and reviewed now, but implementation blocks on that tag.
