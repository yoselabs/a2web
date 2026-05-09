## Context

The Tier protocol from PR3 is generic: a `Tier` returns body+headers+verdict, and the orchestrator runs a fixed extraction/gate/cache pipeline on the result. Site handlers don't fit cleanly: they fetch JSON (not HTML), they need URL-pattern matching (not blanket dispatch), and their output IS the rendered markdown (not a body to extract from). PR5 extends the protocol minimally to accommodate them without breaking the raw tier or future tiers.

The two handlers we ship cover the spike's biggest pain — every other site handler in `v0.1-design.md` lands in PR8.

## Goals / Non-Goals

**Goals:**
- A Reddit thread URL produces markdown containing the post + every comment, depth-quoted, in one fetch.
- An HN item URL produces markdown containing the article comment + every reply, depth-quoted, in one fetch.
- The handler dispatch happens before raw and skips raw entirely on match.
- Non-matching URLs route through raw without any diagnostic noise.
- Trafilatura is bypassed for handler results (their output is already markdown).
- The cache stores the raw JSON response so a future re-render uses fresh formatting logic without re-fetching.
- `make check` green, coverage ≥85%.

**Non-Goals:**
- No PRAW / Reddit OAuth (`more` stubs that need it become a noted operator hint).
- No login-walled content. Public threads only.
- No YouTube / Twitter / Substack / arxiv / GitHub / Wikipedia handlers (PR8).
- No image / media extraction beyond `og.image` already handled by the metadata path. Handlers don't yet populate the `meta` envelope dict; that's nice-to-have for PR8.
- No proxy support for handlers (PR7).

## Decisions

### Decision 1: Handlers are tiers, dispatched by a single `"site_handler"` slot

Instead of inserting `RedditHandler`, `HNHandler` etc. as separate entries in `TIER_ORDER`, we register one slot named `"site_handler"` that resolves to a dispatcher. The dispatcher calls `match_handler(url)` and forwards to the matching handler.

Rationale:
- Keeps `TIER_ORDER` short and readable (`("site_handler", "raw", "jina", "archive", "browser")` rather than 8 entries growing to 16).
- One slot means one diagnostic row when handlers DO produce content; "no handler matched" is silent.
- New handlers are added by registering them in `handlers/__init__.py`'s `_HANDLERS` map; no orchestrator change.

**Alternatives considered:**
- Each handler as a separate tier in `TIER_ORDER` → loud (every fetch tries every handler), needs per-handler URL-match prefilter, registry doubles in size. Rejected.
- Single dispatcher tier that itself contains handler classes → same as our choice but with the dispatcher hidden inside the tier object. We expose it as a module-level function for testability. Rejected the "hidden" version.

### Decision 2: Handlers populate `tier_extras["pre_rendered"]` to bypass extraction

The cleanest interface: handlers return a normal `TierResult` (body, content_type, status, etc.), and additionally set `tier_extras["pre_rendered"]` to a dict with `content_md`, `title`, `byline`, `headings`. The orchestrator checks for this extra and, if present, skips the entire trafilatura/htmldate/metadata phase.

This keeps the `Tier` protocol unchanged and makes the bypass opt-in per call. The handler's `body` is the raw JSON we fetched (kept for cache + replay).

```python
return TierResult(
    body=json_bytes,
    content_type="application/json",
    status_code=200,
    final_url=url,
    headers=response.headers,
    tier_extras={
        "pre_rendered": {
            "content_md": rendered_markdown,
            "title": post_title,
            "byline": author,
            "headings": [Heading(level=1, text=post_title)],
        }
    },
)
```

**Alternatives considered:**
- A separate `HandlerResult` class returned through a different interface → splits the code path; orchestrator branches everywhere. Rejected.
- Handlers go through a NEW pipeline step that "extracts" JSON to markdown via a routed extractor → adds a third extractor type for marginal cleanliness. Rejected.

### Decision 3: `match_handler(url)` is a pure function

```python
_HANDLERS: tuple[Tier, ...] = (RedditHandler(), HNHandler())

def match_handler(url: str) -> Tier | None:
    for handler in _HANDLERS:
        if handler.matches(url):
            return handler
    return None
```

Each handler exposes `def matches(self, url: str) -> bool` (sync, regex match). The dispatcher tier in `tiers/site_handler.py` calls `match_handler(url)`; if `None`, returns a sentinel `TierResult` with `tier_extras["no_match"] = True`. The orchestrator interprets that flag as "skip silently."

