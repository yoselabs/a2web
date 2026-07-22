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

## `a2kit-spine-removed` — `list_tools`

**Two facts in one diff, both deliberate.**

1. **`_meta.a2kit` is gone.** It was a projection of a2kit's internal
   `A2KitMeta` — `router_slug`, `verb`, `surfaces`, `canonical_name_override`,
   `timeout_seconds`, `list_view`. Every key described the *framework's* model
   of the tool, not the tool. With the framework gone there is nothing to
   project, and no consumer read it: the names an agent calls
   (`query` / `fetch_raw`) are now the names in the source, so the
   `canonical_name_override` pins they were mirroring no longer exist either.
   `_meta.fastmcp.tags` is unchanged — it still carries `["read"]`, because
   the tools are still registered with `tags={"read"}`.

2. **One line of the `query` description changed**: "Emits typed events on
   a2kit's logging channel" → "on a2web's logging channel". The tool
   description is agent-visible wire, so this is a real contract byte and gets
   recorded rather than waved through. The sentence was simply false after
   Phase 1 moved emission onto the `a2web` logger.

Everything else in `list_tools` is byte-identical: both tool names, both
titles, all four annotation hints, every `inputSchema` property with its
description and default, the `required` list, and the generic
`{"additionalProperties": true, "type": "object"}` `outputSchema`. That last
one is worth noting — FastMCP produces it natively for a model carrying a
custom `model_serializer`, so it needed no reproduction.


```diff
--- list_tools.json (before)
+++ list_tools.json (after)
@@ -59,39 +59,6 @@
       "type": "object"
     },
     "meta": {
-      "a2kit": {
-        "annotations": {
-          "destructiveHint": false,
-          "idempotentHint": false,
-          "openWorldHint": true,
-          "readOnlyHint": true,
-          "title": "Fetch Raw Web Content (Fallback)"
-        },
-        "context_param_name": null,
-        "extras": {
-          "authorize": null,
-          "canonical_name_override": "fetch_raw",
-          "expose": [
-            "mcp",
-            "api",
-            "cli"
-          ],
-          "list_view": null,
-          "report_schema": null,
-          "router_slug": "web",
-          "surfaces": {
-            "api": "listed",
-            "cli": "listed",
-            "mcp": "listed"
-          },
-          "timeout_seconds": null
-        },
-        "tags": [
-          "read"
-        ],
-        "tool_name": "fetch_raw",
-        "verb": "read"
-      },
       "fastmcp": {
         "tags": [
           "read"
@@ -113,7 +80,7 @@
       "readOnlyHint": true,
       "title": "Query a Web Page"
     },
-    "description": "**Primary web-fetch tool. Use this for any question about a web page.**\n\nFetches the URL via the adaptive tier cascade (site handlers → raw\nHTTP with TLS impersonation → Jina reader → archive fallback →\nheadless browser as last resort), then runs the server-side LLM\nextractor over the content to answer your `query`. Returns the\nfocused answer in `answer`. Pass `include_content=True` to also get\nthe page markdown in `content_md` for grounding.\n\nPrefer this over `fetch_raw` for ~95%% of web reads. The\nextraction model is small and cheap (Haiku 4.5), so server-side\nanswers cost a fraction of streaming raw HTML into a larger model.\n\nCost asymmetry (ADR-0015): `also_here` indexes on-page content the\nanswer skipped — recovering it is a CHEAP re-query of the same URL\n(served from cache). `other_pages` points ELSEWHERE; each one costs a\nNEW fetch. Spend on the scarce resource — the fetch — accordingly.\n\nWhen the LLM is unavailable (no API key and no Claude Code OAuth\nsession), the fetch still succeeds, `answer` is None, and an operator\nhint records the reason — callers can fall back to reading\n`content_md` directly.\n\nEmits typed events on a2kit's logging channel during the fetch.",
+    "description": "**Primary web-fetch tool. Use this for any question about a web page.**\n\nFetches the URL via the adaptive tier cascade (site handlers → raw\nHTTP with TLS impersonation → Jina reader → archive fallback →\nheadless browser as last resort), then runs the server-side LLM\nextractor over the content to answer your `query`. Returns the\nfocused answer in `answer`. Pass `include_content=True` to also get\nthe page markdown in `content_md` for grounding.\n\nPrefer this over `fetch_raw` for ~95%% of web reads. The\nextraction model is small and cheap (Haiku 4.5), so server-side\nanswers cost a fraction of streaming raw HTML into a larger model.\n\nCost asymmetry (ADR-0015): `also_here` indexes on-page content the\nanswer skipped — recovering it is a CHEAP re-query of the same URL\n(served from cache). `other_pages` points ELSEWHERE; each one costs a\nNEW fetch. Spend on the scarce resource — the fetch — accordingly.\n\nWhen the LLM is unavailable (no API key and no Claude Code OAuth\nsession), the fetch still succeeds, `answer` is None, and an operator\nhint records the reason — callers can fall back to reading\n`content_md` directly.\n\nEmits typed events on a2web's logging channel during the fetch.",
     "execution": null,
     "icons": null,
     "inputSchema": {
@@ -193,39 +160,6 @@
       "type": "object"
     },
     "meta": {
-      "a2kit": {
-        "annotations": {
-          "destructiveHint": false,
-          "idempotentHint": false,
-          "openWorldHint": true,
-          "readOnlyHint": true,
-          "title": "Query a Web Page"
-        },
-        "context_param_name": null,
-        "extras": {
-          "authorize": null,
-          "canonical_name_override": "query",
-          "expose": [
-            "mcp",
-            "api",
-            "cli"
-          ],
-          "list_view": null,
-          "report_schema": null,
-          "router_slug": "web",
-          "surfaces": {
-            "api": "listed",
-            "cli": "listed",
-            "mcp": "listed"
-          },
-          "timeout_seconds": null
-        },
-        "tags": [
-          "read"
-        ],
-        "tool_name": "query",
-        "verb": "read"
-      },
       "fastmcp": {
         "tags": [
           "read"
```

