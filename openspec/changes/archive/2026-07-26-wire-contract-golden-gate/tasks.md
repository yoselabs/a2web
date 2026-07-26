# Tasks

> **Prerequisite: SATISFIED (2026-07-22).** `hotfix-fastmcp-error-envelope`
> landed — fastmcp is pinned `>=3.4,<4` (resolved 3.4.4) and the error envelope
> now carries the real prose + a populated `structured_content` on tool failure.
> Goldens captured before that fix would have frozen
> `"ToolResult.__init__() got an unexpected keyword argument 'is_error'"` +
> `structured_content: null` as the migration baseline.

## 1. The capture harness

- [x] 1.1 Build a harness that constructs the real server (`build_app()` → the
      production MCP assembly) and drives it with a real `fastmcp.Client`.
      No `call_wire`, no `compute_schema`, no direct `render_plain`.
      → `tests/contracts/wire_harness.py`.

      **Finding that changed the design: `a2kit.testing.client` cannot be used
      here.** It calls `server.enable(tags={"_meta"})` on construction
      (`a2kit/packages/testing/client.py:96`), re-enabling tools production
      hides via `server.disable(tags={"_meta"})`. Any surface captured through
      it is not the surface agents see. The harness builds the server itself:
      `build_mcp_server(app)` with no `code_mode` override consults
      `config.mcp.code_mode` (a2web: False) and applies the `_meta` disable
      internally, so it is production-exact. This is the "if a byte does not
      come out of the real client, it is not a contract byte" rule paying for
      itself on the first day.

- [x] 1.2 Deterministic fixtures: freeze timings so re-capture is stable without
      post-hoc regex scrubbing of raw bytes. `freeze_clocks()` patches
      `time.perf_counter` on the `time` module (every call site resolves the
      attribute at call time, so one patch reaches all ~18 of them) and pins
      `a2web.fetcher.datetime`. Durations collapse to `0ms`.
- [x] 1.3 Scrubbing applies to `structured_content` ONLY; raw `content[].text`
      is stored verbatim. Only `trace_id` (a uuid, unpinnable by a clock
      freeze) is normalized.

## 2. Artifacts

- [x] 2.1 `wire/list_tools.json` — all advertised tools sorted by name, `_meta`
      retained. Asserts exactly 2 tools (`query`, `fetch_raw`), confirming the
      documentation correction: `expose_cookies_tool` defaults false → `refresh`
      is not on the wire.
- [x] 2.2 `wire/call/<scenario>.json` — 8 scenarios, both channels,
      `content[].text` as an opaque string never `json.loads`-ed.
- [x] 2.3 `wire/errors/<scenario>.json` — missing-required-arg (FastMCP-owned)
      and tool-body exception (the repaired typed envelope).
- [x] 2.4 `wire/notifications.json` — the `notifications/message` stream via
      `Client(..., log_handler=...)`. Confirms the live telemetry surface is
      real: `TierStarted` / `StageStarted` / `StageEnded` frames are forwarded
      mid-call today.

## 3. Anti-vacuity

- [x] 3.1 `list_tools` asserts exactly `["fetch_raw", "query"]`, and that every
      tool advertises a non-empty description and non-empty parameters.
- [x] 3.2 Links scenario asserts the TSV separator is present.

      **Corrected during implementation:** the first version asserted a literal
      tab and failed. The text channel is a JSON *document*, so tabs inside TSV
      cells arrive JSON-escaped as the two characters `\t`. Asserting the
      literal character is precisely the mistake that makes this class of test
      quietly wrong — it fails for the wrong reason, or worse, passes for one.
- [x] 3.3 Same-URL scenario asserts `url` is absent from BOTH channels (the
      deviation-drop rule is live).
- [x] 3.4 `test_no_golden_is_degenerate` walks every artifact and fails on an
      empty file, an empty structure, a response with no content blocks, or a
      text channel under 20 chars. Also asserts the artifact count, so a
      silently-deleted golden fails.

## 4. Adversarial TSV fixtures

- [x] 4.1–4.3 `call/query_adversarial_cells` carries a quote-doubling cell, a
      backslash cell, and a cell with an interior newline + tab.

      **Corrected during implementation:** the first version put the hostile
      characters in `NextLink.anchor`. `other_pages` renders as a TSV of
      `url | reason | kind` — the anchor never reaches that envelope, so the
      scenario was a silent duplicate of `query_success_rich`. The characters
      now live in `reason`. This is exactly the failure mode task 3.4 exists to
      catch, and it was caught by an anti-vacuity assertion rather than by
      review.
- [x] 4.4 Asserted in the goldens. Verified the quote case fires csv
      `QUOTE_MINIMAL` doubling for real:
      `"the page calls this one ""the reference"" for the price band"`.

