## Context

The tier pipeline is HTML-shaped: `raw` fetches, trafilatura extracts prose, the
quality gate accepts based on extracted length. JSON responses fall through the
cracks because the raw tier's content-type policy treats any non-HTML 2xx as a
`content_type_mismatch` — a non-ok verdict the planner escalates on. The next
tier is `jina` (`r.jina.ai/<url>`), an HTML-reader-as-a-service that mangles
JSON into a short markdown stub, tripping `length_floor`. Net: a valid JSON
endpoint returns a false failure.

The synthesis machinery to render JSON already exists and is proven:
`domain.json_to_markdown_rows(JsonPayload)` renders known shapes (Product,
Article, NewsArticle, ItemList, `products`/`items` arrays) to markdown
tables/records, and `_escalate_via_json` wires it into `_phase_extract`. Today
it only ever receives payloads pulled from `<script>` tags in HTML
(`json_in_script.extract_json_payloads`). A JSON *response body* has no script
tags, so this path never fires for it.

Two architecture constraints shape the fix:
- **`json.loads` is funnelled** (`tests/architecture/test_json_loads_funnel.py`).
  The `json_in_script` package already owns `json.loads` for the in-script path;
  response-body parsing must live there too, not in `fetcher.py` or `domain.py`.
- **`packages/` may not import `a2web.<domain>`.** `json_in_script` stays
  domain-free; it returns the package-owned `JsonPayload`, and `domain.py` does
  the markdown synthesis (as it does today).

## Goals / Non-Goals

**Goals:**
- A JSON response (`application/json` and siblings) reaches the caller as
  synthesized markdown, never routed through jina, never a false `length_floor`.
- Reuse the existing `json_to_markdown_rows` synthesis and `JsonPayload`
  boundary — no parallel renderer.
- An unrecognized-but-valid JSON shape still reaches the caller / `ask`
  extractor (never-silently-miss holds).
- No wire-envelope change, no new tool params.

**Non-Goals:**
- URL-shape pre-routing (`/api/`, `*.json`) — content-type after fetch is
  authoritative and catches endpoints without a `.json` suffix; a pre-hint adds
  a code path for no gain. Excluded.
- Requested-vs-actual fetch URL transparency — a separate envelope change
  (ask-first). Deferred to backlog.
