# a2kit feedback — round 3

From: a2web (currently planning migration to `a2kit v0.25`)
Audience: a2kit dev
Context: rounds 1 + 2 (the previous contents of this file) were addressed in v0.24 + v0.25. Thank you — the lifecycle + singleton + testing.client triple is exactly what we asked for. `OPERATIONAL_CONTRACTS.md` is the right move; we now know what to trust and what to handle ourselves.

This round is **one question + three wishes**. None blocks the migration.

---

## Question — how does an external sink subscribe to LDD emissions?

### Context

a2web emits structured events from its fetch orchestrator (tier started, tier ended, gate evaluated, cache write, etc.). Today we run our own anyio `MemoryObjectStream` bus with two subscribers:

```
   orchestrator ──► EventBus ──┬──► mcp_progress_sink ──► ctx.event + ctx.report_progress
                               └──► otel_sink          ──► OpenTelemetry spans
```

v0.25's typed event registry + free-function `a2kit.ldd.event/report` lets us drop the `mcp_progress_sink` half — we just emit via a2kit and the wire side is handled. **But the OTel side loses its subscription point.** That sink needs to see every event the orchestrator emits, regardless of transport, regardless of MCP wire format.

### The question

How does an external in-process consumer (OTel exporter, custom NDJSON sink, anything that wants to observe ldd emissions for its own purposes) subscribe to the emission stream of a given `App`?

Three shapes we can imagine:

```python
# (a) Sink registration on the event registry
app.ldd.events.add_sink(my_sink)

# (b) Callback / hook
app.ldd.on_emit(lambda event, ctx: ...)

# (c) Async iterator
async for evt in app.ldd.events.stream():
    ...
```

If one of these exists and we missed it, just point us at the docs. If none exists and the answer is "double-emit in the orchestrator (call `a2kit.ldd.event(...)` AND push to your own channel)," that works too — we just want to confirm before we refactor `events/sinks.py`.

### Why we'd prefer a first-class subscription API

If a2kit's emission chain is the canonical place tools advertise milestones, then **every observability tool** (OTel, Datadog, Honeycomb, Prometheus push gateway, plain audit logs) will want to consume it. Forcing each app to maintain a parallel "double-emit" channel means every a2kit-using project re-invents the same fan-out.

Counter-argument we'd accept: "Use FastMCP middleware to observe the wire-level notifications; OTel is wire concern, not domain concern." If that's the recommendation, document it and we're happy.

### Impact on a2web

- If subscription API exists → we delete `EventBus`, `mcp_progress_sink`, `otel_sink` becomes ~15 LOC, all events flow through a2kit's chain.
- If no subscription API and double-emit is the answer → orchestrator emits `await event(ctx, ...)` AND `await otel_channel.send(...)`; we keep a tiny ~20 LOC internal channel for OTel only. Manageable but a duplication smell.

A one-line answer unblocks us.

---

## Wish 1 — `@a2kit.read(timeout="60s")` as a decorator kwarg

`OPERATIONAL_CONTRACTS.md` Q2 documents the current contract: no built-in timeout, use `anyio.fail_after(seconds)` inside the tool body. Reasonable default. But:

- Every network-facing tool wants this. Web fetch wants 60s, DB query wants 5s, a quick API call wants 2s.
- Wrapping every tool body in `async with anyio.fail_after(...):` is repetitive.
- A decorator kwarg keeps the budget visible at the tool's signature site (where someone reading `list_tools` output cares most about it).
- The implementation is trivial — the dispatcher wraps the body in `fail_after` before calling.

Proposed:

```python
@a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page", timeout="60s")
async def fetch(*, url: str) -> FetchResponse:
    ...
```

Semantics:
- `timeout=None` (default) — no enforcement, tool body handles its own budgets (current behavior).
- `timeout="60s"` or `timeout=60.0` — dispatcher wraps body in `anyio.fail_after(60)`. On timeout, a `TimeoutError` bubbles per Q1/Q5 conventions.
- The CLI / MCP wire surfaces the configured timeout in the tool description / annotations so agents can decide on retry policy.

Cost to a2kit: probably ~30 LOC + one test. Cost to every a2kit consumer that re-derives the same wrap: scales with adoption.

