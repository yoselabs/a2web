# a2kit feedback — round 11 (2026-05-18)

Outgoing wishes for the next a2kit minor. Captured from a2web v0.8 (browser
cookies) implementation. Not in scope for the v0.8 change itself — these are
upstream framework asks.

## LDD severity levels

**Ask.** Add a `level: Literal["trace","debug","info","warn","error"]` field
to LDD event payloads (or surface it as a separate `emit(level=...)` arg),
and a sink-side filter so operators can route by severity. Sensible default
`info`.

**Why.** a2web v0.8 introduced two new events — `CookiesAttached` (routine
per-fetch attach) and `CookiesStale` (operator-actionable warning). Today
both flow through the same channel at the same volume. Production operators
who want to disable routine LDD chatter still need to see the staleness
warning surface in logs. Without levels they have to enable everything or
nothing.

This isn't a2web-only — `TierStarted` / `TierEnded` are debug-level signals
in production, while `TierHeartbeat` is info-ish only during slow tiers and
arguably trace-level the rest of the time.

**Shape we'd swap to in a single line.**

```python
# today
await a2kit.ldd.event(CookiesStale(...))

# after
await a2kit.ldd.event(CookiesStale(...), level="warn")
```

`app.ldd.add_sink(sink)` already exists. The natural sink-side filter:

```python
app.ldd.add_sink(otel_sink, min_level="warn")
```

**Compatibility.** Additive. Existing emit calls default to `info`. Existing
sinks default to `min_level="trace"` (no filtering) so they keep receiving
everything. No wire-format break — `level` is an optional payload field that
sinks can opt into reading.

**Why a2kit and not just structlog.** structlog records reach operators
through stderr/files, not the LDD wire. The LDD bridge to MCP progress and
OTel spans is what makes events visible to remote operators / agents that
observe a2web from the outside. Levels need to live where the bus lives.

## Per-tool selection at server start

**Ask.** A first-class way for an a2kit app to expose only a subset of its
registered tools at runtime — settable per-invocation (env var, CLI flag,
or both). Shape we'd swap to:

```bash
a2web serve --tools=ask              # only `ask` on the surface
a2web serve --tools=ask,fetch_raw    # default
```

Implementation could be a top-level Typer option intercepted before
`build_mcp_server(app)` / CLI registration, filtering the per-router
`tools` tuple by method name. The `visibility=` decorator kwarg already
covers compile-time tiering — this would complement it with a runtime
toggle.

**Why.** a2web v0.7 ships a workaround: an `ask_only: bool` field on
`AppSettings` plus a constructor-time filter in `WebRouter.__init__` that
rebuilds `self.tools`. It works, but it's strictly per-project — every
a2kit app that wants the same discipline (a2db read-only, a2atlassian
no-write, etc.) reinvents the boolean. Once a2kit absorbs proper
selection, a2web deletes the `ask_only` field with no migration pain.

**Compatibility.** Additive. No selection flag means "expose all tools"
(today's behavior).

## (No other items this round.)

Carrying over from v0.39 / `A2KIT_WISHES_DEFERRED.md`: `Lazy[T]` introspection
helpers + `app.tools()` name-override mechanism are still wished-for. Neither
is blocking v0.8.
