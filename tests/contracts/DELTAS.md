# Wire contract deltas

Every accepted change to the MCP wire surface, with its reason.

a2web is installed globally and wired into live Claude Code MCP configs. The
goldens under `wire/` are the bytes those agents actually receive. This file is
the record of every time those bytes were allowed to move, and why.

## How a change gets in here

The gate rejects an unexplained re-bless. To accept a deliberate change you must
name a reason, and the diff is appended here automatically under that slug:

```sh
A2WEB_ACCEPT_WIRE_DELTA=<reason-slug> uv run pytest tests/contracts/test_wire_contract.py
```

There is intentionally no blanket bless. `A2WEB_BLESS_CONTRACTS=1` still exists
for the older `test_contracts.py` snapshots, but it is too blunt for a substrate
migration: it would let a wholesale replacement silently redefine the wire and
still report green.

## The two gates this file serves

**1. The a2kit sunset — the gate is _zero deltas._**

The composition root, tool registration, response encoder and error envelope are
all being replaced. The whole point is that the substrate underneath changes and
the bytes on top do not. Any delta during that work is a regression until proven
otherwise, and proving otherwise means writing the reason here.

**2. The `lean-wire` adoption — the gate is _bounded, characterized deltas._**

Swapping the TSV codec is *expected* to change bytes, but only in cells
containing `"`, `\`, `\t`, `\n`, `\r`. So every delta from that work must carry
the slug `lean-wire-escaping` and touch only such cells. A delta from that change
landing anywhere else means the swap did more than re-encode — which is exactly
the distinction between "we adopted the fix" and "we broke something".

The `call/query_adversarial_cells` scenario exists to make this checkable: it
deliberately carries a quote-doubling cell, a backslash cell, and a cell with an
interior newline and tab.

## Accepted deltas

The goldens were first captured on 2026-07-22, immediately after
`hotfix-fastmcp-error-envelope` repaired the error envelope — capturing them
before that fix would have frozen `ToolResult.__init__() got an unexpected
keyword argument 'is_error'` with `structured_content: null` as the baseline.

### `notifications-capture-widened` — `notifications` (2026-07-22)

**No wire bytes moved. We started looking at more of them.**

The first capture of the notification stream recorded `{level, event}` per
frame. That left the entire `data.extra` payload — every field an operator or
an OTel exporter actually reads — ungated. The a2kit sunset's logging phase
renames the record-field carrier and re-homes the elapsed-ms key: it changes
exactly the part nothing was watching. A gate that cannot see the change it
exists to gate is decoration, so the capture was widened to the whole `data`
object before that phase began.

```diff
   {
-    "event": "TierStarted",
-    "level": "info"
+    "data": {
+      "extra": {
+        "a2kit_elapsed_ms": "<volatile>",
+        "engine": null,
+        "host": "example.org",
+        "proxy": null,
+        "step": "site_handler",
+        "t_ms": 0
+      },
+      "msg": "TierStarted"
+    },
+    "level": "info"
   },
```

Two things fell out of the widening, both worth recording:

1. **`a2kit_elapsed_ms` is not deterministic** — it came back `4`, `5`, `6` on
   consecutive frames. It reads `time.monotonic`, which `freeze_clocks` does
   not pin, and pinning it globally would freeze the event loop's own clock
   (asyncio resolves `loop.time()` through it), stopping every timeout in the
   process. So the key joined `_VOLATILE_KEYS`. The **key name stays visible**
   in the golden — a rename or a removal is still a diff; only the unpinnable
   integer is masked. Had the widening not happened before the sunset, this
   golden would have been committed flaky.
2. This entry replaces two mechanically-appended diffs from two `ACCEPT` runs
   (one before the volatility fix, one after) with a single honest record of
   the one logical change. The raw appended form is the default; collapsing a
   superseded pair is a deliberate edit, noted here so the ledger is not
   quietly hand-tuned.

### `a2web-owned-log-emitter` — `notifications` (2026-07-22)

**The entire logging substrate changed hands. One key left the wire.**

`sunset-a2kit-dependency` Phase 1 replaced `a2kit.log` with `a2web.log`: a2web's
own logger (`a2web`, `propagate=False`), its own record-field carrier
(`record.fields`, was `record.a2kit_fields`), its own MCP forward resolved
through `fastmcp.server.dependencies.get_context()` instead of a2kit's call
scope. Across all fifteen notification frames the diff below is the **only**
change — same events, same order, same count, same fields, same values.

The dropped key is `a2kit_elapsed_ms`: the call scope's wall-clock age, which
a2kit stamped onto every wire frame. It is not reproduced because it was
redundant. Every typed event already carries `t_ms` (offset from the start of
the fetch) and, on `*Ended`, `dur_ms` — the fields these events were designed
around. Reproducing `elapsed_ms` would have meant a2web maintaining a call-scope
contextvar purely to recompute a number two better-named fields already express.
Dropping it is the substitution being *smaller* than what it replaced, which is
the point of the exercise.

Two decisions worth naming, both of which this capture forced:

- **The wire stream is kept, deliberately** (Q2). The plan of record had the
  option of dropping log notifications during the sunset. Fifteen frames per
  `query` is a live progress feed for a call that can run tens of seconds; an
  agent watching a slow fetch sees tier escalation and extraction happen. That
  is a product surface, so it stays.
- **Emission stays `async`** (Q3), reversing the plan's "sync typed events".
  Async is load-bearing for exactly one reason: the wire forward is an inline
  `await ctx.log(...)`. A sync emitter cannot await, and a `logging.Handler`
  that schedules the forward as a task loses ordering and can outlive the call
  scope it belongs to. The goldens are what proved the async-ness was real
  rather than framework ceremony — without this capture the plan would have
  been executed as written and the stream would have degraded silently.

```diff
--- notifications.json (before)
+++ notifications.json (after)
@@ -2,7 +2,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "engine": null,
         "host": "example.org",
         "proxy": null,
@@ -16,7 +15,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "engine": null,
         "host": "example.org",
         "proxy": null,
@@ -30,7 +28,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "dur_ms": 0,
         "engine": "curl_cffi",
         "extra": {
@@ -49,7 +46,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "step": "extract",
         "t_ms": 0
       },
@@ -60,7 +56,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "step": "json_synth",
         "t_ms": 0
       },
@@ -71,7 +66,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "dur_ms": 0,
         "extra": {
           "outcome": "no_payloads",
@@ -88,7 +82,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "step": "record_synth",
         "t_ms": 0
       },
@@ -99,7 +92,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "dur_ms": 0,
         "extra": {
           "outcome": "no_records"
@@ -115,7 +107,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "dur_ms": 0,
         "extra": {
           "chars": 1919
@@ -131,7 +122,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "step": "gate",
         "t_ms": 0
       },
@@ -142,7 +132,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "dur_ms": 0,
         "extra": {},
         "step": "gate",
@@ -156,7 +145,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "step": "extract_answer",
         "t_ms": 0
       },
@@ -167,7 +155,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "dur_ms": 0,
         "extra": {
           "completion_tokens": 14,
@@ -185,7 +172,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "step": "cache_write",
         "t_ms": 0
       },
@@ -196,7 +182,6 @@
   {
     "data": {
       "extra": {
-        "a2kit_elapsed_ms": "<volatile>",
         "dur_ms": 0,
         "extra": {},
         "step": "cache_write",
```