### Decision 4: Reddit JSON → markdown — depth-quoted comment tree

The Reddit JSON shape:
```
[
  {"data": {"children": [{"data": {<post>}}]}},   # post listing
  {"data": {"children": [{"data": {<comment, kind=t1>}}, {"data": {<more, kind=more>}}]}}  # comments
]
```

Walker:
1. Render post: `# <title>\n\nby <author> — <date>\n\n<post body>\n\n---\n\n## Comments\n\n`
2. For each comment in the tree, render: `> <body>\n>\n> — u/<author>` with `>` repeated by depth.
3. Skip `kind=more` stubs (note in tier_extras: `"more_stubs": <count>`); future PR may PRAW-walk them.

`raw_json=1` strips Reddit's HTML escaping; we still strip leftover markdown-collision characters (`>` at line starts) to keep depth-quoting unambiguous.

### Decision 5: Cache stores the raw JSON; render is per-fetch

Two reasons:
- The JSON is the canonical immutable artifact; the renderer is code we'll iterate on. Caching the rendered markdown means a renderer fix doesn't take effect until the cached entries expire.
- A future PR (PR10's replay) can recompute the rendering from cached bodies. If we cache the rendered text, replay tests rendering bugs we already fixed.

The orchestrator's existing path stores `body` (which is the JSON for handlers) — we just need handlers to set `content_type="application/json"` so a future writer doesn't mistakenly run trafilatura on cached JSON.

### Decision 6: Handlers use `httpx.AsyncClient`, not `curl_cffi`

Reddit and HN APIs are well-behaved JSON endpoints; TLS impersonation buys us nothing. `httpx` is already a declared dep, has saner cookie/redirect handling, and integrates better with future proxy pools (PR7). Per-call `AsyncClient` for now; PR7 introduces a shared client.

### Decision 7: HN handler uses Algolia, not Firebase

Two HN APIs exist: Firebase (`firebaseio.com/v0/item/<id>.json`) and Algolia (`hn.algolia.com/api/v1/items/<id>`). Algolia returns the full kids tree in one call; Firebase requires recursing per-item. Algolia wins on payload, latency, and code complexity.

**Alternatives considered:**
- Firebase for "live" HN items (stories on the front page that change every few minutes) → Firebase has push semantics that could keep cache fresh. Out of scope for v0.1; revisit when PR9's freshness signals land.

## Risks / Trade-offs

- **[Risk] Reddit shutting off `.json` endpoint** → Mitigation: when the JSON path 403s or returns HTML, the handler falls back to `Verdict.connection_error` and the orchestrator continues to raw. Documented in CLAUDE.md "Never" — the handler MUST NOT raise.
- **[Risk] Algolia rate-limiting** → Mitigation: Algolia's free tier is generous (>1000 req/min); v0.1 fetch volumes are nowhere near. Per-host purgatory breaker catches sustained failures.
- **[Risk] HTML in comment bodies (markdown injection / XSS-shaped content)** → Mitigation: we render plain text into the markdown body. Markdown chars like `>`, `_`, `*` are NOT escaped — agents read this as content, not HTML, and the operator's terminal is the consumer. Documented.
- **[Risk] Comment tree depth produces unreadable `>>>>>>` quoting** → Mitigation: depth-quoting is conventional. If it becomes a readability problem in dogfood, we cap at depth 6 in PR8 with a `…` continuation marker.
- **[Risk] `more` stubs lose data on Reddit** → Acknowledged. Operator hint emitted: `code="reddit_more_stubs", message="N replies hidden behind more-stubs; configure Reddit OAuth to expand"`. PR8 may add OAuth.
- **[Risk] Pre-rendered bypass leaves `meta` empty for handler URLs** → Acknowledged. PR8 either adds a metadata path for handlers or accepts that handler envelopes have empty `meta` (the handler-specific signal lives in `title`/`byline`/`headings`).

## Migration Plan

- No schema migration. The cache stores `application/json` bodies for handler hosts going forward; existing rows (if any) for the same URLs continue to be HTML and will simply expire.
- Rollback: revert PR5 — Reddit and HN URLs route to raw again, returning the JS-rendered HTML that the spike showed is unusable.
