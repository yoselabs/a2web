## Why

Both of a2web's feedback mechanisms (`feedback-telemetry`'s mechanical
reporter, `agent-invoked-feedback`'s `report_feedback` tool) ship off by
default, requiring every operator to independently discover, configure,
and enable reporting before a2web's maintainers see any real-world failure
data. In practice this means near-zero signal. The shared gateway now
supports a public, low-privilege, write-only credential meant for exactly
this — a shared feedback-ingest key any a2web install can use without
per-operator signup — so the barrier is no longer "you need your own
gateway," it's purely "this defaults to off." This change flips that
default and makes the resulting behavior discoverable the way an MCP
client actually discovers things: through `tools/list`, not a README a
connecting agent never reads.

## What Changes

- `feedback_enabled` defaults to `True` (was `False`).
- `feedback_include_content` defaults to `True` (was `False`) — one
  consistent unredacted story; `report_feedback`'s own fields were never
  gated by this flag regardless, so leaving the mechanical reporter
  redacted while the agent-invoked tool isn't would be an inconsistent
  half-measure.
- `feedback_endpoint`/`feedback_api_key` ship real shipped defaults (the
  shared gateway + its public ingest token), overridable via
  `A2WEB_FEEDBACK_ENDPOINT`/`A2WEB_FEEDBACK_API_KEY` exactly as today.
- **BREAKING**: every a2web install now sends failure telemetry and
  agent-invoked feedback to that shared gateway from first run, unless
  the operator explicitly opts out.
- Disclosure is MCP-native: a one-line sentence appended to `query`,
  `fetch_raw`, and `report_feedback`'s tool descriptions (not
  `cookies_refresh`, which never triggers the mechanical reporter),
  naming the opt-out env var. No skill, no MCP resource — `tools/list` is
  the one call every MCP client makes, unlike `resources/list`, which is
  optional in the spec and inconsistently implemented.
- README gets a human-facing section too, secondary to the tool
  descriptions, not the enforcement mechanism.
- `tests/architecture/test_no_personal_strings.py` gets an explicit,
  commented carve-out for the shared gateway's hostname — the one
  deliberate, documented exception to a guard whose job is catching
  *accidental* leaks.

## Capabilities

### Modified Capabilities
- `feedback-telemetry`: "Feedback reporting is opt-in and off by default"
  and "Report content excludes raw URL, query, and page content by
  default" both flip their defaults to on.
- `agent-invoked-feedback`: tool descriptions gain a disclosure sentence;
  `report_feedback`'s "off unless configured" framing updates to match the
  new default.

## Impact

- `src/a2web/settings.py`: `feedback_enabled`, `feedback_include_content`,
  `feedback_endpoint`, `feedback_api_key` default values change.
- `src/a2web/routers.py`: `query`/`fetch_raw`/`report_feedback` tool
  description text gains the disclosure sentence.
- `README.md`: new feedback-disclosure section.
- `tests/architecture/test_no_personal_strings.py`: carve-out for the
  gateway hostname.
- `tests/contracts/wire/*.json`: wire deltas for the changed tool
  descriptions.
- `tests/capabilities/feedback_telemetry/`, `tests/capabilities/
  agent_invoked_feedback/`: default-flip test updates.
- `openspec/specs/feedback-telemetry/spec.md`,
  `openspec/specs/agent-invoked-feedback/spec.md`: requirements updated.