- Rich per-API schema mapping — synthesis stays shape-driven with a JSON-text
  fallback; bespoke handlers (like HN's Algolia) remain the path for
  site-specific structure.

## Decisions

### D1 — Detect by response content-type, not URL shape

Trigger on the response `content-type` being JSON-family: `application/json`,
`application/<x>+json` (e.g. `application/vnd.api+json`, `application/ld+json`
as a bare response), `text/json`. This is authoritative (the server declares
it) and catches suffixless APIs. A `_is_json_content_type(ct)` predicate is the
single source of truth, used by both the raw tier and the extract phase.

*Alternative considered:* pre-route by URL shape so jina is skipped from the
start. Rejected — raw fetches everything anyway; catching it by content-type on
the response is simpler, needs no URL heuristics, and can't mis-fire on an HTML
page served from a `/api/` path.

### D2 — Raw tier: JSON → `Verdict.ok`, not `content_type_mismatch`

`_verdict_for_status(status, content_type)` gains a JSON carve-out **before** the
`"html" not in ct` mismatch check:

```python
if status == 404: return not_found
if status == 429: return rate_limited
if status >= 500: return connection_error
if status >= 400: return connection_error
if _is_json_content_type(content_type): return Verdict.ok   # NEW
if "html" not in content_type.lower(): return content_type_mismatch
return Verdict.ok
```

Raw wins on JSON, the loop stops, and `fc.content_type` (already threaded from
`TierResult.content_type`) carries the JSON type into `_phase_extract`. Non-JSON
mismatches (PDF, `text/plain`) are untouched — they still escalate.

*Alternative considered:* a new dedicated verdict (`json_response`). Rejected —
`ok` correctly means "this tier produced usable content"; the JSON-ness is
already carried by `content_type`, so extract keys off that. A new verdict would
ripple through the planner, decision log, and gate for no benefit.

### D3 — Extract phase branches on JSON content-type

In `_phase_extract`, before the trafilatura path, when
`_is_json_content_type(fc.content_type)` and `fc.pre_rendered_payload is None`:

1. `payload = json_in_script.parse_json_response(raw_text)` → a
   `JsonPayload(source="generic", data=...)` or `None` (parse failure → fall
   through to normal handling, which will now content-type-mismatch downstream —
   acceptable, it wasn't really JSON).
2. `md = domain.json_to_markdown_rows(payload)` — known shape → table/records.
3. If `md` is empty (unknown shape): `md = _json_text_fallback(raw_text)` —
   pretty-printed, length-capped JSON so it's readable and bounded.
4. Set `fc.pre_rendered_payload = Rendered(content_md=md, ...)` so the gate's
   content-type check is skipped (`is_pre_rendered → gate_content_type=None`)
   and trafilatura is bypassed.

This mirrors the JSON-in-script contract: synthesis first, and — new here — a
text fallback so a valid-but-unknown payload is never dropped.

*Alternative considered:* hand the raw JSON straight to the LLM extractor
without synthesis. Rejected for `fetch_raw` (no LLM on that path — it would
return nothing) and unnecessary for `ask` (synthesized/pretty JSON extracts
fine, and known shapes get cleaner tables). The fallback covers the long tail.

### D4 — `parse_json_response` lives in `json_in_script`, owns `json.loads`

New package function:

```python
def parse_json_response(text: str) -> JsonPayload | None:
    """Parse a whole-response JSON body into a generic JsonPayload.
    Returns None on parse failure (caller falls back). Owns json.loads
    for the response-body path, keeping the json-loads funnel intact."""
```

`source="generic"` reuses the existing `_framework_state_to_markdown` routing in
`json_to_markdown_rows` (which already handles `generic`), so a top-level
`{"products": [...]}` / `{"items": [...]}` / bare array renders with no new
domain code. Keeps `packages/` domain-free and the funnel test green.

### D5 — JSON bypasses the thin-shell length floor

A complete `{"count": 42}` is 12 chars but is a full answer, not a truncated
shell. When content is JSON-sourced, exempt it from `length_floor`. Cleanest
lever: the pre_rendered payload from a JSON response is tagged so the gate
treats a short JSON render as ok (the gate already length-exempts several
pre-rendered handler sources). Exact seam picked during implementation — either
a `from_json` flag threaded to the gate, or gating on `fc.content_type` being
JSON at the length-floor check. Scope note: this must NOT weaken the floor for
HTML SPA shells (the v0.29.0 confabulation guard) — the exemption keys strictly
on JSON content-type.

## Risks / Trade-offs

- **[A misconfigured API serving JSON as `text/html`]** → the content-type
  detector misses it and it takes the old HTML path. Accepted — conservative by
  design; a body-sniffing fallback (parse-as-JSON on a would-be mismatch) is a
  possible follow-up but risks HTML false positives, so it's out of scope here.
- **[A huge JSON response inflates `content_md`]** → the text fallback is
  length-capped (matching the existing synthetic-output caps in `domain.py`,
  e.g. the 50-row cap), so an unbounded API dump can't blow the envelope.
- **[Length-floor exemption leaks to SPA shells]** → mitigated by keying the
  exemption strictly on a JSON content-type, never on length or pre_rendered
  alone; HTML shells keep the full floor + the v0.29.0 escalate-to-render guard.
- **[`json.loads` on a hostile/huge body]** → same exposure the in-script path
  already has; the cap bounds rendered output, and parse failure is swallowed to
  `None`. No new attack surface beyond today's JSON-in-script parsing.

## Migration Plan

Pure additive behavior change on a previously-failing path — no envelope change,
no data migration, no config. Rollback = revert the change; endpoints return to
the old (failing) behavior. Ships in a normal version bump; `make install-global`
propagates to the MCP binary.

## Open Questions

- **D5 seam** — flag-threaded-to-gate vs content-type check at the floor. Decide
  during implementation; both satisfy the "JSON-only exemption" constraint.
- **`fetch_raw` over unknown JSON** — the text fallback returns pretty-printed
  JSON as `content_md`. Confirm this is the desired `fetch_raw` shape (vs
  returning the JSON verbatim in a code fence). Lean: pretty-printed, capped.
