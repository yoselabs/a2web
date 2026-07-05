## Context

a2web runs as a stdio `uv tool` binary spawned by Claude Code — no address, no image, no CI. `a2web serve --transport=http --host=0.0.0.0 --port=8000` already multiplexes MCP under `/mcp` and REST under `/api`; the entrypoint work is packaging, not new server code. Three heavy things ride in the image: baked browser binaries (~170 MB), the `claude-agent-sdk` bundle (~210 MB, useless without a Claude OAuth session), and the base runtime. Auth: a2kit bundles `GoogleAuth` (an `AuthSpec`; FastMCP accepts one OAuth provider on the HTTP listener), but a2web registers none today — an HTTP-served endpoint is currently open to anyone who can reach the port. Liveness already exists as `a2web health` (non-zero on degraded). This change depends on `openai-compatible-llm-provider` for the container's non-Claude LLM path.

## Goals / Non-Goals

**Goals:**
- One published, public, slim image on `ghcr.io/yoselabs/a2web` that any homelab instance can pull and run as a networked MCP service.
- An authenticated endpoint (Google OAuth, config-gated) so an exposed port is not an open door.
- An LLM path that works with no local Claude session.
- Reproducible build gated by `make check`; secrets runtime-only.

**Non-Goals:**
- No Codex/ChatGPT-subscription gateway (operator's separate track).
- No second published "full" image (the build arg covers local full builds).
- No new server/transport code — `serve --transport=http` already exists.
- No OpenAI-compatible provider work here (its own prerequisite change).

## Decisions

### D1: One slim published image + `INSTALL_CLAUDE_CODE` build arg
Two published images is recurring cost (two matrices, two tests, tag ambiguity) for a niche path. Publish one slim image (no `claude-agent-sdk`); a single `ARG INSTALL_CLAUDE_CODE=false` lets anyone bake the extra locally (`--build-arg INSTALL_CLAUDE_CODE=true`). If a published "full" tag is ever justified, it's a one-line matrix addition later. **Alternative rejected:** always-baseline SDK — carries 210 MB of dead weight into every deployed container.

### D2: `claude-agent-sdk` → `[claude-code]` extra (reverses the v0.7 baseline call)
v0.7 made it baseline because "most callers run inside Claude Code" — true locally, false in a container. Demote to an extra; keep it in `make install-global` so the local piggyback is unchanged. This is **BREAKING** for bare `pip install a2web` piggyback users (they must name the extra), hence the spec contract that auto-select degrades to `anthropic` when the SDK is absent. **Alternative rejected:** keep baseline, exclude at build via pip uninstall — fragile and non-reproducible.

### D3: Baked browsers, non-root, mounted sqlite volume
Browsers install at build (`patchright install --with-deps chromium` + system libs) so no runtime download hits a read-only container. Run as a non-root user. The sqlite HTTP cache lives on a path an operator can back with a volume — otherwise the cache dies each restart (correctness-neutral but a real cost/latency regression). **Alternative rejected:** runtime browser install — breaks on read-only rootfs and adds cold-start latency + network dependence.

### D4: Liveness = a transport-native `/health` on the MCP server (FastMCP `custom_route`), NOT the CLI
A Docker HEALTHCHECK must reflect whether the *running* `serve` process is up. `a2web health` (the CLI) spawns a fresh process and checks sqlite — it proves nothing about the live server (a wedged server still passes). The FastMCP-idiomatic answer is `@mcp.custom_route("/health", methods=["GET"])` returning 200 — a Starlette route on the MCP app, co-resident with `/mcp`, independent of tools and the `/api` surface, so it works in MCP-only mode. The HEALTHCHECK `curl -f`s it.

**Placement (Constitution: substrate vs product):** liveness is a transport concern → it belongs in a2kit, not web-fetching domain code. a2kit today registers `/health` only on the `/api` FastAPI sub-app (so MCP-only drops it) — a substrate placement gap. **Preferred fix: a2kit registers the `custom_route('/health')` on its MCP surface by default** (filed as an a2kit wish). a2kit already exposes the FastMCP instance via the `fastmcp_server` escape hatch, so if the container must ship before that a2kit round lands, a2web can attach the route through the escape hatch as an interim — explicitly a temporary smell, retired once a2kit ships it.

**Alternatives rejected:** (a) `a2web health` CLI as HEALTHCHECK — checks the wrong thing; (b) poke `/mcp` and accept any HTTP status — works but abuses the JSON-RPC endpoint as a liveness signal; a dedicated `/health` is cleaner and is the documented FastMCP pattern.

### D5: Serve MCP-only for now
Per the operator decision, serve the MCP surface alone (`--select surface=mcp`) — no `/api` REST sub-app. Shrinks the attack surface and matches the actual client (an MCP client, not REST). Consequence: the `/api/health` route is gone, which is exactly why D4's liveness must ride the MCP app as a `custom_route`, not the `/api` sub-app. Re-enabling `/api` later is a serve-flag change, no rebuild.

> **✅ RESOLVED in a2kit v0.49.1 (2026-07-05) — D5 now holds.** A prior finding
> (against a2kit v0.48.0) showed `--select surface=mcp` did NOT drop `/api` when a
> health check was registered — the full REST surface (`/api/ask`, `/api/fetch_raw`,
> `/api/refresh`, `/api/_meta.health`, `/api/health`) stayed live, so the
> attack-surface reduction was illusory. Three compounding a2kit bugs, all fixed:
> (1) the synthetic `_meta.health` tool escaped the selector (re-bound after it ran)
> — **v0.49.0** applies the selector to `_meta.*` too; (2) `--select` narrowed the
> derived `expose` but not the source surface matrix that the FastAPI builder reads
> — **v0.49.0** narrows the matrix (single source of truth); (3) the CLI serve path
> built the runtime before parsing `--select`, and `build(runtime, select=...)`
> silently dropped it — **v0.49.1** adds `apply_selection(runtime, select)` (and
> makes the silent-drop path raise). **Verified live on a2kit v0.49.1:** `a2web
> serve --transport=http --select surface=mcp` serves `/mcp` + `/health` only;
> `/api/openapi.json`, `/api/health`, `/api/ask` all return 404. a2web pinned to
> `a2kit v0.49.1`. D5's "shrinks the attack surface" rationale now stands (still
> pair with D3 auth / network policy as defense-in-depth).

