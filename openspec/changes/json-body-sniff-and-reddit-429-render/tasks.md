# Tasks — json-body-sniff-and-reddit-429-render

Test-first (BDD). `make check` (lint + ty + test, coverage ≥85%) is the gate.

## 1. JSON body-sniff (package)

- [x] 1.1 Test (`tests/packages/.../json_in_script`): `sniff_json_body` returns
      True for JSON object/array bytes (leading whitespace tolerated); False for
      HTML, a binary/PDF prefix, plain text, and empty.
- [x] 1.2 Add `sniff_json_body(body: bytes) -> bool` to
      `packages/json_in_script.py` — prefix-guarded on `{`/`[` within a bounded
      window (no full-body `lstrip`); delegates the parse to `parse_json_response`
      (funnel intact).

## 2. Raw tier: content-type recovery

- [x] 2.1 Test (`test_raw_tier`): a 200 `text/html` response whose body parses as
      JSON → `Verdict.ok` + `content_type == "application/json"`; a genuine
      `text/html` HTML body → unchanged (`text/html`).
- [x] 2.2 In `tiers/raw.py`, after the 2xx verdict, sniff the body when the
      content-type is not already JSON; on a JSON parse, normalize the returned
      `content_type` to `application/json` and set `Verdict.ok`.

## 3. Reddit search/listing 429 → escalate-to-render

- [x] 3.1 Test (`test_handlers`): a `429` on a `/search/` and on a listing RSS URL
      → `escalate_to_render` (verdict `block_page_detected`); a `429` on a
      comments/permalink URL → `rate_limited` (unchanged, regression assertion).
- [x] 3.2 In `handlers/reddit.py`, route a search/listing `429` (backoff
      exhausted) to `_render_escalation_signal(url)`; keep thread/permalink `429`
      on `empty_result(url, Verdict.rate_limited)`.

## 4. Gate + wiring

- [x] 4.1 `make check` green (lint + ty + test, coverage ≥85%, all arch fitness
      including json-loads-funnel).
- [x] 4.2 CHANGELOG.md entry under a new version section.
- [ ] 4.3 Version bump + `make install-global` to propagate to the MCP binary.
