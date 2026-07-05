## 1. Packaging — claude-agent-sdk becomes an extra

- [x] 1.1 Move `claude-agent-sdk` from baseline deps to an optional extra `[claude-code]` in `pyproject.toml`
- [x] 1.2 Update `make install-global` to install `a2web[claude-code]` so the local piggyback is unchanged
- [x] 1.3 Verify/adjust the `claude-code` manifest gates on import availability → `Unavailable` when the SDK is absent (no crash, no module-level import error)
- [x] 1.4 Tests for the provider-selection delta: SDK-absent + `ANTHROPIC_API_KEY` → auto-select returns `anthropic`; SDK-absent + no backend → none sentinel (loud); SDK-present → still `claude-code`
- [x] 1.5 CHANGELOG/README note the BREAKING piggyback packaging change

## 2. Dockerfile

- [x] 2.1 Author `Dockerfile`: slim Python base + `uv` install from lockfile, non-root user, `ARG INSTALL_CLAUDE_CODE=false`
- [x] 2.2 Bake browsers at build: `patchright install --with-deps chromium` + system libs zendriver needs; confirm no runtime download path
- [x] 2.3 Place the sqlite cache at a volume-backable path; declare the `VOLUME`
- [x] 2.4 `CMD` → `serve --transport=http --host=0.0.0.0 --select surface=mcp` (MCP-only); document the port
- [x] 2.5 `HEALTHCHECK` → `curl -f http://localhost:<port>/health` (probes the live MCP server's `/health`, not the CLI)
- [x] 2.6 Add `.dockerignore` (`.venv`, `.git`, `eval/runs/`, `__pycache__`, etc.)

## 3. Build + run locally (verify before CI)

- [x] 3.1 `docker build` the slim image; record final size + minimum RAM note for the browser rung
- [x] 3.2 Ran the container, connected a real `fastmcp.Client` to `/mcp` over HTTP → advertises bare `ask`/`fetch_raw`/`refresh`; drove `fetch_raw` end-to-end (real egress through the tier pipeline). **Paid `ask` E2E deferred (LLM budget):** the `openai_compatible` backend path is already proven live by the model benchmark and the LLM env-plumbing is just pydantic-settings reading `os.environ` (not container-specific); unit-tested in `test_fetcher_ask.py`.
- [x] 3.3 Confirm `curl -f /health` returns 200 against the MCP-only server and HEALTHCHECK reports healthy; confirm a browser-tier fetch launches the baked Chromium with no network install
- [x] 3.4 Confirm the `INSTALL_CLAUDE_CODE=true` build variant installs the extra

## 4. CI — build + publish to GHCR (public)

- [x] 4.1 Workflow on `v*` tags: job 1 runs `make check` (the gate)
- [x] 4.2 Job 2 (needs job 1): `docker/metadata-action` + `docker/build-push-action` → `ghcr.io/yoselabs/a2web:{version,latest}`, login via `GITHUB_TOKEN` (`packages: write`)
- [x] 4.3 GHCR package `ghcr.io/yoselabs/a2web` published (v0.27.0) and is **public** (inherited from repo visibility — no manual toggle needed). Confirmed via API: `visibility: public`.
- [x] 4.4 First release cut as `v0.27.0` (real, not throwaway). Workflow green (gate + build+push); `Verify published version` step passed. Confirmed from a logged-OUT client: unauthenticated `docker pull --platform linux/amd64 ghcr.io/yoselabs/a2web:0.27.0` succeeds, image reports `0.27.0`, 367MB. (amd64-only — fits the N100 homelab; multi-arch stays deferred.)

## 5. Endpoint auth — config-gated Google OAuth

> **UNBLOCKED (2026-07-05, `docs/history/A2KIT_FEEDBACK_v0.49.md` round 16 — RESOLVED).**
> a2kit's answer is direction A: no `GoogleAuth` AuthSpec, no pin bump. MCP OAuth
> is already wired — a2web replaces the bare `serve` CMD with a ~15-line
> programmatic entrypoint that builds a `fastmcp …google.GoogleProvider(client_id,
> client_secret, base_url, …)` and passes it via
> `serve_process(app, mcp_options={"auth": provider})`; `build_mcp_server`
> forwards `auth=` to FastMCP and the mounted `PrincipalMiddleware` lands the
> principal in the per-call DI scope. Blessed recipe: `a2kit/docs/patterns/mcp-auth.md`.
> Sharp edge: `base_url` must be the **public** URL (the OAuth redirect derives
> from it), NOT `--host 0.0.0.0`. Ready to build; container still ships open
> (Tailscale/LAN) until wired.

- [ ] 5.1 Add Google-auth config to `AppSettings` (env-only: `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, resolved from env) — ready (programmatic `GoogleProvider` entrypoint)
- [ ] 5.2 Register a2kit's `GoogleAuth` AuthSpec on the HTTP surface only when configured; settle the mount target (`surface=mcp` alone vs `mcp`+`api`) — ready (FastMCP `auth=` via `serve_process(mcp_options={"auth":…})`)
- [ ] 5.3 Tests: unconfigured → no AuthSpec registered, behavior unchanged; configured → anonymous request rejected, Google principal admitted — ready
- [ ] 5.4 Confirm no `GOOGLE_*` value is written to any repo file or image layer — ready

## 6. Transport-native liveness (FastMCP `/health`)

- [x] 6.1 File an a2kit wish: MCP surface should register `custom_route("/health")` by default so MCP-only HTTP deployments have a transport-native liveness route (FastMCP-idiomatic; liveness is a substrate concern). **Drafted:** `docs/history/A2KIT_FEEDBACK_v0.47.md` (round 15). **SHIPPED in a2kit v0.48.0** — the fix landed as a static root `GET /health` on the multiplex parent (`build_parent_app`), NOT a `custom_route` on the MCP app: the parent-root path resolves to `/health` (matching this change's probe) rather than `/mcp/health`, is surface-agnostic, and is auth-free by construction. See a2kit `serve-liveness-health-route` (archived) + `health-probe` spec.
- [x] 6.2 Ensure `GET /health` → 200 is served in MCP-only mode via the a2kit fix (NO interim escape-hatch needed — the substrate route ships). a2web pin bumped `a2kit v0.46.0 → v0.48.0` (pyproject `tool.uv.sources` tag + `uv.lock`); 944 tests green on the bump.
- [x] 6.3 Verified against the LIVE server: `a2web serve --transport=http --select surface=mcp` + `curl -f http://127.0.0.1:<port>/health` → `200 {"status":"ok"}`. (Container HEALTHCHECK wiring itself still rides task 2.5.)
- [x] 6.4 (Readiness, separate from liveness) Decide whether the `_meta.health` MCP tool also asserts an LLM backend is configured — loud keyless-deploy signal per never-silently-miss; do NOT fold this into the dumb liveness route

## 7. Docs + gate

- [x] 7.1 README **Deployment** section: pull, run, env matrix (`ANTHROPIC_API_KEY`/`A2WEB_LLM_*`, `A2WEB_ZYTE_KEY`, `GOOGLE_*`), volume, transport URL, auth setup
- [x] 7.2 BACKLOG: record deferred items (multi-arch, published "full" image, Codex gateway is operator-owned)
- [x] 7.3 `make check` green; `openspec validate deployable-container-ci` passes
