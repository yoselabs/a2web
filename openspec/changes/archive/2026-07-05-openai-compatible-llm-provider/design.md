## Context

a2web extracts answers server-side for `ask`. The `Provider` protocol is deliberately narrow — `complete(system, user, model) -> ProviderResponse` (text-in/text-out; no tool-use/JSON-mode/streaming). Two providers exist: `claude-code` (Claude subscription via `claude-agent-sdk`, in-process, needs a local OAuth session) and `anthropic` (metered API key). Both are Anthropic-only. Selection is centralized in `select_provider(...)` (spec `provider-selection`) with an auto order that prefers the credential-free `claude-code` then `anthropic`, injected into the extraction resource as `Lazy[Provider]`.

The `openai` SDK is already a top-level dependency but has **no importer in `src/`** — latent capacity this change activates. This provider is the prerequisite for `deployable-container-ci`: a headless container has no Claude session, so its LLM path must be a keyed endpoint.

## Goals / Non-Goals

**Goals:**
- One OpenAI-compatible provider reaching OpenAI, Gemini's OpenAI-compatible endpoint, local runtimes (Ollama/LiteLLM), and any operator-run gateway — through a single config surface.
- Zero new dependency; no change to the `Provider` protocol, the `ask`/`fetch_raw` signatures, or the response envelope.
- Empirically confirm (spike) that real backends clear a2web's extraction contract before freezing the production config.

**Non-Goals:**
- No native OpenAI Codex / ChatGPT-subscription provider and no in-tree proxy sidecar (see Decisions).
- No removal or weakening of the native `anthropic` provider — it keeps Anthropic-native prompt caching.
- No `[claude-code]` extra repackaging or container work — that is the downstream `deployable-container-ci` change.

## Decisions

### D1: Add a third provider; do NOT collapse onto OpenAI-compatible
Anthropic offers an OpenAI-compatible endpoint, so in principle `openai_compatible` could subsume `anthropic`. We keep all three. The native `AnthropicProvider` uses `cache_control: ephemeral` prompt-cache breakpoints (the `parts.cache_prefix` path) — a real cost/latency feature a2web built deliberately, and one an OpenAI-compatible `chat/completions` shim cannot express. Collapsing would silently drop prompt caching. **Alternative rejected:** OpenAI-compat-only (2 providers) — loses caching; false economy.

### D2: Derived gated fallback — LAST in the auto order (revised)
`openai_compatible` sits **last** in the auto order (`claude-code → anthropic → openai_compatible`), gated on its manifest being registrable (`OPENAI_API_KEY` present + a resolvable model). Because it is last, a configured OpenAI key can **never shadow** a working Claude/Anthropic path — the concern that first drove "pin-only" evaporates once it is the fallback rather than a peer. So it **derives from config with no explicit pin**: minimal config is just `OPENAI_API_KEY` (base_url/model default or derive), which is exactly the headless-container case. Explicit pin remains an override; a misconfigured/down endpoint that wins as the sole fallback still fails **loud** (never-silently-miss), not silently. An info log names the derived provider + endpoint + model so the auto-selection is transparent (mitigates the "common `OPENAI_API_KEY` in env" surprise). **Supersedes the original pin-only D2.** **Alternative rejected:** gating on `OPENAI_API_KEY` presence *ahead* of Claude — that common var would hijack the preferred subscription path; last-in-order is the fix.

### D3: Config surface — the OpenAI SDK's *standard* env vars, not custom a2web ones
The `openai` SDK reads `OPENAI_API_KEY` and `OPENAI_BASE_URL` by convention, and every OpenAI-compatible tool (and Gemini's compat docs) uses those names. So the backend reads the **standard** vars rather than inventing `A2WEB_LLM_*` knobs — zero-config for anyone who already has them set. The only a2web-native selector stays `A2WEB_LLM_PROVIDER=openai_compatible` (a2web's routing decision, not an OpenAI concern).

| Concern | Var | Notes |
|---|---|---|
| Intent | `A2WEB_LLM_PROVIDER=openai_compatible` | a2web selector; pin-only (D2) |
| Key | `OPENAI_API_KEY` | standard; presence gates availability |
| Endpoint | `OPENAI_BASE_URL` | standard; unset → OpenAI proper; set for Gemini/local |
| Model | `OPENAI_MODEL` → else recommended-by-host → else fail loud | see D7 |

Secret stays env-only (the standing rule). The key-env-name **indirection** is retained but defaults to the standard `OPENAI_API_KEY` (overridable for oddly-named keys). The custom `A2WEB_LLM_API_KEY` / `A2WEB_LLM_BASE_URL` from the first cut are **dropped**. `llm_model`'s Anthropic default is *not* reused for this path (it would send a Claude id to an OpenAI endpoint) — model resolution is dedicated (D7).

### D7: Model resolution + curated recommendations (no silent wrong-model)
There is no universal standard env var for the model, so a2web supplies **recommendations** keyed on the `OPENAI_BASE_URL` host, resolved as: explicit `OPENAI_MODEL` env → else the recommended default for a recognized host → else **fail loud** (`LLMNotAvailable` listing the recommendations). A recognized-host default is emitted with an info log ("using recommended `<model>` for `<host>`; override with `OPENAI_MODEL`") — deterministic, logged, overridable (within the magic budget). An unknown host (local/gateway) with no `OPENAI_MODEL` fails loud rather than guessing — never a silent wrong-model call (never-silently-miss). Recommendations (mid-2026, all Haiku-class cheap/fast tiers — a2web extraction is structured extraction, not hard reasoning; the bench ratifies):

