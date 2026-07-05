## Why

JSON API endpoints are silently mangled. When an agent fetches a JSON URL
(`https://api.example.com/data`, a REST endpoint, a `*.json` file), the raw
tier fetches it fine — 200 + `application/json` — but the raw tier's HTML-only
content policy maps that to `content_type_mismatch`, a non-ok verdict that
drives the planner to escalate to the **jina** tier. Jina wraps the URL as
`r.jina.ai/<url>` and reads the JSON *as a webpage*, producing garbage or a
short markdown stub that trips the length floor → a **false `length_floor`
failure on a perfectly good JSON response**. The raw tier already held the JSON
body; it threw it away.

This is Issue 3 from the 2026-07-05 Reddit/HN fetch feedback report — the one
issue v0.29.0 left untouched (it fixed HN's Algolia API only, via a bespoke
handler). The general case (any JSON endpoint) still fails. And the machinery
to fix it already exists: `domain.json_to_markdown_rows` + the
`_escalate_via_json` synthesis path render JSON to markdown today — they just
only ever run against `<script>` tags embedded in HTML, never against a JSON
*response* body.

## What Changes

- **Raw tier: a JSON response is content, not a mismatch.** A 2xx response with
  a JSON content-type (`application/json`, `application/*+json`, `text/json`)
  maps to `Verdict.ok` instead of `content_type_mismatch`. The raw tier wins,
  the JSON body reaches extraction, and jina is never consulted. Non-JSON
  mismatches (PDF, `text/plain`, octet-stream) keep today's escalation behavior.
- **Extract phase: JSON response bodies get synthesized.** When the won tier's
  `content_type` is JSON, `_phase_extract` parses the body as a JSON payload and
  runs it through the existing `json_to_markdown_rows` synthesis instead of
  trafilatura. Known shapes (Product / Article / ItemList / `products` /
  `items`) render as tables/records exactly as JSON-in-script does today.
- **Never-lose fallback for unknown JSON shapes.** When synthesis produces
  nothing (an arbitrary API shape `json_to_markdown_rows` doesn't recognize),
  the JSON text itself becomes `content_md` — pretty-printed and length-capped —
  so an unrecognized-but-valid JSON payload still reaches the caller and the
  `ask` LLM extractor, never a silent empty miss.
- **JSON payloads bypass the thin-shell length floor.** A small-but-complete
  JSON response (`{"count": 42}`) is a valid answer, not a truncated SPA shell;
  JSON-sourced content is exempt from the `length_floor` gate.
- **`json.loads` stays funnelled.** Response-body parsing lives in the
  `json_in_script` package (which already owns `json.loads` for the in-script
  path) as a new `parse_json_response`, keeping the architecture's
  json-loads-funnel invariant intact.

## Capabilities

### New Capabilities
<!-- none — this extends existing capabilities -->

### Modified Capabilities
- `raw-tier`: a 2xx JSON content-type maps to `Verdict.ok` (JSON is first-class
  content), not `content_type_mismatch`. Only non-JSON non-HTML bodies still
  mismatch.
- `json-extract`: the extractor SHALL also detect a JSON **response body** (not
  just JSON-in-script), emitting a `generic` `JsonPayload` for a parseable
  top-level JSON document.
- `tier-pipeline`: a JSON response wins at the raw tier and is synthesized to
  markdown in the extract phase; it is never routed through the jina HTML reader.
  Unknown-shape JSON falls back to the JSON text as content (never lost, never a
  false `length_floor`).

## Impact

- **Code**: `src/a2web/tiers/raw.py` (`_verdict_for_status` JSON carve-out);
  `src/a2web/packages/json_in_script.py` (+`parse_json_response`);
  `src/a2web/fetcher.py` (`_phase_extract` JSON-response branch + length-floor
  exemption); possibly `src/a2web/packages/block_detector.py` (gate content-type
  policy already skipped for pre-rendered — verify).
- **APIs / envelope**: none. `content_md` gains synthesized-JSON content on
  endpoints that previously failed; no wire-shape change, no new tool params.
- **Dependencies**: none.
- **Out of scope** (deferred to `BACKLOG.md`): surfacing requested-vs-actual
  fetch URL (envelope transparency — a separate, ask-first envelope change);
  Reddit `429`→escalate-to-render; the obstacle-drives-escalation pipeline
  reorder; generic SPA-search-host coverage beyond HN/Reddit.
