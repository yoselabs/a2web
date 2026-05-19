# Design — a2web MCP feature wave

Four decisions need framing. The rest is mechanical.

---

## Decision 1 — Reddit search handler dispatches by URL shape, not by separate handler class

Considered: a separate `RedditSearchHandler` class alongside `RedditHandler`.

Rejected because:
- 80% of the handler machinery is identical — URL parsing, the `.json` rewrite, the httpx client with Safari UA, the error-translation table (`403` → `forbidden`, `429` → `rate_limited`, etc.).
- The split point is the **rendering branch only** — `_render_thread` vs `_render_search`.
- Two handlers would require duplicate `matches()` logic, duplicate registration in the registry, and two separate operator-hint paths.

Chosen shape:
- `RedditHandler.matches(url)` returns True for both comments URLs and search URLs.
- A small `_url_shape(url) -> Literal["comments", "permalink", "search"]` helper classifies the URL once.
- `fetch()` body dispatches the rendering branch on the shape — `_render_thread` for comments/permalink (existing), `_render_search` for search (new).

Trade: the handler grows by ~80 lines (new render function) but stays internally cohesive. Reading the handler top-to-bottom still tells one story: "given a Reddit URL of any shape, produce a Tier result".

---

## Decision 2 — `_render_search` output shape

Reddit's `search.json` response is `{kind: "Listing", data: {children: [{kind: "t3", data: {...}}, ...]}}`. Each `t3` post stub carries `title`, `subreddit`, `author`, `score`, `num_comments`, `permalink`, `created_utc`, `selftext` (often empty for link posts), `url` (the link the post points to), `is_self`.

Considered output shapes:

```
A — terse list (one line per result)
B — verbose blocks (per-result heading + selftext snippet + meta)
C — table (markdown table with columns)
```

**Chosen: A — terse list.** A typical search response is 25 results. Verbose blocks (B) blow up token cost on a surface that's primarily a navigation aid. Tables (C) are token-cheap but harder for agents to skim. Terse lists with structured-but-compact entries are the sweet spot for agent-driven research workflows (agent reads list, picks 1-3 promising results, fetches them individually).

Concrete shape per entry:
```markdown
- **{title}** (r/{subreddit} · u/{author}, score {score}, {num_comments} comments, {age})
  <https://www.reddit.com{permalink}>
```

`age` is computed from `created_utc` via a `human_age(seconds_ago) -> str` helper (returns `"3d"`, `"2y"`, etc.). No selftext snippets — if the agent wants the post body, it fetches the permalink.

Headings: `# Search: {query}` as H1 (extracted from URL `?q=`), `## Results ({n})` as H2.

---

## Decision 3 — `[llm]` extra removed hard, no back-compat alias

Considered:

```
α — Hard removal of [llm] extra (CHOSEN)
   pip install a2web[llm] → error from packaging machinery
   Shell scripts / CI configs that reference the extra break loudly,
   migration intent is unambiguous

β — Keep [llm] = [] as empty alias for one release (REJECTED)
   pip install a2web[llm] → silent no-op
   Reads as "still required" to users who haven't read the changelog

γ — Move only anthropic to base; keep claude-agent-sdk in [llm] (REJECTED)
   Smaller install (~30MB); user explicitly directed otherwise
```

**Chosen: α — hard removal.** Reasoning:
- a2web project convention (per CLAUDE.md and prior migrations) is loud-failure-with-embedded-migration-hint, NOT soft deprecation. Matches a2kit's own convention.
- An empty `[llm]` alias creates exactly the confusion we want to kill: users keep typing `[llm]`, scripts keep referencing it, the operator-hint flow keeps mentioning it. Hard removal forces the mental model update.
- The breakage surface is one line in install scripts — `pip install a2web[llm]` → `pip install a2web`. Migration cost is sub-minute.
- γ was the earlier recommendation when install size was the prevailing concern. User explicitly redirected: "most ppl using it will have claude code and will be reliant on it" → bundle.

The install-size jump (30MB → 240MB) is a real cost we're choosing to pay for OOTB user value. Document it loudly in CHANGELOG.

---

## Decision 4 — Captcha pre-routing: rewrite vs reject

Considered:

```
A — Rewrite Google/Bing search URLs to DDG before tier dispatch
   User gets useful results, transparently

B — Reject Google/Bing search URLs with an operator hint
   "Search engine endpoint not supported; use DDG: https://duckduckgo.com/html/?q=..."
   Forces the caller to learn the constraint

C — Hybrid: rewrite by default, allow caller to opt out via param
   `fetch(url=google_url, no_rewrite=True)` returns the captcha page faithfully
```

**Chosen: A — rewrite by default.** Reasoning:
- The agent calling a2web doesn't know that Google emits captchas. From the agent's perspective, the URL is just a search query encoded as a URL. The agent's intent is "give me search results for X" — rewriting to DDG honors the intent.
- The block-detector gate is a second-line defense (the captcha-page detector) — if a rewrite ever misses (e.g. a Google redirect we don't recognize), the gate produces a structured `block_page_detected` verdict with an operator hint pointing at the rewrite. Belt-and-suspenders.
- C adds API surface (a new param) for a use case nobody's asked for. Defer until someone has a concrete reason.

The rewrite is logged on the FetchContext as `original_url` so diagnostics remain honest — the response shows "you asked for Google but I fetched DDG; here's why".

Counter cap: `url_rewrites` already capped at 2 per fetch by the playbook. Captcha-rewrite counts against that cap (defense against any future rewrite-chain bug). Today only the captcha rewrite and one playbook rewrite consume the budget; budget is sufficient.

---

## Sequencing within the change

```
1. Reddit search handler           (isolated to handlers/reddit.py + tests)
2. Captcha pre-routing             (isolated to domain.py + fetcher.py orchestrator entry + tests)
3. LLM extras promoted to core     (pyproject.toml + llm_resource.py + operator hints audit)
```

1 and 2 are independent — could parallel. 3 is independent of both but more breaking (changes install size, drops operator-hint flow). Recommend shipping 3 last so the migration's effect on cold start (`Lazy[LlmExtractorResource]` gating) can be measured before the install-size change layers on.
