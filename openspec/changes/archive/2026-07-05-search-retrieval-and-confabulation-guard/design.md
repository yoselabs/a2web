## Context

Three defects in community-site search retrieval, all reproduced against live traffic on 2026-07-05:

1. `hn.algolia.com/?q=<query>` (the Algolia search SPA) matches no handler. `HNHandler.matches()` only accepts `news.ycombinator.com`, so the request falls to the generic tier ladder, renders as an SPA shell, and the extractor confabulates a fluent-but-wrong answer at `confidence: high`.
2. `fetcher_response._confidence_for(verdict, content_md)` derives confidence solely from the verdict and the rendered length. It never consults the extractor's own `obstacle` field, so an "empty/blocked" page can surface as high confidence.
3. `actions/playbook._decide_paid_last_resort` only treats `_PAID_WALL_VERDICTS = (paywall, block_page_detected, anti_bot)` as walls. An SPA that raw-shells → escalates to the browser rung → still returns a thin shell lands on `length_floor`, which is not a paid wall, so the paid render tier (Zyte) is never dispatched and the fetch dies incomplete.

Key existing machinery this design builds on (all confirmed in the current tree):

- **Handler**: `HNHandler` already fetches `hn.algolia.com/api/v1/search` and `…/items/{id}` and renders Algolia hits via `_render_front_page` / `_render_item` + `_front_page_candidates`. It is a tier-0 `site_handler`.
- **Pipeline order** (`fetcher._run_pipeline`): `cache_check → tier_loop → extract(structural) → gate_and_escalate → cache_write → build_response → extract_answer(LLM)`. The LLM `obstacle` signal is born in `_phase_extract_answer`, which runs **after** `build_response`.
- **Planner**: `decide_next` walks a priority-ordered rule list — `gate_browser_signal` (HIGH) → archive rules → `paid_last_resort` (LOW, last). Each escalation is capped (`browser_dispatches < 2`, `archive_dispatches < 1`, `paid_dispatches < 1`), so the loop always terminates. `EscalatePaid → _escalate_paid → _PAID_TIER_ORDER = ("zyte", "firecrawl")`; Zyte defaults to `browserHtml` mode.
- **Block detector**: `evaluate()` already emits `BlockVerdict.length_floor` with `subsystem="js_required"` + an `EscalationSignal(next_tier="browser")` when a sub-floor body carries SPA-shell markers (`__next`/`root`/web-component tags/etc.).

Live reachability facts that anchor the routing decisions:

| Target | Route | Result |
|---|---|---|
| `hn.algolia.com/api/v1/search?query=claude+code&tags=story` | direct GET | 200, 20 clean hits (real titles + points) |
| `hn.algolia.com/?q=claude` | Zyte `browserHtml` | 200, 30 stories rendered |
| `old.reddit.com/r/…/search?q=…` | Zyte `browserHtml` | 200, 22 real results |
| `www.reddit.com/r/…/search.rss?q=…` | direct GET | 200, 26 real results (keyless) |
| `www.reddit.com/…/search.json` | Zyte `httpResponseBody` | 520 Website Ban |

## Goals / Non-Goals

**Goals:**

- HN Algolia search UI URLs resolve deterministically via the Algolia search API — no SPA render, no browser, no paid tier.
- The `ask` envelope never reports high confidence when the extractor itself flagged an `obstacle`; empty/blocked obstacles surface as retrieval-incomplete.
- A genuine JS-shell SPA that exhausts the free ladder escalates to a paid render (Zyte `browserHtml`) instead of dying as `length_floor`.
- The installed global MCP binary reflects the current tree (Reddit `search.rss` + the new HN handler).

**Non-Goals:**

- No new Reddit search work — `search.rss` already handles it in-tree.
- No cookie mirror / OAuth for Reddit (explicitly off the table).
- No change to `fetch_raw` behavior — it has no `obstacle`, so the confabulation guard is `ask`-only.
- No change to the wire *shape* — no fields added or removed; only which values are emitted.
- No general "detect wrong-but-substantial content" heuristic beyond the extractor's `obstacle` signal (the deterministic path cannot catch a browser render that returns a full unrelated article; that case is covered by the `obstacle` guard, not by escalation).

## Decisions

### D1 — HN Algolia search: extend `HNHandler`, don't add a new handler

`HNHandler` already owns the Algolia API transport and hit-rendering. Adding a third shape (`hn.algolia.com/?q=`) reuses `fetch_bytes`, `_render_front_page` (the Algolia search-hit shape is identical to `tags=front_page`), and `_front_page_candidates`.

