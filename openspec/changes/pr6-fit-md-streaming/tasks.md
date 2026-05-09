## 1. Pruning filter — `src/a2web/extract/pruning_filter.py`

- [x] 1.1 Implement `prune_html(html: str, *, threshold: float = 0.5) -> str`
- [x] 1.2 Score blocks by text-density and tag class (penalize nav/aside/footer/script/style)
- [x] 1.3 Drop below-threshold blocks; serialize survivors back to markdown via trafilatura
- [x] 1.4 Wrap in `async prune_markdown(html, url) -> str` (asyncio.to_thread chokepoint)
- [x] 1.5 Fallback: on parse error, return empty string; orchestrator handles fit_md=content_md fallback

## 2. Event bus — `src/a2web/events/`

- [x] 2.1 `events/__init__.py` re-exports `EventBus`, event types, sink helpers
- [x] 2.2 `events/types.py` — `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded` `@dataclass(slots=True)` at module scope
- [x] 2.3 `events/bus.py` — `EventBus` wrapping `anyio.create_memory_object_stream(128)`. `async publish(event)`, `subscribe()` returns cloned receiver
- [x] 2.4 `events/sinks.py` — `async mcp_progress_sink(ctx, recv)` consuming events; one ctx.event per event, ctx.report_progress on End events with adaptive `fmt_dur` message

## 3. Orchestrator updates — `src/a2web/fetcher.py`

- [x] 3.1 Add `bus: EventBus | None = None` kwarg to `fetch(...)`
- [x] 3.2 Publish `TierStarted` before each tier invocation; `TierEnded` after (when not no_match)
- [x] 3.3 Publish `StageStarted`/`StageEnded` around extract, gate, cache_write phases
- [x] 3.4 Compute progress estimate per response-format §3.5 (after-tier 0.7, after-extract 0.9, after-fit 1.0)
- [x] 3.5 After successful extract (non-handler path), call `prune_markdown` and populate `fit_md`. For handler results (pre_rendered set), `fit_md = content_md`. Failed/blocked → `fit_md = None`
- [x] 3.6 Populate `TokenCounts(full=len(content_md), fit=len(fit_md or ""))` on success; None on failure

## 4. Router update — `src/a2web/routers.py`

- [x] 4.1 Add `ctx: a2kit.ToolContext` kwarg to `WebRouter.fetch`
- [x] 4.2 Build EventBus per call; subscribe `mcp_progress_sink(ctx, ...)` via anyio TaskGroup
- [x] 4.3 Invoke orchestrator with `bus=bus`; close bus cleanly after fetch returns

## 5. Tests — `tests/test_pruning_filter.py`

- [x] 5.1 `prune_html` against blog fixture: result < 80% of input length
- [x] 5.2 `prune_html` preserves H1/H2 of well-formed article
- [x] 5.3 Malformed HTML returns empty string (caller handles fallback)

## 6. Tests — `tests/test_events.py`

- [x] 6.1 `EventBus` publish without subscribers does not raise
- [x] 6.2 Two subscribers receive the same event
- [x] 6.3 `TierEnded` carries verdict + dur_ms + extra
- [x] 6.4 `mcp_progress_sink` records one `ctx.event` per published event
- [x] 6.5 `mcp_progress_sink` records `ctx.report_progress` only on End events

## 7. Tests — fetcher integration

- [x] 7.1 Successful fetch populates `fit_md` (shorter than content_md)
- [x] 7.2 Successful fetch populates `tokens.full` and `tokens.fit`
- [x] 7.3 Block-page fetch leaves `fit_md=None` and `tokens=None`
- [x] 7.4 Pre-rendered handler fetch: `fit_md == content_md`
- [x] 7.5 With bus supplied: events arrive in chronological order, `t_ms` monotonic non-decreasing
- [x] 7.6 With bus=None: behavior matches PR5 baseline (no events published)

## 8. Tests — router integration

- [x] 8.1 Mock `ToolContext` records `ctx.event` calls per phase boundary
- [x] 8.2 `ctx` kwarg absent from MCP wire schema (snapshot the schema dict)

## 9. Quality gate

- [x] 9.1 `make lint` clean
- [x] 9.2 `make ty` clean
- [x] 9.3 `make test` green, coverage ≥85%
- [x] 9.4 `make check` clean

## 10. Smoke

- [x] 10.1 `uv run a2web web fetch --url=https://example.org/post` (with the blog fixture as a local fixture, or a real richer URL): envelope contains `fit_md` and `tokens`

## 11. Docs + commit

- [x] 11.1 Update `CLAUDE.md` — events package + pruning filter
- [x] 11.2 README "Streaming progress" note
- [x] 11.3 Single commit "PR6: fit_md + diagnostic event bus + MCP streaming"
- [x] 11.4 Hand off to PR7 (Jina + archive + Camoufox + proxy pool + lifespan + OTel sink + playbook)
