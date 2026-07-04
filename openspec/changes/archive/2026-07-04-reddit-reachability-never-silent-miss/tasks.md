> Sequencing note: groups 1–2 (envelope + hint plumbing) are prerequisites for the
> eager/late hints in group 3 and the fail-loud verdict in group 4. Do them first.

## 1. Envelope contract (models.py + decision_log.py)

- [x] 1.1 Add `retrieval_incomplete: bool = False` to `FetchResponse` (near `operator_hints`) and project onto `AskResponse`; put it in the omit-when-empty default bucket
- [x] 1.2 In `_prune_wire`, extend the empty test to treat this field's `False` as empty (scoped to the field name — do NOT globally drop all `False` bools)
- [x] 1.3 Add `severity: Literal["info","critical"] = "info"` to `OperatorHint`; omit `severity` from the wire when `"info"` (avoid snapshot noise) — or accept always-present and plan the re-bless in 6.2
- [x] 1.4 Add `Verdict.paid_auth_error` to `models.Verdict`; give it a rank in `decision_log._verdict_rank` (the exhaustive `match`/`assert_never` forces this)
- [x] 1.5 Unit tests: walled → `retrieval_incomplete:true` + `status:failed`; success → field omitted; `try_user_browser` hint is `critical`; `paid_auth_error` ranks as a hard failure (`tests/capabilities/fetch_response/test_never_silent_miss.py`)

## 2. Hint plumbing (fetcher.py)

- [x] 2.1 NEW propagation: append a site-handler's `TierResult.operator_hint` to `fc.operator_hints` in the tier loop (~`fetcher.py:1016`) — today only the browser escalation consumes it
- [x] 2.2 LATE seam: at the end of `_phase_gate_and_escalate` after the escalation `while` loop breaks (~`fetcher.py:1406`), emit `try_user_browser` (critical) when `fc.resolved_verdict() ∈ {block_page_detected, anti_bot, paywall}` AND host ≠ reddit
- [x] 2.3 Set `retrieval_incomplete` on the response when the resolved verdict is a terminal wall (in `build_response`/`fetcher_response.py`)
- [x] 2.4 Tests: unknown host runs full ladder then emits the late critical hint; hint wording is imperative + capability-generic (no product name); `retrieval_incomplete` set (`tests/capabilities/fetch_response/test_never_silent_miss.py`)

## 3. Reddit RSS projection (handlers/reddit.py)

- [x] 3.1 Add `.json`→`.rss` URL rewrite for `search`/`listing`/`thread`; ALL listing sorts project (bare/`hot`/`best` → `/r/<sub>/.rss`; `top`/`new`/`rising`/`controversial` → `/r/<sub>/<sort>.rss`, preserving `?t=`). (Spec-corrected: `hot` IS projectable via the bare feed — verified live.)
- [x] 3.2 Parse Atom with stdlib `xml.etree.ElementTree` (inline — Reddit feeds are tens of KB, parse in a few ms of pure CPU)
- [x] 3.3 Atom variants `_render_search_atom` / `_render_listing_atom` — shared `_stub_line` markdown helper fed a normalized `_AtomEntry`; `score`/`num_comments` dropped from the meta line (RSS omits them)
- [x] 3.4 New `_render_thread_atom` (flat): OP header (md-div extracted, thumbnail/SC-markers stripped) + flat comment list + explicit sample note; accepts loss of nesting / `more` stubs / scores / permalink-focus
- [x] 3.5 `next_links` for listing from Atom `title`+`link` (reuse `NextLink`, cap 10); NSFW SFW-filter DROPPED — Atom carries no clean `over_18` signal (documented in the render docstring)
- [x] 3.6 `429` handling: bounded `_RSS_BACKOFF_S` retry in `_fetch_rss`; retryable; on exhaustion fail loud (`rate_limited` verdict), never silent empty. (Response `http_cache` reuse stays at the SiteHandlerTier/orchestrator layer.)
- [x] 3.7 EAGER hint: search/listing 403 → `_walled_signal` returns `block_page_detected` + the critical `try_user_browser` `operator_hint` (propagated by 2.1) — no browser dispatch
- [x] 3.8 Unrecognized-Reddit-shape coverage: DEVIATION — rather than a handler branch, dropped the `not is_reddit` exclusion from the group-2 late seam (deduped by `_has_browser_hint`), so reddit shapes the handler does not claim (`/user/`, `/wiki/`) fall through to raw/jina and pick up the critical hint. Tenet honored; the generic hint does not enumerate supported shapes (acceptable — the "not retrieved" imperative is the load-bearing part)
- [x] 3.9 Tests: `_to_rss_url` all shapes; search.rss + listing.rss render + next_links; `_render_thread_atom` flat comment-sample render + sample note; search 403 → block_page_detected + eager critical hint; 429 → fail loud; old.reddit/archive fallbacks re-driven off `.rss`. Handler docstring documents the degradation. (Retired the `.json`-only permalink-focus / crosspost / removed-body tests + orphaned fixtures.)

