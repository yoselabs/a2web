## Why

a2web's LLM extraction (`ask`) can only reach Anthropic today — via the `claude-code` subscription piggyback (in-process, needs a local Claude session) or the metered `anthropic` API key. Neither works for a deployed, headless container: there is no Claude OAuth session, and metering is the only fallback. A generic **OpenAI-compatible** provider unlocks every other backend behind one seam — OpenAI, Gemini's OpenAI-compatible endpoint, local models (Ollama/LiteLLM), and any operator-run gateway (including a Claude- or Codex-subscription gateway) — with zero new dependency (the `openai` SDK is already carried but unused in `src/`). It is also the prerequisite for the downstream `deployable-container-ci` change, whose slim image has no Claude session and needs a keyed or endpoint-based LLM path.

## What Changes

- **New provider `openai_compatible`** implementing the existing text-in/text-out `Provider` protocol via `AsyncOpenAI(base_url=, api_key=)` + `chat.completions`. Maps OpenAI usage → `ProviderResponse` token/cost accounting. No JSON-mode/tool-use dependency — the extractor prompts for JSON and the wobble funnel tolerates it, same as the Anthropic path.
- **Standard env-var config** (design D3): the backend reads the OpenAI SDK's own `OPENAI_API_KEY` + `OPENAI_BASE_URL` (not custom `A2WEB_LLM_*`), with `A2WEB_LLM_PROVIDER=openai_compatible` the only a2web-native selector. Model resolves `OPENAI_MODEL` → curated recommendation for the host → **fail loud** (D7). The provider is **selected only when explicitly pinned**, never guessed into the auto order (an arbitrary endpoint can't be probed for availability the way an installed SDK can).
- **Curated model recommendations + custom-model eval** (D7/D8): a host-keyed recommendations registry (`gpt-4o-mini` for OpenAI, `gemini-2.5-flash` for Gemini-compat, fail-loud for unknown hosts), and a documented path to validate any custom model through the **existing** bench harness (`A2WEB_BENCH_PROVIDER=openai_compatible … make bench`) — no new eval system.
- **Provider-selection updated** to register and honor the third backend while preserving the existing credential-free-first auto order for the two Anthropic backends. All three coexist; the native `anthropic` provider is **kept** (it owns Anthropic-native `cache_control` prompt-cache breakpoints an OpenAI-compatible shim cannot express — see design).
- **Bench spike (task 1, throwaway):** wire a minimal provider and run the existing `make bench` eval across ≥2 backends (OpenAI + a Gemini-compatible endpoint) to confirm each clears a2web's extraction contract (answer quality, token cost, data-contract/`next_links` conformance vs the Haiku baseline). The spike's findings shape the production config surface before it is frozen.
- **Out of scope (recorded, not built):** no native OpenAI Codex / ChatGPT-subscription provider and no in-tree `codex-openai-proxy` sidecar. That subscription rides an *undocumented* `chatgpt.com/backend-api/codex` Responses-API endpoint OpenAI only semi-tolerates for personal use (account-pooling risks a ban); it is served **outside a2web** by the operator's gateway presenting an OpenAI-compatible surface, consumed through this same provider. The ToS/stability caveat is captured in `design.md`.

## Capabilities

### New Capabilities
- `openai-compatible-provider`: an OpenAI-compatible completion backend (base_url + api_key + model) satisfying the `Provider` protocol, with usage→cost mapping and config-gated construction.

### Modified Capabilities
- `provider-selection`: the preference/registration surface gains a third backend id and an explicit-configuration selection rule (configured endpoint → use it; never auto-guessed), while the two-Anthropic auto order and the single-source-of-truth invariants are preserved.

## Impact

- **Deps:** none new — `openai` is already a top-level dependency (activates latent code). `[claude-code]` extra packaging is handled in the downstream `deployable-container-ci` change, not here.
- **Code:** `settings.py` (3 fields); `packages/llm_extract/providers/openai_compatible.py` (new) + `providers/__init__.py`; `_manifests/llm_providers/openai_compatible.py` (new manifest, import-gated); the shared `select_provider(...)` domain function + its order/registration source; token/cost accounting mapping.
- **Specs:** new `openai-compatible-provider`; delta on `provider-selection`.
- **Tests:** provider unit tests (mocked httpx/openai); selection tests for the explicit-config rule; the architecture invariant that the order tuple stays single-source. Spike touches the eval harness only (throwaway).
- **Downstream:** unblocks `deployable-container-ci` (the slim image's LLM path). No wire/tool-signature change to `ask`/`fetch_raw`; no response-envelope change.
