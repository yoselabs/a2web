# Spike: capturing camoufox / playwright subprocess stderr

**Date:** 2026-05-19
**Outcome:** No clean knob exists. Documenting limitation; will not ship in harsh-test-session-fixes. Filed upstream as future work.

## Problem

The harsh-test session against TechCrunch surfaced this from camoufox running under a2web's browser tier:

```
/Users/iorlas/.local/share/uv/tools/a2web/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:49624
              url: pageError.location.url,
                                      ^
TypeError: Cannot read properties of undefined (reading 'url')
    at FFBrowserContext.<anonymous> (.../coreBundle.js:49624:39)
    ...
Node.js v24.15.0
```

The Python side caught it as `verdict=Verdict.connection_error` (good), but the JS stack trace went straight to the user's terminal. We want it captured into LDD as a `browser_subprocess_stderr` event with no user-terminal leak.

## What I checked

1. **`camoufox.async_api.AsyncCamoufox`** — thin wrapper around `AsyncNewBrowser`. Just forwards `**launch_options` to playwright.
2. **`camoufox.async_api.AsyncNewBrowser`** — eventually calls `await playwright.firefox.launch(**from_options)`. No stderr knob.
3. **`playwright.firefox.launch()`** signature — supports `args`, `env`, `headless`, `handle_sigint`, `handle_sigterm`, `handle_sighup`, `timeout`, `traces_dir`, but no stream-redirect parameters. Stderr from the Node driver inherits the Python parent's fd 2.
4. **`playwright._impl._transport.PipeTransport`** — this is the asyncio Process subprocess managing the Node driver. It uses `asyncio.create_subprocess_exec(..., stderr=None)` (inherits) by default. Patching this means monkey-patching playwright internals — fragile across versions.
5. **`os.dup2(<pipe>, 2)`** at the Python level — would capture EVERYTHING the process writes to stderr (not just camoufox's child), AND would break uvicorn / structlog / pytest's own stderr usage. Not viable as a generic solution.

## Conclusion

No supported public API exposes the Node subprocess's stderr stream. The only ways forward are:

- **Monkey-patch `playwright._impl._transport`** to inject `stderr=subprocess.PIPE` and add a reader task. Fragile against playwright version bumps; a2kit-shaped solutions discourage this kind of patching.
- **Fork camoufox** to add a `stderr_callback=` knob to `AsyncCamoufox(...)`. Real fix but outside this change's scope.
- **File an upstream issue** on `camoufox` requesting `stderr_callback=`. Done as part of this spike (link TBD).

## Decision

Skip implementation in `harsh-test-session-fixes`. Document the limitation in `docs/history/A2KIT_FEEDBACK_v0.39.md` (or current cycle feedback) and the camoufox project. The stderr leak is cosmetic (user sees JS noise but the tier handles the error correctly); the cost of an unsafe fix outweighs the benefit.

## Mitigations available today

- Operators can redirect a2web's stderr at the shell level: `a2web web ask ... 2>/tmp/a2web.stderr.log`.
- The MCP server runs over stdio — playwright's stderr goes to fd 2 of the MCP host, which most clients (Claude Code, mcp-cli) already collect into their own log files.
