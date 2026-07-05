## Context

a2web serves via `main()` → `a2kit.run(app)`, which builds the App runtime and
dispatches to MCP (stdio or HTTP) or the CLI. The HTTP MCP endpoint is currently
open. a2kit deliberately ships **no** OAuth `AuthSpec` (round-16 direction A) —
its `App.auth(spec)` registry is for API-key/JWT specs, not OAuth. Instead, the
FastMCP `auth=` seam is reachable programmatically:

```
serve_process(runtime, *, transport, host, port, internal_uds, mcp_options)
    └─ build_mcp_server(runtime, own_app_lifecycle=False, **(mcp_options or {}))
        └─ FastMCP(..., **fastmcp_kwargs)   # auth= lands here
```

and `fastmcp.server.auth.providers.google.GoogleProvider(*, client_id,
client_secret, base_url, …)` is the provider. All three verified against the
installed a2kit v0.49.1 + fastmcp. The one non-obvious constraint: FastMCP
derives the OAuth **redirect URI** from `base_url`, so it must be the **public**
URL the browser will be sent back to — never `http://0.0.0.0:8000`.

## Goals / Non-Goals

**Goals:**
- Protect the HTTP MCP endpoint with Google OAuth **when configured**, via the
  verified `serve_process(mcp_options={"auth": provider})` seam — no a2kit change.
- **Zero behavior change when unconfigured**: stdio, CLI, and unconfigured HTTP
  keep the exact current `a2kit.run(app)` path (auth-free, ship-open).
- Env-only secrets; no `GOOGLE_*` value ever written to the repo or an image layer.
- Fail loud on partial config (id without secret/base_url) — never silently open.
- Unit-test the gating + provider construction without a live handshake.

**Non-Goals:**
- The live OAuth handshake / token exchange (operator-verified; needs a real GCP
  client + public URL).
- API-key or JWT auth (a2kit's `App.auth` path; separate concern).
- Auth on the REST `/api` surface (the container serves `--select surface=mcp`).
- Persisted OAuth client storage / multi-tenant token stores (default in-memory;
  `client_storage` left as a future knob).

## Decisions

### D1: Programmatic `serve_process`, not `a2kit.run`, for the configured HTTP path
`a2kit.run(app)` gives no seam to inject `auth=`. When OAuth is configured and
transport is HTTP, a2web builds the runtime itself and calls `serve_process(...,
mcp_options={"auth": GoogleProvider(...)})`. Everything else stays on
`a2kit.run(app)`. **Alternative rejected:** waiting for an a2kit `GoogleAuth`
AuthSpec — round-16 confirmed it will not ship (direction A).

### D2: Config gate = all-three-present, checked at boot
Auth engages only when `GOOGLE_CLIENT_ID` **and** `GOOGLE_CLIENT_SECRET` **and**
`GOOGLE_BASE_URL` are all set. `client_id` set with either other missing is a
**loud boot failure** (a misconfiguration that must not degrade to an open
endpoint) — consistent with the fail-loud guardrails elsewhere in a2web. All
three absent → unconfigured → unchanged open path.

### D3: `base_url` is operator-supplied and public
FastMCP derives the redirect from `base_url`; it must match the GCP client's
authorized redirect URI and be publicly reachable. a2web does not infer it from
`--host` (which is `0.0.0.0` in the container). Documented as the primary
sharp edge. `GOOGLE_REDIRECT_PATH` (default FastMCP's) and
`GOOGLE_REQUIRED_SCOPES` are optional passthroughs.

### D4: Only gate the HTTP transport
OAuth is meaningless on stdio (no browser, no redirect) and the CLI. The gate is
`configured AND transport == "http"`; stdio/CLI always take `a2kit.run`.

### D5: Testable seam without a live handshake
Factor the decision into a pure helper `build_google_provider(settings) ->
GoogleProvider | None` (None when unconfigured; raises on partial config) and a
thin `main()` that branches on it. Tests assert: unconfigured → None (and the
`a2kit.run` path is taken); fully configured → a `GoogleProvider` with the right
`client_id`/`base_url`; partial config → a loud `ValueError`/settings error. The
provider object is inspected, not exercised against Google.

## Risks / Trade-offs

- **`base_url` misconfiguration** → the OAuth redirect breaks at runtime. Mitigated
  by loud docs + naming it the sharp edge; can't be caught in unit tests.
- **In-memory client storage** → tokens/consent don't survive a restart. Acceptable
  for a single-instance homelab; `client_storage` reserved as a future knob.
- **Divergent serve paths** (`a2kit.run` vs `serve_process`) → two code paths to
  keep working. Mitigated by keeping the `serve_process` branch minimal and
  gated, and by the unconfigured path being the untouched default.
- **fastmcp API drift** — `GoogleProvider` / `serve_process` signatures could
  change in a future a2kit/fastmcp bump. Mitigated by the construction being
  centralized in one helper and pinned deps; a bump that breaks it fails the
  gate loudly.
- **Live handshake unverifiable here** → the automated tests prove wiring, not
  the end-to-end OAuth flow. Operator verification step documented.
