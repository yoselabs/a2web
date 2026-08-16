# a2web

**Agent-to-Web**: adaptive web fetching as an MCP server and CLI for AI agents. Built directly on [`fastmcp`](https://github.com/jlowin/fastmcp), with shared substrate from [the shelf](https://github.com/yoselabs/shelf).

## Why

Most agent web tools, Claude Code's `WebFetch` included, silently fail on Reddit, Hacker News, Cloudflare-protected sites, and JS-heavy SPAs. That's exactly where the content worth reading lives. The agent gets an empty page or a block screen, shrugs, and moves on. The finding is lost.

a2web turns one tool call into an autonomous tier cascade. Site handlers go first, then a TLS-impersonating raw fetch, then reader and archive fallbacks, with a stealth browser held back as a last resort. You get the best content it could reach, plus a structured trace of how it got there, so the agent never has to re-decide routing.

The primary tool, `query`, goes a step past fetching. It runs a small fast model server-side to pull a focused answer out of the page, so your agent's context stays small. The page gets read for you. Only the answer comes back — plus a cheap index of what was left behind, so withholding the body never hides anything.

## Status

v0.49. Cascade and extraction are feature-complete. See [`CHANGELOG.md`](./CHANGELOG.md) for what shipped. Deferred work is tracked in `bd` (beads); run `bd ready` for what's workable.

## Install

a2web is **not on PyPI** (it depends on git-pinned shelf packages). Install it from
the repo by tag, or pull the published container image — see
[Deployment](#deployment-container) for the container, which is the canonical way
to run it as a service.

```bash
uv tool install 'a2web @ git+https://github.com/yoselabs/a2web@v0.49.0'
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
uv tool install 'a2web[browser,cookies,claude-code] @ git+https://github.com/yoselabs/a2web@v0.49.0'
```

From a clone, `make install-global` does the same with every extra.

### As an MCP server

The canonical deployment is the **container over HTTP** (see
[Deployment](#deployment-container)); point your MCP client at that endpoint:

```json
{
  "mcpServers": {
    "a2web": { "type": "http", "url": "https://<your-gateway>/a2web/mcp" }
  }
}
```

A local install can also serve over stdio, which is handy for development and for
the browser/cookie paths that only work on a real desktop:

```json
{
  "mcpServers": {
    "a2web": { "command": "a2web", "args": ["serve"] }
  }
}
```

## Quickstart

No config needed. `fetch_raw` works with no keys at all; `query` needs an LLM
backend, because the extraction runs server-side.

```bash
# 1. Raw fetch — no keys, no LLM. Proves the cascade works.
a2web web fetch_raw --url=https://news.ycombinator.com/

# 2. Point at any OpenAI-compatible backend (or set ANTHROPIC_API_KEY)
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://api.deepseek.com
export OPENAI_MODEL=deepseek-v4-flash

# 3. Ask the page a question — the model reads it, you get the answer
a2web web query --url=https://news.ycombinator.com/ --query="top stories, AI"
```

You get back an `answer` plus `confidence`, and — since the body was withheld —
`also_here` / `other_pages` telling you what else was on the page and where to go
next. Add `--debug` for the timing, cache, and tier-by-tier trace.

Without an LLM backend, `query` returns a loud `llm_unavailable` operator hint
rather than a silent empty answer.

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `query` | read | The one you'll reach for. Fetches the URL through the cascade, then a small fast model extracts a focused answer to your `query` server-side. Returns a lean answer envelope, not the page. |
| `fetch_raw` | read | Fallback. Same cascade, no LLM. Returns the page itself: `content_md`, headings, links. Use it when you want the raw page or plan to extract yourself. |
| `report_feedback` | write | Report your own subjective read on a fetch that didn't answer what you needed, even if it came back `status: ok` — a2web's own pipeline only catches mechanical failures on its own. Free text (`note`, optional `wanted`), no category to pick. Off by default — same `A2WEB_FEEDBACK_*` config as the automatic reports below. |
| `refresh` (cookies) | write | Refreshes the local browser-cookie mirror so fetches arrive logged-in. Local-only, off by default — set `A2WEB_EXPOSE_COOKIES_TOOL=true` to expose it (see Cookies). The one moment a Keychain prompt may fire. |

### CLI

```bash
# Primary: query a page (server-side extraction)
a2web web query --url=https://example.com --query="return policy"

# Fallback: fetch the raw page, no LLM
a2web web fetch_raw --url=https://example.com

# Refresh the cookie mirror (opt-in; see Cookies)
a2web cookies refresh

# Ops
a2web health            # readiness probe, non-zero exit on degraded
a2web version
```

`--query` takes a terse **query**, not a sentence: drop the verb frame and the
page's own name, keep the target plus at most one operator (`,` list · `vs`
contrast · `/` alternatives), CAPS the word that decides.

The `query` response always carries `answer` and `confidence`. Because the page
body is withheld by default, it also leaves an index of what it did not surface:
`also_here` (same-page content the answer skipped — recovering it is a
cache-served re-query) and `other_pages` (pointers elsewhere, each costing a new
fetch, so they stay sparse). Every URL it emits is traceable to the fetched page;
it never invents one. Failures don't fall silent — you get a `status`, a
`narrative`, a `diagnostics_summary`, and `operator_hints`. Pass `debug=true` for
the full timing, cache, and diagnostics trace, or `include_content=true` to also
get the page markdown for grounding.

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
            ┌───────────▼─────────┐   ┌──────────────────┐   ┌──────────────┐
            │ archive             │   │ browser          │   │ paid         │
            │ Wayback CDX +       │   │ patchright, then │   │ Zyte /       │
            │ archive.ph (hedged) │   │ zendriver (CDP)  │   │ Firecrawl    │
            └─────────────────────┘   └──────────────────┘   └──────────────┘
         dispatched on a playbook    on a gate verdict     opt-in extra
         retry signal                of "browser"
```

- Site handlers turn known sites into clean structured content (and `next_links`) without an LLM: Reddit threads, the HN front page, arXiv listings, GitHub issue/PR mixes, Wikipedia outbound links. URLs they don't match skip silently.
- raw is the common path. `curl_cffi` impersonating a real browser's TLS fingerprint.
- jina wraps `r.jina.ai`. The free tier works without a key; `A2WEB_JINA_KEY` raises the limits.
- archive (Wayback plus archive.ph, hedged in parallel) and browser run out of band, only when the cascade or gate calls for them. The browser tier is two rungs: `patchright` (fast, stealth-patched Chromium) and `browser_robust` (`zendriver`, driving Chrome over CDP) for what the fast rung can't pass. Both come from the shelf's `any-browser` behind the `[browser]` extra.
- paid tiers (Zyte, Firecrawl) are opt-in behind an env key.

Throughout: per-host and per-tier proxy routing with circuit breakers, conditional-GET caching, single-flight, and a bounded retry budget. The quality gate catches block pages and paywalls before they ever enter the cache.

## Link discovery

Because `query` withholds the page body, it must leave a way to reach what it
didn't surface. `other_pages` carries curated "what to fetch next" pointers, each
with a `url`, a `reason`, and a `kind` — `structural` (a deterministic
continuation: pagination, page order) or `drilldown` (a choice that depends on
your question). `fetch_raw` carries the page-shaped `next_links` instead.

Two sources feed it. Site handlers emit candidates deterministically from their
structured upstream payloads, at zero LLM cost — this works on `fetch_raw` too.
The extraction adds candidates picked from links the model just read, on the same
call, with no extra round-trip.

**Every URL is traceable to the fetched page.** The model references links by
handle from a closed set built out of the page's own anchors; a handle that
doesn't resolve is dropped rather than guessed, and a URL that appears nowhere in
the page never ships. A fetcher that invents a plausible-looking URL is worse
than one that admits the link isn't there.

```bash
# Reddit listing, then an individual thread
a2web web query --url=https://www.reddit.com/r/LocalLLaMA/hot/ --query="RTX 5090 inference"
# other_pages -> [{url: "…/comments/…", reason: "412 score, 89 comments", kind: "drilldown"}, …]
a2web web query --url=https://reddit.com/r/.../comments/... --query="model, prompt size"
```

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

## Feedback

a2web reports its own failures back to its maintainers by default — a
best-effort report goes out to a shared gateway whenever a fetch resolves
a warning/critical hint, and whenever an agent calls the `report_feedback`
tool directly. This includes the URL involved and, when an agent calls
`report_feedback`, whatever context it chose to include about what it
expected versus what it got. There's no per-operator setup: the shipped
default endpoint and API key are a shared, write-only, ingest-only
credential meant for exactly this.

This is disclosed to connecting agents directly, in the tool descriptions
themselves (`query`, `fetch_raw`, `report_feedback`) — not only here —
since an agent talking to a2web over MCP has no way to read this file.

To turn it off:

```bash
export A2WEB_FEEDBACK_ENABLED=false
```

Or keep it on but stop sending the raw URL/query/content:

```bash
export A2WEB_FEEDBACK_INCLUDE_CONTENT=false
```

Both are also settable via `~/.a2web/config.yaml`
(`feedback_include_content`; `feedback_api_key` is secret and env-only) or
`docker run -e A2WEB_FEEDBACK_ENABLED=false ...`.

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
`A2WEB_GOOGLE_CLIENT_ID` / `A2WEB_GOOGLE_CLIENT_SECRET` / `A2WEB_GOOGLE_BASE_URL`
are all set (per
a FastMCP `GoogleProvider`; no auth abstraction of a2web's own). Unset → open, as
above. Partial config (id without secret/base_url)
fails loud at boot rather than silently serving open.

> **The `A2WEB_` prefix is mandatory on these.** a2web reads settings with
> `env_prefix="A2WEB_"`, so an unprefixed `GOOGLE_*` name reaches nothing — auth
> stays off and the endpoint serves **unauthenticated**, with no error. This
> README documented the bare spelling until 2026-08-01; `a2web-serve` now
> refuses to start when it finds bare auth vars and no prefixed ones.

```bash
docker run -d --name a2web -p 8000:8000 -v a2web-cache:/data \
  -e OPENAI_API_KEY=... -e OPENAI_BASE_URL=https://api.deepseek.com -e OPENAI_MODEL=deepseek-v4-flash \
  -e A2WEB_GOOGLE_CLIENT_ID=...apps.googleusercontent.com \
  -e A2WEB_GOOGLE_CLIENT_SECRET=... \
  -e A2WEB_GOOGLE_BASE_URL=https://a2web.example.com \
  -e A2WEB_GOOGLE_JWT_SIGNING_KEY="$(openssl rand -hex 32)" \
  ghcr.io/yoselabs/a2web:latest
```

Setup:

1. Create a GCP OAuth **client** (Web application) and add
   `https://a2web.example.com/auth/callback` (your `A2WEB_GOOGLE_BASE_URL` + FastMCP's
   redirect path) as an authorized redirect URI.
2. **`A2WEB_GOOGLE_BASE_URL` MUST be the public URL** clients reach — the OAuth redirect
   derives from it. It is **not** the bind host (`0.0.0.0`). Getting this wrong is
   the #1 failure mode.
3. Recommended: set a stable `A2WEB_GOOGLE_JWT_SIGNING_KEY` (`openssl rand -hex 32`) so
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
| `A2WEB_LLM_PROVIDER` | Pin the backend instead of auto-selecting: `auto` (default), `openai-compatible`, `anthropic-api`, `claude-code-sdk`, `claude-code-cli`. These are `anyllm.ProviderName` values — the pre-rename spellings (`anthropic`, `claude-code`, `openai_compatible`) now fail at settings construction. Pin it when you want a deterministic backend and no fallback — a pinned provider that is unavailable fails loudly instead of silently selecting another. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Only for the `claude-code` backend. That backend needs a logged-in Claude Code **session**, not just the installed package — the `claude-agent-sdk` extra bundles its own CLI, so a container has the binary but no session. Without a session (token, `~/.claude/.credentials.json`, or a macOS Keychain entry) it reports unavailable and auto-selection moves on. |
| **Paid + token tiers** (all optional) | |
| `A2WEB_ZYTE_KEY` | Paid Zyte tier (Reddit thread depth + hard walls). |
| `A2WEB_FIRECRAWL_KEY` | Paid Firecrawl tier (needs the `[paid]` extra). |
| `A2WEB_JINA_KEY` | Jina reader — raises the keyless free-tier limits. |
| `A2WEB_GITHUB_TOKEN` | GitHub handler token — raises the API rate limit 60 → 5000 req/hr. Set this if you fetch GitHub issues/PRs at any volume. |
| `A2WEB_REDDIT_TIER_POLICY` | `robustness` (default: Reddit → Zyte → RSS) or `privacy` (RSS-only; no third party ever sees the URL). |
| **Failure-feedback reporting (opt-in, off by default)** | |
| `A2WEB_FEEDBACK_ENABLED` | `true` to report a diagnostic event whenever a fetch resolves a warning/critical `OperatorHint`: hint code/severity/fix, the full tier-escalation chain (every attempt, not just the last), the fetch's terminal status/content-type/cache-state, what was expected (`query` wants an extracted answer, `fetch_raw` wants raw content) vs. the actual result status/confidence the caller received, and a2web version. Unset → a2web sends nothing to any endpoint, ever. Requires `A2WEB_FEEDBACK_ENDPOINT` and `A2WEB_FEEDBACK_API_KEY` to also be set — no shipped default endpoint. |
| `A2WEB_FEEDBACK_ENDPOINT` | OTLP/HTTP logs endpoint to report to (e.g. your own OTel Collector). |
| `A2WEB_FEEDBACK_API_KEY` | Sent as the `X-Api-Key` header (not `Authorization: Bearer`) — match your gateway's expected auth scheme. |
| `A2WEB_FEEDBACK_INCLUDE_CONTENT` | `true` to include the raw requested/final URL and query text in reports, as `requested_url`/`final_url`/`requested_query` fields — the narrative message text also stops being redacted locally, but treat the dedicated fields as the authoritative source: a receiving gateway may still redact the narrative text on its own policy regardless of this flag (a2web has no control over that once the report leaves the process). Default `false`, and every known fetch URL is replaced with `[url-redacted]` in the narrative text when off. |
| **Storage + surface** | |
| `A2WEB_CACHE_DIR` | sqlite HTTP-cache dir. Defaults to `/data` in the image; back it with a volume so the cache survives restarts. |
| `A2WEB_EXPOSE_COOKIES_TOOL` | Leave **unset** on a server (the cookie mirror is local-only). Set `true` only for a local `serve`. |
| `A2WEB_HTTP_HOST` / `A2WEB_HTTP_PORT` | Bind host/port for the `a2web-serve` entrypoint (defaults `0.0.0.0` / `8000`). |
| **Auth (Google OAuth — optional)** | |
| `A2WEB_GOOGLE_CLIENT_ID` + `A2WEB_GOOGLE_CLIENT_SECRET` | GCP OAuth client. Both (with `A2WEB_GOOGLE_BASE_URL`) turn auth on; unset → open. **The `A2WEB_` prefix is required** — bare `GOOGLE_*` is read by nothing, and a2web now refuses to boot on it rather than serving open. |
| `A2WEB_GOOGLE_BASE_URL` | **Public** URL clients reach — the OAuth redirect derives from it (NOT the bind host). |
| `A2WEB_GOOGLE_JWT_SIGNING_KEY` | `openssl rand -hex 32` — stable signing key so sessions survive restarts. Recommended. |
| `A2WEB_GOOGLE_REQUIRED_SCOPES` | OAuth scopes (default `openid,email`). |
| `A2WEB_OAUTH_CACHE_DIR` / `A2WEB_OAUTH_ENCRYPTION_KEY` | Token-store dir (default `<cache_dir>/oauth`) + optional Fernet passphrase to encrypt it at rest. |
| `A2WEB_*` | Any other `AppSettings` field (`A2WEB_STEALTH`, `A2WEB_DIAGNOSTICS_DEFAULT`, `A2WEB_BROWSER_MAX_POOL`, cache TTLs, …). |

Without any LLM key the container still serves `fetch_raw` (raw pages, no
extraction); `query` returns a loud `llm_unavailable` operator hint rather than a
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

a2web composes on `fastmcp` directly and owns its own spine — server composition, the Typer CLI (derived from the registered MCP tools, so `--help` and the MCP `inputSchema` cannot disagree), a single composition root with `Lazy[T]` thunks, LIFO resource lifecycle, wire encoding, and the typed error envelope. Shared, substrate-level pieces come from [the shelf](https://github.com/yoselabs/shelf) (`anyllm`, `any-browser`, `llm-wobble`, `llm-cache`, `lean-wire`, `http-cache`, …).

On top of that, a2web owns the web-fetching domain:

- The tier-cascade orchestrator, its quality gate, and the escalation playbook.
- Site handlers: `arxiv`, `discourse`, `github`, `habr`, `hn`, `reddit`, `twitter`, `v2ex`, `wikipedia`.
- Content extraction: Trafilatura, date detection, structured-record and microdata extraction.
- Per-host and per-tier proxy routing with `purgatory` circuit breakers.
- Server-side LLM extraction for `query`, with a wobble-tolerant JSON contract parser.
- The browser-cookie mirror.

Heavy resources (the browser pool, the LLM extractor, the cookie jar) are injected lazily. They start on the first fetch that needs them, which keeps cold start cheap.

## Contributing

```bash
make bootstrap   # uv sync --all-extras
make check       # lint + ty + test (coverage >= 85%) — the gate
make fix         # ruff format + auto-fix
make arch        # architecture invariants only
make dev         # local stdio MCP server
make install-global   # optional: rebuild and reinstall the local uv tool
```

`make check` is the gate — it must be green before anything lands.

Two documents are worth reading before a non-trivial change.
[`CONSTITUTION.md`](./CONSTITUTION.md) governs what belongs in the product versus
shared substrate, when a dependency may be adopted, and how much magic is
allowed. [`docs/architecture/`](./docs/architecture/) explains the invariants
enforced by `make arch` — module boundaries live in `tach.toml`, and call-site
and class-shape rules live as AST tests under `tests/architecture/`. Adding a new
invariant means writing a test; landing a violation fails CI.

One house rule that will otherwise surprise you: **a structural guard must assert
it found something.** A walk that reports "0 violations in 0 candidates" is
indistinguishable from a passing one, and this repo has been burned by exactly
that more than once. Pair every walk with a floor, every golden set with a count.

## Benchmark

`make bench` runs the output benchmark (`src/a2web/llm_eval/`, corpus `eval/corpus.yaml`). It scores three systems, a faithful reproduction of Claude Code's `WebFetch` plus the two a2web modes, across four axes: answer quality (LLM judge), token cost, output clarity (LLM judge), and data-contract conformance (a deterministic field-presence check). Listing URLs get an extra `next_links` axis.

It hits the live network and spends LLM quota, so it stays out of `make check` on purpose. Reports land under `eval/runs/`.

```bash
make bench
A2WEB_BENCH_PROVIDER=anthropic make bench   # opt in to the metered API (cheap models only)
```

It defaults to the Claude Code OS session — a flat subscription, no
`ANTHROPIC_API_KEY` needed. If that session is missing it **fails loudly** rather
than falling through to the metered API: a silent fallback there is a surprise
bill, not a graceful degrade. Every call passes a cost guard that asserts the
resolved `(provider, model)` pair before spending, so an expensive model on a
metered backend raises instead of billing.

## License

[Apache-2.0](./LICENSE) — © 2026 Denis Tomilin.