## 4. Paid tiers — greenfield, out-of-band (tiers/ + _manifests/ + playbook.py)

- [x] 4.1 `settings.py`: add `zyte_key: str = ""` + `firecrawl_key: str = ""` (env `A2WEB_ZYTE_KEY` / `A2WEB_FIRECRAWL_KEY`); add both to the `EXCLUDE` secret set
- [x] 4.2 `tiers/zyte.py` + `tiers/firecrawl.py`: `Tier` classes (async `fetch` → `TierResult(pre_rendered=Rendered(...))`), copying `jina.py` shape; map auth/billing failure (401/402/403) → `Verdict.paid_auth_error` with `authoritative=True`
- [x] 4.3 `_manifests/tiers/zyte.py` + `firecrawl.py`: `MANIFEST = PluginManifest(..., priority=-1)`; factory returns `Unavailable("no key")` when un-keyed (boot-time gating)
- [x] 4.4 `actions/playbook.py`: new `EscalatePaid` action + a `_RULES` entry firing on block/paywall/anti_bot gate verdict **only after the free/proxied attempts are exhausted** (paid = cost-incurring last resort, before the terminal hint) + a `PlannerCaps` cap (1/fetch); extend `NextTier` if routing via `escalation.next_tier`
- [x] 4.5 `fetcher.py`: `_escalate_paid` handler (model on `_escalate_browser`, ~`fetcher.py:1433`); dispatch from the post-gate planner loop
- [x] 4.6 FAIL-LOUD STOP branch: when a paid tier returns `paid_auth_error`, STOP escalation (no CONTINUE/downgrade) and let the authoritative verdict surface — never silent fall-through
- [x] 4.7 Article III adoption ADRs for Zyte + Firecrawl (`_deps.md` per Article VIII)
- [x] 4.8 Tests: un-keyed → tier absent from registry; keyed → dispatched only on block signal; bad key → `paid_auth_error` STOPs + surfaces loudly (not a silent lower-tier result)
- [ ] 4.9 Manual: validate a keyed service actually passes Reddit's Datadome with a trial key before relying on it (their product claim is untested here)

## 5. Tenet + decision records

- [x] 5.1 Strengthen the `CLAUDE.md` "Never silently drop a fetch" line into the first-class "Never tolerate ANY unfetched URL" invariant
- [x] 5.2 ADR-0009 (tenet) + ADR-0010 (reachability + rejection memory) — DONE; keep in sync if decisions shift
- [x] 5.3 Add Zyte + Firecrawl adoption dep-decisions (Article VIII) alongside ADR-0010
- [x] 5.4 Future-direction notes (not build tasks): browser-container track (gated on the logged-in-`.json` test) + yt-dlp/YouTube tier + Agent-Reach multi-backend/`doctor` ideas

## 6. Spikes / validation still outstanding

- [x] 6.1 SPIKE (2026-07-03) — **NO, and the premise was wrong.** Read the user's logged-in Chrome reddit cookies (`reddit_session`/`token_v2`/`loid` present) + replayed via curl_cffi `chrome120` against listing/search `.json`: 403 **byte-identical with vs without cookies**. Block page is Reddit's own *"whoa there, pardner / network policy"* (`server: snooserv`), **NOT Datadome**; no `datadome` cookie in jar. Browser-like headers + real `Bearer token_v2` → `oauth.reddit.com` also 403. → cookie replay is a dead end; the `.json` wall is IP/network-policy, not cookie-solvable. Recorded in ADR-0010 (open question answered) + script at `docs/history/spikes/reddit_json_cookie_spike.py`. Caveat: run from operator's current egress IP (may be flagged); re-eval trigger = re-run from known-clean residential IP.
- [x] 6.2 Re-blessed golden snapshots for the new `retrieval_incomplete` + `severity` keys (`tests/contracts/tool_schemas.json` + `tests/contracts/ask_failure.json`; verified additive-only, 39 insertions / 0 deletions). `tests/eval_replay/` + envelope capability snapshots did NOT drift (they don't serialize the new fields). The `ask_failure` golden now exercises the eager `try_user_browser` critical hint end-to-end through the real MCP wire.
- [x] 6.3 Re-run the four-axis output-benchmark harness tests (`tests/capabilities/output_benchmark/`) — envelope shape changed. Green under `make check` (they run in the gate; the live-network `make bench` scoring run is separate and deferred — see note below).

## 7. Gate

- [x] 7.1 `make check` green (lint + ty + tests, coverage ≥85%); `make arch` green
- [x] 7.2 Update CHANGELOG.md; confirm additive-only envelope (new fields + one new `Verdict` value; no removals)
