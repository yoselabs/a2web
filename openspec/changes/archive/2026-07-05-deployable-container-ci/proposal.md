## Why

a2web ships only as a `uv tool` stdio binary today — Claude Code spawns it as a subprocess over a pipe. That model cannot be "deployed on the homelab and reached from another server": a pipe has no address, and there is no container, no image, no CI to publish one. To run a2web as a long-lived networked service (its `serve --transport=http` mode already exists), it needs a container image, a pipeline that builds and publishes it publicly, an authenticated endpoint (an open MCP port on a homelab-exposed box is the thing you'd regret), and an LLM path that works with no local Claude session.

## What Changes

- **Dockerfile** producing a slim, reproducible image: `python:3.11-slim` + `uv` install from the lockfile, **browser binaries baked at build time** (`patchright` Chromium + system deps; zendriver's system Chromium), **non-root** runtime user, sqlite cache on a **mounted volume**, `CMD` running `serve --transport=http --host=0.0.0.0`, and a Docker `HEALTHCHECK` shelling `a2web health` (exits non-zero on degraded). All `A2WEB_*` / `A2KIT_*` / secret env vars pass through untouched (pydantic-settings already reads them).
- **`claude-agent-sdk` demoted to an optional extra `[claude-code]`** (**BREAKING** for `pip install a2web` users who relied on the bundled Claude piggyback — they must now name the extra). `make install-global` keeps the extra so the local piggyback is unchanged. The image builds **without** it via an `INSTALL_CLAUDE_CODE=false` build arg (default), dropping ~210 MB of dead weight (no OAuth session exists in a container). One published image; the arg lets anyone build a "full" variant locally without a second CI artifact.
- **Container LLM path** = the `openai_compatible` provider (from the prerequisite change) or a metered `ANTHROPIC_API_KEY`. Verify auto-select degrades cleanly to `anthropic` when `claude-agent-sdk` is absent, so the slim image never silently loses `ask`.
- **CI pipeline** (GitHub Actions): on `v*` tags, run `make check` as the gate, then `buildx` → push to **`ghcr.io/yoselabs/a2web:{version,latest}`**, published **public** so any instance can `docker pull`. amd64 (bee/shen are x86-64); arm64 optional.
- **Config-gated Google OAuth** on the HTTP listener via a2kit's bundled `GoogleAuth` AuthSpec, fed by `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` from env. When configured, the served `/mcp` (+`/api`) endpoint requires Google login; when unconfigured (e.g. local stdio), nothing changes.
- **`.dockerignore`**, a README **Deployment** section, and BACKLOG updates.

## Capabilities

### New Capabilities
- `container-image`: the a2web Docker image contract — base, baked browsers, non-root, HTTP-transport entrypoint, `a2web health` HEALTHCHECK, sqlite volume, env passthrough, and the `INSTALL_CLAUDE_CODE` build arg.
- `image-publishing`: the CI pipeline that gates on `make check` and publishes a public multi-tag image to `ghcr.io/yoselabs/a2web` on release tags.
- `endpoint-auth`: config-gated Google OAuth protecting the HTTP-served endpoint, off by default, driven by `GOOGLE_*` env.

### Modified Capabilities
- `provider-selection`: `claude-code` becomes optional at the packaging layer — when `claude-agent-sdk` is not installed, its manifest SHALL report `Unavailable` and auto-select SHALL fall through to `anthropic` (or `openai_compatible` by pin), never crashing or silently disabling `ask`.

## Impact

- **Depends on** `openai-compatible-llm-provider` (the container's non-Claude LLM path).
- **Deps/packaging:** `claude-agent-sdk` moves from baseline to `[claude-code]` extra (BREAKING for bare-`pip` piggyback users); `make install-global` and CI account for it.
- **New files:** `Dockerfile`, `.dockerignore`, `.github/workflows/<publish>.yml`, an auth-registration seam (register `GoogleAuth` when `GOOGLE_*` configured).
- **Code:** `settings.py` (Google auth config toggle); `server.py`/app-composition (conditional AuthSpec registration); `pyproject.toml`; `Makefile`; README.
- **Ops:** operators supply secrets at runtime only (`ANTHROPIC_API_KEY` or `A2WEB_LLM_*`, `A2WEB_ZYTE_KEY`, `GOOGLE_*`) — never baked into a layer; sqlite cache needs a mounted volume to survive restarts; browser rung needs documented minimum RAM.
- **Non-goals:** no Codex/subscription gateway (operator's separate track); no second published "full" image.
