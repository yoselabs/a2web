## Context

a2web is a **remote-first** MCP/CLI fetcher: its purpose is to run on a server so an AI agent can offload web retrieval. Reddit is a high-value source, but as of mid-2026 every anonymous, automated, remote-safe path into it is walled. This design records the evidence, the resulting tier design, and the rejected/deferred alternatives so the decision is durable (Constitution Article VIII — dependency memory).

### Evidence trail (all tested live, 2026-06-29 → 07-03)

| Path | Result |
|---|---|
| `www.reddit.com/search/.json` (curl) | 403 — Datadome challenge HTML (~190KB) |
| `www.reddit.com/r/x/top.json` (listing) | 403 |
| `www.reddit.com/r/x/comments/<id>/.json` (thread) | 403 — **all `.json` shapes walled, incl. threads** (tested 2026-07-03) |
| `.json` via curl_cffi `impersonate=chrome` | 403 — TLS impersonation does not help |
| jina reader (`r.jina.ai`) | 403 — *"log in to your Reddit account or use your developer token"* |
| Patchright / Camoufox browser tier | HTTP 200 but body = *"blocked by network security"* (`block_page_detected`, 14s) |
| proxy-through-Shen (Contabo **datacenter** egress) | 403 — datacenter ASN + JS challenge |
| Claude Code native `WebFetch` (www + old.reddit) | domain-denylisted — refuses before any network call |
| Claude Code native `WebSearch` | zero reddit.com URLs (Reddit not in the index); secondhand summaries only |
| **Reddit `.rss` (Atom)** | **200** — search returned 25 entries; thread `.rss` returned post + comment bodies. Works even via the datacenter proxy. Rate-limited (429) on bursts. |
| PullPush.io (Pushshift successor) | 200, scored full-text comment search — but newest record ~May 2025; **ingest stalled ~14 months** |
| Public Redlib instances | 403 / 429 / anti-bot `.gandalf/check` / a "we shut down" redirect — dying |

Two structural facts fall out: (1) Reddit's wall is a **JS challenge** (Datadome), not pure IP reputation, so an HTTP client — however good its TLS or IP — cannot solve it; (2) Reddit's own error text names the only two endorsed paths: **log in** or **use a developer token**. Everything that works is either keyless-but-different-channel (RSS) or authenticated.

## Goals / Non-Goals

**Goals:**
- A keyless, live, **remote-safe** Reddit path (RSS) covering search/listing/thread with comment samples.
- Cheap, reputable, remote-safe paid backstop for the walled residual (Zyte + Firecrawl), env-gated and graceful.
- Make an unfetched URL **impossible to mistake for success** — the never-silently-miss contract — via an explicit envelope signal + a critical, imperative escalation hint.
- Codify "never tolerate ANY unfetched URL" as a first-class a2web product tenet.
- Preserve the full evidence + rejection rationale so none of it is re-litigated.

**Non-Goals:**
- Solving *authenticated, remote, headless* Reddit in this change (that is the future browser-container track, gated behind an untested crux).
- Reddit OAuth (deferred — approval gate) and PullPush (deferred — stale).
- `hot` listings (algorithmic; not projectable to any queryable source).
- Full nested/scored comment trees on large threads (RSS gives flat, ~25 recent, unscored samples; paid tiers give more).
- Write actions (vote/comment) — a2web is read-only.

## Decisions

### D1 — RSS as the primary keyless Reddit path
Reddit gates `.json` with Datadome but leaves `.rss` open (feed readers need it). Rewrite `search`/`listing`/`thread` → `.rss`, parse Atom. **Why over `.json`:** `.json` is 403 anonymously; `.rss` is 200 from the same host, even from a datacenter IP. **Limits (documented, not hidden):** flat structure (no reply tree), ~25 recent entries (not top-ranked), no comment scores, tight per-IP rate limit → mandatory backoff + `http_cache` reuse. `hot` does not project; `top`/`new`/search/thread/user do.

### D2 — Paid tiers env-gated, fail-loud, no silent fallback
Zyte (`$0.13/1K`, pay-as-you-go, the Scrapy company) and Firecrawl (`$16/mo`, already partially wired) as `_manifests/tiers/` plugins. **Why both:** user choice; both rent clean residential IPs + solve anti-bot (their product claim — verify with a trial key before relying). **Fail-loud rule:** keyed-but-failing → report the service/key error; never silently drop to a lower-quality tier. This is the never-silently-miss tenet applied to bad credentials — inconsistent silent degradation is exactly what we refuse.

