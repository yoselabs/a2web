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

The base install is lean. Heavy, situational capabilities are opt-in extras so a
server deployment stays small:

| Extra | Adds | For |
|---|---|---|
| `[browser]` | patchright + zendriver (stealth Chromium rungs) | JS-heavy / hard anti-bot sites without a paid tier. First browser use pulls a Chromium once. |
| `[cookies]` | `browser-cookie3` | mirroring your *local* browser cookies (local-only; see Cookies). |
| `[claude-code]` | `claude-agent-sdk` | the Claude Code OS-session LLM backend (OAuth piggyback). |
| `[paid]` | `firecrawl-py` | the env-gated Firecrawl paid tier. |

```bash
uv tool install 'a2web[browser,cookies,claude-code]'   # full local experience
```

`make install-global` installs all of these for the local Claude Code MCP server.

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
| `refresh` (cookies) | write | Refreshes the local browser-cookie mirror so fetches arrive logged-in. Local-only, off by default — set `A2WEB_EXPOSE_COOKIES_TOOL=true` to expose it (see Cookies). The one moment a Keychain prompt may fire. |

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

## Deployment (container)

a2web publishes a public image to GHCR that any homelab instance can pull and
run as a networked MCP service. It serves MCP under `/mcp` (HTTP transport,
MCP-only) plus a transport-native liveness route at `/health`. The published
image includes the browser rendering tier (patchright + zendriver + baked
Chromium) so browser escalation works out of the box — allow ~1.5-2 GB RAM.

```bash
docker pull ghcr.io/yoselabs/a2web:latest

docker run -d --name a2web -p 8000:8000 \
  -v a2web-cache:/data \
  -e OPENAI_API_KEY=... \
  -e OPENAI_BASE_URL=https://api.deepseek.com \
  -e OPENAI_MODEL=deepseek-v4-flash \
  ghcr.io/yoselabs/a2web:latest
# MCP:      http://<host>:8000/mcp
# liveness: http://<host>:8000/health   -> 200 {"status":"ok"}
```

> ⚠️ **Unauthenticated by default.** With no `GOOGLE_*` config, the HTTP endpoint
> is open — do **not** expose port 8000 to the public internet; run it behind
> Tailscale or a private LAN. To expose it publicly, configure **Google OAuth**
> (below).

### Authentication (optional, Google OAuth)

The container serves via `a2web-serve`, which turns on Google OAuth when
`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_BASE_URL` are all set (per
a2kit's blessed MCP-auth recipe — a FastMCP `GoogleProvider`, no a2kit auth
abstraction). Unset → open, as above. Partial config (id without secret/base_url)
fails loud at boot rather than silently serving open.

```bash
docker run -d --name a2web -p 8000:8000 -v a2web-cache:/data \
  -e OPENAI_API_KEY=... -e OPENAI_BASE_URL=https://api.deepseek.com -e OPENAI_MODEL=deepseek-v4-flash \
  -e GOOGLE_CLIENT_ID=...apps.googleusercontent.com \
  -e GOOGLE_CLIENT_SECRET=... \
  -e GOOGLE_BASE_URL=https://a2web.example.com \
  -e GOOGLE_JWT_SIGNING_KEY="$(openssl rand -hex 32)" \
  ghcr.io/yoselabs/a2web:latest
```

Setup:

1. Create a GCP OAuth **client** (Web application) and add
   `https://a2web.example.com/auth/callback` (your `GOOGLE_BASE_URL` + FastMCP's
   redirect path) as an authorized redirect URI.
2. **`GOOGLE_BASE_URL` MUST be the public URL** clients reach — the OAuth redirect
   derives from it. It is **not** the bind host (`0.0.0.0`). Getting this wrong is
   the #1 failure mode.
3. Recommended: set a stable `GOOGLE_JWT_SIGNING_KEY` (`openssl rand -hex 32`) so
   tokens survive restarts. OAuth sessions persist in an encrypted-optional
   FileTree store under `/data/oauth` (back the volume). Set
   `A2WEB_OAUTH_ENCRYPTION_KEY` to encrypt the store at rest.
