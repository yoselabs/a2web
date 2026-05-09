## Context

PR1–5 shipped the static envelope and the dispatch pipeline. PR6 closes two response-format §3 gaps that are visible in every fetch. fit_md is a denser markdown for token-conscious agents; the streaming bus turns the fetch from a black-box latency into a live trace the client renders. The bus is also the right shape for OTel (PR6.5/PR7) and any future "watch this fetch" tooling — single producer, pluggable consumers, anyio under the hood.

## Goals / Non-Goals

**Goals:**
- A successful fetch populates `fit_md` with a denser markdown variant; `tokens` carries `full` + `fit` char counts.
- An MCP client invoking `fetch` receives `ctx.event` calls per phase boundary plus `ctx.report_progress` updates rendered live.
- The orchestrator emits events through one stream-based bus; sinks are independent.
- CLI invocation behavior is unchanged from PR5 (no MCP client → no streaming, but the bus is still wired with no-op sink).
- `make check` clean, coverage ≥85%.

**Non-Goals:**
- No OTel sink (PR6.5/PR7).
- No NDJSON migration (the writer's direct call from fetcher.py stays).
- No autonomous-action playbook (PR7).
- No tiktoken or model-specific tokenization for `tokens` — char counts only.
- No content-aware pruning beyond block-density; we don't classify "main article" vs "navigation" semantically. Selectolax + density heuristic is enough for v0.1.
- No image/media handling in fit_md.

## Decisions

### Decision 1: pruning filter is in-tree, ~80 LOC, no crawl4ai

`v0.1-design.md` calls out "Crawl4AI-style PruningContentFilter" but crawl4ai is a heavy dep with its own scraping stack, browser automation, and many transitive deps we don't need. The actual algorithm is simple: walk the DOM, score each block element (`<p>`, `<div>`, `<article>`, etc.) by text-density (text length / element count) and tag class (penalize `<nav>`, `<aside>`, `<footer>`), drop blocks below a threshold, render the survivors back to markdown.

```python
def prune_html(html: str, *, threshold: float = 0.5) -> str:
    """Score blocks, drop below-threshold, render survivors as markdown."""
```

The output goes through trafilatura's markdown serializer (already imported) — we DON'T re-implement HTML→markdown.

**Alternatives considered:**
- Depend on crawl4ai → 30+ transitive deps, including playwright. Rejected.
- LLM-based summarization for fit_md → not deterministic; cost; defeats the point. Rejected.
- Drop fit_md entirely → leaves a typed envelope field permanently empty. Rejected.

### Decision 2: events are dataclasses, bus is anyio MemoryObjectStream

```python
@dataclass(slots=True)
class TierStarted:
    t_ms: int
    step: str
    engine: str | None = None
    host: str | None = None
    proxy: str | None = None

@dataclass(slots=True)
class TierEnded:
    t_ms: int
    step: str
    engine: str | None
    verdict: Verdict
    dur_ms: int
    extra: dict[str, str | int] = field(default_factory=dict)
```

(plus `StageStarted`, `StageEnded` for non-tier phases like extract/gate/cache.)

The bus is `anyio.create_memory_object_stream(max_buffer_size=128)`. The orchestrator gets the send half; sinks get receive halves cloned via `clone()`. Backpressure is opt-in (default unlimited buffer for v0.1; bounded later).

**Alternatives considered:**
- A pub/sub registry with synchronous callbacks → couples sinks to producer's call stack. Rejected.
- A pydantic-modeled event hierarchy → overhead with no payoff (events are internal). Rejected.

### Decision 3: bus is opt-in via fetcher kwarg

`fetcher.fetch(url, *, state, bus: EventBus | None = None)`. When `bus is None`, the orchestrator skips event publishing (no overhead). When supplied, every phase boundary calls `bus.publish(event)`.

The router builds the bus per-call: one bus, one MCP sink subscribed, then passes to fetcher. PR7 will add OTel as a second sink subscribed by the same router.

**Alternatives considered:**
- Bus on AppState → process-wide; events from concurrent fetches would interleave on the same channel. Rejected.
- Always-on bus → per-fetch overhead even when no client is watching. The opt-in cost is one nullable kwarg. Rejected always-on.

### Decision 4: MCP progress sink renders both event + progress per phase

```python
async def mcp_progress_sink(ctx: ToolContext, recv: ObjectReceiveStream[Event]) -> None:
    async for event in recv:
        await ctx.event(event.__class__.__name__, **payload(event))
        if isinstance(event, (TierEnded, StageEnded)):
            await ctx.report_progress(progress=_estimate(event), message=_one_liner(event))
```

`ctx.event` carries the structured payload; `ctx.report_progress` renders a one-line message + numeric progress in the client UI. Progress estimation follows §3.5 of `v0.1-response-format.md` (after-handler 0.5, after-tier 0.7, after-extract 0.9, after-fit 1.0; reset to 0.3 on tier escalation).

### Decision 5: Tokens are char counts; tokenization deferred

`TokenCounts(full=len(content_md), fit=len(fit_md or ""))`. tiktoken adds a ~5 MB binary download and 100 ms cold-start cost per process for marginal benefit at v0.1 scale. Char counts give the agent enough signal ("fit is 3.5× denser") and stay zero-cost. PR7+ may add tiktoken behind an extra.

### Decision 6: ToolContext injection through a2kit DI

a2kit auto-injects `ctx: ToolContext` when a tool declares it as a kwarg. We add it to `WebRouter.fetch`. CLI invocation gets a `StderrToolContext`; MCP gets a `FastMCPContextAdapter` (per a2kit's antipattern #14). Both expose the same `ctx.event` / `ctx.report_progress` API, so the sink doesn't branch.

### Decision 7: NDJSON write stays direct, not bus-driven

Tempting to move `state.log_writer.write_record(...)` into a bus sink: one event per fetch end, one consumer. Rejected for PR6 because the log record is *derived from* `FetchResponse` (which is built post-fetch), not from individual events. Reconstructing the response shape from event stream is more work than the direct call costs.

If PR7 builds a "FetchCompleted(response)" event, the log writer becomes a bus sink trivially. Defer until then.

## Risks / Trade-offs

- **[Risk] Pruning filter discards real content on edge cases (single-paragraph articles, code-heavy posts)** → Mitigation: threshold defaults to 0.5; if `fit_md` ends up shorter than 30% of `content_md`, fall back to `content_md` and log a hint. Tunable per profile in PR9.
- **[Risk] Event bus adds latency on every fetch even when no client subscribes** → Mitigation: opt-in via `bus=None`. When the router builds a bus, the cost is ~50–100 µs of stream allocation + 8–10 stream sends, negligible against network/extract latency.
- **[Risk] MCP `notifications/progress` not rendered by all clients** → Mitigation: response-format spec already accepts this (§3 "agent UI will render either as a bar or as text-only"). The events are still useful for OTel later.
- **[Risk] CLI invocation gets sink overhead with no UI consumer** → Mitigation: `StderrToolContext.event/report_progress` writes to stderr per a2kit's contract. Useful when running interactively (`-v`); when piping, stderr is redirectable.
- **[Risk] Adding `ctx` kwarg to fetch tool may break MCP wire schema** → Mitigation: a2kit excludes DI-injected kwargs from the wire schema (verified in PR2). Tests pin this.
- **[Risk] Pruning filter relies on selectolax which may bail on malformed HTML** → Mitigation: wrap parse in try/except; on failure, return original markdown unchanged (fit_md = content_md, no extra tokens saved but no failure).

## Migration Plan

- No data migration. Existing cached HTML is re-extracted on hit; fit_md is computed at extract time and not cached separately (regenerated every fetch).
- Rollback: revert PR6 — `fit_md` returns to None on every response, `tokens` returns to None, MCP clients stop seeing per-phase progress. Cache and log paths unaffected.