### D6: Google OAuth registered only when configured
Register `GoogleAuth` on the HTTP surface iff `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are set; otherwise register nothing (local stdio stays frictionless). This keeps the default path unchanged while making the exposed-endpoint case safe. Secrets are env-only (standing a2web rule). Which target the AuthSpec mounts on (`mcp` vs both `mcp`+`api`) is settled during implementation against a2kit's auth-target API. **Alternative rejected:** always-on auth — breaks local/stdio and tests.

### D7: CI = gate then publish, amd64
One workflow on `v*` tags: job 1 `make check`; job 2 (needs job 1) `docker/build-push-action` → `ghcr.io/yoselabs/a2web:{version,latest}` via `docker/metadata-action`, logging in with the workflow `GITHUB_TOKEN` (`packages: write`). Package set public once in repo settings. amd64 only (bee = N100, shen = Contabo, both x86-64); arm64 is a later matrix line if needed.

## Risks / Trade-offs

- **BREAKING: bare-pip piggyback users lose the SDK** → documented in CHANGELOG/README; `make install-global` keeps the extra; provider-selection degrades to `anthropic` rather than crashing.
- **Open endpoint if deployed before auth wired** → D6 makes auth part of this change (proposal marks it required); document "do not expose the port without `GOOGLE_*` set."
- **Liveness route depends on an a2kit change** → D4's preferred fix lands in a2kit; the `fastmcp_server` escape-hatch interim unblocks a2web if the a2kit round lags. Either way `/health` ships with the container; only the *layer* it lives in differs.
- **Image size from baked browsers** → accepted; slimming the SDK (D1/D2) offsets ~210 MB; document the resulting size + minimum RAM for the browser rung.
- **`GoogleAuth` a2kit API drift** → pin a2kit version already tracked in pyproject; validate the auth-target wiring against the installed a2kit during implementation.
- **Cold sqlite cache on restart without a volume** → documented as an ops requirement, not a code guarantee.

## Migration Plan

1. Land `openai-compatible-llm-provider` first (dependency).
2. Repackage `claude-agent-sdk` → extra; verify slim-install degrade path (provider-selection delta) green.
3. Add Dockerfile + `.dockerignore`; build locally; run the image and hit `/mcp` + HEALTHCHECK.
4. Add the CI workflow; cut a test pre-release tag to confirm GHCR publish + public pull.
5. Wire config-gated `GoogleAuth`; verify unconfigured = unchanged, configured = rejects anonymous.
6. README Deployment section + BACKLOG updates.

Rollback: the image/CI/Dockerfile are additive (delete to revert); the only code-facing change is the `[claude-code]` extra move, reverted by restoring it to baseline deps.

## Open Questions

- Liveness `/health` stays dumb ("process is up", 200). Separately: should *readiness* (the `_meta.health` MCP tool) also assert an LLM backend is configured, so a keyless deploy is loud rather than silently degrading `ask`? (Leaning yes — aligns with never-silently-miss; readiness only, never the liveness route.)
- `GoogleAuth` mount target: resolved to `/mcp` only (D5 — MCP-only serve). Revisit only if the REST surface is ever exposed.
- Multi-arch now or later? (Default: amd64 only for v1.)
- Base image: `python:3.11-slim` vs a `uv`-provided base — pick the smaller reproducible option during implementation.