### D3 — retrieval-completeness contract (the headline)
Terminal `paywall`/`block_page_detected`/`anti_bot` → envelope carries `retrieval_incomplete: true` + `OperatorHint(code="try_user_browser", severity="critical")` with imperative wording. The wire serializer must never dress a miss as a soft low-confidence answer. **Eager for Reddit** (handler emits immediately on `.json`/RSS exhaustion — the full ladder is proven to lose, so spending 14s on the browser tier is waste); **late generically** (other sites' jina/archive/browser tiers have real hit rates, so hint only when exhausted). Capability-generic wording (never names `claude-in-chrome`).

### D4 — Tenet home: CLAUDE.md + ADR, NOT CONSTITUTION.md
`CONSTITUTION.md` is a verbatim copy synced from a2kit governing *how decisions are made* across the ecosystem; a product-behavior invariant would pollute it and break the sync contract. The tenet strengthens the existing `CLAUDE.md` "Never silently drop a fetch" line (its natural sibling); the rationale + evidence live in an ADR (Article VII).

### D5 — Rejections/deferrals recorded as ADRs (Article VIII)
- **Redlib — rejected:** OAuth-spoofing service ("OAuth in a costume"); public instances dying (tested); self-host = a fragile spoofing service to babysit, same ~100 req/10min limit as your own OAuth.
- **PullPush — deferred:** free scored cross-Reddit comment search, but ingest stalled ~14 months → historical-only; automatic use = silent staleness, which violates D3. Keep for a future cloud/home node-mode.
- **Reddit OAuth — deferred:** works (100 QPM free non-commercial) but Nov-2025 approval gate; revisit if RSS + paid prove insufficient.
- **proxy-through-Shen — rejected:** datacenter egress + JS challenge (tested 403).
- **Chrome-inside-a2web / rdt-cli / OpenCLI / Agent-Reach login-CLIs — rejected for remote:** all local-desktop browser-cookie architectures. rdt-cli under the hood is `.json` + `browser-cookie3` — i.e. exactly `cookie_jar` + a2web's handler, plus write-actions we don't need. No anti-Datadome magic; useless on a headless server (no local browser).

## Implementation-level decisions (from the architecture self-assessment, 2026-07-03)

Three read-only agents mapped the tier-dispatch/fail-loud seam, the envelope/hint seam, and the reddit-render/dependency seam. Findings that shaped the plan:

### D6 — RSS is a handler-internal projection, not a new registry tier
The Reddit handler already rewrites URLs (`_to_json_url`) and returns `TierResult(pre_rendered=Rendered.from_dict(...))`. The change swaps the projection target `.json`→`.rss` and adds Atom render producers; the `TierResult`/`Rendered` construction site is **unchanged**. `_render_search`/`_render_listing` get thin Atom variants (factor out the shared markdown tail); `_render_thread` gets a **new flat `_render_thread_atom`** (the recursive `_render_comment`/`_find_comment_path`/permalink-focus helpers do not port to flat Atom). `xml.etree` (stdlib) parses Reddit Atom cleanly — **no feedparser/lxml dep** (Article III: don't add a dep stdlib covers). Spiked ✓.

### D7 — Paid tiers dispatch out-of-band as the cost-incurring last resort (after proxied free attempts fail)
There is **no existing paid/Firecrawl tier** (greenfield; copy the Jina manifest). Register Zyte/Firecrawl at `priority=-1` (out of `TIER_ORDER`) and dispatch via a new `EscalatePaid` planner action/rule in `actions/playbook.py` (mirroring `EscalateBrowser`) with its own `PlannerCaps` cap, so paid calls fire only when a cheaper tier hits a block/paywall/anti_bot verdict — never on every fetch. **Ordering:** paid is the *cost-incurring* escalation of last resort — it fires only **after the free attempts are exhausted** (the raw tier already retries through the proxy pool per route rules + per-proxy circuit breakers, and the browser tier where applicable), and **before** the terminal `try_user_browser` hint. This honors "escalate to paid only if proxies fail." Un-keyed → factory returns `Unavailable` → tier never enters the registry (boot-time gating, cleaner than Jina's always-registered-but-header-gated approach).

**Why paid tiers are permanent, not superseded by the future browser container:** a real user segment is credential-averse — they will not sign into a browser container with their real account, and prefer to pay a service (or lean on proxies) to beat a wall. Paid + proxy is the no-account path; the browser container is the have-an-account path. Both persist. (Proxies themselves need no new work here — they are already a2web's raw-tier mechanism; paid is simply the next rung when proxied attempts still hit a wall.)

### D8 — Fail-loud is a NEW mechanism (today every non-ok verdict silently CONTINUEs)
`_execute_tier_action` returns CONTINUE for any non-`ok` verdict (`fetcher.py:886`) — a bad key is indistinguishable from a routine miss and falls through. Build: a new `Verdict.paid_auth_error` (the exhaustive `match` in `_verdict_rank` forces ranking it), set `authoritative=True` on that observation (so it outranks a later lower-tier success in `resolve_verdict` rather than being masked), and a **STOP branch** so escalation halts and the loud verdict surfaces. This is the retrieval-completeness tenet (ADR-0009) applied to credentials.

### D9 — `retrieval_incomplete` needs a scoped `_prune_wire` tweak; `severity` needs snapshot re-bless
A plain `retrieval_incomplete: bool = False` would **not** be omitted (`False` matches none of `_prune_wire`'s empty sentinels `None`/`""`/`[]`/`{}`). Add the field to the omit-when-empty default bucket and extend the empty test to treat this field's `False` as empty (scoped to the field to avoid a global bool-dropping behavior change). `OperatorHint.severity` defaults to `"info"` (non-empty → always serializes), so either omit-when-`info` in the hint serializer or accept it and **re-bless** the golden snapshots that contain `operator_hints` (`tests/contracts/tool_schemas.json`, `tests/eval_replay/`, envelope capability tests).

### D10 — The eager Reddit hint needs a new propagation seam
A site handler's `TierResult.operator_hint` **does not reach `fc.operator_hints`** today (only the browser escalation consumes it, `fetcher.py:1500-1501`). Add a one-line propagation in the tier loop (~`fetcher.py:1016`) so a site_handler's hint is appended to `fc.operator_hints`. The eager Reddit seam is the 403 branch (`reddit.py:163-172`); the late generic seam is the end of `_phase_gate_and_escalate` after the escalation `while` loop breaks (~`fetcher.py:1406`), gated on `resolved_verdict() ∈ {block_page_detected, anti_bot, paywall}` and host ≠ reddit.

## Risks / Trade-offs

- **RSS gives shallow comments** → surface the limits explicitly (sample, not full tree; no scores); route deep/large-thread needs to the paid tier; never imply completeness.
- **RSS rate limits (429)** → backoff + `http_cache`; treat 429 as retryable, not terminal; if exhausted, fail loud (D3), never silent.
- **Paid tiers unverified against Datadome** → their product claim, untested here → validate with a trial key before depending; if a keyed service can't pass, that is a loud failure, not a silent skip.
- **The hint is advisory** → a2web can guarantee the failure is loud/unmissable in its envelope but cannot force the caller to obey → make ignoring it require active negligence (`retrieval_incomplete` + `status:failed` + critical severity + imperative text).
- **Future browser-container is security-sensitive** (a browser holding the user's logins) and egresses a datacenter IP → out of scope here; gated behind the untested crux "does `.json` + logged-in cookies pass Datadome?" — cheap to test first.

## Migration Plan

Additive only. New envelope fields (`retrieval_incomplete`, hint `severity`) are backward-compatible; parsers ignoring unknown fields are unaffected but should begin honoring `retrieval_incomplete`. New tiers are opt-in (RSS is on for Reddit; paid tiers no-op until keyed). Rollback = remove the RSS projection branch and the paid manifests; the handler falls back to today's `.json` path (which fails loud under D3). No data migration.

## Open Questions

- **The load-bearing crux:** does `.json` + *logged-in* cookies pass Datadome? (rdt-cli's existence implies yes.) Answering it unlocks the future browser-container track. Cheap to test with the user logged in + `cookie_jar`.
- Zyte vs Firecrawl default preference order when both are keyed?
- Should the unsupported-shape hint also fire for `hot` listings specifically (since they are the one shape RSS structurally cannot project)?
- yt-dlp/YouTube transcription tier — separate change; Article III adoption research pending.
