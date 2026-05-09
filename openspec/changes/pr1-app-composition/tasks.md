## 1. Tooling

- [x] 1.1 Add `[tool.uv.sources] a2kit = { git = "https://github.com/yoselabs/a2kit.git", tag = "v0.22.0" }` to `pyproject.toml`
- [x] 1.2 Run `make bootstrap` and confirm `uv sync --all-extras` resolves
- [x] 1.3 Add `pyyaml>=6,<7` to `[project] dependencies` in `pyproject.toml`
- [x] 1.4 Re-run `make bootstrap` after adding pyyaml

## 2. Reference reading

- [x] 2.1 Read `~/Workspaces/a2kit/examples/tracker/server.py` for `App` composition shape
- [x] 2.2 Read `~/Workspaces/a2kit/examples/tracker/routers.py` for `@a2kit.read()` tool registration shape
- [x] 2.3 Read `~/Workspaces/a2kit/ANTIPATTERNS.md` (mandatory)
- [x] 2.4 Skim `~/Workspaces/a2db/src/a2db/server.py` and `routers.py` for the a2 idiom (note where they use `connections_cli` — we deliberately don't)

## 3. Models — `src/a2web/models.py`

- [x] 3.1 Define `Verdict(StrEnum)` with the 12 closed members from the spec
- [x] 3.2 Define `FetchStatus(StrEnum)`: `ok`, `failed`, `partial`
- [x] 3.3 Define `Confidence(StrEnum)`: `high`, `medium`, `low`
- [x] 3.4 Define `CacheState(StrEnum)`: `hit`, `miss`, `bypass`
- [x] 3.5 Define `Diagnostic(BaseModel)`: `t_ms: int`, `step: str`, `engine: str | None`, `host: str | None`, `proxy: str | None`, `verdict: Verdict`, `subsystem: str | None`, `dur_ms: int`, `extra: dict[str, str | int | float] = {}`
- [x] 3.6 Define `Heading(BaseModel)`: `level: int` (1–6), `text: str`
- [x] 3.7 Define `Link(BaseModel)`: `anchor: str`, `href: str`
- [x] 3.8 Define `OperatorHint(BaseModel)`: `code: str`, `message: str`
- [x] 3.9 Define `TokenCounts(BaseModel)`: `full: int`, `fit: int`
- [x] 3.10 Define `FetchResponse(BaseModel)` with the full field set from `v0.1-response-format.md` §2 (see design.md decision 8)
- [x] 3.11 Confirm all types are at module scope (no nested classes); add a unit test that imports each from `a2web.models`

## 4. Settings — `src/a2web/settings.py` (replaces `src/a2web/connection.py`)

- [x] 4.1 Delete `src/a2web/connection.py`
- [x] 4.2 Define `ProxyEntry(BaseModel)` and `RouteRule(BaseModel)` (carry over from old connection.py)
- [x] 4.3 Define `AppSettings(BaseSettings)` with all fields from the spec (default_ua, stealth, proxies, routes, cache_ttl_*, log_retention_days, diagnostics_default, live_only_hosts, jina_key)
- [x] 4.4 Wire pydantic-settings sources: env (`A2WEB_*`) > YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml` > defaults
- [x] 4.5 `jina_key` MUST resolve only from `A2WEB_JINA_KEY` (exclude from YAML source); ensure a YAML-set `jina_key` is ignored
- [x] 4.6 Provide a `get_settings() -> AppSettings` factory (cached) for downstream use; PR1 doesn't call it but PR2 will

## 5. Router — `src/a2web/routers.py`

- [x] 5.1 Create `WebRouter` (subclass per a2kit tracker example)
- [x] 5.2 Add `@a2kit.read()` decorated `async def fetch(self, url: str) -> FetchResponse:` returning a placeholder `FetchResponse` with `tier="stub"`, `status=ok`, `confidence=low`, populated `started_at` and `total_ms=0`
- [x] 5.3 Confirm the router exposes exactly one tool named `fetch`

## 6. Server — `src/a2web/server.py`

- [x] 6.1 Build the `a2kit.App` with metadata from package
- [x] 6.2 Chain `.add_router(WebRouter())` only — NO `add_cli(connections_cli(...))`
- [x] 6.3 Define `def main() -> None:` invoking `a2kit.run(app)`
- [x] 6.4 Confirm `a2web = "a2web.server:main"` script entrypoint resolves

## 7. Verification

- [x] 7.1 `uv run a2web --help` exits 0 and shows `web` and `serve` subcommands; does NOT show `connections`
- [x] 7.2 `uv run a2web web fetch --url=https://example.com` exits 0 and prints a TOON-formatted `FetchResponse` with `tier="stub"`
- [x] 7.3 `uv run a2web serve --transport=stdio` starts (sanity: send `initialize` and confirm a `fetch` tool is listed)
- [x] 7.4 With `HOME` pointed at an empty temp dir (no `~/.a2web/config.yaml`), the fetch command still exits 0

## 8. Tests — `tests/test_app_composition.py` and `tests/test_settings.py`

- [x] 8.1 Test: `WebRouter` registers exactly one tool named `fetch`
- [x] 8.2 Test: invoking `fetch(url=...)` returns a `FetchResponse` with `status == FetchStatus.ok` and `tier == "stub"`
- [x] 8.3 Test: every model in `a2web.models` is importable (smoke for module-scope rule)
- [x] 8.4 Test: constructing a `Diagnostic` with an invalid verdict raises a pydantic `ValidationError`
- [x] 8.5 Test: `a2web.server.main` exists and is callable
- [x] 8.6 Test: `AppSettings()` constructs with no config file present (defaults applied)
- [x] 8.7 Test: `AppSettings()` reads stealth/diagnostics_default from a temp YAML pointed to by `A2WEB_CONFIG`
- [x] 8.8 Test: `A2WEB_STEALTH=true` env override beats a YAML `stealth: false`
- [x] 8.9 Test: `jina_key` set in YAML is ignored; only `A2WEB_JINA_KEY` populates it

## 9. Quality gate

- [x] 9.1 `make lint` — ruff clean
- [x] 9.2 `make ty` — Astral `ty` clean, zero `# ty: ignore` introduced
- [x] 9.3 `make test` — pytest green, coverage ≥85%
- [x] 9.4 `make check` — full gate green

## 10. Commit

- [x] 10.1 Update `CLAUDE.md`: replace the `connection.py` description with `settings.py`, remove references to `connections_cli`, mention the YAML config path
- [x] 10.2 Update `README.md` quick-start to show `~/.a2web/config.yaml` and env var examples (no `a2web connections` mentions)
- [ ] 10.3 Single commit "PR1: a2kit App composition + stub fetch tool + YAML config" (workspace is not a git repo yet — `git init` first or skip)
- [ ] 10.4 Hand off to PR2 (AppState + lifespan)
