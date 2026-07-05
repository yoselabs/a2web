# Tasks — json-endpoint-direct-routing

Test-first (BDD): write the failing test in each group before the code that
makes it pass. `make check` (lint + ty + test, coverage ≥85%) is the gate.

## 1. Shared JSON content-type predicate

- [x] 1.1 Test: `_is_json_content_type` returns True for `application/json`,
      `application/vnd.api+json`, `application/ld+json`, `text/json` (with charset
      params); False for `text/html`, `application/pdf`, `text/plain`, `""`, `None`.
- [x] 1.2 Add `_is_json_content_type(content_type: str | None) -> bool` in a shared
      location both the raw tier and the orchestrator import (avoid duplicating the
      predicate). Case-insensitive; tolerant of `; charset=` params.

## 2. Raw tier: JSON is `ok`, not a mismatch

- [x] 2.1 Test (extend `tests/.../raw` or `test_raw_tier`): 200 + `application/json`
      → `Verdict.ok`; 200 + `application/vnd.api+json` → `ok`; 200 + `application/pdf`
      → `content_type_mismatch` (unchanged); 200 + `text/html` → `ok`.
- [x] 2.2 Add the JSON carve-out to `_verdict_for_status` in `tiers/raw.py`,
      evaluated BEFORE the `"html" not in ct` mismatch check, using
      `_is_json_content_type`.

## 3. Response-body JSON parsing (package)

- [x] 3.1 Test (`tests/packages/.../json_in_script`): `parse_json_response` returns
      a `JsonPayload(source="generic")` for a JSON object and for a JSON array;
      returns `None` for non-JSON HTML and for truncated/malformed JSON (no raise).
- [x] 3.2 Add `parse_json_response(text: str) -> JsonPayload | None` in
      `packages/json_in_script.py` — owns `json.loads` for the response path; keeps
      the package domain-free. Verify `tests/architecture/test_json_loads_funnel.py`
      still passes (no new `json.loads` outside `json_in_script`).

## 4. Extract phase: synthesize JSON responses

- [x] 4.1 Test (`tests/.../fetcher` or capability): a `fetch` over a stub raw tier
      returning `application/json` with a `products` array yields synthesized rows in
      `content_md`, `status == ok`, and NO `jina` diagnostic step.
- [x] 4.2 Test: an unrecognized JSON shape (`{"weather": {...}}`) yields
      pretty-printed capped JSON in `content_md`, `status == ok`, not a
      `length_floor` failure.
- [x] 4.3 In `_phase_extract`, before the trafilatura path and when
      `pre_rendered_payload is None` and `_is_json_content_type(fc.content_type)`:
      parse via `parse_json_response` → `json_to_markdown_rows`; on empty synthesis
      fall back to `_json_text_fallback(text)` (pretty-print + length cap matching
      existing `domain.py` synthetic caps); install `fc.pre_rendered_payload`.
- [x] 4.4 On `parse_json_response` returning `None` (declared JSON but unparseable),
      fall through to existing handling — do not crash, do not fabricate content.

## 5. Length-floor exemption for JSON

- [x] 5.1 Test: a small complete JSON response below the length floor
      (`{"count": 42}`) is accepted (`status == ok`); an HTML SPA shell below the
      floor is still rejected (v0.29.0 guard intact — regression assertion).
- [x] 5.2 Implement the exemption keyed strictly on JSON content-type at the
      length-floor check (seam per design D5 — flag-to-gate or content-type check).
      Confirm no weakening of the HTML thin-shell floor.

## 6. Live verification + wiring

- [x] 6.1 Live check (network): `a2web web fetch-raw --url=<a real JSON API>` returns
      the synthesized/pretty JSON, not a `length_floor` failure. Record the endpoint
      + result in the change notes (do not commit secrets).
- [x] 6.2 Live check: `a2web web ask` over a JSON endpoint extracts a correct answer
      from the synthesized content.
- [x] 6.3 `make check` green (lint + ty + test, coverage ≥85%, all arch fitness
      tests including json-loads-funnel).

## 7. Housekeeping

- [x] 7.1 CHANGELOG.md entry under a new version section.
- [x] 7.2 Move the deferred Out-of-Scope items (requested-vs-actual URL transparency;
      Reddit 429→escalate-to-render; obstacle-drives-escalation reorder; generic
      SPA-search-host coverage) into `BACKLOG.md`.
- [ ] 7.3 Version bump + `make install-global` to propagate to the MCP binary.
