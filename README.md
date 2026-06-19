# a2web

**Agent-to-Web**: adaptive web fetching as an MCP server and CLI for AI agents. Sibling to [`a2db`](https://github.com/yoselabs/a2db) and [`a2atlassian`](https://github.com/yoselabs/a2atlassian). Built on [`a2kit`](https://github.com/yoselabs/a2kit).

## Why

Most agent web tools, Claude Code's `WebFetch` included, silently fail on Reddit, Hacker News, Cloudflare-protected sites, and JS-heavy SPAs. That's exactly where the content worth reading lives. The agent gets an empty page or a block screen, shrugs, and moves on. The finding is lost.

a2web turns one tool call into an autonomous tier cascade. Site handlers go first, then a TLS-impersonating raw fetch, then reader and archive fallbacks, with a stealth browser held back as a last resort. You get the best content it could reach, plus a structured trace of how it got there, so the agent never has to re-decide routing.

The primary tool, `ask`, goes a step past fetching. It runs a small fast model server-side to pull a focused answer out of the page, so your agent's context stays small. The page gets read for you. Only the answer comes back.

## Status

v0.23, on `a2kit` v0.44. Cascade and extraction are feature-complete. See [`CHANGELOG.md`](./CHANGELOG.md) for what shipped and [`BACKLOG.md`](./BACKLOG.md) for deferred work.

## Install

```bash
uv tool install a2web
a2web --help
```

The stealth browser tier ships in the base install: the `camoufox` Firefox binary, around 150 MB. First browser use pulls it once.

```bash
python -m camoufox fetch
```

Optional paid tier (Firecrawl, env-gated):

```bash
uv tool install 'a2web[paid]'
```

### As an MCP server

Point your MCP client at the installed binary over stdio. For Claude Code:

```json
{
  "mcpServers": {
    "a2web": { "command": "a2web", "args": ["serve"] }
  }
}
```

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `ask` | read | The one you'll reach for. Fetches the URL through the cascade, then a small fast model (Claude Haiku 4.5 by default) extracts a focused answer to your `question` server-side. Returns a lean answer envelope, not the page. |
| `fetch_raw` | read | Fallback. Same cascade, no LLM. Returns the page itself: `content_md`, headings, links. Use it when you want the raw page or plan to extract yourself. |
| `refresh` (cookies) | write | Refreshes the local browser-cookie mirror so fetches arrive logged-in. The one moment a Keychain prompt may fire. |

### CLI

```bash
# Primary: ask a question about a page (server-side extraction)
a2web web ask --url=https://example.com --question="What does this say about X?"

# Fallback: fetch the raw page, no LLM
a2web web fetch_raw --url=https://example.com

# Refresh the cookie mirror (opt-in; see Cookies)
a2web cookies refresh

# Introspection
a2web list-tools        # every registered tool plus its declared errors
a2web schema            # tool input/output schemas
a2web health            # aggregated health probe, non-zero exit on degraded
```

The `ask` response always carries `answer` and `confidence`, a `structural_form` and `shape` classification of the page, and curated `next_links` on listings. Failures don't fall silent. You get a `status`, a `narrative`, a `diagnostics_summary`, and `operator_hints`. Pass `debug=true` for the full timing, cache, and diagnostics trace. Pass `include_content=true` to also get the page markdown for grounding.

## The tier cascade

The orchestrator walks tiers in order, runs a quality gate after each, and escalates only when the gate isn't satisfied. Expensive tiers are capped at one attempt per fetch.

```
                 ┌─────────────┐
   url ─────────▶│ site_handler│  Reddit, HN, arXiv, GitHub, Wikipedia,
                 └──────┬──────┘  Discourse, Habr, v2ex, Twitter/X
                        │ (no match / insufficient)
                 ┌──────▼──────┐
                 │     raw     │  curl_cffi, TLS/JA3 impersonation
                 └──────┬──────┘
                        │ gate unsatisfied
                 ┌──────▼──────┐
                 │    jina     │  r.jina.ai reader (free tier works keyless)
                 └──────┬──────┘
                        │
        out-of-band ────┼──────────────────────────────────────────
                        │
            ┌───────────▼─────────┐   ┌──────────────┐   ┌──────────┐
            │ archive             │   │ browser      │   │ paid     │
            │ Wayback CDX +       │   │ Camoufox     │   │ Firecrawl│
            │ archive.ph (hedged) │   │ (stealth FF) │   │ env-gated│
            └─────────────────────┘   └──────────────┘   └──────────┘
         dispatched on a playbook    on a gate verdict     opt-in extra
         retry signal                of "browser"
```

- Site handlers turn known sites into clean structured content (and `next_links`) without an LLM: Reddit threads, the HN front page, arXiv listings, GitHub issue/PR mixes, Wikipedia outbound links. URLs they don't match skip silently.
- raw is the common path. `curl_cffi` impersonating a real browser's TLS fingerprint.
- jina wraps `r.jina.ai`. The free tier works without a key; `A2WEB_JINA_KEY` raises the limits.
- archive (Wayback plus archive.ph, hedged in parallel) and browser (Camoufox, a stealth-patched Firefox driven through Playwright, with locale, timezone, and geo aligned to the egress IP) run out of band, only when the cascade or gate calls for them.
- paid (Firecrawl) is opt-in behind the `[paid]` extra and an env key.

Throughout: per-host and per-tier proxy routing with circuit breakers, conditional-GET caching, single-flight, and a bounded retry budget. The quality gate catches block pages and paywalls before they ever enter the cache.

## Link discovery: `next_links`

Every response can carry up to 10 curated "what to fetch next" candidates. Each one has an `anchor`, a `url`, a `reason`, and a `kind` (`drilldown`, `related`, `source`, or `discussion`). Two sources feed it.

Site handlers emit candidates deterministically from their structured upstream payloads, at zero LLM cost. This works on `fetch_raw` too.

The `ask=` extraction adds candidates picked from inline links the model just read, on the same call, no extra round-trip. A URL that isn't present in the page markdown gets dropped with an `extraction_drift` diagnostic. That's the hallucination defense. When both sources fire, the model re-ranks the handler's candidates against your question.

```bash
# Reddit listing, then an individual thread
a2web web ask --url=https://www.reddit.com/r/LocalLLaMA/hot/ --question="threads about RTX 5090 inference"
# next_links -> [{anchor: "RTX 5090 benchmark…", url: "…/comments/…", reason: "412 score, 89 comments", kind: "drilldown"}, …]
a2web web ask --url=https://reddit.com/r/.../comments/... --question="what model and prompt size?"
```

Pass `next_links=false` on terminal fetches to save a few hundred output tokens.

## Configuration

a2web runs with no config. To override the defaults, drop a YAML at `~/.a2web/config.yaml`, or set `$A2WEB_CONFIG` to a path of your choice. `${ENV_VAR}` references inside the YAML resolve at load time.

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

Any field is overridable via `A2WEB_<FIELD>`. Secrets are env-only. Keep them out of the YAML.

```bash
export A2WEB_JINA_KEY=...     # optional Jina free-tier API key
export A2WEB_STEALTH=true
```

## Cookies (opt-in)

a2web can mirror your local browser cookies into its own sqlite, so fetches arrive logged-in. It leans on `browser-cookie3`, which is cross-platform (macOS, Linux, Windows) and reads most browsers (Chrome, Chromium, Brave, Edge, Firefox, Safari).

```bash
export A2WEB_COOKIE_SOURCE=chrome         # or firefox, brave, …; default: none
export A2WEB_COOKIE_PROFILE=Default
export A2WEB_COOKIE_STALE_AFTER_HOURS=24
a2web cookies refresh                     # the only moment a Keychain prompt may fire
```

After a refresh, every fetch attaches cookies for the request host to the raw (`curl_cffi`) and browser tiers. The Jina tier skips them on purpose, since its reader is third-party. When the mirror goes stale, or was never refreshed, responses carry an `OperatorHint(code="cookies_stale", …)`, so agents can branch on it and operators see a "run `a2web cookies refresh`" suggestion. Cookie values are redacted everywhere a2web logs. Only names, hosts, and lengths show up.

## Architecture

`a2kit` (v0.44) owns the framework: the MCP server and Typer CLI, dependency injection (`Lazy[T]` plus per-resource providers), resource lifecycle, the type-driven formatter (JSON, TSV, page-TSV), schema discovery, in-process testing, and typed diagnostic events on stdlib `logging`.

a2web owns the web-fetching domain:

- The tier-cascade orchestrator, its quality gate, and the escalation playbook.
- Site handlers: `arxiv`, `discourse`, `github`, `habr`, `hn`, `reddit`, `twitter`, `v2ex`, `wikipedia`.
- Content extraction: Trafilatura, date detection, structured-record and microdata extraction.
- Per-host and per-tier proxy routing with `purgatory` circuit breakers.
- Server-side LLM extraction for `ask`, with a wobble-tolerant JSON contract parser.
- The browser-cookie mirror.

Heavy resources (the browser pool, the LLM extractor, the cookie jar) are injected lazily. They start on the first fetch that needs them, which keeps cold start cheap.

## Development

```bash
make bootstrap   # uv sync --all-extras
make check       # lint + ty + test (coverage >= 85%)
make fix         # ruff format + auto-fix
make dev         # local stdio MCP server
make install-global   # rebuild and reinstall the global uv tool
```

## Benchmark

`make bench` runs the output benchmark (`src/a2web/llm_eval/`, corpus `eval/corpus.yaml`). It scores three systems, a faithful reproduction of Claude Code's `WebFetch` plus the two a2web modes, across four axes: answer quality (LLM judge), token cost, output clarity (LLM judge), and data-contract conformance (a deterministic field-presence check). Listing URLs get an extra `next_links` axis.

It hits the live network and spends LLM quota, so it stays out of `make check` on purpose. Reports land under `eval/runs/`.

```bash
make bench
A2WEB_BENCH_PROVIDER=anthropic make bench   # force the provider
```

It prefers the Claude Code OS session (the OAuth subscription, no `ANTHROPIC_API_KEY` needed) and falls back to the Anthropic API provider.

## License

Apache-2.0, © Denis Tomilin
