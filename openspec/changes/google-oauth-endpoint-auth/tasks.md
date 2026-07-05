## 1. Config — env-only Google OAuth settings

- [x] 1.1 Add to `AppSettings`: `google_client_id: str = ""`, `google_client_secret: str = ""`, `google_base_url: str = ""`, optional `google_required_scopes: list[str] = []`, `google_redirect_path: str = ""` — all env-only (`GOOGLE_*` via the standard-env pattern, like the LLM keys; excluded from YAML sources like the other secrets).
- [x] 1.2 Docstring the `base_url`-must-be-public sharp edge inline in settings.

## 2. Serve entrypoint — gated GoogleProvider injection

- [x] 2.1 Add `build_google_provider(settings) -> GoogleProvider | None` in `server.py`: returns `None` when all `GOOGLE_*` unset; constructs a `fastmcp.server.auth.providers.google.GoogleProvider(client_id=…, client_secret=…, base_url=…, required_scopes=… or None, redirect_path=… or None)` when fully configured; raises a loud `ValueError` naming the missing var(s) when `client_id` is set but secret/base_url is not (never silently open).
- [x] 2.2 Add a runtime builder + gated serve in `main()`: when `build_google_provider` returns a provider AND the resolved transport is HTTP, build the App runtime and call `a2kit.packages.serve.serve_process(runtime, transport="http", host=…, port=…, internal_uds=None, mcp_options={"auth": provider})`; otherwise keep the current `a2kit.run(app)` path unchanged (stdio, CLI, unconfigured HTTP).
- [x] 2.3 Resolve host/port/transport for the `serve_process` branch consistently with a2kit's CLI defaults (host `0.0.0.0` in-container, port `8000`, `--select surface=mcp`) — reuse a2kit's arg resolution rather than re-parsing where possible; keep `base_url` distinct from `host`.

## 3. Tests — gating + provider construction (no live handshake)

- [x] 3.1 `build_google_provider` unit tests: all-unset → `None`; fully configured → a `GoogleProvider` whose `client_id`/`base_url` match the env; `client_id` set + secret missing → `ValueError` naming the gap; + base_url missing → `ValueError`.
- [x] 3.2 Serve-path test: unconfigured `main()` takes the `a2kit.run` path (no `serve_process` call, no provider); configured + HTTP takes the `serve_process` path with `mcp_options["auth"]` a `GoogleProvider` (mock/inspect the seam, don't bind a socket or call Google).
- [x] 3.3 Confirm no `GOOGLE_*` value is written to any repo file or image layer (grep guard / dockerignore review).

## 4. Docs + gate + supersede

- [x] 4.1 README Deployment: an **Auth** subsection — GCP OAuth client setup, the `GOOGLE_*` env matrix, the public-`base_url` sharp edge, and the "unset → open, Tailscale-only" default. Cross-reference from the env matrix.
- [x] 4.2 CHANGELOG entry (new capability; note it retires `deployable-container-ci` group 5).
- [x] 4.3 Mark `deployable-container-ci` tasks 5.1–5.4 superseded-by-this-change (pointer), so that change can archive.
- [x] 4.4 Operator-verification note (NOT automated): with a real GCP client + public `GOOGLE_BASE_URL`, an anonymous MCP request is rejected and a Google login admits the principal. Record the manual steps in the README auth section.
- [x] 4.5 `make check` green; `openspec validate google-oauth-endpoint-auth` passes.
