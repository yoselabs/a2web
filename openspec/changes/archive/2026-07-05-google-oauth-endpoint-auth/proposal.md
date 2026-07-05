## Why

The `deployable-container-ci` arc shipped a public a2web MCP image, but its HTTP
endpoint has **no authentication** — anyone who can reach the port can call the
tools. The documented mitigation is "run it behind Tailscale / a private LAN,"
which is a real constraint on homelab exposure. Group 5 of that change scoped
Google OAuth but was parked while an a2kit `GoogleAuth` AuthSpec was expected.

The a2kit round-16 feedback (`docs/history/A2KIT_FEEDBACK_v0.49.md`) resolved
that: **no AuthSpec and no a2kit change are needed.** MCP OAuth is already wired
in the installed stack. Verified against a2kit v0.49.1 + the bundled fastmcp:

- `fastmcp.server.auth.providers.google.GoogleProvider(*, client_id, client_secret, base_url, …)` exists.
- `a2kit.packages.serve.serve_process(runtime, *, transport, host, port, internal_uds, mcp_options)` forwards `mcp_options` to `build_mcp_server(**mcp_options)`.
- `build_mcp_server(app, *, …, **fastmcp_kwargs)` forwards `auth=` straight to FastMCP.

So a2web can protect the endpoint today with a small programmatic serve
entrypoint — this is the concrete, verified path, and it retires group 5.

## What Changes

- **Config**: add env-only Google OAuth settings to `AppSettings`
  (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_BASE_URL`, optional
  `GOOGLE_REQUIRED_SCOPES` / `GOOGLE_REDIRECT_PATH`). All secret/env-only, never
  persisted to YAML or an image layer.
- **Serve entrypoint**: `main()` gains a config gate. When Google OAuth is
  configured **and** the transport is HTTP, a2web builds the App runtime, builds
  a `GoogleProvider`, and serves via `serve_process(runtime, …, mcp_options={"auth": provider})`.
  Otherwise it keeps the current `a2kit.run(app)` path unchanged (stdio, CLI, and
  unconfigured HTTP all behave exactly as before — auth-free, ship-open).
- **Never-silent misconfig** (consistent with the fail-loud guardrails): if
  `GOOGLE_CLIENT_ID` is set but `GOOGLE_CLIENT_SECRET` or `GOOGLE_BASE_URL` is
  missing, fail loud at boot with an actionable message rather than silently
  serving open.
- **Docs**: README Deployment auth section (GCP client setup, the public
  `base_url` sharp edge, the `GOOGLE_*` env matrix) + CHANGELOG.
- **Retire group 5** of `deployable-container-ci` (superseded by this change).

Out of scope: the full live OAuth handshake (needs a real GCP client + a public
URL) is operator-verified, not automated. No a2kit change. No API-key/JWT auth.

## Capabilities

### New Capabilities
- `endpoint-auth`: config-gated OAuth on the a2web HTTP MCP endpoint — Google
  provider construction, the serve-time injection seam, the unconfigured
  auth-free default, and the loud partial-config failure.

### Modified Capabilities
<!-- none: no existing a2web spec's requirements change; the serve path gains a
     gated branch but the current behavior is preserved unchanged. -->

## Impact

- **Code**: `src/a2web/settings.py` (new env fields), `src/a2web/server.py`
  (gated serve entrypoint; new `build_runtime` + provider construction helpers).
- **Deps**: none new — `fastmcp` (via a2kit) already ships `GoogleProvider`;
  `a2kit.packages.serve.serve_process` is already present.
- **Docs**: `README.md` (Deployment auth + env matrix), `CHANGELOG.md`.
- **OpenSpec**: supersedes `deployable-container-ci` group 5 (tasks 5.1–5.4).
- **Deployment**: unconfigured deployments are byte-for-byte unchanged (open,
  Tailscale-only). Configured deployments reject anonymous MCP requests and
  admit a Google principal. `GOOGLE_*` values stay env-only — never in the repo
  or an image layer.
- **Security**: closes the open-endpoint gap for operators who expose the port
  beyond a private network.