4. Gate access with the GCP consent screen's test-user list (the GCP project *is*
   the allowlist — keep none in code).

**Operator verification** (not automated — needs the live GCP client): an
anonymous `curl`/MCP request to `/mcp` is rejected; a browser OAuth login admits
the Google principal.

**Environment matrix** (secrets are env-only, never baked into a layer). Every
`AppSettings` field is settable as `A2WEB_<FIELD>` (case-insensitive; nested via
`__`) — the full list lives in `src/a2web/settings.py`. The deployment-relevant
ones:

> **Two namespaces, on purpose.** a2web's *own* configuration is `A2WEB_`-prefixed.
> LLM backend credentials use the **unprefixed industry-standard names** —
> `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY` — so the
> same env that works for every other SDK works here, with no translation layer. If
> you need a different variable name (e.g. `OPENROUTER_API_KEY`), redirect it with
> `A2WEB_LLM_OPENAI_API_KEY_ENV` rather than copying the secret.

| Variable | Purpose |
|---|---|
| **LLM backend** | |
| `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL` | OpenAI-compatible LLM backend — the container default. Point at DeepSeek / OpenAI / Gemini / OpenRouter / a local endpoint. Unset base URL → OpenAI proper. Setting **both** key and base URL marks this an *explicit* gateway: it then leads `auto` selection and cannot be shadowed by another backend. |
| `ANTHROPIC_API_KEY` | Alternative LLM backend (Anthropic Messages API). Preferred over an openai-compatible backend that was configured by key alone; an explicit gateway (key + base URL) still wins. |
| `A2WEB_LLM_OPENAI_API_KEY_ENV` | Rename the key env var a2web reads for the OpenAI-compatible backend (default `OPENAI_API_KEY`; set to `OPENROUTER_API_KEY` etc.). `A2WEB_LLM_API_KEY_ENV` does the same for the Anthropic key. |
| `A2WEB_LLM_MODEL` | Override the extraction model. Note `OPENAI_MODEL` wins for the openai-compatible backend, so a Claude id is never sent to an OpenAI endpoint. |
| `A2WEB_LLM_PROVIDER` | Pin the backend instead of auto-selecting: `auto` (default), `openai_compatible`, `anthropic`, `claude-code`. Pin it when you want a deterministic backend and no fallback — a pinned provider that is unavailable fails loudly instead of silently selecting another. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Only for the `claude-code` backend. That backend needs a logged-in Claude Code **session**, not just the installed package — the `claude-agent-sdk` extra bundles its own CLI, so a container has the binary but no session. Without a session (token, `~/.claude/.credentials.json`, or a macOS Keychain entry) it reports unavailable and auto-selection moves on. |
| **Paid + token tiers** (all optional) | |
| `A2WEB_ZYTE_KEY` | Paid Zyte tier (Reddit thread depth + hard walls). |
| `A2WEB_FIRECRAWL_KEY` | Paid Firecrawl tier (needs the `[paid]` extra). |
| `A2WEB_JINA_KEY` | Jina reader — raises the keyless free-tier limits. |
| `A2WEB_GITHUB_TOKEN` | GitHub handler token — raises the API rate limit 60 → 5000 req/hr. Set this if you fetch GitHub issues/PRs at any volume. |
| `A2WEB_REDDIT_TIER_POLICY` | `robustness` (default: Reddit → Zyte → RSS) or `privacy` (RSS-only; no third party ever sees the URL). |
| **Storage + surface** | |
| `A2WEB_CACHE_DIR` | sqlite HTTP-cache dir. Defaults to `/data` in the image; back it with a volume so the cache survives restarts. |
| `A2WEB_EXPOSE_COOKIES_TOOL` | Leave **unset** on a server (the cookie mirror is local-only). Set `true` only for a local `serve`. |
| `A2KIT_MCP__CODE_MODE` | `true` re-enables a2kit's code-execution sandbox (search/get_schema/execute meta-tools). a2web ships it off; only flip per-deployment if a client needs it. |
| `A2WEB_HTTP_HOST` / `A2WEB_HTTP_PORT` | Bind host/port for the `a2web-serve` entrypoint (defaults `0.0.0.0` / `8000`). |
| **Auth (Google OAuth — optional)** | |
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | GCP OAuth client. Both (with `GOOGLE_BASE_URL`) turn auth on; unset → open. |
| `GOOGLE_BASE_URL` | **Public** URL clients reach — the OAuth redirect derives from it (NOT the bind host). |
| `GOOGLE_JWT_SIGNING_KEY` | `openssl rand -hex 32` — stable signing key so sessions survive restarts. Recommended. |
| `GOOGLE_REQUIRED_SCOPES` | OAuth scopes (default `openid,email`). |
| `A2WEB_OAUTH_CACHE_DIR` / `A2WEB_OAUTH_ENCRYPTION_KEY` | Token-store dir (default `<cache_dir>/oauth`) + optional Fernet passphrase to encrypt it at rest. |
| `A2WEB_*` | Any other `AppSettings` field (`A2WEB_STEALTH`, `A2WEB_DIAGNOSTICS_DEFAULT`, `A2WEB_BROWSER_MAX_POOL`, cache TTLs, …). |

