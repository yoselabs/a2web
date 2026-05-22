# a2web

**Agent-to-Web** — adaptive web fetching MCP server and CLI for AI agents. Sibling to [`a2db`](https://github.com/yoselabs/a2db) and [`a2atlassian`](https://github.com/yoselabs/a2atlassian). Built on [`a2kit`](https://github.com/yoselabs/a2kit).

## Why

Claude Code's `WebFetch` silently fails on Reddit, HN, Cloudflare-protected sites, and JS-heavy SPAs — exactly where the highest-value content lives. Subagents shrug and move on, losing research findings.

a2web is a single tool call (`fetch(url)`) that runs an autonomous tier cascade: site handlers → TLS-impersonating raw fetch → archive fallbacks → Camoufox browser as last resort. It returns the best content it could obtain plus a structured trace (LDD), so the agent never re-decides routing.

## Status

v0.1.0 — first tagged release; cascade feature-complete. See [`CHANGELOG.md`](./CHANGELOG.md) for what shipped and [`BACKLOG.md`](./BACKLOG.md) for deferred work. Design in `~/Documents/Knowledge/Projects/120-a2web/`.

## Install (when published)

```bash
uv tool install a2web
a2web --help
```

For browser tier:

```bash
uv tool install 'a2web[browser]'
camoufox fetch
```

## Use

```bash
# CLI: in-process, no MCP roundtrip
a2web web fetch --url=https://example.com

# MCP server (stdio)
a2web serve --transport=stdio
```

## Configuration

a2web is zero-config out of the box. To override defaults, drop a YAML at
`~/.a2web/config.yaml` (or set `$A2WEB_CONFIG` to a path of your choice):

```yaml
stealth: true
diagnostics_default: brief
proxies:
  residential_eu:
    url: socks5://user:pass@host:1080
    region: eu
    kind: residential
routes:
  - host: archive.ph
    proxy: residential_eu
    proxy_required: true
live_only_hosts:
  - reddit.com
  - news.ycombinator.com
```

Secrets are env-only — never put them in the YAML:

```bash
export A2WEB_JINA_KEY=...        # optional Jina free-tier API key
export A2WEB_STEALTH=true        # any field overridable via A2WEB_<FIELD>
```

## Link discovery — `next_links` (v0.7)

Every `fetch` response carries a `next_links` field — up to 10 curated "what to fetch next" candidates, each with `anchor`, `url`, `reason`, and `kind` (`drilldown` / `related` / `source`). Two sources feed the field:

- **Tier 1 — site handlers.** Listing-style URLs (Reddit subreddit, HN front page, arXiv `/list/<cat>/<window>`, GitHub repo issue/PR mix, Wikipedia outbound article links) emit candidates deterministically from their structured upstream payloads. Zero LLM cost.
- **Tier 2 — `ask=` LLM extraction.** When a question is set, the extraction prompt asks the LLM to also return up to 10 candidates picked from inline markdown links it just read. Same provider call as the answer — no extra round-trip. URLs that don't appear in the markdown are dropped with an `extraction_drift` diagnostic (hallucination defense).

When both fire, the LLM re-ranks the handler's candidate set against the question, rewriting each `reason` to reflect question-relevance.

Example flow — Reddit listing → individual thread:

```bash
a2web web fetch --url=https://www.reddit.com/r/LocalLLaMA/hot/ --question="threads about RTX 5090 inference"
# response.next_links → [{anchor: "RTX 5090 benchmark...", url: "https://reddit.com/r/.../comments/...", reason: "412 score, 89 comments", kind: "drilldown"}, ...]
# follow up:
a2web web fetch --url=https://reddit.com/r/.../comments/... --question="what model + prompt size?"
```

Pass `next_links=false` on terminal fetches (you know you won't drill down) to save a few hundred output tokens.

## Cookies (v0.8, opt-in)

a2web can mirror your local Chrome (macOS) or Firefox cookies into its own sqlite so fetches arrive logged-in:

```bash
export A2WEB_COOKIE_SOURCE=chrome         # or firefox; default: none
export A2WEB_COOKIE_PROFILE=Default       # Chrome profile name
export A2WEB_COOKIE_STALE_AFTER_HOURS=24  # staleness threshold (default 24)
```

Then run the refresh action — this is the only moment macOS pops a Keychain prompt:

```bash
a2web cookies refresh
```

After that, every `a2web web fetch ...` automatically attaches cookies for the request host to the raw (curl_cffi) and browser (Playwright) tiers. The Jina tier deliberately skips — its reader is third-party.

When the mirror is older than the threshold (or has never been refreshed), every fetch response includes an `OperatorHint(code="cookies_stale", ...)` so agents can branch on `code` and operators see a `Run a2web cookies refresh` suggestion. Cookie values are redacted from all observability output (LDD events, structlog, diagnostics) — only names, hosts, and lengths appear.

macOS Chrome is the only Chrome path in v0.8. Linux/Windows Chrome, Safari, Edge, and Brave are not supported.

## Architecture

a2kit owns the framework surface — MCP server, CLI builder, ConnectionStore, formatter, DI container, schema discovery, testing fixtures, LDD kill-switches.

a2web owns the web-fetching domain logic:

- Tier cascade orchestrator (raw curl_cffi → Jina → Wayback CDX / archive.ph → Camoufox)
- Site handlers (Reddit, HN, YouTube transcript, arxiv, GitHub, Wikipedia, Substack, Twitter)
- Block-page detector / quality gate
- Trafilatura + htmldate extraction; Crawl4AI-style pruning filter for `fit_md`
- Per-host + per-tier proxy routing with circuit breakers
- Conditional GET cache, hedged archive requests, singleflight, retry budget
- Structured LDD (Log-Driven Diagnostics) with adaptive time format

See `~/Documents/Knowledge/Projects/120-a2web/handover.md` for the full design.

## Development

```bash
make bootstrap   # uv sync --all-extras
make check       # lint + ty + test
make fix         # ruff format + auto-fix
make dev         # local stdio MCP server
```

## Benchmark

`make bench` runs the output benchmark — the maintained, package-resident
harness at `src/a2web/llm_eval/`. It runs `eval/corpus.yaml` (Reddit comment
threads, Hacker News comment/item pages, index/listing pages, plus
clean/gated/SPA controls) against three systems — a faithful local
reproduction of Claude Code's `WebFetch` and the two a2web modes — and
scores four axes per (URL, system) cell:

- **answer quality** — LLM judge against per-question criteria
- **token cost** — per-field tokens of the response envelope the agent reads
- **output clarity** — LLM judge: can a downstream agent act on it directly
- **data-contract conformance** — deterministic envelope field-presence check

Listing URLs also get a `next_links_picked_correctly` axis. The run writes a
dated report under `eval/runs/` — see `axes.md` for the per-system table and
the vs-WebFetch delta.

```bash
make bench                          # full matrix
A2WEB_BENCH_PROVIDER=anthropic make bench   # force the provider
```

It prefers the Claude Code OS session (OAuth subscription — no
`ANTHROPIC_API_KEY` needed) and falls back to the Anthropic API provider.
