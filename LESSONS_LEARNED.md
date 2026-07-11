# a2web: deployment / operation lessons

Feedback for the a2web owner, collected while deploying a2web into a homelab as an
MCP-gateway backend + tailnet-direct MCP server (2026-07-11). Each item is friction
a deployer hit, with a concrete suggestion. Grouped by severity.

## Footguns (worth fixing)

### 0. CRITICAL: `query` returns empty answers — the 1024-token extraction cap truncates the contract-v2 JSON

On a homelab deploy (0.44.0 and 0.44.1), `query` returned `extraction_empty` (answer `""`,
`also_here`/`other_pages`/`structural_form` all `None`) on ordinary content pages
(en.wikipedia.org/wiki/Home_Assistant, /wiki/Nginx), while `fetch_raw` and plain LLM
completions worked fine. Reproduced across THREE models — `deepseek-v4-flash`,
`deepseek-chat`, `gpt-4.1-mini` — and BOTH image versions, so it is neither model- nor
version-specific.

Root cause (traced to source): `Extractor` hardcodes `max_tokens=1024`
(`packages/llm_extract/extractor.py:105`) and is constructed in `llm_resource.py:137`
WITHOUT any settings/env override — `settings.py` has no extraction-token field. The
router-shape JSON output (answer + `also_here` + `other_pages`, enlarged by the 0.41
contract-v2) overflows 1024 on link-rich pages, so the model's JSON truncates, the wobble
parser (`_first_json_object`) finds no complete object, and everything comes back empty.
This is EXACTLY the failure the 2026-07-05 bench already documented ("hit
`completion_tokens=1024` ... truncating before the answer ... Real fix = raise extraction
`max_tokens`") — but it shipped unraised, and contract-v2 made the output bigger, so it now
bites ordinary pages, not just verbose models.

Impact: `query` (the primary tool, "~95% of web reads") is effectively broken on real pages
for a self-hoster. There is NO operator workaround: the cap is not exposed via any `A2WEB_*`
env, so a deployer cannot raise it, swap prompt, or disable the index from outside.

- Suggestion (owner-side, high priority): (a) raise the extraction `max_tokens` default
  substantially (the bench's own prescription), AND/OR (b) expose it as `A2WEB_EXTRACT_MAX_TOKENS`
  so operators can tune it, AND/OR (c) emit the `answer` field FIRST so a truncated response
  still carries the answer, AND/OR (d) gate `also_here`/`other_pages` off by default on
  non-listing pages (the 0.44.1 "gate options on listing" change moved this direction but did
  not fix the answer-truncation). Any one of these unblocks `query`.


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

## Runtime / operation (from deploy + live verify)

### 5. `example.com` trips `length_floor` → `status: failed` (bad first smoke test)

The instinctive first smoke-test URL, `https://example.com`, returns `status: "failed",
verdict: "length_floor"` for BOTH `fetch_raw` and `ask` (the page is below the content
length floor), and `ask` returns `answer: null` because extraction never runs. During
verification this looks like a broken deployment when it is not: the content is actually
present in `content_md`. A real page (Wikipedia) immediately returned `confidence: high`
with a correct extracted answer.

- Suggestion: either document a known-good smoke-test URL in the README, or when the tier
  fetched content but only the length floor "failed", surface that as a distinct low-signal
  status rather than a bare `failed` (it reads as an error to a first-time operator).

### 6. Tool descriptions hardcode "Haiku 4.5" even when `OPENAI_MODEL` overrides it

`a2web web ask --help` (and the MCP tool description) states "the server-side Haiku
extractor" and "The extraction model is small and cheap (Haiku 4.5)." We configured
`OPENAI_MODEL=openrouter/deepseek/deepseek-v4-flash`, so the advertised model is wrong at
runtime. This compounds footgun #1: the docs assume Anthropic Haiku throughout. An operator
reading the tool description would not know which model is actually answering.

- Suggestion: template the configured model name into the description, or make it generic
  ("a small, cheap extraction model, configurable via OPENAI_MODEL").

### 7. `ask` and `fetch_raw` return different top-level envelopes

`ask` returns `{tier, confidence, answer, title, ...}` (or `{status, answer, narrative,
diagnostics_summary}` on failure); `fetch_raw` returns `{url, status, content_md, headings,
narrative, diagnostics_summary}` on the short-page path but a `{tier, confidence, content_md,
...}` shape on the success path. Scripting both uniformly means guarding for keys that appear
in one but not the other (e.g. `status`/`diagnostics_summary` were present for one call and
absent for another).

- Suggestion: a stable top-level envelope across both tools (always include `tier`, `status`,
  `confidence`, `diagnostics_summary`) would make programmatic use and monitoring simpler.

## What worked well (runtime)

- **The CLI is excellent for operability.** `a2web web ask/fetch_raw`, `a2web health`,
  `a2web list-tools`, `a2web schema` let an operator smoke-test every tier from `docker exec`
  with zero MCP plumbing. This made deploy verification trivial and is a genuinely great
  feature. Keep it.
- **`diagnostics_summary` + `narrative` + `operator_hints` are best-in-class.** Every result
  says exactly which tier served it, the verdict, and elapsed ms (e.g. `tier=zyte
  verdict=not_found total_ms=8297`), and failures carry actionable hints (`reddit_forbidden_
  try_archive`). This made "is Zyte actually engaging?" answerable in one call.
- **Tier cascade + Zyte escalation works as documented.** A normal page served from `raw`/
  `site_handler`; a hard Reddit page escalated all the way to `tier=zyte` and fetched a real
  listing at `confidence: high`. The paid rung is reached only when the cheaper tiers fail.
- **`ask` degradation is honest.** The help text and behavior match: when the LLM is
  unavailable the fetch still succeeds and `extracted_answer` is null with a hint, rather than
  a hard failure.

