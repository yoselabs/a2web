# a2web: deployment / operation lessons

Feedback for the a2web owner, collected while deploying a2web into a homelab as an
MCP-gateway backend + tailnet-direct MCP server (2026-07-11). Each item is friction
a deployer hit, with a concrete suggestion. Grouped by severity.

## Footguns (worth fixing)

### 0. CRITICAL: `query` returns empty answers — `auto` selects a session-less Claude Code provider

**Status: root cause identified 2026-07-20 and fixed. An earlier version of this entry
blamed the 1024-token extraction cap; that was a misdiagnosis — see the note at the end,
which is kept deliberately because the wrong turn is instructive.**

On a homelab deploy, `query` returned `extraction_empty` (answer `""`, `also_here` /
`other_pages` / `structural_form` all `None`) on ordinary content pages
(en.wikipedia.org/wiki/Home_Assistant, /wiki/Nginx), while `fetch_raw` and plain LLM
completions worked fine. Reproduced across THREE models — `deepseek-v4-flash`,
`deepseek-chat`, `gpt-4.1-mini` — and BOTH image versions.

Root cause: **the configured model was never called at all.** `settings.llm_provider`
defaults to `auto`, and the `auto` order put `claude-code` first. The `claude-code`
manifest gated on SDK *importability* (`find_spec("claude_agent_sdk")`), and 0.46.0 bakes
that SDK into the published image — so in a container the rung reported
`available() == True` while there was no Claude Code OAuth session behind it. It won the
order, returned empty text on every call, and the operator's configured `OPENAI_*` gateway
was never consulted.

Verified in-process inside the running container (0.46.0, digest `sha256:752ab7b7…042d9`):

```
select_provider(AppSettings())                        -> ("claude-code", "claude-haiku-4-5-…")
Extractor(...).extract(...)                           -> answer == ''
select_provider(s, override="openai_compatible")      -> gpt-4.1-mini
                                                      -> correct answer + full RouterPayload
```

The "reproduced across THREE models and BOTH image versions" evidence was pointing at this
all along: model-independence is the signature of a code path that never reaches *any*
model. It was read as "therefore not model-specific, so it must be the shared cap" when it
should have been read as "therefore no model is involved."

Impact: `query` (the primary tool, "~95% of web reads") was fully broken on any
containerized deploy that had the claude-code extra baked in, with a diagnostic
(`extraction_empty`: "retry, use `fetch_raw`, or rephrase the question") that misdirected
diagnosis toward page content and prompt shape.

- **Fixed (owner-side):** the `claude-code` manifest now additionally probes for the
  `claude` CLI — SDK-importable is no longer treated as available, since the SDK is a thin
  wrapper that must spawn that CLI. Independently, an explicitly configured gateway
  (`OPENAI_API_KEY` + `OPENAI_BASE_URL`) now leads the `auto` order rather than trailing
  it: a deliberate operator configuration is never shadowed by a session-based backend.
  Two guards, either sufficient. Regression test:
  `tests/packages/llm_extract/test_claude_code_optional.py`.
- **Operator workaround (pre-fix):** pin `A2WEB_LLM_PROVIDER=openai_compatible`.

#### Note: how the wrong conclusion was reached (kept deliberately)

The original entry blamed the hardcoded `max_tokens=1024` in
`packages/llm_extract/extractor.py`, reasoning that the contract-v2 router JSON overflowed
the cap, truncated, and left `_first_json_object` with no complete object. The theory was
coherent, matched a real prior bench finding from 2026-07-05, and pointed at real code —
but it was never measured against the failing page. When it finally was, on
en.wikipedia.org/wiki/Home_Assistant (16k chars, `EXTRACT_ROUTER_V1`, via the gateway):

```
max_tokens=1024  -> finish_reason=stop, completion_tokens=62,  valid JSON
max_tokens=4096  -> finish_reason=stop, completion_tokens=143, valid JSON
```

62 tokens is 6% of the cap. Raising it changes nothing.

Two transferable lessons. First, a plausible mechanism that explains the symptom is not
evidence; the cheap measurement (count the actual completion tokens) was available the
whole time and would have killed the theory in one call. Second, the disconfirming
evidence was already *inside* the entry — "reproduced across three models" — but got
absorbed as support for the theory rather than tested against it. A symptom invariant
across every model is evidence about the *call path*, not about any model's output.

The 1024 cap remains unexposed and is still worth addressing on its own merits (see
footgun #8) — it was simply not this bug.


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

### 8. Extraction `max_tokens` is hardcoded at 1024 and unexposed

`Extractor` hardcodes `max_tokens=1024` (`packages/llm_extract/extractor.py`) and is
constructed without any settings/env override, so an operator cannot tune it from outside
the image.

This is **not** the cause of footgun #0 — measured on the page that motivated that entry,
the model returns 62 completion tokens with `finish_reason=stop`, 6% of the cap. But the
cap is real and unreachable, and a genuinely link-rich page with a verbose model can still
approach it. Filed on its own merits, explicitly decoupled from the empty-answer story.

- Suggestion: (a) expose `A2WEB_EXTRACT_MAX_TOKENS` so operators can raise it, AND/OR
  (b) emit the `answer` field FIRST in the router contract so a truncated response still
  carries the answer (degrades the index, preserves the primary output). Worth pairing
  with a `finish_reason == "length"` signal surfaced as a distinct operator hint, so a
  real truncation is never again mistaken for an empty answer — the two are currently
  indistinguishable on the wire, which is exactly what made #0 diagnosable only from
  inside the container.

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

- **RESOLVED (2026-07-21, `honest-tiny-page-length-floor`).** The suggestion's second
  half shipped as the real fix: `length_floor` conflated "walled/empty" with "too little
  to extract". `is_complete_small_page` (a strict sibling of `is_confirmed_empty`) now
  promotes a thin page to `status: ok` — extraction runs on the real body — when an
  independent browser render corroborates that it is small-not-walled (no wall/
  subresource/challenge evidence anywhere). `example.com` now answers at `confidence:
  low` instead of failing. The promotion is wire-only (never cached) and errs toward the
  wall on any ambiguity (the empty-vs-wall false-positive asymmetry). Regression-guarded
  by the `tiny-complete-page` corpus entry + `test_complete_small_page_promotion.py`.

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

