## 1. Redaction-authority fix (design.md D7 — blocks the content work below)

- [x] 1.1 Trace every place a URL/query can reach the outgoing feedback payload today — `OperatorHint.message` interpolation in `hints.py`'s factories is the gap; confirm there are no others (`fc.inputs.ask`, `fc.url`, `fc.final_url` already correctly gated)
- [x] 1.2 Make `A2WEB_FEEDBACK_INCLUDE_CONTENT` authoritative over the hint message text: when off, strip/replace URL-shaped substrings from `hint.message` before it goes into the payload body; when on, send it unmodified — done via exact substring replacement of `fc.inputs.requested_url`/`fc.url`/`fc.final_url` (`_redact_known_urls`), not regex, since the exact URL strings are already known
- [x] 1.3 Unit tests: default (flag off) → hint message with an embedded URL comes out with the URL removed/masked; flag on → message passes through unmodified
- [x] 1.4 ~~Message the homelab session to relax the collector-side blanket `body` scrub~~ — **declined, correctly, and no longer needed**: the gateway's attribute redaction is name-anchored, so `requested_url`/`final_url` (§2) already arrive intact with zero gateway change; the scrub also protects a different property (a shared-key public-endpoint boundary guarantee) that doesn't become redundant just because a2web's own flag started working. See design.md D7. Resolved guidance: read the URL from `requested_url`/`final_url`, not `body`, when content is included.
- [x] 1.5 (found by the gateway operator against the real payload, fixed) Rename attribute `query` → `requested_query` and `severity` → `feedback_severity` — both were name-anchored/collision hazards on the gateway's storage side (`query` gets masked to `****` by the same redaction pattern; `severity` silently shadows OTLP `severityText` in flat storage). Regression tests added.
- [x] 1.6 (found by the gateway operator, fixed) Replace the unverified per-step `chain.<i>` nested `kvlistValue` encoding with a single `chain` attribute holding the step list as one JSON string — avoids relying on unconfirmed nested-attribute flattening behavior and the risk of one new column per chain step per record (design.md D5's per-record schema union).

## 2. Richer report content (design.md D6)

- [x] 2.1 Add `operation: "query" | "fetch_raw"` to the payload — derived from `fc.inputs.ask is not None`, matching how `routers.py` already distinguishes the two tools; no new field needed on `FetchContext`/`FetchInputs`
- [x] 2.2 Replace `fc.observations[-1]`-only usage with the full chain: emit one entry per `Observation` (source, verdict, authoritative, t_ms), in order — shipped as a single `chain` JSON-string attribute (revised per §1.6, not per-step attributes)
- [x] 2.3 Add `status_code`, `content_type`, `cache_state`, `tier_used` from `FetchContext` to the payload — unconditional, none of these name a URL or query
- [x] 2.4 Add `hint.fix` to the payload when present (currently computed, currently discarded) — omitted entirely (not sent as an empty value) when the hint carries none
- [x] 2.5 Add `requested_url`/`final_url` as two distinct fields (both content-gated per §1) rather than the current single URL field, so a redirect/rewrite is visible when content is included
- [x] 2.6 Unit tests: multi-tier fetch → payload's chain has one entry per attempt, not just the last; `hint.fix` present when the triggering hint carries one; `requested_url` differs from `final_url` in the payload when a rewrite occurred and content is enabled
- [x] 2.7 (raised during shape review) Add explicit `expected`/`result_status`/`result_confidence` fields — `expected` derived from `operation`, `result_status`/`result_confidence` sourced from the actual built `FetchResponse` passed into `_record_feedback` (not re-derived), so the report's outcome can never diverge from what the caller received. `_record_feedback` signature and its one call site (`fetcher/__init__.py`) updated accordingly. See design.md D6 addendum.

## 3. Verification

- [x] 3.1 Re-run the real-payload capture technique (`capture_real_payload.py`-style, no network) against the updated `_record_feedback` to confirm the new fields appear and the redaction fix actually removes URLs from `message` by default — confirmed both `INCLUDE_CONTENT=false` (`[url-redacted]` in body) and `=true` (real URL, plus `requested_url`/`final_url`/`query`) variants
- [ ] 3.2 Live smoke test against the real gateway — **no longer blocked** (§1.4 reversed). Assert, content flag ON: `requested_url`/`final_url`/`requested_query` arrive intact in storage, `body` may still show `[url-redacted]` (gateway's own scrub, expected and correct) rather than asserting a full URL in body. Content flag OFF: `body` shows `[url-redacted]` via a2web's own redaction. Send an updated payload capture (naming fixes applied) for the homelab session to push from shen, same pattern as before
- [x] 3.3 `make lint` / `make ty` / full `uv run pytest tests/` — clean, 1863 passed, 2 deselected
- [x] 3.4 Update `README.md`'s `A2WEB_FEEDBACK_INCLUDE_CONTENT` row to describe the new scope (governs the hint message too, not only a separate url/query pair)

## 4. Deferred, not this change (design.md D1–D4)

- [ ] 4.1 Tracing-seam shelf `bootstrap()` and the shared `OtlpEndpointConfig` — tracked here as a placeholder only; resolve the shelf loop and open a follow-up change when `shelf` is actually touched, per `AGENTS.md`'s lazy-resolution convention