- `matches()`: return `True` when `host == "hn.algolia.com"` and the query carries a non-empty `q`.
- `fetch()`: build `api_url = f"https://hn.algolia.com/api/v1/search?query={quote(q)}&tags=story&hitsPerPage=30"`, then flow through the existing JSON-parse → render → `TierResult(pre_rendered=…, next_links=…)` path.
- `tags=story` chosen so results are submissions (matches the "list top HN stories" intent). `hitsPerPage=30` matches the front-page cap.

_Alternative considered_: a standalone `hn_algolia.py` handler. Rejected — it would duplicate the transport + rendering that already lives in `hn.py`, and the two hosts are the same logical source (HN over Algolia).

_Alternative considered_: route the SPA URL to Zyte `browserHtml` (proven to render it). Rejected as the primary path — a paid render is strictly worse than a free API GET when the API is open; Zyte stays the fallback for *unknown* SPAs (D3).

### D2 — Confabulation guard lives in the ask-path projection, not `build_response`

**Ordering constraint (load-bearing):** `obstacle` is produced by `_phase_extract_answer`, which runs *after* `build_response`. Wiring the reconciliation into `build_response` / `_confidence_for` would read `obstacle = None` every time. The reconciliation therefore lives in the ask-path projection (`build_ask_response` / `_project_routing`), where `obstacle` has already been extracted and is being placed on the wire.

Reconciliation rule:

- `obstacle ∈ {empty, blocked, paywalled, error}` → `confidence = low` (downgrade only; never upgrade).
- `obstacle ∈ {empty, blocked}` → additionally `retrieval_incomplete = true` + append `OperatorHint(code="retrieval_incomplete", …)` naming the likely cause (SPA shell / stale / unrelated page).
- `paywalled` / `error` cap confidence but are not forced to `retrieval_incomplete` here — a paywalled page may still carry a legitimate partial answer, and the existing paywall/verdict machinery already owns the incomplete signal for true walls.

This complements the shipped `extraction_empty` guard (`ask_unanswered = extraction_empty or llm_unavailable`), which only fires on a *literally empty* answer. The confabulation case has a *non-empty, fluent* answer, so it slips past `extraction_empty` today; the `obstacle` reconciliation is the piece that catches it.

_Alternative considered_: reorder the pipeline so `extract_answer` runs before `build_response`, letting `obstacle` drive tier escalation too. Rejected for this change — a larger refactor, and escalation-on-obstacle would cost a second extraction pass. Kept as a possible future once the cheap guard is in place.

### D3 — Paid escalation for `length_floor` + `js_required`, cost-gated on the subsystem

Extend the paid last-resort trigger so it also fires when the latest gate/regate verdict is `length_floor` **and** `subsystem == "js_required"`, with the existing `paid_dispatches < 1` cap. Because the rule is declared LOW/last, it is reached only after the browser rung is spent (`gate_browser_signal` stops firing at `browser_dispatches == 2` or once the signal is gone).

- Add `length_floor` to a companion condition, **not** by adding it bare to `_PAID_WALL_VERDICTS` — the subsystem check (`js_required`) is what keeps paid spend scoped to genuine SPA shells. A generic sub-floor page (thin article, empty result) has no `js_required` subsystem and must *not* trigger paid egress.
- The dispatched paid tier is Zyte in its default `browserHtml` mode — the mode proven to render both the HN SPA and old.reddit search.

_Alternative considered_: add `length_floor` to `_PAID_WALL_VERDICTS` unconditionally. Rejected — it would fire Zyte on every short page (empty search results, stubs), a cost and latency regression.

### D5 — Escalate to a paid site render via a first-class `escalate_to_render` signal

When a handler's optimized route fails — a converting handler's rewritten fetch errors (HN: SPA URL → Algolia API), or a walled surface 403s (Reddit search/listing RSS) — the original URL is still a real, renderable page. Add a typed `escalate_to_render: bool` field on `TierResult`. The handler sets it; the orchestrator records the failed attempt as a diagnostic, logs a **non-authoritative** observation, sets `fc.render_requested`, and **stops the free ladder**. The gate/escalate phase then dispatches the **paid tier (Zyte `browserHtml`) directly** onto the original URL.

