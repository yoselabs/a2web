## Why

**Every typed error a2web raises is destroyed before it reaches the caller, on
every host.** Verified live, 2026-07-21.

`pyproject.toml:24` pins `a2kit[code-mode]>=0.46,<1` at tag `v0.49.2`, whose
`TypedErrorEnvelopeMiddleware` (`a2kit/packages/mcp/_wrappers.py:61-65`)
constructs `ToolResult(..., is_error=True)`. The installed FastMCP is **3.2.4**,
whose `ToolResult.__init__` accepts only `['self', 'content', 'structured_content',
'meta']` — confirmed by direct signature inspection. The keyword is rejected, the
`TypeError` is caught by FastMCP's own masking, and the caller receives:

```
is_error:           True
content[0].text:    "ToolResult.__init__() got an unexpected keyword argument 'is_error'"
structured_content: null
```

The real message, the `ErrorEnvelope`, the diagnostics, the narrative, and the
`try_user_browser` operator hint are all gone.

**This is the ADR-0009 harm class, structurally.** The product invariant says a
walled or failed fetch MUST carry `status: failed` + `retrieval_incomplete: true`
+ populated `diagnostics` + `narrative` + a critical operator hint, so the caller
can never mistake a miss for a complete answer. Today the caller receives a
Python `TypeError` string instead — which is not merely uninformative, it is
indistinguishable from an a2web bug, so the caller cannot even tell that a
retrieval was attempted and walled.

**Distinct from `envelope-wire-hygiene`.** That change tracks the
`encode_envelope` defect, whose blast radius is limited to hosts that read
`content[].text` and ignore `structuredContent` — latent on a2web's primary
deployment. This defect sets `structured_content: null`, so it bites **both
channels on every host**, including Claude Code. It is tracked nowhere else.

**The fix is upstream and already shipped.** a2kit HEAD commit `8df0337`
(`fix(mcp): require fastmcp>=3.4 for the error-envelope is_error API`) raises the
FastMCP floor to the version whose `ToolResult` accepts `is_error`. a2web's pin
predates it.

## What Changes

- **Raise the FastMCP floor.** Depend on a2kit at a tag that includes `8df0337`
  (or add an explicit `fastmcp>=3.4` floor to a2web's own dependencies if a2kit
  has not yet cut a tag carrying it), `uv lock`, and confirm the resolved FastMCP
  is >= 3.4.
- **Add a regression test that would have caught this.** A test that forces a
  tool-body exception through a real `fastmcp.Client` and asserts the recovered
  error carries the real message and a non-null `structured_content`. This path
  is currently untested from a2web — the same class of gap `envelope-wire-hygiene`
  §2 identified for the dispatch encoder, and the reason a total error-envelope
  failure shipped unnoticed.
- **`make install-global`** so the live MCP server picks up the fix.

## Impact

- `pyproject.toml` (dependency pin), `uv.lock`.
- One new test under `tests/capabilities/` covering the tool-failure path
  end-to-end through `fastmcp.Client`.
- **Not breaking.** This restores the intended envelope; no caller can be
  depending on the `TypeError` string.
- **Sequencing:** land this FIRST, before `wire-contract-golden-gate`. The golden
  snapshots must capture the *repaired* error envelope, not today's garbage —
  otherwise the migration gate freezes a defect as the baseline.

## Open questions

- Does a2kit have a released tag containing `8df0337`? If not, decide between
  (a) waiting for the tag, or (b) adding a direct `fastmcp>=3.4` floor in a2web
  and accepting a temporary co-pin. Option (b) unblocks immediately and is
  harmless — a2kit's own floor moves the same direction.
- Verify no other a2kit↔FastMCP API drift is latent at the 3.2.4/3.4 boundary.
  This defect was found by inspection, not by a test; there may be siblings.
  A quick sweep of a2kit's FastMCP call sites against the 3.4 signatures is
  cheap insurance.