## `other-pages-tsv-no-longer-destroyed` — `call/query_success_rich`

**This is a BUG FIX, not a migration artifact — the golden had frozen a
defect.**

`AskResponse._prune_wire` renders `other_pages` to a TSV string itself. a2kit's
`encode_envelope` then tested `isinstance(rows, (list, tuple))`, saw a `str`,
fell through to `[]`, and overwrote the finished TSV with the empty marker
`"\n"`. The machine channel (`structured_content`) carried the real rows the
whole time; only the text channel — the one the *agent* reads — was emptied.

So a caller was told "a2web looked for off-page pointers and found none" when
a2web had found them and encoded them one layer down. That is an ADR-0015
violation: withholding the body obliges a2web to leave the index.

`a2web.wire.encode_envelope` now leaves an already-encoded string alone and
only attaches the `_<field>_format` discriminator.

The defect was known and deliberately kept out of the goldens —
`test_populated_other_pages_survives_to_text_channel` was `xfail(strict=True)`
precisely because a golden captured against the broken encoder would have
frozen it, and a faithful port would then have passed the gate. Owning the
encoder is what let the fix land; the strict xfail is what forced it to be
noticed. That test is now un-xfailed and passing.


```diff
--- call/query_success_rich.json (before)
+++ call/query_success_rich.json (after)
@@ -1,7 +1,7 @@
 {
   "content": [
     {
-      "text": "{\"confidence\":\"high\",\"answer\":\"The page is about adaptive web fetching.\",\"title\":\"How adaptive web fetching saves agent tokens\",\"byline\":\"Jane Doe\",\"published\":\"2026-04-01\",\"other_pages\":\"\\n\",\"operator_hints\":\"\\n\",\"_operator_hints_format\":\"tsv\",\"headings\":\"\\n\",\"_headings_format\":\"tsv\",\"_other_pages_format\":\"tsv\",\"refinement_axes\":\"\\n\",\"_refinement_axes_format\":\"tsv\",\"options\":\"\\n\",\"_options_format\":\"tsv\"}",
+      "text": "{\"confidence\":\"high\",\"answer\":\"The page is about adaptive web fetching.\",\"title\":\"How adaptive web fetching saves agent tokens\",\"byline\":\"Jane Doe\",\"published\":\"2026-04-01\",\"other_pages\":\"url\\treason\\tkind\\nhttps://example.org/related\\trelated read\\tstructural\\n\",\"operator_hints\":\"\\n\",\"_operator_hints_format\":\"tsv\",\"headings\":\"\\n\",\"_headings_format\":\"tsv\",\"_other_pages_format\":\"tsv\",\"refinement_axes\":\"\\n\",\"_refinement_axes_format\":\"tsv\",\"options\":\"\\n\",\"_options_format\":\"tsv\"}",
       "type": "text"
     }
   ],
```

