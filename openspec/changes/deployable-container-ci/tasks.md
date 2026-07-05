## 1. Packaging — claude-agent-sdk becomes an extra

- [x] 1.1 Move `claude-agent-sdk` from baseline deps to an optional extra `[claude-code]` in `pyproject.toml`
- [x] 1.2 Update `make install-global` to install `a2web[claude-code]` so the local piggyback is unchanged
- [x] 1.3 Verify/adjust the `claude-code` manifest gates on import availability → `Unavailable` when the SDK is absent (no crash, no module-level import error)
- [x] 1.4 Tests for the provider-selection delta: SDK-absent + `ANTHROPIC_API_KEY` → auto-select returns `anthropic`; SDK-absent + no backend → none sentinel (loud); SDK-present → still `claude-code`
- [x] 1.5 CHANGELOG/README note the BREAKING piggyback packaging change

## 2. Dockerfile

- [ ] 2.1 Author `Dockerfile`: slim Python base + `uv` install from lockfile, non-root user, `ARG INSTALL_CLAUDE_CODE=false`
- [ ] 2.2 Bake browsers at build: `patchright install --with-deps chromium` + system libs zendriver needs; confirm no runtime download path
- [ ] 2.3 Place the sqlite cache at a volume-backable path; declare the `VOLUME`
- [ ] 2.4 `CMD` → `serve --transport=http --host=0.0.0.0 --select surface=mcp` (MCP-only); document the port
- [ ] 2.5 `HEALTHCHECK` → `curl -f http://localhost:<port>/health` (probes the live MCP server's `/health`, not the CLI)
- [ ] 2.6 Add `.dockerignore` (`.venv`, `.git`, `eval/runs/`, `__pycache__`, etc.)

## 3. Build + run locally (verify before CI)

- [ ] 3.1 `docker build` the slim image; record final size + minimum RAM note for the browser rung
- [ ] 3.2 Run the container, connect an MCP client to `/mcp` over HTTP, and run an `ask` against a keyed backend (env-supplied `ANTHROPIC_API_KEY` or `A2WEB_LLM_*`)
- [ ] 3.3 Confirm `curl -f /health` returns 200 against the MCP-only server and HEALTHCHECK reports healthy; confirm a browser-tier fetch launches the baked Chromium with no network install
- [ ] 3.4 Confirm the `INSTALL_CLAUDE_CODE=true` build variant installs the extra

## 4. CI — build + publish to GHCR (public)

- [ ] 4.1 Workflow on `v*` tags: job 1 runs `make check` (the gate)
- [ ] 4.2 Job 2 (needs job 1): `docker/metadata-action` + `docker/build-push-action` → `ghcr.io/yoselabs/a2web:{version,latest}`, login via `GITHUB_TOKEN` (`packages: write`)
- [ ] 4.3 Set the GHCR package Public (one-time repo/org setting); document it
- [ ] 4.4 Cut a throwaway pre-release tag to confirm publish + unauthenticated `docker pull` succeeds; confirm image `--version` matches the tag

## 5. Endpoint auth — config-gated Google OAuth

- [ ] 5.1 Add Google-auth config to `AppSettings` (env-only: `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, resolved from env)
- [ ] 5.2 Register a2kit's `GoogleAuth` AuthSpec on the HTTP surface only when configured; settle the mount target (`surface=mcp` alone vs `mcp`+`api`)
- [ ] 5.3 Tests: unconfigured → no AuthSpec registered, behavior unchanged; configured → anonymous request rejected, Google principal admitted
- [ ] 5.4 Confirm no `GOOGLE_*` value is written to any repo file or image layer

## 6. Transport-native liveness (FastMCP `/health`)

- [x] 6.1 File an a2kit wish: MCP surface should register `custom_route("/health")` by default so MCP-only HTTP deployments have a transport-native liveness route (FastMCP-idiomatic; liveness is a substrate concern). **Drafted:** `docs/history/A2KIT_FEEDBACK_v0.47.md` (round 15). **SHIPPED in a2kit v0.48.0** — the fix landed as a static root `GET /health` on the multiplex parent (`build_parent_app`), NOT a `custom_route` on the MCP app: the parent-root path resolves to `/health` (matching this change's probe) rather than `/mcp/health`, is surface-agnostic, and is auth-free by construction. See a2kit `serve-liveness-health-route` (archived) + `health-probe` spec.
- [x] 6.2 Ensure `GET /health` → 200 is served in MCP-only mode via the a2kit fix (NO interim escape-hatch needed — the substrate route ships). a2web pin bumped `a2kit v0.46.0 → v0.48.0` (pyproject `tool.uv.sources` tag + `uv.lock`); 944 tests green on the bump.
- [x] 6.3 Verified against the LIVE server: `a2web serve --transport=http --select surface=mcp` + `curl -f http://127.0.0.1:<port>/health` → `200 {"status":"ok"}`. (Container HEALTHCHECK wiring itself still rides task 2.5.)
- [ ] 6.4 (Readiness, separate from liveness) Decide whether the `_meta.health` MCP tool also asserts an LLM backend is configured — loud keyless-deploy signal per never-silently-miss; do NOT fold this into the dumb liveness route

## 7. Docs + gate

- [ ] 7.1 README **Deployment** section: pull, run, env matrix (`ANTHROPIC_API_KEY`/`A2WEB_LLM_*`, `A2WEB_ZYTE_KEY`, `GOOGLE_*`), volume, transport URL, auth setup
- [ ] 7.2 BACKLOG: record deferred items (multi-arch, published "full" image, Codex gateway is operator-owned)
- [ ] 7.3 `make check` green; `openspec validate deployable-container-ci` passes