Without any LLM key the container still serves `fetch_raw` (raw pages, no
extraction); `ask` returns a loud `llm_unavailable` operator hint rather than a
silent empty answer.

**Liveness** is wired as a Docker `HEALTHCHECK` (`curl -f /health`) against the
live serve process.

**The published image bakes in the browser rendering tier** (patchright +
zendriver + Chromium + its desktop system-lib tree, `INSTALL_BROWSER=true`),
so browser escalation works without any extra setup — image size ~1.9 GB.
The Claude Code OS-session backend (`claude-agent-sdk`) stays a **build-arg
opt-in** (not published), since the container's default LLM backend is
OpenAI-compatible:

| Build arg | Adds | When you need it |
|---|---|---|
| `--build-arg INSTALL_CLAUDE_CODE=true` | `claude-agent-sdk` (~210 MB) | the Claude Code OS-session LLM backend (OAuth piggyback). |

A slimmer, browserless image (~390 MB) can still be built locally by omitting
`INSTALL_BROWSER` — useful when you lean entirely on `A2WEB_ZYTE_KEY` for hard
sites and want to skip the ~1.35 GB Chromium layer:

```bash
docker build -t a2web-slim .
```

On a browserless container, a browser-only site degrades **loudly** — it
returns a critical `try_user_browser` operator hint, never a silent empty
result.

**Publishing** is automated: pushing a `v*` tag runs the quality gate, then
builds and pushes `ghcr.io/yoselabs/a2web:{version,latest}` with the browser
tier baked in (`.github/workflows/release.yml`). One-time after the first
publish: set the GHCR package visibility to **Public** so `docker pull` needs
no auth.

## Cookies (opt-in, local-only)

a2web can mirror your local browser cookies into its own sqlite, so fetches arrive logged-in. It leans on `browser-cookie3` (the `[cookies]` extra), which is cross-platform (macOS, Linux, Windows) and reads most browsers (Chrome, Chromium, Brave, Edge, Firefox, Safari).

This is a **local-only** feature: it reads the cookie store on the machine a2web runs on, so it does nothing useful in a server container (there's no browser there). Two independent switches guard it:

- `[cookies]` **extra** — controls whether it can *function*. `make install-global` installs it; the published container omits it. Absent → `cookies_refresh` returns a loud "install `a2web[cookies]`" note.
- `expose_cookies_tool` **toggle** (default `false`) — controls whether the `cookies_refresh` tool is even *exposed*. A server never registers it; set `A2WEB_EXPOSE_COOKIES_TOOL=true` for a local `serve` (or CLI use) where you want it.

```bash
export A2WEB_EXPOSE_COOKIES_TOOL=true      # register the tool (default: off, server-safe)
export A2WEB_COOKIE_SOURCE=chrome          # or firefox, brave, …; default: none
export A2WEB_COOKIE_PROFILE=Default
export A2WEB_COOKIE_STALE_AFTER_HOURS=24
a2web cookies refresh                      # the only moment a Keychain prompt may fire
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