## `other-pages-tsv-no-longer-destroyed` — `call/query_adversarial_cells`

Same fix as above, on the adversarial-cell scenario: the populated
`other_pages` TSV (with its quoting-sensitive cells) now survives to the text
channel instead of being flattened to the empty marker.


```diff
--- call/query_adversarial_cells.json (before)
+++ call/query_adversarial_cells.json (after)
@@ -1,7 +1,7 @@
 {
   "content": [
     {
-      "text": "{\"confidence\":\"high\",\"answer\":\"The page is about adaptive web fetching.\",\"title\":\"How adaptive web fetching saves agent tokens\",\"byline\":\"Jane Doe\",\"published\":\"2026-04-01\",\"other_pages\":\"\\n\",\"operator_hints\":\"\\n\",\"_operator_hints_format\":\"tsv\",\"headings\":\"\\n\",\"_headings_format\":\"tsv\",\"_other_pages_format\":\"tsv\",\"refinement_axes\":\"\\n\",\"_refinement_axes_format\":\"tsv\",\"options\":\"\\n\",\"_options_format\":\"tsv\"}",
+      "text": "{\"confidence\":\"high\",\"answer\":\"The page is about adaptive web fetching.\",\"title\":\"How adaptive web fetching saves agent tokens\",\"byline\":\"Jane Doe\",\"published\":\"2026-04-01\",\"other_pages\":\"url\\treason\\tkind\\nhttps://example.org/p/hd600\\t\\\"the page calls this one \\\"\\\"the reference\\\"\\\" for the price band\\\"\\tstructural\\nhttps://example.org/p/driver\\tsee C:\\\\drivers\\\\readme.txt on the vendor page\\tstructural\\nhttps://example.org/p/spec\\t\\\"row 1:\\tmax SPL\\nrow 2:\\timpedance\\\"\\tstructural\\n\",\"operator_hints\":\"\\n\",\"_operator_hints_format\":\"tsv\",\"headings\":\"\\n\",\"_headings_format\":\"tsv\",\"_other_pages_format\":\"tsv\",\"refinement_axes\":\"\\n\",\"_refinement_axes_format\":\"tsv\",\"options\":\"\\n\",\"_options_format\":\"tsv\"}",
       "type": "text"
     }
   ],
```

## `envelope-presence-guard` — every success payload

**a2web's own round-17 bug report, fixed by owning the encoder.**

`docs/history/A2KIT_FEEDBACK_v0.49-envelope-leak.md` filed this against a2kit
on 2026-07-21 with the status line *"OPEN — one-line fix requested; **no a2web
workaround exists**"* — because a2web had no formatter seam: the encoding plan
was inferred at registration time from the return type, and a2web never
touched the formatter. The sunset gave a2web the seam, so the fix a2web was
waiting on simply shipped here.

a2kit's `encode_envelope` looped the **static** `tsv_fields` tuple and, for
every name, did `envelope.get(name)` → `None` → `[]` → `encode_tsv([])` →
`"\n"`, then re-inserted the key **plus** a `_<name>_format` sidecar. So each
conditional the model had deliberately pruned came back as *two* dead keys.
With five conditionals on `AskResponse`, a healthy answer carried ten.

The minimal success payload, before and after:

```
-  {"confidence":"medium","answer":"…","operator_hints":"\n",
-   "_operator_hints_format":"tsv","headings":"\n","_headings_format":"tsv",
-   "other_pages":"\n","_other_pages_format":"tsv","refinement_axes":"\n",
-   "_refinement_axes_format":"tsv","options":"\n","_options_format":"tsv"}
+  {"confidence":"medium","answer":"…"}
```

Eleven keys to two. This is the omit-empty discipline `_prune_wire` always
intended, finally reaching the channel the agent actually reads — the machine
channel (`structured_content`) was already correct, which is precisely why the
leak survived so long.

