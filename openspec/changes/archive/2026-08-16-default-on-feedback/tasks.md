## 1. Settings defaults

- [x] 1.1 `settings.py`: flip `feedback_enabled` and `feedback_include_content`
      defaults to `True`.
- [x] 1.2 `settings.py`: ship real default values for `feedback_endpoint`/
      `feedback_api_key` (the shared gateway + its public ingest token).
      Update the surrounding comment block — it currently documents an
      off-by-default, no-shipped-default posture that no longer holds.
- [x] 1.3 `tests/architecture/test_no_personal_strings.py`: add an
      explicit, commented carve-out for the gateway hostname — per design
      D5, this is the one deliberate exception to a guard that catches
      accidental leaks.

## 2. Tool description disclosure

- [x] 2.1 `routers.py`: append the disclosure sentence to `query` and
      `fetch_raw`'s descriptions.
- [x] 2.2 `routers.py`: update `register_feedback_tools`'s
      `extra_instructions` string — append the disclosure sentence to the
      existing "subject = the URL you fetched." line.
- [x] 2.3 Confirm `cookies_refresh`'s description is untouched.

## 3. Tests

- [x] 3.1 `tests/capabilities/feedback_telemetry/`: update default-flip
      assertions — default settings now send, explicit `false` now
      required to silence.
- [x] 3.2 `tests/capabilities/agent_invoked_feedback/`: update
      `test_flag_off_sends_nothing_and_returns_false` and friends for the
      new default; add a test asserting the disclosure sentence appears
      in `query`/`fetch_raw`/`report_feedback` descriptions and not in
      `cookies_refresh`'s.

## 4. Wire contract + docs

- [x] 4.1 Accept the wire deltas for the changed tool descriptions
      (`A2WEB_ACCEPT_WIRE_DELTA=default-on-feedback-disclosure`).
- [x] 4.2 `README.md`: add the human-facing feedback-disclosure section
      (secondary to the tool descriptions, not the enforcement mechanism).

## 5. Verification

- [x] 5.1 `make check` passes.
- [x] 5.2 Sync this change's delta specs into
      `openspec/specs/feedback-telemetry/spec.md` and
      `openspec/specs/agent-invoked-feedback/spec.md`.
