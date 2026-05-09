## Context

a2web sits on top of `a2kit` v0.22, which owns the MCP server, CLI, ConnectionStore, formatter, DI, and schema discovery. PR1 is the first of a 10-PR bootstrap and only wires composition; no real fetching happens yet. The reference shapes are `~/Workspaces/a2kit/examples/tracker/server.py` and `routers.py`. Constraints in `CLAUDE.md` and `v0.1-patterns.md` are authoritative — most importantly, a2kit antipatterns #1 (no `-> str` from tools) and #2 (return types at module scope), plus the operating principle that `fetch(url)` is one-shot and never asks the calling agent to do work.

## Goals / Non-Goals

**Goals:**
- `a2web --help`, `a2web web fetch --url=https://example.com`, `a2web serve --transport=stdio`, `a2web connections {list,add,...}` all run.
- Lock the public envelope: tool name `fetch`, router `web`, return type `FetchResponse` (pydantic, module-scope).
- Lock the diagnostic types: `Verdict` as a closed `StrEnum`, `Diagnostic` as a pydantic model — even though they are unused in PR1, downstream PRs depend on them.
- `make check` (ruff + ty + pytest, coverage ≥85%) green on the PR1 surface.

**Non-Goals:**
- No fetching, no tier dispatch, no AppState, no lifespan, no streaming events, no LDD wiring. All deferred to PR2+.
- No proxy, no cache, no browser pool. Even imports are out of scope.
- No CLI flag plumbing beyond what a2kit derives automatically from the tool signature.
- No site-handler routing, no quality gate, no playbook.

## Decisions

### Decision 1: Router name is `web`, not `fetch`

a2kit produces `a2web <router> <tool>` from the registered router class. With a router named `fetch` and a tool named `fetch`, the CLI becomes `a2web fetch fetch --url=...` — awkward and noisy. Naming the router `web` yields `a2web web fetch --url=...`, which reads naturally and leaves room for sibling tools (e.g., `a2web web search` later) under the same router. The router class is `WebRouter`.

**Alternatives considered:**
- Keep router `fetch`, tool `get` → reads `a2web fetch get --url=...`; inverted from the design docs that name the tool `fetch`.
- Use a top-level tool with no router → not idiomatic in a2kit; loses CLI verb grouping.

### Decision 2: Stub returns a fully populated `FetchResponse`

The stub doesn't fetch, but it returns the *real* envelope shape (status, content_md, fetched_at, elapsed, tier, etc.) with placeholder values. This forces every field decision in PR1 — once the envelope is wire-visible, changing it later is a breaking change for MCP clients. Better to argue about field names now than after we have callers.

**Alternatives considered:**
- Return `{"todo": "not implemented"}` dict. Rejected: violates antipattern #1 and pushes the envelope decision to PR3.

### Decision 3: a2kit consumed via git tag, not editable path

a2kit v0.22 isn't on PyPI yet. `[tool.uv.sources] a2kit = { git = "https://github.com/yoselabs/a2kit.git", tag = "v0.22.0" }` keeps `a2kit>=0.22,<1` in the dependency list (the PyPI fence) and resolves to a frozen GitHub tag. Removing the `tool.uv.sources` block when a2kit publishes is the only change.

**Alternatives considered:**
- Editable path dep `path = "../a2kit"` → faster local iteration on a2kit, but breaks clean checkouts and CI without the sibling repo. Rejected: a2kit is stable enough at v0.22 that we don't need live edits from a2web. Switch back temporarily if we need to iterate on a2kit while building a2web.
- Vendor a2kit into a2web → permanent fork hazard. Rejected.

### Decision 4: Module-scope types only

`FetchResponse`, `Diagnostic`, `Verdict` live at `src/a2web/models.py` module scope. Even auxiliary helper types (e.g., a small `Hint` model) go to module scope, never nested inside a function or method. This is non-negotiable: a2kit antipattern #2 explicitly bans nested return types because they break schema discovery for MCP.

### Decision 5: `Verdict` is a closed `StrEnum`

