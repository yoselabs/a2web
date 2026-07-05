# a2kit feedback — round 15 (2026-07-04)

> **Status: SHIPPED in a2kit v0.48.0 (2026-07-05), completed through v0.49.1.**
> a2web pinned to `a2kit v0.49.1`. Resolved differently (and better) than asked:
> instead of a `custom_route("/health")` on the MCP app (which lands at
> `/mcp/health`), a2kit added a **static root `GET /health`** on the multiplex
> parent (`build_parent_app`) — surface-agnostic, auth-free by construction, and
> at the stable path `/health` regardless of which surfaces mount. See a2kit
> `serve-liveness-health-route` (archived) + `health-probe` spec.
>
> Follow-on: verifying this against MCP-only surfaced a *separate* a2kit bug —
> `--select surface=mcp` did NOT actually drop `/api` (three compounding
> selector bugs: `_meta.health` escaping the selector, the source surface matrix
> not being narrowed, and the CLI building the runtime before parsing
> `--select`). Fixed across **v0.49.0 + v0.49.1**. **Verified live on v0.49.1:**
> `serve --transport=http --select surface=mcp` → `/mcp` + `/health` only;
> `/api/*` returns 404. Both this liveness ask and the `deployable-container-ci`
> D5 attack-surface rationale now hold. Original ask preserved below.

## Serve a transport-native `/health` liveness route on the MCP surface

**Ask.** Register a FastMCP `custom_route("/health", methods=["GET"])` (returning
HTTP 200, e.g. `{"status": "ok"}`) on the MCP surface's FastMCP server inside
`build_mcp_server(...)` (or `McpSurface.bind`, `packages/mcp/surface.py`), so any
HTTP MCP deployment — **including MCP-only** — exposes a cheap, dumb liveness
endpoint co-resident with `/mcp`. Keep it liveness-only; readiness/degraded
aggregation stays on the existing `_meta.health` MCP tool.

**The gap today.** The only HTTP `/health` route is registered on the **`/api`
FastAPI sub-app** (`packages/http/build.py:105`, `@app.get("/health")`), which
`packages/serve.py`'s parent app mounts under `/api` — and only when the `api`
surface has registrations. So:

```
serve --transport=http                     → /mcp  + /api/health   (probe /api/health ✓)
serve --transport=http --select surface=mcp → /mcp  ONLY            (NO liveness route ✗)
```

An MCP-only server has no route a load balancer / Docker `HEALTHCHECK` / k8s
liveness probe can hit. The `/mcp` JSON-RPC endpoint is not a substitute: a bare
`GET /mcp` needs the streamable-HTTP handshake (`Accept: text/event-stream` /
session) and returns 4xx/406, so `curl -f` fails against a perfectly healthy
server. Liveness wants a dedicated 200.

**Why this belongs in a2kit (not a2web).** Liveness is a **transport concern**,
not a web-fetching-domain concern and not a REST-surface concern — per a2web's
Constitution (substrate vs product placement), it sits in the substrate. MCP-only
is a legitimate, common deployment shape (a2web's homelab container serves MCP
alone to shrink the attack surface); coupling the sole liveness route to the
`/api` surface being enabled is the wrong dependency. FastMCP's own idiom for
this is exactly `@mcp.custom_route("/health", ...)` — confirmed available in the
pinned FastMCP (`fastmcp 3.2.4`, `fastmcp/server/mixins/transport.py:100`).

**Notes for the a2kit side.**
- Register the route on the FastMCP instance in `build_mcp_server`; return a
  static 200. No DI, no resource resolution — dumb liveness by design (a wedged
  DI graph should still answer liveness; readiness is the `_meta.health` tool's
  job).
- **Auth exemption (important):** the liveness route MUST sit outside whatever
  OAuth/token gate the MCP surface applies — a probe should not need
  credentials. Ensure the `custom_route` is registered such that it is not
  captured by the surface's auth middleware (the analog of how `/api/health`
  should be reachable without an API key). Please confirm the interaction with
  the auth path (`AppAuthRegistry` / `_install_auth_middlewares`) when an MCP
  `auth=` provider is configured.
- **Path/mount question for the a2kit side:** when the parent app
  (`packages/serve.py` `build_parent_app`) mounts the MCP surface at `/mcp`, a
  `custom_route("/health")` lands at `/mcp/health`. That is fine to probe, but
  consider whether the parent should ALSO surface a **root `/health`** (forwarding
  to the active surface's liveness) so operators get a stable probe path
  regardless of surface layout. At minimum: guarantee *some* liveness route
  exists whenever any surface is served over HTTP, MCP-only included.
- Additive / back-compatible: the existing `/api/health` on the FastAPI sub-app
  can stay for REST deployments; this only adds the MCP-side equivalent. No
  behavior change for servers that already mount `/api`.

**a2web's adoption (the bridge).** Once shipped, a2web's container `HEALTHCHECK`
becomes `curl -f http://localhost:<port>/health` (or `/mcp/health`, per the
final path decision) against the MCP-only `serve` process — probing the *live
server*, not a fresh `a2web health` CLI subprocess (which builds a new process
and checks sqlite, proving nothing about the running server). a2web then drops
its interim workaround (attaching the route locally via a2kit's `fastmcp_server`
escape hatch, `packages/mcp/surface.py:76`) — that interim is domain code owning
a transport concern, which is exactly what this ask moves into the substrate.

**Tracked in a2web by** the `deployable-container-ci` OpenSpec change
(`openspec/changes/deployable-container-ci/`, design decision D4 + tasks 6.1–6.3).
Until this lands, a2web uses the `fastmcp_server` escape-hatch interim, marked
retire-on-a2kit-fix.
