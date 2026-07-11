# a2web: deployment / operation lessons

Feedback for the a2web owner, collected while deploying a2web into a homelab as an
MCP-gateway backend + tailnet-direct MCP server (2026-07-11). Each item is friction
a deployer hit, with a concrete suggestion. Grouped by severity.

## Footguns (worth fixing)

### 1. Default model is metered Anthropic

`src/a2web/settings.py` ships `llm_model = "claude-haiku-4-5-20251001"` as the default.
A self-hoster who wires an OpenAI-compatible gateway (`OPENAI_API_KEY` + `OPENAI_BASE_URL`)
but forgets `OPENAI_MODEL` will silently spend on metered Anthropic instead of their
gateway's cheap route. The code comment right there even names DeepSeek V4 Flash as "the
cheapest backend that clears the contract at Haiku-class quality," yet the shipped default
is the expensive metered one.

- Suggestion: default to the benchmarked cheap model, OR when a non-Anthropic
  `OPENAI_BASE_URL` is set, require `OPENAI_MODEL` (fail loud) rather than silently
  falling back to a hardcoded Anthropic id.

### 2. Split env-var namespace: `A2WEB_*` vs unprefixed `OPENAI_*`

Config is split across two prefixes with no signposting in the README:
`A2WEB_ZYTE_KEY`, `A2WEB_CACHE_DIR` (prefixed) but `OPENAI_API_KEY`, `OPENAI_BASE_URL`,
`OPENAI_MODEL` (unprefixed). A deployer reasonably expects all config under `A2WEB_`.
Learning that the model knob is `OPENAI_MODEL` (not `A2WEB_MODEL` / `A2WEB_LLM_MODEL`)
requires reading `settings.py` source, because it is only in code comments.

- Suggestion: accept `A2WEB_MODEL` / `A2WEB_OPENAI_*` aliases, and/or publish one
  copy-pasteable deploy-time env matrix in the README (var, required?, default, meaning).

## Minor friction

### 3. Zyte key: no deploy-time env matrix

The README explains Zyte conceptually but does not surface `A2WEB_ZYTE_KEY` in a
scannable env table, nor say where the key comes from (Zyte dashboard). A deployer has
to grep source to confirm the exact var name and that it is optional (unset = paid tier
disabled, both tools still work). A one-line-per-var table would remove the guesswork.

### 4. Release cadence lags the repo

At deploy time the working tree was `v0.40.0-15-gb0b4c57` (15 commits past the latest
tag), so the newest *published* image was `0.40.0`. Unreleased improvements are not
deployable until tagged + pushed to GHCR. Not a blocker, but worth a note in the README
that deployers should pin the latest published tag/digest, not assume `main` is available.

## What worked well (keep it)

- **Liveness + MCP endpoints are clearly documented** in the Dockerfile: MCP at `/mcp`,
  liveness at `/health`, both on `:8000`, overridable via `A2WEB_HTTP_HOST/PORT`. Made
  the healthcheck + gateway wiring trivial.
- **Config-gated auth is exactly right for a backend-behind-a-gateway**: `GOOGLE_*` unset
  = serve open. Let a2web run as an internal open backend with the gateway owning auth,
  zero code changes.
- **Multi-arch image**: the published `ghcr.io/yoselabs/a2web` is an OCI index (amd64 +
  arm64), so pinning the index digest just works across architectures.
- **Slim default image (~390MB, browserless)**: browser + claude-code are build-arg opt-ins,
  so the default backend footprint is small. Good default.

<!-- Runtime/operation lessons appended after deploy + verify below. -->