- **Why go straight to paid, skipping the free ladder AND the own-browser** (the crux — this is what makes it not "pointless"): empirically, `raw` of the HN SPA returns a **587-char shell** — *above* the 500 `LENGTH_FLOOR` — so the block detector returns `ok` and the extractor confabulates. The `js_required` paid rung (D3) only fires *below* the floor, so it would never catch this shell. And the own-browser (Camoufox) is the exact tier that returned the wrong Anthropic-policy page in the original report. Zyte `browserHtml` is the only route proven to reliably render both the HN SPA (30 stories) and Reddit search (22 results). A fallback that lands anywhere else dead-ends — so the render goes straight to paid.
- **Cost**: one paid call per escalation — but only fires when the primary (free) route already failed (API error / RSS 403), so it is not on the common path. Bounded by the single-paid-dispatch cap; un-keyed deployments no-op and fail loud.
- **Loud on render failure**: because the free ladder was stopped, the render is the *only* route. If it produces nothing (no paid key, or paid failed), `build_response` forces `retrieval_incomplete` regardless of the handler's placeholder verdict (HN's Algolia `404` is not a "wall" verdict but the miss is real), and the gate phase appends the critical `try_user_browser` hint. Never-silently-miss holds.
- **Why a typed field, not `no_match`**: `no_match` means "no handler claimed this URL" and suppresses the diagnostic; here the handler *did* claim and *did* try. Honors the "typed field, no `dict[str, Any]` bag" convention.
- **Generic, HN + Reddit first**: the field + orchestrator handling are handler-agnostic; HN (converted-fetch failure) and Reddit (walled search/listing) are the first adopters.

_Alternative considered — own-browser first, paid only if thin_ (reuse the D3 rung via a seeded `js_required` signal): rejected. The own-browser can return a shell/wrong content that *passes* the gate, so it "wins" with a bad render — the exact failure from the report. Reliability is the whole point; straight-to-paid is the reliable route.
_Alternative considered — fall through to the free ladder_ (the earlier `escalate_to_ladder` design): rejected. `raw` returns the 587-char shell, which passes the gate → confabulation. It dead-ends without ever rendering.

### D4 — Operational propagation

Add `make install-global` as an explicit task. The MCP entry points at the installed binary (fast cold start), so source edits — including the already-landed Reddit `search.rss` handler — do not reach the running server until reinstalled. This is why the original session still saw broken Reddit search despite the fix being in-tree.

## Risks / Trade-offs

- **Algolia API contract drift** (field/param rename, `tags`/`numericFilters` rules) → the handler pins only `query` + `tags=story` + `hitsPerPage` (the report's 400s came from unsupported `numericFilters` like `points>80`, which this change deliberately does not send); `map_non_ok` already surfaces upstream 4xx bodies, so a future break is loud, not silent.
- **Over-aggressive confidence downgrade** — a healthy page the model mislabels with an `obstacle` would be capped to `low` → this is the safe direction (under-confident, never over-confident); the model is instructed to OMIT `obstacle` on healthy pages, so a false `obstacle` is already a model error we would want surfaced.
- **Paid-cost creep from D3** → double-gated: `subsystem == "js_required"` scopes it to SPA shells, and `paid_dispatches < 1` caps it to one render per fetch; un-keyed deployments fall through to the existing never-silently-miss hint (no-op paid dispatch).
- **`retrieval_incomplete` hint noise** on legitimately empty result sets (a real search with zero hits) → acceptable: "we retrieved nothing answer-bearing" is exactly the honest signal the caller should get, and the HN/Reddit search handlers return their own not_found/empty paths for true empties before this guard applies.

## Migration Plan

1. Land the three code changes behind the existing test suite (`make check`, coverage ≥85%).
2. Add/extend capability specs (`site-handlers`, `ask-response`, `retrieval-completeness`, `paid-fetch-tiers`).
3. `make install-global` to refresh the MCP binary; confirm end-to-end in a live session (HN Algolia search returns real stories; Reddit search returns real results; an unknown SPA either renders via Zyte or reports `retrieval_incomplete`).
4. Rollback: each piece is independent and additive — reverting any one leaves the others working. The confabulation guard and paid trigger are pure verdict/wire tightenings with no schema change, so rollback is a straight revert with no data migration.

## Open Questions

- Should `tags` for HN Algolia search be `story` only, or `(story,comment,poll)` for broader recall? Defaulting to `story` for the "top stories" intent; can widen if search recall proves too narrow.
- Longer term (out of scope here): is it worth the pipeline reorder in D2 so `obstacle` can also *drive escalation* (retry via Zyte) rather than only downgrade confidence? Revisit after the cheap guard ships and we see how often `obstacle: empty` fires on pages a paid render would have recovered.