**Absence is the signal.** A caller reading the text channel now learns "no
off-page pointers" from `other_pages` being absent, exactly as it learns it
from `structured_content`. The two channels agree for the first time.

Populated conditionals are unaffected — they still render as real TSV with
their `_<field>_format` discriminator (see the sibling
`other-pages-tsv-no-longer-destroyed` entry, which fixed the case where they
were being *destroyed*).

Pinned by `tests/capabilities/ask_response/test_envelope_dispatch_encoder.py`,
both scenarios, which were `xfail(strict=True)` until this landed. The strict
marker is what forced the fix to be noticed rather than quietly skipped the
moment the constraint lifted.


## `percent-escape-typo` — `list_tools`

`~95%%` → `~95%` in both web tool descriptions.

A stray doubled percent, introduced in `797772f` (v0.10) and shipped in the
agent-facing tool description ever since. `%%` is the escape for a literal `%`
under `%`-formatting, but nothing in the path ever ran `%`-formatting over these
docstrings — so the escape had no consumer and the literal `%%` is simply what
every agent has read when deciding whether to call `query` or `fetch_raw`.

Found by the sunset's Phase 5 CLI capture: it rendered into `--help` as `95%%`,
which prompted checking the MCP wire, where it had been sitting unnoticed
through seventeen rounds of wire review. Worth recording as a lesson about what
goldens do and do not buy — `list_tools.json` contained this string the whole
time and froze it perfectly. A golden proves a surface has not *changed*; it
says nothing about whether the surface was right when captured.

```diff
--- list_tools.json (before)
+++ list_tools.json (after)
@@ -7,7 +7,7 @@
       "readOnlyHint": true,
       "title": "Fetch Raw Web Content (Fallback)"
     },
-    "description": "**Fallback only — prefer `query` for ~95%% of web reads.**\n\nReturns the page's markdown content with no server-side LLM\nextraction. Use only when:\n\n1. You need the full structural content (link graphs, repeated\n   rows for scraping, tables to transform).\n2. A previous `query` call returned `answer: null` with an\n   `llm_unavailable` operator hint and you need the page text\n   to answer your own question.\n3. `query`'s answer is suspect and you need to verify against\n   source.\n\nDo not default to this tool — `query` is cheaper end-to-end because\nthe server-side Haiku extractor is much smaller than the model\ncalling this tool. Same tier cascade, same diagnostics, just\nwithout the extraction phase.",
+    "description": "**Fallback only — prefer `query` for ~95% of web reads.**\n\nReturns the page's markdown content with no server-side LLM\nextraction. Use only when:\n\n1. You need the full structural content (link graphs, repeated\n   rows for scraping, tables to transform).\n2. A previous `query` call returned `answer: null` with an\n   `llm_unavailable` operator hint and you need the page text\n   to answer your own question.\n3. `query`'s answer is suspect and you need to verify against\n   source.\n\nDo not default to this tool — `query` is cheaper end-to-end because\nthe server-side Haiku extractor is much smaller than the model\ncalling this tool. Same tier cascade, same diagnostics, just\nwithout the extraction phase.",
     "execution": null,
     "icons": null,
     "inputSchema": {
@@ -80,7 +80,7 @@
       "readOnlyHint": true,
       "title": "Query a Web Page"
     },
-    "description": "**Primary web-fetch tool. Use this for any question about a web page.**\n\nFetches the URL via the adaptive tier cascade (site handlers → raw\nHTTP with TLS impersonation → Jina reader → archive fallback →\nheadless browser as last resort), then runs the server-side LLM\nextractor over the content to answer your `query`. Returns the\nfocused answer in `answer`. Pass `include_content=True` to also get\nthe page markdown in `content_md` for grounding.\n\nPrefer this over `fetch_raw` for ~95%% of web reads. The\nextraction model is small and cheap (Haiku 4.5), so server-side\nanswers cost a fraction of streaming raw HTML into a larger model.\n\nCost asymmetry (ADR-0015): `also_here` indexes on-page content the\nanswer skipped — recovering it is a CHEAP re-query of the same URL\n(served from cache). `other_pages` points ELSEWHERE; each one costs a\nNEW fetch. Spend on the scarce resource — the fetch — accordingly.\n\nWhen the LLM is unavailable (no API key and no Claude Code OAuth\nsession), the fetch still succeeds, `answer` is None, and an operator\nhint records the reason — callers can fall back to reading\n`content_md` directly.\n\nEmits typed events on a2web's logging channel during the fetch.",
+    "description": "**Primary web-fetch tool. Use this for any question about a web page.**\n\nFetches the URL via the adaptive tier cascade (site handlers → raw\nHTTP with TLS impersonation → Jina reader → archive fallback →\nheadless browser as last resort), then runs the server-side LLM\nextractor over the content to answer your `query`. Returns the\nfocused answer in `answer`. Pass `include_content=True` to also get\nthe page markdown in `content_md` for grounding.\n\nPrefer this over `fetch_raw` for ~95% of web reads. The\nextraction model is small and cheap (Haiku 4.5), so server-side\nanswers cost a fraction of streaming raw HTML into a larger model.\n\nCost asymmetry (ADR-0015): `also_here` indexes on-page content the\nanswer skipped — recovering it is a CHEAP re-query of the same URL\n(served from cache). `other_pages` points ELSEWHERE; each one costs a\nNEW fetch. Spend on the scarce resource — the fetch — accordingly.\n\nWhen the LLM is unavailable (no API key and no Claude Code OAuth\nsession), the fetch still succeeds, `answer` is None, and an operator\nhint records the reason — callers can fall back to reading\n`content_md` directly.\n\nEmits typed events on a2web's logging channel during the fetch.",
     "execution": null,
     "icons": null,
     "inputSchema": {
```

