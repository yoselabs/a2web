## Context

See `proposal.md` for motivation. This is the a2web-side half of a
two-repo change; the shelf-side package itself is designed in
`openspec/changes/add-mcp-feedback-package/design.md` (shelf repo) — that
document owns the schema/transport/correlation decisions (D1-D6). This
document only covers what a2web-specific integration requires.

Grounding facts:
- Today's implementation: `report_feedback` MCP tool in `routers.py`
  (`register_feedback_tools`), backed by `feedback_transport.py`
  (`record_agent_feedback`, `FeedbackReportResult`, and the shared
  `post_feedback_logs` — also used by `_record_feedback` in
  `fetcher/pipeline.py`, the OTHER, mechanical reporter).
- `post_feedback_logs` is used by BOTH the agent-invoked tool and the
  mechanical pipeline reporter today. Only the agent-invoked half is being
  replaced by the shelf package; `_record_feedback` must keep a working
  POST path after `record_agent_feedback`/`FeedbackReportResult` are
  deleted.
- `fetcher_response.py`'s `_with_feedback_nudge` synthesizes a hint that
  tells the agent to call `report_feedback(url=..., note=...)` — this text
  references the parameter name directly and must be updated to `subject=`
  to stay accurate, or the wire contract will describe a call shape that
  no longer works.
- `AGENTS.md`: no local `path=` shelf source pin permitted
  (`tests/architecture/test_no_local_shelf_source.py`) — this change can
  only land once the shelf package has a real tag, not mid-development.

## Goals / Non-Goals

**Goals:**
- Delete a2web's local reimplementation of the agent-invoked feedback
  tool's schema/transport once the shelf package covers it.
- Keep `_record_feedback` (mechanical) working unchanged, since it is
  explicitly out of scope for the shelf package.
- Update every reference to the `url` parameter name (nudge text, wire
  goldens, main spec) to `subject`.

**Non-Goals:**
- Not redesigning the mechanical pipeline reporter's payload — untouched.
- Not deciding the shelf package's own schema/transport/correlation — that
  belongs to `add-mcp-feedback-package` (shelf repo), referenced not
  re-decided.
- Not attempting a non-breaking migration for the `url`→`subject` rename.
  Confirmed **BREAKING** in the proposal — a2web is pre-1.0 and the tool
  is a few days old with no known external callers depending on the exact
  field name; a compatibility shim (`url` as a deprecated alias) would add
  permanent surface for a transition that has no real users to protect.

## Decisions

### D1 — `post_feedback_logs` stays a2web-local for the mechanical reporter

**Alternative considered:** have `_record_feedback` also route through the
shelf package's transport, so a2web has exactly one OTLP POST
implementation. Rejected: the shelf package's transport is scoped
specifically to `report_feedback`'s fixed schema
(`subject`/`note`/`wanted`) — the mechanical reporter's payload
(`hint_code`/`chain`/`tier_used`/etc.) doesn't fit that shape and isn't
meant to (per the shelf design's own Non-Goals). `_record_feedback` keeps
its own POST mechanics in `feedback_transport.py` (or is inlined directly
into `pipeline.py` if the remaining shared surface is small enough post-
deletion — implementation-time call). Two small, independent POST paths
are preferable to bending the shelf package's fixed schema to also carry
mechanical-reporter fields.

### D2 — Dependency pin: real tag, not a path source

Per `AGENTS.md` (`tests/architecture/test_no_local_shelf_source.py`),
`pyproject.toml` must pin `mcp-feedback` by git tag, never a local
`path=`. This change is written now but its `pyproject.toml` edit and
`uv.lock` update are blocked until the shelf change ships a real
`mcp-feedback-v0.1.0` (or later) tag — sequencing note captured in tasks.

### D3 — `extra_instructions` content

a2web passes exactly: `"subject = the URL you fetched."` — mirroring the
original a2web-only tool's own field description, so the effective agent-
facing guidance is unchanged even though the parameter name is. No other
a2web-specific copy is added; the shelf package's fixed base docstring
already covers "no category, just say what's wrong."

### D4 — Reconciling a2web's three-way gate with the shelf package's two-value gate

**Gap found during implementation, not addressed by the original design:**
a2web's settings carry `feedback_enabled: bool` as an explicit master switch
*in addition to* `feedback_endpoint`/`feedback_api_key` — an operator can
have endpoint/key configured without having opted in
(`settings.py`: "Default OFF... unless the operator explicitly enables this
AND supplies both an endpoint and a key"). The shelf package only knows
`endpoint`/`api_key` — it has no `enabled` parameter, deliberately (exactly
two knobs, per its own D4). Passing `feedback_endpoint`/`feedback_api_key`
straight through regardless of `feedback_enabled` would have silently
dropped the boolean gate — the mechanical reporter's own
`A2WEB_FEEDBACK_ENABLED=false` default would no longer stop
`report_feedback` from sending.

**Decision:** `register_feedback_tools` blanks both `endpoint` and
`api_key` to `""` when `feedback_enabled` is false, before ever calling
into the shelf package. The shelf package's own "both non-empty" gate then
naturally also enforces a2web's boolean — no third parameter needed on the
shelf side, and no behavior change from before this adoption (same net
gating: enabled AND endpoint AND key, same as the deleted
`record_agent_feedback`'s reliance on `post_feedback_logs`).

## Risks / Trade-offs

- **[Risk] Breaking change with no deprecation path.** Accepted per
  Non-Goals — no known external callers, and the tool is new enough that
  the cost of a compatibility shim outweighs the (currently zero) benefit.
- **[Risk] Sequencing dependency on an external repo's release.** This
  change cannot be applied until `add-mcp-feedback-package` (shelf) ships
  a tag. Proposal/design/specs can be written and reviewed now; `tasks.md`
  names the blocking step explicitly rather than letting it surface as a
  surprise mid-implementation.
