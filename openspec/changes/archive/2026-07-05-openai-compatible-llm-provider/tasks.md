> **REORDERED (2026-07-05):** no LLM keys are present in the environment, so the
> live bench (§1) is blocked on credentials + spends quota. The production
> provider is backend-agnostic and the config surface is low-uncertainty, so §§2–5
> were built first (deterministic, mock-tested, zero cost). §1 remains the
> **pre-freeze validation gate** — run it once OpenAI + a Gemini-compatible key
> are available, to confirm real backends clear the extraction contract before
> merge. The production provider IS the "minimal provider" §1.1 asks for, so no
> throwaway is needed — point it at the backends and run `make bench`.

## 1. Spike — validate backends against the extraction contract (needs keys)

- [x] 1.1 ~~Wire a minimal throwaway provider~~ → superseded: the production `openai_compatible` provider (§3) is the vehicle; no disposable branch needed
- [x] 1.2 Run the bench across the quality-first set via **one OpenRouter endpoint** (13 candidates incl. DeepSeek V4 Flash, gpt-5-mini/gpt-4.1-mini, Gemini 2.5 Flash, Qwen, GLM, Mistral, Kimi) with **claude-haiku-4-5 as reference + cost red-line**; captured quality, per-call cost, and data-contract/`next_links` conformance → committed as the reference experiment `eval/model_benchmark/` (methodology-as-code + provenance-stamped results)
- [x] 1.3 Findings recorded in `eval/model_benchmark/results/2026-07-05.{json,md}` (supersedes the `findings_<date>.md` convention): DeepSeek V4 Flash prescribed (quality 4.71, clarity 4.43, 0/7 empty, ~1/14th Haiku cost); GLM-4.7-flash/gpt-5-mini clear the contract but produce empty answers — root cause confirmed as the 1024-token extraction output cap, not model weakness

> **DESIGN SETTLED (2026-07-05) — contract reworked, supersedes the v1 config.**
> After the v1 cut (custom `A2WEB_LLM_*` vars), design D3/D7/D8 settled on: the
> **standard** OpenAI env vars (`OPENAI_API_KEY` / `OPENAI_BASE_URL`), a
> host-keyed **recommendations** registry with fail-loud-on-unknown model
> resolution (`OPENAI_MODEL` → recommended → fail), and **custom-model eval via
> the existing bench** (no new eval path). §§2, 4.1, 5 reopened for the rework;
> the `complete()` core (§3.1–3.3) and the not-in-auto-order wiring (§4.2–4.3)
> carry over unchanged.

## 2. Config surface — standard env vars + recommendations (REWORK)

- [x] 2.1 Drop the custom `A2WEB_LLM_API_KEY` / `A2WEB_LLM_BASE_URL`; read the standard `OPENAI_API_KEY` (via a retained key-env indirection defaulting to `OPENAI_API_KEY`) and `OPENAI_BASE_URL`. Keep `A2WEB_LLM_PROVIDER=openai_compatible` as the only a2web-native selector
- [x] 2.2 Add a module-level host→recommendation registry (D7 table) + `resolve_model(...)`: `OPENAI_MODEL` env → recommended-for-host (info log) → fail loud (`LLMNotAvailable` listing recommendations). Reconfirm the model IDs against current lineups at implementation time
- [x] 2.3 Document the env contract in the settings docstring (deployment README deferred to `deployable-container-ci`)

## 3. Provider implementation

- [x] 3.1 Implement `packages/llm_extract/providers/openai_compatible.py`: `AsyncOpenAI(base_url=, api_key=)` + `chat.completions`, returning `ProviderResponse` (first-choice message text)
- [x] 3.2 Map OpenAI usage (`prompt_tokens`/`completion_tokens`) → `ProviderResponse`; unknown model → `cost_usd = 0.0` (no fabricated price)
- [x] 3.3 Mirror `AnthropicProvider`'s error contract: API error/timeout/malformed body → empty-`text` `ProviderResponse` with error detail on `raw`, never a crash
- [x] 3.4 Export the provider from `providers/__init__.py`; keep the package boundary clean (no `a2web.<domain>` imports)

## 4. Manifest + selection wiring

- [x] 4.1 Add `_manifests/llm_providers/openai_compatible.py`: gate on **`OPENAI_API_KEY`** presence (not the dropped `llm_base_url`) → `Unavailable(reason)` when absent, else the constructed provider (no module-level side effects — arch test enforces)
- [x] 4.2 Add `openai_compatible` **last** in the auto fallback-order tuple (single source; D2-revised — gated fallback that never shadows Claude/Anthropic); update the order arch test to match
- [x] 4.3 `select_provider(...)` needs no new code — the existing walk handles both explicit pin and last-in-order fallback; manifest gating (key + model) makes pinned-but-unconfigured resolve to the none sentinel

## 5. Tests

- [x] 5.1 Provider unit tests (mocked openai transport): happy path returns text; API error → empty-text response; usage → token counts; unknown model → `cost_usd == 0.0` *(carries over; retarget env to `OPENAI_API_KEY`)*
- [x] 5.2 Manifest tests: no `OPENAI_API_KEY` → `Unavailable`; key present → constructed provider
- [x] 5.3 Selection tests: explicit-pin selects it; pin-without-config → none; auto prefers Claude over openai_compatible (never shadowed); auto derives openai_compatible when preferred backends absent
- [x] 5.4 Confirm the fallback-order-tuple + surface-string single-source architecture invariant still holds (existing arch test passes unchanged)
- [x] 5.5 Model-resolution tests: `OPENAI_MODEL` wins; recognized host → recommended default (+ log); unknown host + no model → fail loud

## 7. Custom-model evaluation (D8 — reuse the bench, no new eval path)

- [x] 7.1 Verified the bench runs end-to-end through the backend: `A2WEB_BENCH_PROVIDER=openai_compatible OPENAI_BASE_URL=… OPENAI_MODEL=… ` drives `A2WebExtract` through the custom model and emits four-axis scores — this is exactly how the 13-model sweep in §1.2 ran (`eval/model_benchmark/run.py`)
- [x] 7.2 Documented the custom-model validation recipe (the command + reading the data-contract axis as the pass/fail gate) in the `llm_openai_api_key_env` settings docstring, pointing at `eval/model_benchmark/` as the committed reference

## 6. Gate

- [x] 6.1 `make check` green (lint + ty + tests + arch, coverage ≥85%)
- [x] 6.2 `openspec validate openai-compatible-llm-provider` passes; confirmed no `ask`/`fetch_raw` wire-signature or response-envelope change (touched only the LLM backend: provider + settings + manifest)