Not urgent. We'll use `anyio.fail_after` until you ship it (or decide not to).

---

## Wish 2 — Streaming response for large outputs (Q6)

`OPERATIONAL_CONTRACTS.md` doesn't cover Q6. Our `FetchResponse.content_md` can be 100KB+ for big articles. Today the agent waits for the entire body before any of it is visible. MCP supports chunked / streaming responses for this exact case.

Two API shapes we'd like:

```python
# (a) Yield from the tool body — async iterator
@a2kit.read(streaming=True)
async def fetch(*, url: str) -> AsyncIterator[FetchChunk]:
    async for chunk in fetcher.stream_fetch(url):
        yield chunk

# (b) Explicit chunk emit via ctx, terminal return for final shape
@a2kit.read(streaming=True)
async def fetch(*, url: str, ctx: a2kit.ToolContext) -> FetchResponse:
    async for chunk in fetcher.stream_fetch(url):
        await ctx.chunk(chunk.markdown)
    return final_response
```

Either works. The (a) form composes better with type-driven format routing; the (b) form mirrors how `event` / `report` already work.

This is genuinely a v0.x scope concern — leaving it un-addressed is fine. Filing for the backlog so it's not lost.

---

## Wish 3 — Documentation lead with imperative composition, not fluent

You shipped imperative APIs in v0.24 (`@app.on_startup`, `@app.singleton`, `@app.health_check`) — thank you. But the README's leading example is still:

```python
app = (
    a2kit.App("tracker")
    .add_router(ProjectsRouter())
    .add_router(TasksRouter())
    .provide(TrackerStore)                   # class-as-factory; container reads __init__
    .add_cli(connections_cli(TrackerConn))   # auto-installs TrackerConn provider
)
```

This still has the two problems we raised in round 1 item 11:

1. **Hidden side effect.** `.add_cli(connections_cli(TrackerConn))` "auto-installs TrackerConn provider" — the comment admits the chain does two unrelated things.
2. **Class-as-factory introspection.** `.provide(TrackerStore)` reading `__init__` is implicit container behavior; signature drift breaks registration at runtime, not at composition time.

New contributors copying the docs will copy this pattern, including its smells.

The wish (small): **make the imperative form the canonical example in the README**, and call out the fluent form as a shorthand:

```python
# Canonical:
app = a2kit.App("tracker", health_tool=True)
app.add_router(ProjectsRouter())
app.add_router(TasksRouter())
app.provide(TrackerStore, factory=lambda conn: TrackerStore(conn))  # explicit
app.add_cli(connections_cli(TrackerConn))
app.provide(TrackerConn)  # explicit, no longer hidden in add_cli

# Shorthand (chained, when it fits in 3-4 lines):
app = a2kit.App("tracker").add_router(R()).provide(S)
```

Documentation-only change. Reframes the patterns the ecosystem will copy.

Bonus ask: if `.add_cli(connections_cli(X))` continues to auto-install providers, **document the side effect on the method itself**, not in adjacent comments. The chain-call signature is the contract; what it does shouldn't depend on a `# this also …` comment.

---

## What we're NOT asking for this round

To save you reading: we explicitly do not need the following, even though we discussed them earlier:

- Per-tool retry policy (we own retry semantics at the tier layer).
- Built-in caching layer (hishel works).
- Built-in proxy support (out of scope, app concern).
- Auto-reload (Q4) — `watchexec` is the documented answer; that's fine.
- Cancellation cleanup hooks — Q1's "tool author's responsibility" is the right contract.

---

## Migration status

Migrating a2web v0.23.0 → v0.25.0 imminently. Expected impact: **~190 LOC dropped from a2web** (lifecycle + singleton + testing.client + tool annotations + docstring rewrites + EventBus deletion modulo the question above). Plus additional ~510 LOC dropped in a separate phase (hishel + stdlib RotatingFileHandler + trafilatura bundled metadata + purgatory for proxy quarantine).

We'll send a "post-migration debrief" if anything turns up that's not in `OPERATIONAL_CONTRACTS.md`.

Thanks again for the v0.24 + v0.25 turnaround. The shape is right.