Per `CLAUDE.md`, verdicts are a closed enum (`ok`, `paywall`, `block_page_detected`, `anti_bot:<system>`, `length_floor`, `content_type_mismatch`, `connection_error`, `timeout`, `not_found`, `rate_limited`, `proxy_unavailable`, `other`). For the `anti_bot:<system>` family we use a single `anti_bot` enum member in PR1 and defer the system suffix to a sibling field on `Diagnostic` (e.g., `subsystem: str | None`). This keeps the enum truly closed for type checking while preserving expressive diagnostics.

### Decision 6: No AppState in PR1

PR2 is "AppState + lifespan". PR1 deliberately ships without DI so the composition itself stays trivial and reviewable. The stub tool needs no shared state.

### Decision 7: Drop `connections_cli`; configuration is a single YAML file

a2web has no per-instance connection concept (unlike a2db/a2atlassian which connect to specific databases or Jira workspaces). The `WebFetchConn` profile was a misfit — what we actually need is global config (proxy pool, route rules, default UA, stealth, diagnostics default, cache TTLs, optional Jina key). One file, optional, env-overridable.

- File: `~/.a2web/config.yaml` (override via `$A2WEB_CONFIG`).
- Loader: `pydantic-settings` with a custom YAML source.
- Field overrides via `A2WEB_*` env vars (e.g., `A2WEB_STEALTH=true`, `A2WEB_JINA_KEY=...`).
- Secrets (`jina_key`) — env-only, never written to the YAML by the tool.
- No paid-tier keys in v0.1 (no Firecrawl, no Bright Data).

The fetch tool MUST work zero-config: when no file exists, `AppSettings` returns defaults, the proxy pool is empty, and direct fetches still work in later PRs.

**Alternatives considered:**
- Keep `connections_cli(WebFetchConn)` (option A from discussion) → preserves a2 idiom but the "connection" naming is genuinely confusing for a tool that fetches the open web. Rejected.
- TOML instead of YAML → matches sibling repos' format. Rejected because we are diverging from the connection pattern entirely; YAML is more familiar for human-edited config.
- Multiple named profiles (e.g., `default`, `stealth`, `archive-heavy`) → premature for v0.1. Add via a `profiles:` section in the same YAML if/when needed; selection via `A2WEB_PROFILE=stealth`.

### Decision 8: Full `FetchResponse` envelope locked in PR1

Following `v0.1-response-format.md` §2, the envelope fields are: `url`, `status`, `tier`, `confidence`, `title`, `byline`, `published`, `started_at`, `total_ms`, `tokens` (full + fit), `cache`, `narrative`, `diagnostics`, `meta`, `links`, `headings`, `content_md`, `fit_md`, `operator_hints`. All of these land in PR1 even though most are unused; renaming after MCP clients exist is breaking. Subsidiary types (`Verdict`, `FetchStatus`, `Confidence`, `CacheState`, `Diagnostic`, `Heading`, `Link`, `OperatorHint`, `TokenCounts`) all live at module scope in `models.py`.

The TOON-flavored markdown serializer ships in PR2 or PR3; PR1's stub tool returns the model and lets a2kit's default formatter handle it (likely as TOON of the pydantic shape). The custom renderer is a *renderer* over this fixed model, not a different envelope.

## Risks / Trade-offs

- **[Risk] Locking the envelope before fetching exists may force a breaking change later** → Mitigation: derive fields directly from the design docs (`v0.1-response-format.md`) which already specify the envelope. If a field is uncertain, mark it `Optional` and default to `None` rather than omitting.
- **[Risk] Git-tag dep on a2kit may slow CI cold installs** → Mitigation: tags are immutable so uv caches resolve quickly; remove the `tool.uv.sources` block when a2kit publishes to PyPI.
- **[Risk] Router rename `fetch → web` deviates from the prompt's CLI examples** → Mitigation: explicitly captured in the proposal and design as a locked decision; CLAUDE.md and READMEs to be updated in this PR so the examples stay coherent.
- **[Risk] Coverage gate (≥85%) may be hard to hit on three small files** → Mitigation: the test module exercises every code path (one tool, one router, one server composition); placeholder logic is small enough to cover fully.

## Migration Plan

- No migration. First runnable surface; nothing exists to migrate from.
- Rollback: revert the PR1 commit. The workspace returns to its pre-PR1 scaffold (no working CLI, no working MCP server).
