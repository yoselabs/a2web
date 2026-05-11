# v0.3 — engine improvements

## Why

The 2026-05-11 vs-WebFetch benchmark (`benchmarks/vs-webfetch/2026-05-11/`) ran 20 URLs across 5 classes through Claude Code's built-in `WebFetch` and three a2web response shapes, blind-judged on per-URL criteria. Two findings dominate everything else:

1. **a2web's content tier already wins on quality** (mean judge 3.40 vs WebFetch 2.95) but **leaks ~5× more tokens** into the calling agent's context than the downstream agent actually consumes. Stripping `links` + `fit_md` + `diagnostics` saved a median 83% of tokens with judge scores tied-or-better on 17/20 URLs.
2. **a2web's expensive escalation tiers never fire.** `from_browser=False` and `from_archive=False` on 20/20 fetches, including Reddit / X / Linear / LWN / t.co where raw failed and the gate had a clear opportunity to suggest browser. We ship capability we don't trigger.

Three concrete leaks the benchmark surfaced:

- `fit_md` byte-for-byte duplicates `content_md` on 14/20 fetches (~19% of all tokens across the corpus). Leftover field from a deprecated pruning filter; CLAUDE.md already calls it forward-compat-only.
- The `links` field is **49% of total payload tokens**, dominated by aggregator/UI noise (HN: 197 links, gh-trending: 1,142, pypi: 287). Tasks that need links are a minority.
- `diagnostics` adds ~190 tokens to every response (3% always-on) but is almost never read by the downstream agent.

Reach gaps the benchmark surfaced:

- Reddit fails because (a) the handler's `.json` endpoint returns 404 for the test thread and (b) raw curl_cffi gets HTTP 200 but extracts 0 chars (JS shell), and the gate's `length_floor` verdict does not produce `suggested_tier="browser"` to escalate.
- Linear marks `status=failed` on content that judges scored 5/5 — a gate false-positive on JS-heavy but content-bearing pages.
- Twitter/X has no handler at all and no working tier; the only practical solution short of paid API is a Nitter mirror or browser.

v0.3 closes both axes — envelope diet and reach reliability — as one cohesive engine release. The follow-up v0.4 (`a2web.llm` module) builds on this foundation but is out of scope here.

## What Changes

**Envelope diet** (kills ~80% of default token cost with zero measurable quality regression):

- Stop populating `fit_md` with a copy of `content_md` when no pruning filter ran. Return `None` / omit. The field stays on the model for forward-compat; the *behavior* of duplicating is what dies.
- Add `include_links: bool = False` parameter to the `fetch` tool. Default off. When `True`, links are returned as today.
- Compact `diagnostics` by default: return a single-line summary string (`"tier=raw verdict=ok 708ms"`) on the `FetchResponse`. Full diagnostics trace returned only when `debug: bool = True` is passed.
- **Not changing** the existing field shape on `FetchResponse` — `links`, `diagnostics`, `fit_md` stay typed where they are. New params gate population, not the contract.

**Reach reliability** (uses the tiers we already ship):

- Fix the gate → orchestrator escalation pathway: when `GateResult.verdict == length_floor` AND the previous tier's body suggests JS shell (e.g. very thin extracted text + JS-only DOM markers), gate SHALL produce `suggested_tier="browser"`. Orchestrator already routes on `suggested_tier`; this just fixes the producer.
- Audit `block_detector` thresholds against the Linear payload from the benchmark; document and adjust whatever threshold misfires. Add a regression scenario to `quality-gate` spec.
- Reddit handler: when the `<host>/r/.../comments/.../.json` request returns 404 OR an empty thread, fall back to `old.reddit.com/<path>` (HTML, server-rendered) and re-extract.
- Twitter/X handler (new): match `x.com` / `twitter.com` status URLs, fetch via configured Nitter mirror with rotation across multiple instances. Returns structured tweet + comments.

**Anticipatory work for v0.4** (no public surface change):

- Move `benchmarks/vs-webfetch/2026-05-11/judge.py` + `aggregate.py` into a shape that's lift-and-shift ready for the future `a2web.llm.eval/` module. No actual move yet — just consolidate prompt strings + Provider boundaries inside the existing scripts.

## Impact

**Affected specs:**
- `tier-pipeline` — new envelope-shape requirements (fit_md, links default-off, diagnostics summary).
- `quality-gate` — new length_floor → suggested_tier mapping; Linear-style FP regression scenario.
- `site-handlers` — Reddit old.reddit fallback; new Twitter/X handler via Nitter.
- `extraction` — fit_md population rule changes.

**Affected code:**
- `src/a2web/fetcher.py` — wire `include_links` + `debug` params into the response builder.
- `src/a2web/models.py` — diagnostics summary string field (additive).
- `src/a2web/routers.py` — expose new params on `fetch` tool.
- `src/a2web/gate/block_detector.py` — length_floor → browser mapping; Linear FP fix.
- `src/a2web/handlers/reddit.py` — old.reddit.com fallback.
- `src/a2web/handlers/twitter.py` (new) — Nitter-backed.
- `src/a2web/settings.py` — Nitter instance list + rotation.
- `tests/` — new scenarios + regression coverage.

**Breaking? No.** All new params default to existing-behavior-preserving values; existing fields stay typed where they are. The one default change (`include_links` from "always on" to `False`) is breaking *only* for callers who relied on links being present without asking. Documented in CHANGELOG; existing benchmark already shows 17/20 URLs have zero quality regression.

**Token impact (projected from benchmark):**
- Median per-fetch tokens: 6,353 → ~1,335 (-79%) on the corpus.
- gh-trending: 27,167 → 379 (-99%) when caller doesn't pass `include_links=True`.
- Calling agents that explicitly want links flip one bool and pay the cost knowingly.

## Non-goals

- **No LLM dependency.** No `anthropic` or `openrouter` import lands in v0.3. The `a2web.llm` module is v0.4.
- **No Claude Code hook integration.** Deferred per user direction — engine first, hook later.
- **No Reddit OAuth.** old.reddit fallback covers the common case; OAuth is BACKLOG.
- **No Twitter API.** Free tier is too rate-limited to be useful; paid is out of scope. Nitter only.
- **No response-envelope rewrite.** Field shape stays; only population behavior changes.