## 5. The two-phase bless protocol

- [x] 5.1 `A2WEB_ACCEPT_WIRE_DELTA=<slug>` writes the new golden AND appends the
      unified diff to `tests/contracts/DELTAS.md` under that slug.
- [x] 5.2 A re-bless with no slug is rejected when goldens exist.
- [x] **Both phases exercised end-to-end**, not merely implemented: tampered a
      golden → confirmed rejection without a slug → confirmed acceptance with
      `A2WEB_ACCEPT_WIRE_DELTA=demo-tamper` → confirmed the diff landed in
      `DELTAS.md` → restored. An unexercised protocol is a claim, not a
      mechanism.

      Required one production-adjacent fix: `tests/conftest.py` scrubs every
      `A2WEB_*` env var for hermeticity, with an allowlist for harness controls.
      `A2WEB_ACCEPT_WIRE_DELTA` had to be declared there or it was silently
      stripped — the protocol would have appeared to "not work" for a reason
      unrelated to its logic.
- [x] 5.3 The two gates are documented in `DELTAS.md`: migration = zero deltas;
      `lean-wire` adoption = every delta slugged `lean-wire-escaping` and
      confined to cells containing `" \ \t \n \r`.

## 6. The one non-golden invariant

- [x] 6.1 `test_populated_other_pages_survives_to_text_channel` — for a scenario
      whose model carries a non-empty `other_pages`, the target URL must appear
      in `content[0].text`.
- [x] 6.2 `xfail(strict=True)` today. **Confirmed failing for the documented
      reason**, and the goldens now capture the defect in full:

      ```
      structured_content.other_pages:  "url\treason\tkind\nhttps://example.org/related\trelated read\tstructural\n"
      content[0].text  other_pages:    "\n"
      ```

      A populated off-page index survives on the structured channel and is
      annihilated on the text channel. `strict=True` turns the fix into a hard
      failure, forcing the marker off the moment the sunset deletes the
      middleware.

## 7. Reconcile with existing contract tests

- [x] 7.1 **RESOLVED 2026-07-22 — by the sunset, then by cleanup.** Delete the `call_wire` + `compute_schema`
      snapshots in `tests/contracts/test_contracts.py`, or retain them as a
      `structured_content`-only view? Recommend delete: they measure a path the
      wire does not take and will not exist after the sunset. Left in place for
      now — deleting is the user's call, and they are harmless meanwhile.
- [x] 7.2 If deleted, confirm Artifact 2 subsumes their coverage (it does — all
      six scenarios are reproduced, plus two).

      Sunset Phase 4 (`9bb4c37`) deleted `test_contracts.py` outright, which
      settled 7.1 — but it left the six snapshot JSONs behind with no reader.
      An orphaned golden is worse than a deleted one: it looks like coverage,
      greps like coverage, and asserts nothing. Removed 2026-07-22.
- [x] 7.3 `tests/capabilities/ask_response/test_error_envelope_wire.py` (from
      the hotfix) is complementary, not duplicated: it owns the substrate
      guard + the real-cause assertion; Artifact 3 owns the frozen bytes.
- [x] 7.4 Substrate-drift check landed as
      `test_framework_matches_the_resolved_mcp_substrate`: AST-walks installed
      a2kit, asserts every `fastmcp`/`mcp` symbol resolves and no call site
      passes a keyword the resolved signature rejects. Carries its own
      anti-vacuity assertion (`checked > 0`). Non-vacuous overall — it flags the
      `is_error` defect when run against fastmcp 3.2.4.

## 8. Ship

- [x] 8.1 All goldens captured on the post-hotfix build: 11 artifacts under
      `tests/contracts/wire/`.
- [x] 8.2 `make check` green — **1205 passed, 3 xfailed, coverage 90.40%**.
      (Was 1190/2 before this change: +15 tests, +1 xfail.)
- [x] 8.3 Recorded in `sunset-a2kit-dependency` that the gate is armed.

## 9. Findings for the sunset (discovered while capturing)

- [x] 9.1 **DECIDED + FIXED 2026-07-22 — and the "harmless" read was wrong.**
      A THIRD a2kit encoder defect surfaced, distinct from the two already
      tracked: `FormatRoutingMiddleware: content re-derivation failed for
      fetch_raw: encode_tsv expected BaseModel or dict rows, got list`. The
      text channel silently falls back. It happens to be harmless here (the
      fallback preserves a2web's own `model_serializer` output, so `links`
      survives intact) — but it is a bare `except` swallowing an encoder error
      on the production path. Both channels are now frozen, so the sunset will
      surface any behaviour change. Worth an explicit decision rather than
      inheriting it.
