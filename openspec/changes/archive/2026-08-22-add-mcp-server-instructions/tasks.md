## 1. Implementation

- [x] 1.1 Add a module-level constant near the `FastMCP(...)` call in `src/a2web/server.py` holding the instructions string (see `design.md` - Decisions for the drafted copy).
- [x] 1.2 Pass `instructions=<constant>` into the `FastMCP(name="a2web", ...)` construction at `src/a2web/server.py:94`.

## 2. Verification

- [x] 2.1 Add/extend a test asserting the built `FastMCP` server's `.instructions` is a non-empty string (mirrors the assertion style of existing composition-root tests, e.g. `tests/architecture/test_one_composition_root.py`).
- [x] 2.2 Manually confirm via `mcp_client` (or an equivalent smoke check) that `initialize` returns the new `instructions` value over the real transport, not just the constructor kwarg.
- [x] 2.3 Run `make check`.

## 3. Close-out

- [x] 3.1 Confirm no `tests/contracts/cli/*.json` capture changed (the `initialize` handshake is outside CLI-invocation scope; if it did change, name the delta in `_ACCEPTED` with a reason per `AGENTS.md`).
- [ ] 3.2 Link this change to its bead via `--spec-id` if a bead is filed for it (no bead filed for this change).
