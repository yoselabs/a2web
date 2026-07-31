# a2web — Agent-to-Web

> **Read [`CONSTITUTION.md`](CONSTITUTION.md) before any non-trivial
> change** — the rules above the rules govern substrate vs product
> placement, dependency adoption, and magic budget. Canonical source is
> a2kit; this repo carries a verbatim copy. Currently Phase A: agents
> apply, human confirms each Constitution-touching change.

## The shelf — shared micro-software you consume

This project consumes **the shelf** (`github.com/yoselabs/shelf`) — shared, ownable,
contract-guaranteed software pieces, pinned in `pyproject.toml` by git tag. Reach for it before
hand-rolling substrate; adopt only if **DEEP · STABLE · WINS**; contribute back by *promotion*.

**Full behaviour = the shelf loop.** Resolve it **once per session, lazily** — the first time you
consider adopting or promoting substrate, never at startup:

1. Find the local clone: `$SHELF_HOME` → `../shelf` → `~/Workspaces/shelf`.
2. If absent (greenfield), clone it once: `git clone https://github.com/yoselabs/shelf ~/Workspaces/shelf`.
3. Read `<shelf>/docs/agent-loop.md` and follow it. Load once; cache for the session.

Never hit GitHub to start a session or to write code — only to clone (once) or during an actual
adopt/promote (a lazy `git pull` at that checkpoint). Never commit a local `path=`/editable shelf
source. Enforced by `tests/architecture/test_no_local_shelf_source.py`, which
runs in `make check` and therefore in CI on every push and PR (see
**Enforcement — what actually blocks** below). The shelf also installs a
pre-commit hook that catches it earlier, but that hook resolves its check out of
a shelf clone and exits 0 when it cannot find one — it is a convenience, not the
floor.

CLI and MCP server for AI agents to fetch web content adaptively. Built directly on `fastmcp` (>=3.4) — the `a2kit` framework it used to sit on was retired on 2026-07-22 by `openspec/changes/sunset-a2kit-dependency/`; read that change's `design.md` before touching the composition, wire encoding, or error envelope.

Design rationale that predates this repo lives in the maintainer's private notes and is not required to work here — everything load-bearing is in `openspec/` and `docs/adr/`. Migration history lives in `openspec/changes/archive/`; the most recent is `a2kit-v043-migration/` (ADR-0028 unified surface: App authored by subclassing + flat `{slug}_{leaf}` canonical names pinned back to bare names via `canonical_name_override`; ADR-0027 LDD refound: `a2kit.ldd` retired, events emit via `await a2kit.log.info(...)` and sinks are `logging.Handler`s). Outgoing feedback rounds in `docs/history/A2KIT_FEEDBACK_v0.*.md`; deferred wishes in `docs/history/A2KIT_WISHES_DEFERRED.md`.

## Architecture (FastMCP direct — a2kit retired 2026-07-22)

**a2web composes on `fastmcp.FastMCP` directly.** a2kit was retired by the
`sunset-a2kit-dependency` change; its App/Router/DI-container/formatter spine is
replaced by ~300 lines a2web owns. What moved where:

| a2kit | now |
|---|---|
| `App` subclass + `routers` ClassVar | `server.build_mcp_server()` |
| `app.provide(...)` container | `components.build_components()` — the ONE composition root |
| implicit wire/injected param split | explicit tool signatures in `routers.py` (design D1) |
| `Lazy[T]` from the container | `lazy.Lazy` + `scope.memoized(factory)` |
| resource entry on resolution | `scope.ResourceScope` (LIFO, records only after a successful `__aenter__`) |
| `EncodingPlan` inference + `FormatRoutingMiddleware` | `wire.py` — a LITERAL `_TSV_FIELDS` table, not inference |
| `McpErrorRenderStage` + envelope middleware | `error_wire.py` |
| `a2kit.log` | `a2web.log` (Phase 1) |
| `encode_tsv` | shelf `lean-wire` (adopted 2026-07-22; `_tsv_compat.py` is gone) |
| `a2kit.testing.client` | `tests/_helpers/mcp.py` |
| `a2kit lint rego` | **dropped — a real loss**, see `BACKLOG.md` 2026-07-22 |

`a2effect` (the typed error taxonomy + `ErrorEnvelope`) is now a DIRECT
dependency rather than transitive through a2kit.

**The two guarantees hand-wiring turned from structural into convention**, each
now pinned by an architecture test: cold-start laziness
(`test_cold_start_laziness.py` — a cache- or raw-served `query` must resolve
neither the browser nor the LLM thunk) and single-composition-root
(`test_one_composition_root.py`).

