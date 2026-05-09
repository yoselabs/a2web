# a2web

**Agent-to-Web** — adaptive web fetching MCP server and CLI for AI agents. Sibling to [`a2db`](https://github.com/yoselabs/a2db) and [`a2atlassian`](https://github.com/yoselabs/a2atlassian). Built on [`a2kit`](https://github.com/yoselabs/a2kit).

## Why

Claude Code's `WebFetch` silently fails on Reddit, HN, Cloudflare-protected sites, and JS-heavy SPAs — exactly where the highest-value content lives. Subagents shrug and move on, losing research findings.

a2web is a single tool call (`fetch(url)`) that runs an autonomous tier cascade: site handlers → TLS-impersonating raw fetch → archive fallbacks → Camoufox browser as last resort. It returns the best content it could obtain plus a structured trace (LDD), so the agent never re-decides routing.

## Status

v0.1.0.dev0 — scaffolding. Design in `~/Documents/Knowledge/Projects/120-a2web/`.

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

## Inspecting the log

Every fetch writes one NDJSON record to `~/.a2web/logs/fetches-YYYY-MM-DD.ndjson`
(override the directory with `$A2WEB_LOG_DIR`, disable entirely with
`A2WEB_LOG_ENABLED=false`). Use stdlib Unix tools to inspect:

```bash
# Most recent 20 fetches
tail -n 20 ~/.a2web/logs/fetches-*.ndjson | jq

# All non-ok fetches grouped by host
grep -h '"status":"failed"' ~/.a2web/logs/fetches-*.ndjson \
  | jq -r '"\(.host)\t\(.verdict)"' | sort | uniq -c | sort -rn

# p50/p95 total_ms across the active log
jq -s 'sort_by(.total_ms) | {p50:.[(length*0.5|floor)].total_ms, p95:.[(length*0.95|floor)].total_ms}' \
  ~/.a2web/logs/fetches-*.ndjson
```

Active files rotate at 16 MiB and gzip on rollover (`fetches-YYYY-MM-DD-NN.ndjson.gz`).

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
