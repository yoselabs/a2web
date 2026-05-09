## Why

a2web is scaffolded but has no runnable surface yet — the workspace ships `pyproject.toml`, `connection.py`, and empty subpackage dirs, but `a2web --help` and `a2web serve` cannot start. Before any tier, handler, or fetch logic lands, we need the a2kit `App` composition + a single stub tool wired end-to-end so every subsequent PR plugs into a real router and a real CLI/MCP entrypoint. PR1 establishes that skeleton and locks the public tool shape (return type, naming) before we begin to implement behavior.

## What Changes

- Add `src/a2web/models.py` with the `FetchResponse`, `Diagnostic`, `Verdict` types — all pydantic / enum, all at module scope (a2kit antipattern #2).
- Add `src/a2web/routers.py` with `WebRouter` exposing a single stub `fetch(url, ...)` tool via `@a2kit.read()` returning a placeholder `FetchResponse` (no I/O, no real fetch).
- Add `src/a2web/server.py` composing `a2kit.App`: `.add_router(WebRouter())`, with `main() = a2kit.run(app)`. **No `connections_cli`** — a2web has no per-instance connection concept; configuration lives in a single optional YAML file (see settings below).
- Replace `src/a2web/connection.py` with `src/a2web/settings.py` — a pydantic-settings `AppSettings` model loaded from `~/.a2web/config.yaml` (override via `$A2WEB_CONFIG`) and `A2WEB_*` env vars. Holds proxy pool, route rules, default UA, stealth toggle, diagnostics default, cache TTLs, live-only hosts, and `jina_key` (env-only). **No Firecrawl/Bright Data keys in v0.1** — paid tiers deferred.
- Wire `[project.scripts] a2web = "a2web.server:main"` end-to-end so `a2web --help`, `a2web web fetch --url=...`, and `a2web serve --transport=stdio` all work against the stub.
- Decide CLI router naming: route the fetch tool under `web` (so `a2web web fetch --url=...` reads naturally), not `fetch`.
- Lock the full `FetchResponse` envelope shape in `models.py` (per `v0.1-response-format.md`): `Verdict`, `FetchStatus`, `Confidence`, `CacheState` enums; `Diagnostic`, `Heading`, `Link`, `OperatorHint`, `TokenCounts`, `FetchResponse` pydantic models — all module-scope.
- Add `pyyaml>=6,<7` to dependencies (settings file loader).
- Add a minimal pytest covering: tool returns `FetchResponse`, status is the placeholder, `WebRouter` registers a single tool named `fetch`, settings load with no config file present, settings load from a temp YAML file.
- Add `[tool.uv.sources] a2kit = { git = "https://github.com/yoselabs/a2kit.git", tag = "v0.22.0" }` to `pyproject.toml` while a2kit is pre-PyPI.

## Capabilities

### New Capabilities

- `app-composition`: a2kit `App` wiring — router registration, CLI subcommands, MCP server entrypoint, and the public `fetch` tool signature + return envelope shape.

### Modified Capabilities

<!-- none — this is the first capability -->

## Impact

- **Code**: new files `src/a2web/models.py`, `src/a2web/routers.py`, `src/a2web/server.py`, `src/a2web/settings.py`; **delete** `src/a2web/connection.py`; new test module `tests/test_app_composition.py`.
- **Public surface**: locks the `fetch` tool name, its router (`web`), the full `FetchResponse` envelope, and the config file path/schema. Future PRs add fields to `FetchResponse` but cannot rename existing ones without a breaking change for MCP clients.
- **Dependencies**: a2kit consumed via git tag (`yoselabs/a2kit@v0.22.0`) until it lands on PyPI; one new top-level dep — `pyyaml`.
- **CLI**: `a2web --help`, `a2web web fetch`, `a2web serve` runnable. **`a2web connections *` removed** — no per-instance connection concept; configuration is a single optional YAML file.
- **Config**: `~/.a2web/config.yaml` (optional). Override path via `$A2WEB_CONFIG`. Individual fields override via `A2WEB_*` env vars (e.g., `A2WEB_JINA_KEY`, `A2WEB_STEALTH=true`).
- **No behavior change**: stub returns a placeholder body; real fetching arrives in PR3+.