- `src/a2web/settings.py` — `AppSettings(BaseSettings)` from env (`A2WEB_*`) + optional YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml`. Holds proxy pool, route rules, default UA, stealth toggle, diagnostics default, cache TTLs, `jina_key` (env-only secret). `${ENV_VAR}` references inside YAML resolve at load time.
- `src/a2web/server.py` — `build_mcp_server(*, settings=None, components=None, **fastmcp_kwargs) -> FastMCP`. Builds the graph via `build_components()`, registers the tools, installs two middlewares and a lifespan whose exit calls `components.aclose()` (LIFO teardown of whatever was actually entered). **Middleware order is load-bearing**: `TypedErrorEnvelopeMiddleware` is added FIRST so it is outermost and sees the `ToolError` that `guard_tool` raised; `EnvelopeContentMiddleware` sits inside it and only touches success results. `expose_cookies_tool` gates whether `register_cookies_tools` runs — a served a2web has no local browser, so the tool is ABSENT rather than present-and-failing. `serve_http_main()` is the container entrypoint: `build_mcp_server(auth=provider)` + `mcp.run(transport="http")`, with config-gated Google OAuth. Also registers `GET /health` (`_register_health_route`) — the route the Dockerfile HEALTHCHECK curls; a2kit's multiplex parent served it for free, Phase 4 404'd it for a day, and `tests/capabilities/endpoint_auth/test_health_route.py` reads the path out of the Dockerfile so the two cannot drift again.
- `src/a2web/cli.py` — the Typer CLI, **derived** from the registered MCP tools rather than hand-written in parallel. `build_cli(components=…)` walks `mcp.list_tools()`, and each tool's `inspect.signature` becomes the command's options via `field_to_typer_annotation` (vendored from a2kit's 54-line `_field_to_typer.py`), so `--help` text and the MCP `inputSchema` descriptions are the same string and cannot disagree. Safe only because D1 made the parameter list wire-only; under a2kit's ambient wire/injected split the derivation would have been a guess. `_TOOL_GROUPS` is a LITERAL tool→(group, command) table for the same reason `wire._TSV_FIELDS` is literal — a tool missing from it is a build-time error, not a silently absent command. Commands own their teardown (`components.aclose()` in a `finally`): skipping it does not merely leak, the aiosqlite worker thread keeps the process alive after the JSON prints. Dropped vs a2kit: `--format`, `--json` (a no-op), `schema`/`list-tools`/`code`/`_meta`, and the never-called 50k truncate cap.
- `src/a2web/components.py` — **the one composition root.** `Components` is a frozen dataclass holding `settings` + `scope` + six `Lazy[T]` thunks (`state`, `sqlite`, `browser_backend`, `browser_robust_backend`, `llm_extractor`, `cookie_jar`). `build_components(*, settings=None, **factory_overrides)` wires them; nothing is constructed or entered until something awaits a thunk. The `*_factory` overrides are the test seam that `app.provide(T, fake)` used to be — `dataclasses.replace` fails loudly on a field that does not exist, so an override that stopped matching the graph breaks the test instead of quietly disarming it.
- `src/a2web/scope.py` — `ResourceScope` (enter + LIFO unwind; records ONLY after a successful `__aenter__`, keeps unwinding past a failing `__aexit__`) + `memoized(factory) -> Lazy[T]` (double-checked lock, so twenty concurrent cold `query` calls launch one browser, not twenty).
- `src/a2web/wire.py` — envelope encoding for the `content[0].text` channel + `PruneEmpty`. `_TSV_FIELDS` is a LITERAL per-tool table, not inference: a2web has two response models and which fields render as TSV is a contract. **Three a2kit encoder defects are fixed here, not ported** — the presence guard (a pruned field stays pruned instead of being resurrected as `"\n"` + a `_<name>_format` sidecar; this alone took the minimal success payload from 11 keys to 2), the already-a-string guard (a populated `other_pages`, which `_prune_wire` hands over pre-encoded, was being overwritten with the empty marker), and the shape guard (`encode_tsv` raises on rows that are neither `BaseModel` nor dict — `headings` is a list of `[level, text]` pairs — and a2kit swallowed the raise, so ONE unencodable field voided the encode for the whole envelope and `fetch_raw` never shipped a `_<field>_format` discriminator at all). The first two were a2web's round-17 bug reports against a2kit, filed as *"no a2web workaround exists"*. The codec itself is the shelf's `lean-wire`; the split is that `lean-wire` owns how a row becomes a line, a2web owns which fields become tables and what happens when one cannot — which is why adopting the shelf codec could not reintroduce any of the three, and why the shape guard is still needed (`lean-wire` raises the same `TypeError`).
- `src/a2web/error_wire.py` — the typed error envelope, in TWO pieces because one does not work: FastMCP masks a plain exception before middleware sees it, so `guard_tool` must convert at the tool boundary (`quarantine` a non-`AppError` into `UnexpectedDefect`, then `raise ToolError(prose) from exc`) and `TypedErrorEnvelopeMiddleware` recovers the envelope from `__cause__` on the way out. Prose for the model, `{"error": envelope}` for machine consumers, deliberately non-overlapping.
- `src/a2web/routers.py` — `register_web_tools(mcp, components)` and `register_cookies_tools(mcp, components)`. Tools are plain closures over `Components`, registered with `@mcp.tool(name=..., annotations=ToolAnnotations(...), tags=...)`. **The parameter list IS the wire schema** (design D1) — there is no wire/injected partition to guess, and no registration elsewhere can change it. `query(url, query, ...)` is primary (renamed from `ask(url, question)` in v0.23 / ADR-0015; runs server-side LLM extraction, returns the lean `AskResponse`); `fetch_raw(url, ...)` is the fallback (no LLM, page-shaped `FetchResponse`). Both delegate to `fetcher.fetch`; `query` projects via `build_ask_response`. Resources reach the orchestrator as UNAWAITED thunks (`browser_backend=components.browser_backend`) — awaiting one here would silently kill cold start. Tool args use `Annotated[T, pydantic.Field(description=...)]`. Phases emit via `await a2web.log.info(...)` and never receive ctx.
- `src/a2web/state.py` — `AppState` `@dataclass(slots=True)` carries the **always-on** resources only: `settings`, `breakers`, `proxy_pool`, `sqlite`. The heavy ones are `Lazy[T]` thunks on `Components`, never here. This module owns **HOW** each resource is constructed (`build_breakers`, `build_proxy_pool`, `build_browser_backend`, `build_browser_robust_backend`, `build_selected_provider`, `build_llm_extractor`); `components.py` owns **WHEN**, and is their only caller. Also exports `unavailable_lazy(cls, *, reason)` + `ResourceUnavailable`. **`bootstrap_state` and the `Resources` bundle are GONE** — they were the second assembly point, absorbed into `build_components`. Resource pattern: sync `__init__`, internal `_lock`, lazy `_ensure()`, idempotent `close()`, plus `__aenter__`/`__aexit__` thin wrappers.
- `src/a2web/models.py` — `FetchResponse` (page-shaped, returned by `fetch_raw`), `AskResponse` + `AskExtraction` (the lean `query` envelope — drops `content_md`/`headings`/`tokens`, omits empty optionals via a `@model_serializer`. Field tiers: failure-only `status`/`narrative`/`diagnostics_summary` (absent on success — absence of `status` means ok); debug-only `extraction`/timing/`cache`/`diagnostics`. `other_pages` renders as a TSV block, not a JSON array; truncation surfaces as an `answer_truncated` operator hint, never an `extraction: {truncated}` object). **Router-shape on `AskResponse` (v0.23 / ADR-0015):** `answer` (always) + conditionals via `_prune_wire` (`obstacle` Literal-4, `also_here: list[str]` — the same-page index in query grammar, `other_pages: list[OtherPage]` — kind-tagged `structural`|`drilldown`, unifying the former `next_links` + `try_url`) — conditionals omitted from the wire when empty/null. `FetchResponse` (`fetch_raw`) keeps its own `next_links: list[NextLink]`; the `other_pages` fold is scoped to the `query` envelope. `RouterPayload` pydantic mirrors the package-side `RouterPayload` boundary; closed-enum violations at the seam (`fetcher_response._project_routing`) drop the 7 fields but `answer` survives. Plus `Diagnostic`, `Verdict`, `Heading` (serializes as a compact `[level, text]` tuple), `Link`, `OperatorHint`, `TokenCounts`. Both `AskResponse` and `FetchResponse` carry a wire-only `@model_serializer` that delegates to the shared `_prune_wire(data, *, required, tsv, deviation, failure_only, debug_fields)` helper — one omit-empty + TSV + deviation + debug-regroup implementation, two thin serializers parameterized per envelope. Field tiers (v0.14 `envelope-deviation-trim`): always-present `confidence` (+ `answer` on ask); deviation-only `status` (dropped when `ok`), `tier` (dropped when `raw`), `url` (dropped when it equals the requested URL — builder-gated in `build_response` against `FetchContext.requested_url`); failure-only `narrative`/`diagnostics_summary`; debug-only `started_at`/`total_ms`/`cache`/`tokens`/`diagnostics`/`extraction` — these stay flat fields on the model but the serializer **regroups them into a wire-only nested `debug` object** (present only under `debug=True`). `links` + `next_links`/`other_pages` render as TSV. The serializer is wire-only — attribute access is unaffected, so `fetch()`'s internal callers (eval harness, `build_ask_response`) keep reading `.cache`/`.extraction`/etc. flat. `original_url` was removed in v0.14 — the surviving `url` (when present) is the deviation. All at module scope (a2kit antipattern #2). pydantic at boundaries; `dataclass(slots=True)` internally. `FetchResponse.fit_md` / `is_user_authored` were removed in v0.11 — never reintroduce a field that is provably always `None`/constant.
- `src/a2web/fetcher.py` — orchestrator. `_run_pipeline` is a 12-line coordinator calling six named phases: `_phase_cache_check`, `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate` (which calls `_escalate_browser` / `_dispatch_archive`), `_phase_cache_write`. State flows through a single `FetchContext` `dataclass(slots=True)` instead of 20+ parameters. **Verdict is a pure projection of the decision log** (v0.23) — no `gate_verdict` / `gate_subsystem` snapshot slots; reads go via `fc.last_gate_outcome() -> GateOutcomeProjection | None`. **Resources are non-optional `Lazy[T]` on FetchContext** — phases `await + try/except ResourceUnavailable` instead of `if not None` checks; `fetch()` normalizes any `None` caller-kwarg to an `unavailable_lazy(...)` stub at the entrypoint. **Extraction escalators are pure** — `_escalate_via_json` / `_escalate_via_records` return immutable `ContentCandidate | None`; single assignment site in `_run_extraction_escalation`. Tier loop body is split into named helpers (`_install_won_tier`, `_install_archive_payload`, `_apply_after_tier_action` returning `_AfterTier` enum). Escalators share `_emit_tier_started` / `_emit_tier_ended` + `_regate_after_escalation` helpers.
- `src/a2web/tiers/` — Strategy + Registry. `raw.py` (curl_cffi), `jina.py` (r.jina.ai reader), `archive.py` (Wayback CDX + archive.ph hedged via anyio task group), `browser.py` (`patchright`/`zendriver` via the shelf `any_browser` package — Camoufox is gated off, see `_manifests/browser_backends/camoufox.py`), `paid.py` (Firecrawl env-gated). `TIER_ORDER = ("site_handler", "raw", "jina")`; archive + browser are in REGISTRY but **not** in TIER_ORDER — orchestrator dispatches them out-of-band (archive on playbook `RetryViaArchive`; browser on gate `suggested_tier == "browser"`, capped at 1/fetch). **`TierResult` is a typed dataclass with named fields** (`pre_rendered: Rendered | None`, `from_archive`, `from_browser`, `js_executed`, `browser_wall_ms`, `browser_bytes`, `snapshot_age_days`, `operator_hint`, `no_match`, `skipped`, `handler_name`, `conditional_hit`, `archive_source`) — the `tier_extras: dict[str, Any]` bag is gone.
- `src/a2web/handlers/` — site-specific tier-0 (Handler protocol = Tier + `matches(url)`). `reddit.py`, `hn.py`, `arxiv.py`, `wikipedia.py`, `github.py` (optional `A2WEB_GITHUB_TOKEN` raises rate limit 60→5000/hr). Handlers populate `TierResult.pre_rendered: Rendered` (typed: `content_md`, `title`, `byline`, `headings`) so the orchestrator skips trafilatura/metadata; gate still runs. No-match URLs return `TierResult(no_match=True)` and are skipped silently. **Shared helpers** (v0.23): `handlers/_common.py` provides `empty_result(url, verdict)` (was duplicated in 9 handlers) + `map_non_ok(outcome, *, url) -> TierResult | None` for the standard `FetchVerdict → Verdict` short-circuit. Reddit's shape-aware `status_code == 403` policy stays inline (only handler that needs it).
- `src/a2web/domain.py` — domain-coupled glue. Pure functions reading `AppSettings` or models but too small for their own files: `compute_profile_hash`, `is_live_only`, `rewrite_captcha_host` (Google/Bing `/search` → DuckDuckGo HTML pre-routing). Lives at top level because the previous per-domain seam directories were nuked.
- `src/a2web/events/` — `types.py` (typed event payloads: `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded`, `TierHeartbeat`), `sinks.py` (`OtelHandler(logging.Handler)` — sync `emit(record)` reading `record.getMessage()` + `record.a2kit_fields`, one span per `*Ended` event, no-op when SDK absent). a2kit routes typed events through stdlib logging. Emit via `await a2kit.log.info(StageStarted(...))` from anywhere in the pipeline; `app.log.add_handler(OtelHandler())` attaches the OTel half (via the sink plugin manifest, which now yields `logging.Handler` instances). Bench-only event types (`CellStarted`, `CellEnded`) live separately under `llm_eval/events.py` and are consumed only by `llm_eval/live_sink.LiveSink` (itself a `logging.Handler`) — not on the OTel path.
- `src/a2web/llm_resource.py` — `LlmExtractorResource`. AppSettings-aware provider selection (auto/anthropic/claude-code), plumbs `SqliteResource` into `ExtractionCache`. As of v0.7 `anthropic` + `claude-agent-sdk` are baseline deps — no install gating. Domain-coupled — stays out of `packages/`. Surfaced at the tool seam via `Lazy[LlmExtractorResource]` so the provider only constructs when `ask=` is actually passed.
- `src/a2web/cookie_jar.py` — `CookieJarResource` (v0.8). Opt-in browser-cookie mirror. Domain-coupled (reads `AppSettings`, depends on `SqliteResource` for the two new tables `a2web_cookies` + `cookies_meta`). Wired in `components.build_components()`, surfaced at the tool seam as `Lazy[CookieJarResource]`. Pure cookie-store I/O lives in `packages/cookie_store/{chrome,firefox,models}.py` (Chrome on macOS: `security` CLI for the Keychain key + AES-GCM via `cryptography`; Firefox: plaintext sqlite). The `refresh` MCP tool (registered by `register_cookies_tools`, gated on `expose_cookies_tool`) is the only moment a Keychain prompt fires — CLI surface `a2web cookies refresh`. Staleness surfaces as `OperatorHint(code="cookies_stale", ...)` on every fetch when the mirror is past `cookie_stale_after_hours`; `CookiesStale` log event mirrors the signal for operators. Cookie values are redacted from log events via `redact_cookie_for_event(cookie)`.
- `src/a2web/llm_eval/` — eval harness (`EvalSuite`, `Judge` wrapper, `WebFetchBaseline` / `A2WebDetail` / `A2WebExtract` systems). Domain-coupled — imports `AppSettings`, `FetchResponse`, `build_state`.
- `src/a2web/cache.py` — the **cache seam** over the shelf `sqlite-resource` + `http-cache` primitives (adopted back after promotion; was `packages/http_cache.py`<!-- gone -->). Domain policy lives here: `cache_dir()` (`$A2WEB_CACHE_DIR`), the on-open schema (via `_migrate_and_apply_schema`, which drops a legacy `profile_hash`-shaped `cache` table so existing installs rebuild rather than crash on the renamed `variant` column), and a `SqliteResource(_sqlite_resource.SqliteResource)` subclass adding the `(url, profile_hash)` `.get`/`.put` accessor. a2web keeps its HTTP cache + extraction cache + cookie mirror in ONE sqlite file behind this one shared connection (`ensure()` / `conn`). The composite `http_cache.HttpCache` owns a private connection, so a2web uses http-cache's free functions instead.
- `src/a2web/packages/` — in-tree microsofware. Modules under here MUST NOT import from `a2web.<domain>`. Boundary types are owned by the package; domain-coupled wiring lives in `domain.py` / `llm_resource.py` / `cache.py`. Current packages: `block_detector`, `proxy_routing/`, `escalation`, `llm_extract/` (folder — multi-author surface with `extractor`, `judge`, `prompts`, `errors`, `router_payload`, `wobble`). **`llm_extract/providers/` is GONE** — promoted to the shelf as `anyllm` and adopted back; the concrete adapters now come from `anyllm[anthropic,openai,claude-code-sdk]` and a2web keeps only the Extractor/Judge/prompts above them. **`browser_backends/` is GONE** — promoted to the shelf as `any_browser` (2026-07-26); a2web keeps the product half (`select_backend*` in `state.py`, manifest gating in `_manifests/browser_backends/`, the fast/robust rung split, the `RenderOutcome→Verdict/OperatorHint` mapping in `tiers/browser.py`). The engine override env is now `ANY_BROWSER_EXECUTABLE_PATH`. Likewise `llm_cost_guard` → shelf `anyllm.cost`, the extraction `cache` → shelf `llm-cache`, and `content_extract`/`cookie_store`/`html_fragment`/`record_extract` were promoted/retired earlier — see `openspec/changes/shelf-sweep-promotions/`. The boundary is enforced by `tach.toml` (`uv run tach check`, in `make arch`); `tests/architecture/test_tach_covers_every_package.py` asserts its module list and the real package tree stay the same set, because an UNLISTED package silently gets no contract at all.

  **LLM contract parsing.** Every site that parses LLM JSON funnels through `packages/llm_extract/wobble.parse_with_policy` (object envelopes) or `parse_list_with_policy` (JSON-array envelopes). The funnel owns `json.loads` (no other site in `packages/llm_extract/` may call it; the pytest-archon `json.loads`-ban will close this loop) and returns an opaque `Wobbled` NewType — downstream code typed as `Wobbled` cannot accept a hand-rolled payload fabricated outside. Per-field `WobblePolicy` (`STRICT` / `DERIVE` / `DEFAULT` / `SKIP`) tables live centrally in `wobble/_policies.py` for static cases; tables that bind a DERIVE callable (e.g. `_JUDGE_POLICY` referencing `_derive_reached`) stay adjacent to the callable in their consumer module. Recovered wobbles fire the single structured log key `llm_wobble`. Sites today: `judge.py`, `bench_judge.py` (clarity + next_links), `extractor.py` (router-shape + next_links), `fetcher_response.py::_project_routing` (pydantic-validate, not JSON parse — emits `llm_wobble` on closed-enum violations).
- `src/a2web/actions/` — pure deterministic decision logic (no I/O, no domain writes): `playbook.py` (`next_action_after_gate` / `next_action_after_tier`), `terminal.py` (`classify_terminal(observations, resolved_verdict) -> TerminalOutcome` — the backward-looking failure-story classifier, sibling of the forward planner; shared evidence predicates `has_hard_wall_evidence` / `has_subresource_block_evidence` / `has_empty_marker`), `empty.py` (`is_confirmed_empty(observations, url)` — the empty→`ok` promotion conjunction, decided upstream of the failure-only `classify_terminal`). Per-fetch counters in `FetchContext`: `url_rewrites`, `archive_dispatches`, `browser_dispatches`.
- shelf `plugin_surface` + `src/a2web/_manifests/` — plugin manifest framework (Pattern 2 of ADR-0001). Every extension surface converges on `PluginManifest[T]` + `Unavailable` + `load_surface(...)` / `load_surface_sorted(...)`. Each plugin lives as a no-side-effects module under `_manifests/<surface>/<name>.py` declaring `MANIFEST = PluginManifest(...)`. Surfaces today: `llm_providers/` (anthropic, claude-code), `eval_systems/` (webfetch_baseline, a2web_detail, a2web_extract), `sinks/` (otel), `handlers/` (9 site handlers), `tiers/` (5 tiers). Adding a plugin = drop one file; `load_surface(...)` discovers it at boot, drops `Unavailable` returns silently. Module-level side effects banned by `tests/architecture/test_plugin_modules_only_declare_manifest.py`. Package-side classes stay settings-free (microsofware-pure); domain wiring lives in the manifest.

## Testing

`tests/_helpers/mcp.py` is the seam. `async with mcp_client(components=parts) as c: await c.call_tool("query", {...})` drives a real `fastmcp.Client` over the real production server, so nothing about the transport is faked.

**The CLI has its own gate.** `tests/contracts/cli/*.json` froze the a2kit-generated CLI at commit `d2dc5d8` (capture harness preserved verbatim as `_captured_with.py`); `tests/contracts/test_cli_contract.py` replays the same argv against a2web's own CLI. Unlike the MCP wire gate, the rule is **not** zero-deltas — the capture recorded a2kit artifacts (a no-op `--json`, unreachable `--format` values, framework-only `serve` flags) that would be wrong to port. Instead every difference must be named in `_ACCEPTED` with a reason, and `test_every_accepted_delta_is_real` fails when an entry stops describing a real difference, so the table can't rot. The five `_PAYLOAD_CASES` are byte-for-byte — that's what a script pipes into `jq`.

**Two channels, two helpers — the distinction is load-bearing.** `call_wire(client, tool, **kw)` returns `structured_content` as JSON (the pruned model dump — what a2kit's old `client.call_wire` reported, so the ~1350 existing field-presence assertions still mean what they meant). `call_text(...)` returns `content[0].text` — the same payload PLUS the TSV blocks and their `_<field>_format` discriminators. Asserting `"headings" not in call_wire(...)` says nothing about what the agent sees; use `call_text` when the agent's view is the point.

Fakes go in via `dataclasses.replace(parts, llm_extractor=lazy(fake))` — `replace` raises on a field that does not exist, so an override that stopped matching the graph fails the test instead of silently doing nothing (a2kit's `app.provide(T, fake)` would happily register a key nothing resolved).

Unit tests typically call `fetcher.fetch(...)` directly for real `FetchResponse` instances. `tests/conftest.py::make_default_state(...)` builds an `AppState` synchronously for those (the one reviewed exception to the single-composition-root rule — the guard walks `src/`, so conftest is out of its reach by design); `make_default_components(...)` is the async full-graph version. `a2web.lazy.lazy(value)` wraps a pre-built resource as a `Lazy[T]` thunk.

## Dev Commands

- Full gate: `make check` (lint + ty + test, coverage ≥85%)
- Lint: `make lint`; auto-fix: `make fix`
- Type check: `make ty` (Astral `ty`)
- Tests: `make test` (pytest, asyncio_mode=auto)
- Local MCP: `make dev`
- Bootstrap: `make bootstrap` (uv sync --all-extras)
- Output benchmark: `make bench` (see below)
- Local CLI / local-browser dev: `make install-global` (optional — see below)

## Enforcement — what actually blocks

Stated plainly, because overstating enforcement is how a guard comes to read as
coverage while providing none.

| mechanism | when it runs | what it actually does |
|---|---|---|
| `make check` via `.github/workflows/ci.yml` | **every push, every branch, every PR** | The floor. Lint, types, full suite, coverage ≥85%, every architecture guard. Reports red; does not block a merge (see below). |
| `make check` via `release.yml` | every `v*` tag | Runs again independently — a tag can point at any commit, and this path publishes a public image. |
| `make test-browser` via `release.yml` | every `v*` tag only | Real Chromium launch, skips forbidden. **Does NOT guard a push.** |
| `.pre-commit-config.yaml` | locally, if the contributor installed hooks | Lint only — ruff, format, markdown, actionlint (+ `ty` on pre-push). No tests, no architecture guards. A fresh clone and every CI runner have no hooks at all. |
| the shelf's `no-local-shelf-source` hook | locally, if both the hooks and a shelf clone are present | Convenience. Exits 0 when it cannot find a shelf clone. The real floor for that invariant is the architecture test in `make check`. |

**Branch protection is an operator setting, not a file.** CI running and
reporting red does not prevent a merge; making the check required is configured
in the GitHub repository settings. This matters more here than usual — `fb:no-prs`
means this repo merges to `main` directly, so there is often no PR for a check to
block. **The realistic protection is: the push is gated and the author sees red
immediately.** Not: the merge is blocked. Do not write or imply otherwise.

Before 2026-07-31 the only workflow was `release.yml` (`on: push: tags: v*`), so
every architecture guard ran at tag time and at no other time — a violation
landed, survived, and surfaced in a batch attributed to whoever tagged. Fixed by
`openspec/changes/run-the-gate-on-every-push/`.

## Deployment — remote-first

The canonical a2web runtime is a **remote container reached over HTTP**, not a
local binary and not a `serve` subprocess. Build the `Dockerfile` image, publish
it to a container registry, and run it behind any HTTP MCP gateway; an MCP client
then points at that endpoint (`{"type": "http", "url": "https://<your-gateway>/a2web/mcp"}`).
A source change goes live by rebuilding and redeploying that image — deploying is
a separate, operator-driven step, never a side effect of pushing.

The container is deliberately slimmed — no `[browser]`/`[cookies]`/`[claude-code]`
extras — so a served a2web has no local browser and the `cookies_refresh` tool is
ABSENT (gated by `expose_cookies_tool`).

**`make install-global` is optional, for LOCAL work only** — a `uv tool` install
carrying the extras the container drops (`[browser]` patchright/zendriver,
`[cookies]` local-browser mirror, `[claude-code]` OS-session piggyback). Use it
for the local CLI or to exercise the browser/cookie paths that only work on a
real desktop. It is NOT part of the deploy path, so there is no "reinstall after
a version bump" step — that trade-off died with the remote switch.

## Benchmark

`make bench` runs the output benchmark — `src/a2web/llm_eval/`, corpus `eval/corpus.yaml` — scoring three systems (WebFetch reproduction + the two a2web modes) on four axes: answer quality, token cost, output clarity, data-contract conformance (+ `next_links` on listing URLs). It is **live-network and spends LLM quota**, so it is deliberately NOT in `make check` and is not run by default.

Run it after a change that could move output quality or cost: the response envelope shape, the extraction pipeline, tier routing/escalation, handlers, or `next_links`. Skip it for unrelated changes. The four-axis tests under `tests/capabilities/output_benchmark/` keep the harness itself from rotting and DO run in `make check`. Write findings to `eval/findings_<date>.md`; run artifacts land under `eval/runs/` (gitignored, regenerable).

**Never lose a case.** Every time a new failure, edge case, or scenario surfaces — in a conversation, a proposal, a bug report — capture it in `eval/corpus.yaml` as a corpus entry the *same session*, before the context is lost. A discussed-but-unrecorded case is a regression waiting to happen. Phrase `criteria` against **stable structural facts** (not today's page text) so the entry survives content rotation. The `affordance` class covers "the answer or its link lives on a different page than the one fetched" (link-affordances / ADR-0009 / ADR-0012). This rule is mirrored in the `eval/corpus.yaml` header.

## Conventions

- `dataclass(slots=True)` for internal pipeline objects; pydantic only at API boundaries.
- `asyncio.to_thread` chokepoint per sync module (trafilatura, sqlite). Ruff `ASYNC100/210/230` enforces.
- Always-on shared state hangs off `AppState`; heavy/conditional resources (browser, LLM, cookies) are `Lazy[T]` thunks on `Components`. Tools close over `Components` and pass the thunks down UNAWAITED. No globals, no module-level lazy caches.
- Lifecycle: `ResourceScope` enters a resource on first thunk resolution and unwinds LIFO from the FastMCP `lifespan=` exit. Each resource exposes `__aenter__`/`__aexit__` as thin wrappers over its idempotent `_ensure()` / `close()`.
- Every resource is constructed by a named factory in `state.py` and wired in `components.py` — those two modules, and no others.
- Heavy/conditional resources use `Lazy[T]` at the tool seam — keeps cold start cheap on the common path. Unwrap exactly once at the consuming phase, then thread the resolved value (not the Lazy callable) into helpers.
- Events: emit via `await a2web.log.info(PayloadType(...))` on stdlib logging (**keep the `await`**; `info` is async). The synchronous log to the `a2web` logger always fires; the MCP-wire forward only happens under a tool dispatch. Phases never accept or pass ctx. Subscribe consumers as `logging.Handler`s via `a2web.log.add_handler(...)` — which REPLACES a same-type sink by default, because the logger is process-wide and `build_mcp_server()` is not.
- All logging flows through the single `a2web` logger (`propagate=False` + a NullHandler floor — MCP is stdio, so an escaped record can corrupt the JSON-RPC stream). Async sites emit `await a2web.log.{info,warning,…}`; sync boot/pure-function sites use `log_debug/log_info/log_warning/log_error` on the same logger. No bare `structlog`.
- `purgatory` for circuit breakers (per-host, per-proxy, global).
- Closed-enum verdicts for diagnostics.
- `fmt_dur(ms)` helper for every duration string.
- Don't return `-> str` from a tool. Return dict / pydantic model.
- All return-type pydantic models at module scope.

## Architecture invariants (enforced by `make arch`)

Module boundaries are encoded in `tach.toml`; call-site / signature / class-shape rules live as AST tests under `tests/architecture/`. See `docs/architecture/README.md` for the workflow. Adding a new rule = writing a test; landing a new violation fails CI; one-time grandfathering carries a retirement comment.

Currently enforced:

- Packages may not import from `a2web.<domain>` — `tach.toml`.
- No `json.loads` outside `packages/llm_extract/wobble/` — `tests/architecture/test_json_loads_funnel.py`.
- No direct `trafilatura` calls — HTML extraction funnels through the shelf
  `content_extract` — `tests/architecture/test_trafilatura_funnel.py`. Two
  handlers are exempt with the reason inline (the shelf has no `include_comments`
  knob and comment threads need it); that is a shelf gap to promote, not a
  standing exception.
- Handlers parse markup with a DOM, never a regex — `tests/architecture/test_handler_markup_funnel.py`.
  In `handlers/`, every `re.compile` pattern must be an anchored URL path; markup
  goes through the shelf's `dom_schema.extract`. Structural on purpose: classifying
  patterns by their text was tried and failed BOTH ways (named groups `(?P<x>` read
  as markup; `listing_oracle`'s `rel\s*=` was missed because the target is itself a
  regex). Born 2026-07-28 when the arXiv listing and wikipedia wikilink parsers were
  both found returning ZERO rows against live pages holding 47 entries and 1066
  anchors, each behind a GREEN suite over hand-written fixtures.
- No `dict[str, Any]` on slotted dataclasses (allowlist gated) — `tests/architecture/test_no_dict_str_any_on_dataclasses.py`.
- Tools never return `str` — `tests/architecture/test_tools_return_pydantic_not_str.py`.
- Cold start resolves neither browser nor LLM — `tests/architecture/test_cold_start_laziness.py`.
- Exactly one composition root — `tests/architecture/test_one_composition_root.py`.
- Every architecture walk asserts it is non-vacuous — `tests/architecture/_walk.py` + `test_walk_is_not_vacuous.py`.
- `BaseModel` subclasses defined at module scope — `tests/architecture/test_response_models_at_module_scope.py`.
- `packages/*/__init__.py` `__all__` is frozen — `tests/architecture/test_packages_boundary_frozen.py`.
- aiosqlite worker thread doesn't leak — `tests/architecture/test_aiosqlite_daemon.py`.
- Plugin manifest files in `_manifests/` have no module-level side effects — `tests/architecture/test_plugin_modules_only_declare_manifest.py`.

## Never

- Never commit credentials. Secrets are env-only (`A2WEB_*`).
- Never bypass the quality gate when writing to cache (block pages must never enter cache).
- **Never tolerate ANY unfetched URL** (the first-class product invariant — ADR-0009). A wall is not an outcome, it is an unfinished job: a walled/failed fetch MUST carry `status: failed` + `retrieval_incomplete: true` + populated `diagnostics` + `narrative` + a critical `try_user_browser` operator hint (or `paid_auth_error` when a keyed paid tier's key is bad). The caller must never be able to mistake a miss for a complete answer. Adding a fetch path that can silently return empty-but-`ok` violates this — the floor is loud, explicit incompleteness. **The terminal story is a single pure `classify_terminal(observations)` (ADR-0017), NOT a per-verdict whitelist:** effort ∝ the prior that content exists; terminal confidence ∝ corroboration (a `404` is `gone_confirmed` only when ≥2 tiers agree or a handler is authoritative, else `gone_unverified`); hint severity encodes confidence (`info` = verified dead URL, `warning` = unverified/soft-404 residual, `critical` = a wall — a `404` is NEVER `critical`, never the anti-bot `try_user_browser` klaxon). A tier that retrieves an error page surfaces the real upstream status (tier-truthfulness) — never launder a 404 into `ok`; reader-wrapper decoding (jina's `Target URL returned error <status>` stub) is tier work, not gate work.
- **Never manufacture a selection** (the first-class product invariant — ADR-0012). a2web shapes & relays content; it never ranks, filters, hides, or crowns by a criterion of its own. On a question that asks a2web to pick from a set (which/best/compare), the `query` answer MUST NOT assert a2web's own "best" — it presents the option space, relays any *source-stated* preference attributed to the page ("the site marks X as preferred"), and MAY offer only a criterion-disclosed lead ("by rating, X leads — one lens"). "Best" is criteria-less to a fetcher; criteria belong to the caller. Neutral is not lazy: the answer stays exhaustive (Exhaustive · Faithful · Neutral · One-shot) so the caller never re-fetches the same page to recover data already in hand — the scarce cost is the proxy fetch, not tokens. Sibling to ADR-0009: presenting a manufactured pick as the answer is the same class of harm as a silent miss.
- **Never surface a URL that isn't on the page** (the first-class product invariant — ADR-0014). Every URL a2web emits — in `other_pages` OR inline in the `answer` prose — must be traceable to the fetched page: a `{{n}}` digest handle (an anchor href, closed-set rehydrated) or a URL literally present in the page content. A URL from the model's training knowledge or pattern-guessing (`…/reviews`, `…-yorumlari`) is forbidden — when the needed link isn't on the page, say so (ADR-0009 honest absence), never invent it. Off-domain rehydrated targets carry the `OtherPage.off_domain` wire flag and require question-conditioned justification (anchor labels are attacker-controlled — ADR-0014 / D11). Enforced structurally at the `EXTRACT_ROUTER_V1` "LINKS IN THE ANSWER · HARD RULE" prompt clause + closed-set handle rehydration; the `answer` prose is rehydrated so a stray `{{n}}` becomes a real URL or is dropped, never leaked. **Prompt-source hazard:** marker refs must be written `{{{{n}}}}` so `.format()` emits the literal `{{n}}` the digest uses (a bare `{{n}}` collapses to `{n}` and leaks un-rehydrated — locked by `test_router_handle_markers_render_double_brace`).
- **Never withhold the body without leaving the index** (the first-class product invariant — ADR-0015). `query` withholds the page body by default (`include_content=False`) for token economy, so the caller — itself an AI agent that never sees the body — is blind to everything the answer didn't surface. a2web, having read the whole body, MUST leave a faithful cheap index of what it withheld: `also_here` (same-page content the answer skipped — query-grammar strings; recovering it is a cache-served same-URL re-query, no new fetch) and `other_pages` (pointers ELSEWHERE, kind-tagged `structural`|`drilldown`; each costs a NEW proxy fetch — be sparse). Dropping a load-bearing page region silently while presenting a distilled answer is the same class of harm as a silent miss (ADR-0009). Orthogonal to ADR-0012: the `answer` stays exhaustive over the *asked* set; the index covers the *un-asked remainder* and must never force a same-page re-fetch of data that was asked for. On a `listing`, `also_here` defers to `options` + `refinement_axes` and never restates a heading/option/axis.
- **Never assert a wall on evidence-free thinness, and never promote an unverified empty to `ok`** (the first-class product invariant — empty-vs-wall-discrimination). A retrieved thin 200 (`length_floor`) is AMBIGUOUS between a genuine empty result and an unfingerprinted wall — the discriminator is NOT in the body text (a regex or LLM read is equally blind to the walled-API fake-empty: an SPA shell that 200s and renders an authentic "0 results" while its data API was 403'd). So a thin page with no wall evidence is `thin_unverified` (`content_thin` WARNING, worded AGNOSTICALLY, body attached — never the critical klaxon, never a "most likely empty" claim); an empty-result marker only sharpens it to `empty_unverified` (still failed). Promotion to an `ok` "no results" answer requires the pure `is_confirmed_empty` conjunction: an independent BROWSER render also read empty (the browser wins the tier loop so jina never runs on a thin 200 — the browser is the second retrieval, and it watches subresources) + an HTTP tier returned a body + NO 4xx/challenge status + NO `subresource_blocks` evidence + NO hard-wall evidence anywhere + a search-shaped URL. The browser's `subresource_blocks` observation (a challenged XHR/fetch during render) is a `wall` — the fake-empty catch no text reader can make. The promoted empty is wire-only, NEVER cached (a wrongly-cached empty is a repeating silent miss). The design's center of gravity is the false-positive asymmetry: a false-positive wall over-warns (cheap); a false-positive empty is a confident silent miss (the ADR-0009 harm), so every ambiguous case errors toward the wall side. Sibling to ADR-0009/0015.
- **Never bill the metered Anthropic API in the dev/eval/bench loop** (the dev-loop invariant — ADR-0016). Expensive models only via subscription, never metered: `make bench` defaults `A2WEB_BENCH_PROVIDER=claude-code-sdk` and the provider is wrapped in the shelf's `anyllm.cost` guard (`with_cost_guard`), so every `complete()` asserts the resolved `(provider, model)` pair before the call — the two subscription backends (`claude-code-sdk` / `claude-code-cli`) allow any model, metered `anthropic-api` allows only Haiku-class, `openai-compatible` a conservative cheap allowlist, and any pair absent from the table raise `CostViolation` before spending (the $20 regression). Undetected subscription session → fail loud (`LLMNotAvailable`), never silent-fall-through to metered billing. Every run artifact stamps the `provider` + model used (the ADR-0016 "provenance" — provider stamping, NOT ADR-0014's URL provenance). Metered `anthropic-api` (cheap only) is explicit-opt-in via `A2WEB_BENCH_PROVIDER=anthropic-api`. **Provider ids are `anyllm.ProviderName` values** — the pre-rename spellings (`claude-code`, `anthropic`) are no longer valid and fail at resolution.
- Never retry the whole flow — retries live at one of 5 specific layers (connection / HTTP / proxy / tier / handler) with circuit breakers.
- **Never add an unbounded wait, and never bound it per-call-site.** Three
  layers, each enforced at ONE seam: `settings.request_timeout(default)` scales
  every per-request network bound (14 tier/handler constants — a SCALE, so the
  deliberate 5s:60s ratios survive); `llm_resource.TimeoutProvider` bounds every
  `complete()` at the provider seam (`anyllm` has none of its own); and
  `fetcher._within_budget` bounds the whole fetch by `min(hop timeout, remaining
  budget)` at the dispatch site. The per-site alternative was rejected for a
  reason that has now cost real defects twice: a bound re-implemented N times is
  the one missing from the N+1th. Pinned by
  `test_request_bounds_are_configurable.py`,
  `test_recursive_renderers_are_bounded.py`, and the deadline witnesses.
  `fetch_deadline_s`'s default is DERIVED from summing the hop constants (407s
  worst case → 480s) — re-derive it, don't nudge it, when a hop constant moves.
- **Never let a recursive renderer walk untrusted remote input unbounded.** A
  handler's comment/reply tree comes from the network; `hn._render_kid` had no
  cap and a thread nested past CPython's frame limit raised `RecursionError` out
  of the handler. Cap depth AND a shared node budget, because a branch that does
  not advance `depth` (a deleted-comment chain) defeats a depth cap alone. Then
  declare the truncation — a caller that cannot tell "the thread ends here" from
  "a2web stopped rendering" will read the first into the second (ADR-0009).
- Never add `print()` or sync I/O in async paths.
- Never reintroduce `tier_extras: dict[str, Any]` — add a typed field on `TierResult` instead.
- Never bypass `Lazy[T]` for heavy resources at the tool seam — `await components.browser_backend()` inside a tool body defeats lazy first-use for every caller. Pass the thunk down; unwrap once at the consuming phase. Pinned by `test_cold_start_laziness.py`.
- Never build the resource graph outside `components.build_components()`. A parallel root works right up until a resource is added to one and not the other — which is exactly what `bootstrap_state` cost in v0.22. Pass a `*_factory` override instead. Pinned by `test_one_composition_root.py`.
- Never pass `ctx` as a kwarg to a phase function or helper — `await a2web.log.info(...)` logs unconditionally and forwards to the MCP wire only under a dispatch scope. Phases don't need ctx.
- Never re-derive the TSV field list from model introspection. `wire._TSV_FIELDS` is literal on purpose: inference is how a field added to `AskResponse` silently changes the agent-facing wire. **This does NOT extend to a table's columns** — which fields become tables is a contract, which columns a table has is a property of the rows, and conflating the two is what let `_derive_columns` read only `rows[0]` and delete every key the first row happened to elide (2026-07-31).
- Never let `encode_envelope` resurrect a pruned field or re-encode an already-encoded string. Both were a2kit defects a2web filed and could not fix; owning the encoder is the whole point.
- **Never let a TSV table's columns come from one row.** Rows are heterogeneous BY CONSTRUCTION — model serializers elide fields at their default (`OperatorHint._omit_default_severity`, `PruneEmpty`) — so columns are the UNION of every row's keys, via the one shared `wire.encode_rows`. Reading `rows[0]` dropped the `critical` severity from `try_user_browser` whenever a quieter hint preceded it: ADR-0009's loudest signal reached the agent unmarked. `structured_content` was unaffected, which is why ~1350 field-presence assertions missed it — **when the agent's view is the point, assert on `call_text`, not `call_wire`.**
- **Never let a handler report retrieved-but-walled content as `ok`.** A challenge page extracts to prose perfectly well, so any handler running a generic extractor (`trafilatura.extract`, `extract_markdown`) on retrieved HTML must call `challenge_verdict` first. Pinned by `tests/architecture/test_handler_challenge_check.py`. Related: a wall marker that only matches below `LENGTH_FLOOR` is inert against a wordier interstitial — a marker that cannot appear in prose (verbatim vendor or site UI copy) belongs in the length-independent set.
- **Never let a degraded sub-fetch render as absent-at-source.** Retrieved-with-rows, retrieved-and-empty, and NOT-retrieved are three outcomes; collapsing the last two into `[]` made a rate-limited GitHub comments call indistinguishable from an issue with no comments. Mark the section and emit `section_unretrieved`. Failing the whole fetch is the wrong fix when the primary object was retrieved.
- Never let a CLI command return without unwinding its `ResourceScope`. `aiosqlite`'s worker thread is **non-daemon** in production (the daemon patch is test-only, by design — durability matters outside tests), so an unclosed scope parks that thread on an empty queue and `threading._shutdown()` never completes: the command prints correct output and then hangs forever. Not a leak — a hang. `cli._make_command` closes in a `finally`; a new command must too.
- Never allowlist a guard to expect nothing on the strength of an unverified claim. `test_terminal_hint_coherence` mapped `operator_error` to `frozenset({None})` commented "paid_auth_error hint emitted at the paid tier" — no such hint existed, and the entry would have stayed green through its deletion. An allowlist justified by something that does not exist is worse than no entry: it reads as a decision. Assert the hint is PRESENT, and that the code named is constructible.
- Never add a structural guard (AST walk, golden gate, contract table) without an assertion that it found something. A guard reporting "0 violations in 0 candidates" is indistinguishable from a passing one and reads as coverage while providing none. This has now failed twice for real: 30 of 32 architecture tests passed against an *empty source tree* (fixed by `_walk.walked_files(minimum=…)`), and `test_tools_return_pydantic_not_str` stayed green for the whole sunset while matching `@a2kit.read`, a decorator that no longer existed. Pair every walk with a floor, every golden set with a count, every accepted-delta table with a test that the delta is still real.
- **Never let a hand-written fixture be the oracle for whether a parser matches a
  live site.** It encodes the same assumption as the parser, authored by the same
  person at the same moment, so it cannot fail when that assumption is wrong — it
  can only confirm the parser agrees with itself. This cost two silently dead
  parsers behind five green tests (2026-07-28). Site-parse fixtures are CAPTURED
  and committed (`tests/fixtures/captured/`); synthetic fixtures are legitimate
  only where they control a variable (a count, a language) and must be written in
  the real markup shape so they cannot drift from what the parser accepts.
- Never treat a golden as proof of correctness. A golden proves a surface has not **changed**; it says nothing about whether it was right when captured. `list_tools.json` froze `~95%%` — a typo in the description every agent reads — perfectly, through seventeen rounds of wire review. It took rendering the same string through a different surface (`--help`) to see it.

## Backlog

`BACKLOG.md` tracks deferred work (Phase D workspace packaging, OSS swaps that turned out to be wrong fit, post-v0.1 features). CHANGELOG.md is the shipped record.

**Three files, one queue.** `BACKLOG.md` is the *queue* — one entry per open item, plus the TRACKS index that groups them and states the dependency order. `BACKLOG-CLOSED.md` holds shipped/resolved/superseded entries; move an item there rather than deleting it, because a closed entry often records the incident a surviving invariant exists to prevent. `docs/findings/` holds the *evidence* — measurements, `file:line` citations, verification notes — for entries whose backing is too long to sit in a queue. A backlog entry that needs more than a paragraph of proof should carry a pointer, not the proof.

## Ask First

- Before changing tool signatures (breaking for MCP clients).
- Before adding new top-level dependencies.
- Before changing the response envelope shape (breaking for parsers).
- Before introducing a new tier or handler that doesn't fit Strategy + Registry.
- Before reintroducing a `dict[str, Any]` bag on a typed pipeline object.
- Before promoting a new module to `packages/` — boundary types need design, and the seam may need conversion logic.
