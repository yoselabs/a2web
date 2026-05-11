# v0.3 — engine improvements: design

## Key decisions

### 1. Envelope diet ships as new params, not a new response shape

Three approaches considered:

| Approach | Why rejected / accepted |
|---|---|
| **Rewrite `FetchResponse` to be minimal-by-default** | Breaks parsers; couples envelope policy to schema versioning. |
| **Add a `mode: "full" | "compact"` enum** | One axis collapses what are really three independent toggles (links, diagnostics, debug). |
| **Add three independent params (`include_links`, `debug`)** ✅ | Keeps the schema stable. Caller opts into cost. Mirrors the way `format=auto|json|tsv` already works. |

**`fit_md` is not a param — it's a behavior fix.** The current code populates `fit_md = content_md` because the deprecated pruning filter is gone; this is a leftover defect, not a design choice. The field stays on `FetchResponse` for forward-compat (per CLAUDE.md), it just stays `None` until a real pruning filter ships.

### 2. The diagnostics summary string is additive, not replacing

`FetchResponse.diagnostics` (the typed list) stays. We add `FetchResponse.diagnostics_summary: str` — a one-line `"tier=raw verdict=ok 708ms"` always populated. When `debug=False` (default), the full `diagnostics` list is **omitted from serialization** (not nulled, omitted, so it doesn't even show up as a key). When `debug=True`, both are present.

This keeps the typed shape for in-process callers (tests, internal a2web composition) while compacting the MCP/CLI wire output.

### 3. Length-floor → browser is a gate change, not an orchestrator change

The orchestrator already routes on `suggested_tier` (per existing `quality-gate` spec, browser-tier change `2026-05-10-pr7c`). The defect is that the gate produces `verdict=length_floor` with `suggested_tier=None` even when the prior tier returned a JS-shell signature.

Concrete heuristic for v0.3 (intentionally narrow):

```
if verdict == length_floor:
    body_lower = body[:8192].lower()
    if (
        b"<script" in body_lower
        and (
            b'id="__next"' in body_lower            # next.js shell
            or b'id="root"' in body_lower           # react shell
            or b'id="app"' in body_lower            # vue / generic
            or b"window.__data__" in body_lower     # ember-style
            or b"<noscript>" in body_lower          # progressive enhancement marker
        )
    ):
        suggested_tier = "browser"
```

False-positive surface is "page is mostly empty AND has a JS framework marker." Acceptable — those pages benefit from browser. Future refinement (full DOM-emptiness analysis) is BACKLOG.

### 4. Linear false-positive: separate root-cause investigation

The benchmark shows Linear scored 5/5 on content but `status=failed`. Two possible defects:
- (a) block_detector flags `length_floor` despite content_md having real content
- (b) the path through fetcher.py mismaps verdict → status

The fix is gated on which it is. Investigation task in `tasks.md`; no design commitment until evidence lands. Likely (a) with a too-aggressive length threshold for Linear's compact landing copy.

### 5. Reddit fallback strategy

```
   www.reddit.com/r/X/comments/Y/title/  
     ├── try .json append                              [existing]
     │     ├── 200 + content → render                  ✓ done
     │     ├── 200 + empty thread → fallback           NEW
     │     └── 404 → fallback                          NEW
     │
     └── fallback: GET old.reddit.com/r/X/comments/Y/title/
           └── server-rendered HTML, trafilatura works
```

We do **not** try old.reddit *first* — the `.json` path is faster (one request, structured) when it works. Fallback is purely on failure.

### 6. Twitter/X handler via Nitter

Nitter design constraints:
- Public Nitter instances rotate / die constantly. Hardcoded list is brittle.
- Need rotation + per-instance circuit breaker (we already have `purgatory` infra for proxies — reuse pattern).
- Single config: `A2WEB_NITTER_INSTANCES` env / yaml — comma-separated list. Empty list = handler disabled (returns no-match).

```
handler.matches(url):  host in {x.com, twitter.com, www.x.com, www.twitter.com}
                       AND path matches /<user>/status/<id>(/.*)?

handler.fetch(url):
  for instance in rotate(settings.nitter_instances):
      try:
          GET <instance>/<user>/status/<id>  with 5s timeout
          parse via trafilatura (Nitter is plain HTML)
          return Rendered
      except: continue
  return TierResult(no_match=True)  # falls through to other tiers
```

No external dep — just httpx + trafilatura we already have.

### 7. Anticipatory v0.4 prep: minimal

Two micro-refactors in `benchmarks/vs-webfetch/2026-05-11/`:

- Pull the judge prompt out of `judge.py` into a `prompts.py` module beside it.
- Extract the Anthropic CLI call into a tiny `provider.py` with a `class ClaudeCliProvider` shape that matches the future `Provider` protocol.

No new packages, no new modules, no a2web import changes. Just a refactor that costs ~30 minutes and saves a re-write at v0.4 start.

## Risks

| Risk | Mitigation |
|---|---|
| Callers depend on `links` being present by default | CHANGELOG entry + benchmark evidence (17/20 URLs unchanged). Add a one-line MCP tool description: "for list-extraction tasks, pass `include_links=True`." |
| length_floor heuristic over-triggers browser → cost explosion | Heuristic only fires on the narrow JS-shell pattern. Already gated behind `length_floor` verdict (low base rate). Browser tier remains capped per fetch. |
| Nitter instances all die simultaneously | Handler returns no-match; falls through to raw + browser. Graceful degrade. |
| Reddit old.reddit.com gets blocked too | Add raw + browser fallthrough (already the design). Reddit OAuth is the v0.4+ escalation. |

## What this change does NOT do

- Add LLM-backed extraction (`a2web.llm` is v0.4).
- Change MCP wire format / response schema versioning.
- Touch the proxy pool or browser pool internals beyond the gate fix.
- Add new dependencies (`pyproject.toml` deps stay).
