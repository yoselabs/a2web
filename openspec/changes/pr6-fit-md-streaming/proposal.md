## Why

Two missing pieces from the response-format spec land here. First, **fit_md**: today the envelope ships only `content_md`, which on a 50KB blog can be 8–12K tokens of which maybe 2–3K is signal. A denser pruned variant lets the calling agent stay below context limits without losing information. Second, **agent-visible progress**: today the agent sees the final envelope only, even though the orchestrator has already done the work in 5–8 distinguishable steps. MCP supports server→client `notifications/progress` natively; wiring those up turns "fetch took 2.3s and here's the result" into "raw → paywall (420ms); archive → ok (1.9s); extract → ok (35ms); fit → ok (12ms)" rendered live in the client.

The diagnostic event bus underneath both — an `anyio.MemoryObjectStream` that the orchestrator publishes step events to and that has pluggable sinks — is the right shape for PR7's OTel sink and PR4's NDJSON writer too (currently a direct call). Building it now means OTel and the playbook plug in without surgery.

## What Changes

- Add `src/a2web/extract/pruning_filter.py` — a Crawl4AI-style block-density pruning algorithm (NO crawl4ai dependency; ~80 LOC over selectolax). Walks the rendered HTML, scores each block by text-density and tag-class signals, drops below-threshold blocks, returns a denser markdown.
- Update `FetchResponse.fit_md` (already typed) so the orchestrator populates it after the gate pass — never on failed/blocked responses.
- Update `TokenCounts` population in the orchestrator: count chars (not tokens — adding tiktoken is overkill for v0.1; PR7 may revisit).
- Add `src/a2web/events/__init__.py`, `events/bus.py` — `EventBus` thin wrapper over `anyio.create_memory_object_stream()` with `publish(event)` and `subscribe()`.
- Define `Event` types as `@dataclass(slots=True)` in `events/types.py`: `TierStarted`, `TierEnded`, `StageStarted`, `StageEnded`. Each carries `t_ms` (offset from fetch start), `step`, optional `engine`/`host`/`proxy`, and a verdict for end events.
- Update `src/a2web/fetcher.py` to publish events at each phase boundary (tier start/end, extract, gate, cache write). The orchestrator is the only producer; sinks subscribe in parallel.
- Add `src/a2web/events/sinks.py` — `mcp_progress_sink` that takes an a2kit `ToolContext` and forwards events as `ctx.event` + `ctx.report_progress` calls. Ships in PR6.
- Update `WebRouter.fetch` to accept a `ctx: a2kit.ToolContext` kwarg (a2kit DI auto-injects it). The router builds an `EventBus`, attaches the MCP progress sink, and threads the bus into `fetcher.fetch(url, state=state, bus=bus)`.
- Update `fetcher.fetch` signature to optionally accept `bus: EventBus | None = None`. When None, the orchestrator runs as today (no events published). When present, every phase boundary publishes.
- Update the NDJSON log path: kept as direct call from the fetcher (the bus is for live streaming; the log writes one record at the end). PR7 may move log writes to a bus sink if it cleans up.
- Tests:
  - Pruning filter against blog fixture — `fit_md` is shorter than `content_md` and preserves headings + signal paragraphs.
  - `EventBus` produces events in the right order with correct `t_ms` offsets.
  - MCP progress sink renders one `ctx.event` + one `ctx.report_progress` per published event (mock `ToolContext`).
  - End-to-end: `WebRouter.fetch` invoked with a fake context — verify `ctx.event`/`ctx.report_progress` calls match the orchestrator's phase boundaries.
- README: add a short "Streaming progress" note referencing MCP `notifications/progress`.

## Capabilities

### New Capabilities

- `streaming-progress`: diagnostic event bus + MCP progress sink + `Event` types. The single producer (`fetcher.fetch`) publishes phase boundaries; pluggable sinks (MCP, future OTel/NDJSON) consume.
- `fit-md`: pruning-filter-based dense variant of `content_md`, populated only on successful fetches.

### Modified Capabilities

- `app-composition`: `WebRouter.fetch` gains a `ctx: ToolContext` kwarg (DI-injected, hidden from wire schema). Successful fetches now populate `fit_md` and `tokens`.
- `tier-pipeline`: orchestrator publishes events at phase boundaries when a `bus` is supplied; without one, behavior is unchanged.

## Impact

- **Code**: 5 new files (pruning_filter, events/bus, events/types, events/sinks, events/__init__), ~300–400 LOC.
- **Public surface**: `FetchResponse.fit_md` and `FetchResponse.tokens` become populated (typed since PR1; behavior change). `EventBus` is internal to a2web — sinks are the extension point.
- **Dependencies**: no new top-level deps. anyio is already declared.
- **Performance**: pruning filter adds ~10–30 ms per fetch on a 50 KB blog. Event publish/dispatch is sub-millisecond per event (8–10 events per fetch).
- **Streaming behavior**: MCP clients (Claude Code, Cursor) render `notifications/progress` inline. CLI invocations see no streaming (the events still publish; with no MCP context, the sink is a no-op).
- **Defer**: OTel sink lands in PR6.5 / PR7 (`opentelemetry-api` lazy import + env-gating). NDJSON write stays a direct call for PR6; may migrate to a bus sink later if it cleans up.
- **No autonomous-action playbook**: the table's high-value entries (paywall → archive, AMP rewrite, arxiv PDF → HTML) need the archive tier (PR7) or are URL-rewrite-only and don't yet have a clear injection point. Defer to PR7 where the archive tier provides the consumer.