| `OPENAI_BASE_URL` host | Recommended default | Note |
|---|---|---|
| `api.deepseek.com` | `deepseek-v4-flash` | ~$0.14/$0.28 per 1M, 1M ctx, caching — the value standout |
| `generativelanguage.googleapis.com` | `gemini-2.5-flash` | `-flash-lite` cheaper |
| `api.openai.com` (or unset) | `gpt-4.1-mini` | current cheap tier (not the dated `4o-mini`); `gpt-4.1-nano` cheapest |
| unknown (OpenRouter, local, gateway) | none → require `OPENAI_MODEL` | OpenRouter multiplexes many models; a single default would be wrong |

Goal is **quality-first under Haiku's cost** — not the cheapest model, but the closest quality to `claude-haiku-4-5` (the current baseline, deemed too expensive) that undercuts it. Model IDs move fast; the table is a one-module registry the bench (D6) reconfirms.

### D8: Custom-model evaluation reuses the bench harness (no parallel eval path)
Operators can plug arbitrary models through this provider, so validating "does this model behave" must be first-class — but it needs **no new eval system**. The bench already selects via the shared `select_provider(settings, override=...)` (`llm_eval/__main__.py`) and injects into `bootstrap_state`, so `A2WEB_BENCH_PROVIDER=openai_compatible OPENAI_BASE_URL=… OPENAI_API_KEY=… OPENAI_MODEL=… make bench` runs the whole pipeline through the custom model and scores it four-axis. The **data-contract axis** (router-shape JSON / `next_links`) is the pass/fail gate for a custom model. We document this as a capability and verify the bench runs clean end-to-end through `openai_compatible`; we do **not** fork a second eval path (`A2WebExtract` through the configured provider *is* the eval).

### D4: Usage/cost mapping is provider-local
OpenAI usage (`prompt_tokens`/`completion_tokens`) differs from Anthropic's three-way split (`extract_token_counts` is Anthropic-shaped). The new provider maps OpenAI usage itself; unknown model → `cost_usd = 0.0` (the documented sentinel), never a fabricated price. Cache-tier accounting is not attempted for arbitrary endpoints.

### D5: Codex / ChatGPT-subscription reuse is served *outside* a2web
Research (2026-07, sourced in the spike notes) found: reusing a ChatGPT/Codex subscription runs through an **undocumented** `chatgpt.com/backend-api/codex` **Responses API** (not `chat/completions`), with raw OAuth tokens in `~/.codex/auth.json`. OpenAI *semi*-tolerates personal single-user use (a Huet statement, not a written ToS clause); **account pooling plausibly risks a ban** — and server-side extraction drifts toward pooling. Therefore a2web builds **no** native Codex provider and vendors **no** proxy. Operators who want subscription reuse run their own gateway that presents an OpenAI-compatible surface; a2web consumes it through this provider, blind to what's behind it. This keeps the undocumented endpoint, the credential handling, and the ToS exposure entirely out of the a2web codebase. **Reverify before depending on it** — endpoint/model availability here is fast-moving (e.g. GPT-5.5 was subscription-only at launch).

### D6: Multi-model bench before freeze (quality-first, via OpenRouter)
The production provider IS the bench vehicle (no throwaway). Run `make bench` across the quality-first candidate set — **DeepSeek V4 Flash, OpenAI gpt-4.1-mini/gpt-5-mini, Gemini 2.5 Flash, Qwen, Mistral** — with **`claude-haiku-4-5` as the reference + cost red-line** (bench it too). All reachable through **one OpenRouter endpoint** (`OPENAI_BASE_URL=https://openrouter.ai/api/v1`, `OPENAI_MODEL=<vendor/model>`, an OpenRouter key in the key-env), varying only `OPENAI_MODEL` per run — so a single config sweeps every model and OpenRouter reports the per-call cost. The genuine unknown is not transport but whether a cheaper model honors a2web's router-shape JSON contract at Haiku-level quality; the four-axis eval (esp. data-contract) ranks that. Blocked on OpenRouter creds (operator to share).

## Risks / Trade-offs

- **Non-Anthropic model degrades extraction quality (closed-enum/`next_links` conformance)** → the spike (D6) measures it before we freeze config; if a backend fails the contract, we document the minimum viable model tier rather than ship a silent quality regression.
- **Misconfigured endpoint shadows a working provider** → mitigated by D2 (explicit pin + config-gated; never auto).
- **Prompt caching lost on the OpenAI-compat path** → accepted and documented; the native `anthropic` path (D1) remains for cache-sensitive workloads.
- **Codex/subscription endpoint changes or is restricted by OpenAI** → contained by D5: it lives in the operator's gateway, not a2web; nothing in-tree breaks if it changes.
- **Cost misreporting for unpriced models** → `cost_usd = 0.0` sentinel (D4); callers already told not to treat 0.0 as "free."

## Migration Plan

Purely additive. No wire/tool-signature/envelope change; default behavior (auto → `claude-code`/`anthropic`) is unchanged when no endpoint is configured. Rollback = remove the manifest + settings fields; nothing else references them. Enables `deployable-container-ci` as the next change.

## Open Questions

- Which backends earn a documented, tested "known-good" note (OpenAI tier? Gemini-compat? a local model?) — an output of the bench (D6/D8).
- Whether a small hardcoded price table is worth carrying for common OpenAI models, or `cost_usd = 0.0` everywhere is acceptable for v1.
- `OPENAI_MODEL` is a common-but-unofficial convention (litellm et al.), not read by the openai SDK itself — confirm it reads cleanly as a2web's model override, or fall back to an a2web-native `A2WEB_LLM_MODEL` if collisions surface.
- Recommendation defaults (D7) should be reconfirmed against current model lineups at implementation time (IDs move fast).
