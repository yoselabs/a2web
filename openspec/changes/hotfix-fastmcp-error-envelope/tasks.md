# Tasks

## 1. Confirm the defect and the fix path

- [x] 1.1 Reproduce: force a tool-body exception through a real `fastmcp.Client`
      against `build_app()`; capture `is_error`, `content[0].text`,
      `structured_content`. Record the output in the change for provenance.

      **Captured 2026-07-22 on fastmcp 3.2.4** (`ToolResult.__init__` params:
      `['self', 'content', 'structured_content', 'meta']`), tool body raising
      `RuntimeError("the real error message that must survive")`:

      ```
      is_error:            True
      content[0].text:     ToolResult.__init__() got an unexpected keyword argument 'is_error'
      structured_content:  None
      ```

      Server-side log showed what *should* have reached the caller:
      `ToolError: Internal error (UnexpectedDefect): the real error message that
      must survive`. Both channels destroyed, exactly as the proposal predicted.

- [x] 1.2 Check whether a2kit has a released tag containing commit `8df0337`.

      **No.** `8df0337` (2026-07-08) is on a2kit `main` but the newest tag
      `v0.49.2` is dated 2026-07-05 — `git tag --contains 8df0337` is empty.
      Took option (b): a direct `fastmcp>=3.4,<4` floor in a2web, documented in
      `pyproject.toml` as a TEMPORARY CO-PIN with the removal condition. This is
      also forward-compatible with `sunset-a2kit-dependency`, which makes fastmcp
      a direct dependency permanently.

## 2. Land the fix

- [x] 2.1 Update `pyproject.toml`; `uv lock`.
      Resolved: `fastmcp 3.2.4 -> 3.4.4` (+ `fastmcp-slim 3.4.4`,
      `starlette 1.0.0 -> 1.3.1`).
- [x] 2.2 Assert the resolved FastMCP is >= 3.4 and that
      `inspect.signature(ToolResult.__init__)` contains `is_error`.
      Asserted permanently by
      `test_resolved_fastmcp_supports_the_error_flag`, not just checked once.
- [x] 2.3 Re-run 1.1; confirm the real error message and a non-null
      `structured_content` are recovered.

      ```
      is_error:            True
      content[0].text:     Internal error (UnexpectedDefect): the real error message that must survive
      structured_content:  {'error': {'type': 'UnexpectedDefect', 'kind': 'bug',
                            'retryable': False, ..., 'cause': {'type': 'RuntimeError',
                            'message': 'the real error message that must survive',
                            'trace_id': '...'}, 'envelope_version': '1'}}
      ```

## 3. Close the test gap

- [x] 3.1 Add a test driving a tool-body exception through `fastmcp.Client` and
      asserting: `is_error is True`, the real exception prose appears in
      `content[0].text`, and `structured_content` is not null.
      → `tests/capabilities/ask_response/test_error_envelope_wire.py`.
      **Verified non-vacuous**: downgraded to fastmcp 3.2.4 and confirmed BOTH
      tests fail with the intended diagnostics, then restored 3.4.4. A
      regression test never seen to fail is a decoration.
- [x] 3.2 ~~Assert the recovered envelope carries the ADR-0009 fields for a
      walled fetch.~~ **Premise corrected.** a2web raises no typed `AppError`
      anywhere (`grep a2effect|AppError src/a2web/` → empty): a walled or empty
      *retrieval* returns SUCCESSFULLY carrying `status: failed` +
      `retrieval_incomplete: true` + diagnostics + narrative + a critical
      operator hint. It never touches the error envelope. The two mechanisms are
      distinct and the first draft of the spec conflated them; the spec delta
      now says so explicitly and asserts the accurate property instead (an
      unanticipated fault names its real cause). ADR-0009's retrieval fields
      remain covered by the existing `retrieval_completeness` suite.

## 4. Sweep for siblings

- [x] 4.1 Diff a2kit's FastMCP call sites against the FastMCP 3.4 public
      signatures.

      Two AST passes over the installed a2kit: (a) all 19 distinct
      `fastmcp`/`mcp` symbols a2kit imports resolve against 3.4.4; (b) no call
      site passes a keyword the resolved signature rejects. **No siblings.**
      The pass is non-vacuous — `_wrappers.py:61` calls
      `ToolResult(..., is_error=True)` through a module-level import, so against
      3.2.4's `[self, content, structured_content, meta]` it flags exactly the
      defect this change fixes.

      Worth promoting into `wire-contract-golden-gate` as a standing check: it
      catches substrate drift by construction, which is how this defect should
      have been caught rather than by inspection.

## 5. Ship

- [x] 5.1 `make check` green. **1190 passed, 2 deselected, 2 xfailed, coverage
      90.40%** (floor 85%). The 2 xfails are the `envelope-wire-hygiene`
      tripwires — still correctly failing; that defect is untouched by this fix.
- [ ] 5.2 `make install-global` so the live MCP server picks up the fix.
- [x] 5.3 Note in `wire-contract-golden-gate` that goldens must be captured
      AFTER this lands.