## `tsv-row-shape-guard` — `call/fetch_raw_include_links`

```diff
--- call/fetch_raw_include_links.json (before)
+++ call/fetch_raw_include_links.json (after)
@@ -1,7 +1,7 @@
 {
   "content": [
     {
-      "text": "{\"confidence\":\"high\",\"title\":\"How adaptive web fetching saves agent tokens\",\"byline\":\"Jane Doe\",\"published\":\"2026-04-01\",\"meta\":{\"og.type\":\"article\",\"og.title\":\"How adaptive web fetching saves agent tokens\",\"og.image\":\"https://example.org/cover.jpg\",\"og.url\":\"https://example.org/post/adaptive-fetching\",\"twitter.card\":\"summary_large_image\",\"twitter.site\":\"@example\",\"jsonld[0].@context\":\"https://schema.org\",\"jsonld[0].@type\":\"Article\",\"jsonld[0].headline\":\"How adaptive web fetching saves agent tokens\",\"jsonld[0].datePublished\":\"2026-04-01T09:00:00Z\",\"jsonld[0].articleSection\":\"Engineering\"},\"links\":\"anchor\\thref\\trole\\nthe cascade deep dive\\thttps://example.org/cascade-deep-dive\\tprimary\\nquality gate internals\\thttps://example.org/quality-gate\\tprimary\\ngithub.com/example/a2web\\thttps://github.com/example/a2web\\tprimary\\n\",\"headings\":[[1,\"How adaptive web fetching saves agent tokens\"],[2,\"Why one fetch matters\"],[2,\"The cascade in three layers\"],[2,\"Quality gates do the heavy lifting\"],[2,\"Why the cache is profile-scoped\"]],\"content_md\":\"# How adaptive web fetching saves agent tokens\\n\\n## Why one fetch matters\\n\\nWhen AI agents fetch URLs naively, they pay for every redirect, every block page, every JavaScript challenge that returns nothing useful. The agent's context window fills with garbage HTML or worse, with their own follow-up retries that double the token cost without recovering the missing content. Adaptive fetching means the calling agent makes one decision: *get me the best content available at this URL*, and lets the fetch service handle every routing question.\\n\\n## The cascade in three layers\\n\\nThe first layer is a per-domain handler — Reddit, HN, Wikipedia, GitHub each have their own canonical APIs that return cleaner data faster than scraping the rendered page. The second layer is a TLS-impersonating raw fetch with a real browser fingerprint; this carries roughly 80 percent of the long tail. The third layer is escalation: archive fallbacks for paywalled origins, headless browsers for genuine JavaScript challenges, and paid services for the small set of sites that defeat everything else.\\n\\n## Quality gates do the heavy lifting\\n\\nThe crucial machinery isn't the fetch itself — it's the post-fetch quality gate that decides whether the result is worth caching. Block pages, anti-bot interstitials, and \\\"are you human\\\" challenges all carry distinctive fingerprints. A regex set plus a length floor catches most of them; an Anubis script-src marker catches the rest. Anything that fails the gate gets surfaced as a structured diagnostic and never enters the cache to corrupt later reads.\\n\\n## Why the cache is profile-scoped\\n\\nA single URL can return different content depending on the user-agent, the proxy, the geographic region, and a half-dozen other request-shape variables. Caching by URL alone gives wrong answers as soon as you switch profiles. Hashing the relevant settings into a profile key keeps the cache safe across stealth toggles, paid-tier escalations, and per-host route rules. The cost is a few bytes per row; the benefit is correctness.\\n\\nRead more about the cascade deep dive or the quality gate internals. The full repo lives at github.com/example/a2web.\\n\"}",
+      "text": "{\"confidence\":\"high\",\"title\":\"How adaptive web fetching saves agent tokens\",\"byline\":\"Jane Doe\",\"published\":\"2026-04-01\",\"meta\":{\"og.type\":\"article\",\"og.title\":\"How adaptive web fetching saves agent tokens\",\"og.image\":\"https://example.org/cover.jpg\",\"og.url\":\"https://example.org/post/adaptive-fetching\",\"twitter.card\":\"summary_large_image\",\"twitter.site\":\"@example\",\"jsonld[0].@context\":\"https://schema.org\",\"jsonld[0].@type\":\"Article\",\"jsonld[0].headline\":\"How adaptive web fetching saves agent tokens\",\"jsonld[0].datePublished\":\"2026-04-01T09:00:00Z\",\"jsonld[0].articleSection\":\"Engineering\"},\"links\":\"anchor\\thref\\trole\\nthe cascade deep dive\\thttps://example.org/cascade-deep-dive\\tprimary\\nquality gate internals\\thttps://example.org/quality-gate\\tprimary\\ngithub.com/example/a2web\\thttps://github.com/example/a2web\\tprimary\\n\",\"headings\":[[1,\"How adaptive web fetching saves agent tokens\"],[2,\"Why one fetch matters\"],[2,\"The cascade in three layers\"],[2,\"Quality gates do the heavy lifting\"],[2,\"Why the cache is profile-scoped\"]],\"content_md\":\"# How adaptive web fetching saves agent tokens\\n\\n## Why one fetch matters\\n\\nWhen AI agents fetch URLs naively, they pay for every redirect, every block page, every JavaScript challenge that returns nothing useful. The agent's context window fills with garbage HTML or worse, with their own follow-up retries that double the token cost without recovering the missing content. Adaptive fetching means the calling agent makes one decision: *get me the best content available at this URL*, and lets the fetch service handle every routing question.\\n\\n## The cascade in three layers\\n\\nThe first layer is a per-domain handler — Reddit, HN, Wikipedia, GitHub each have their own canonical APIs that return cleaner data faster than scraping the rendered page. The second layer is a TLS-impersonating raw fetch with a real browser fingerprint; this carries roughly 80 percent of the long tail. The third layer is escalation: archive fallbacks for paywalled origins, headless browsers for genuine JavaScript challenges, and paid services for the small set of sites that defeat everything else.\\n\\n## Quality gates do the heavy lifting\\n\\nThe crucial machinery isn't the fetch itself — it's the post-fetch quality gate that decides whether the result is worth caching. Block pages, anti-bot interstitials, and \\\"are you human\\\" challenges all carry distinctive fingerprints. A regex set plus a length floor catches most of them; an Anubis script-src marker catches the rest. Anything that fails the gate gets surfaced as a structured diagnostic and never enters the cache to corrupt later reads.\\n\\n## Why the cache is profile-scoped\\n\\nA single URL can return different content depending on the user-agent, the proxy, the geographic region, and a half-dozen other request-shape variables. Caching by URL alone gives wrong answers as soon as you switch profiles. Hashing the relevant settings into a profile key keeps the cache safe across stealth toggles, paid-tier escalations, and per-host route rules. The cost is a few bytes per row; the benefit is correctness.\\n\\nRead more about the cascade deep dive or the quality gate internals. The full repo lives at github.com/example/a2web.\\n\",\"_links_format\":\"tsv\"}",
       "type": "text"
     }
   ],
```
