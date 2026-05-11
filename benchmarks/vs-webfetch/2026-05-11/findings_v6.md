# Findings v6 — local-vs-cloud full eval

Ran 2026-05-12. 28 models across cloud (OpenRouter, 22) and local (Ollama, 8).
Stage 0 → 1 → 2 winnow + 4 reliability axes (inject, hallucinate, language,
determinism) on the final top 5. **mistral:7b is the only local model that
cracked the top 5** — and the reliability axes expose why "local for free"
is not a strict win.

## TL;DR — three production tiers

```
   Tier              Pick                          Why
   ───────────────────────────────────────────────────────────────────────
   CLOUD-BALANCED    microsoft/phi-4               Best stage-2 quality (3.33),
   (default)                                       cheapest cloud ($0.001/call),
                                                   tied-best injection resistance.
                                                   Decent on every axis. No
                                                   single big weakness.

   CLOUD-SPEED       google/gemini-2.5-flash       1.4s latency, perfectly
   (real-time)                                     deterministic. ⚠️ Easily
                                                   jailbroken (2.60). NEVER use
                                                   on adversarial content.

   LOCAL-PRIVACY     mistral:7b (Ollama)           $0 cost. Perfect on all 6
   (offline / EU /                                 languages. Tied-best inject
   regulated)                                      resistance (4.40). ⚠️ Worst
                                                   hallucination floor (2.80) —
                                                   add downstream verification.
                                                   30s/call latency.
```

## Stage 1 leaderboard — 28 models

```
   Rank  Model                                    Mean   Cost     Lat
   ──────────────────────────────────────────────────────────────────────
    1    minimax/minimax-m2                       5.00   $0.007    6.5s
    2    microsoft/phi-4                          4.80   $0.001    4.2s
    2    deepseek/deepseek-chat-v3.1              4.80   $0.004    3.1s
    2    google/gemini-2.5-flash                  4.80   $0.006    1.0s
    5    mistral:7b              ★LOCAL           4.60   FREE     45.6s
    5    qwen/qwen3-30b-a3b                       4.60   $0.003   14.7s
    5    openai/gpt-4.1-mini                      4.60   $0.003    2.3s
    5    qwen/qwen3-max                           4.60   $0.006    4.0s
    5    z-ai/glm-4.6                             4.60   $0.009   20.8s
    5    deepseek/deepseek-r1-0528                4.60   $0.010   13.3s
    5    qwen/qwen3-235b-a22b                     4.60   $0.012    8.2s
    5    anthropic/claude-haiku-4-5               4.60   $0.019    2.6s
    5    mistralai/mistral-large-2411             4.60   $0.039    3.3s
   14    llama3.2:3b             ★LOCAL           4.40   FREE      2.6s
   14    llama3.1:8b             ★LOCAL           4.40   FREE     43.6s
   14    qwen3:8b                ★LOCAL           4.40   FREE    111.4s
   14    phi4 (14B)              ★LOCAL           4.40   FREE     77.0s
   14    deepseek/deepseek-v3.2-exp               4.40   $0.004    3.2s
   14    moonshotai/kimi-k2                       4.40   $0.009    3.4s
   14    cohere/command-r-plus                    4.40   $0.043    2.6s
   14    google/gemini-2.5-pro                    4.40   $0.067   17.4s
   22    qwen2.5:7b              ★LOCAL           4.20   FREE      4.9s
   22    openai/gpt-4o-mini                       4.20   $0.002    1.3s
   22    meta-llama/llama-3.3-70b                 4.20   $0.002    2.0s
   25    nvidia/nemotron-nano-9b:free             4.00   $0.000   10.6s
   26    phi3.5:3.8b             ★LOCAL           3.80   FREE     17.0s
   26    gemma2:2b               ★LOCAL           3.80   FREE      4.8s
   26    amazon/nova-pro-v1                       3.80   $0.013    1.0s
```

### Local model takeaways

```
   mistral:7b        4.60   45.6s    ★ best local — top 5 overall
   llama3.2:3b       4.40    2.6s    ★ best local cost/speed (small + fast)
   llama3.1:8b       4.40   43.6s
   qwen3:8b          4.40  111.4s    ⚠️ painfully slow (reasoning)
   phi4 (14B)        4.40   77.0s    bigger ≠ better than the 3B versions
   qwen2.5:7b        4.20    4.9s
   phi3.5:3.8b       3.80   17.0s    Microsoft phi3 < phi-4 (cloud) by a lot
   gemma2:2b         3.80    4.8s    Google's smallest — too small
```

### Cloud headlines

```
   minimax-m2      5.00  reborn after stage-0 elimination — provider
                         variance is real; one-shot smoke tests over-cull.
   gemini-2.5-pro  4.40  at $0.067/call, 10x flash for LOWER quality.
                         Worst cloud value in this set.
   command-r-plus  4.40  at $0.043, 8x more than peers — extraction-
                         training claim doesn't deliver.
   nemotron:free   4.00  at $0 — still respectable for batch jobs.
```

## Stage 2 — top 5 on full 20-URL corpus

```
   Rank  Model                          Mean   Cost     Lat    A/B/C/D/E
   ─────────────────────────────────────────────────────────────────────────────
    1    microsoft/phi-4                3.33   $0.002    3.1s  4.0/1.3/5.0/3.2/2.3
    2    minimax/minimax-m2             3.27   $0.022    6.4s  4.0/0.5/5.0/4.0/2.5
    3    google/gemini-2.5-flash        3.22   $0.011    1.4s  4.5/0.3/4.8/3.5/2.0
    4    deepseek-chat-v3.1             3.11   $0.009    4.1s  3.8/1.0/4.2/3.5/2.3
    5    mistral:7b           ★LOCAL    3.00   FREE     30.0s  4.0/1.0/4.0/3.0/2.3
```

mistral:7b on full corpus is 0.33 points below phi-4 at $0 cost. The gap is mostly in
A_clean (4.0 vs phi-4's 4.0 — even) and D_structured (3.0 vs phi-4's 3.2 — slight).
**B_gated and E_edge are flat across all 5** — those are universal weak spots.

## Reliability axes (final top 5)

### Injection resistance
```
   microsoft/phi-4                  4.40    ← tied #1
   mistral:7b           ★LOCAL      4.40    ← tied #1 — best local property
   minimax/minimax-m2               3.00
   deepseek-chat-v3.1               2.75
   google/gemini-2.5-flash          2.60    ← weakest
```

phi-4 and mistral:7b are the only top-5 models that consistently ignore
embedded jailbreak attempts. Gemini-flash gets jailbroken ~40% of the
time — never deploy on user-supplied adversarial content.

### Hallucination floor
```
   deepseek-chat-v3.1               4.80    ← best refusal
   google/gemini-2.5-flash          4.60
   microsoft/phi-4                  4.20
   minimax/minimax-m2               4.00
   mistral:7b           ★LOCAL      2.80    ← WORST, fabricates badly
```

**The mistral:7b trade-off**: best at refusing injection, worst at refusing
to fabricate when content is missing. Critical if your fetcher often
encounters partial / missing-answer pages — pair with downstream
verification.

### Language coverage (en/es/tr/ru/zh/ja)
```
   microsoft/phi-4                  5.00   all 6 langs perfect
   deepseek-chat-v3.1               5.00   all 6 langs perfect
   mistral:7b           ★LOCAL      5.00   all 6 langs perfect
   google/gemini-2.5-flash          4.88   ja → 4.0
   minimax/minimax-m2               4.67   some langs failed entirely
```

**Three-way tie at 5.00 — including mistral:7b LOCAL.** International
content is solved on commodity hardware.

### Determinism (3 runs, same prompt, temp=0)
```
   google/gemini-2.5-flash          similarity 1.000   ← perfectly deterministic
   microsoft/phi-4                  similarity 0.673
   deepseek-chat-v3.1               similarity 0.525
   minimax/minimax-m2               similarity 0.242   ← wildly varied surface
                                                       (but scores stable)
   mistral:7b                       not run (top-3 only)
```

Gemini-flash is the ONLY model that gives byte-identical answers across 3
runs at temp=0. Everyone else gives ~50% surface variance. If your pipeline
depends on answer-hash caching or stable evals, this is decisive.

## The reliability cross-matrix

```
                          Inject   Halluc   Lang(de)  Determ   Cost   Lat
   ──────────────────────────────────────────────────────────────────────────
   phi-4                    4.40    4.20      5.00     0.673  $0.001   3.1s
   gemini-2.5-flash         2.60⚠   4.60      4.88     1.000✓ $0.011   1.4s
   deepseek-chat-v3.1       2.75⚠   4.80      5.00     0.525  $0.009   4.1s
   minimax/minimax-m2       3.00    4.00      4.67     0.242  $0.022   6.4s
   mistral:7b ★LOCAL        4.40    2.80⚠     5.00      -     FREE    30.0s

   ✓ = clear winner   ⚠ = clear weak point on this axis
```

**No single best model.** The trade-off lines are:
- gemini-flash trades injection resistance for determinism + speed.
- mistral:7b trades hallucination floor for $0 cost + privacy + language.
- phi-4 has the smallest weak point (worst score is its 4.20 hallucination).
- deepseek-chat is the cloud "safe default" but weak on injection.

## Production deployment patterns

```
   1. STANDARD WORKLOAD              microsoft/phi-4
      ─ Best-in-class quality for cost ($0.001).
      ─ Tied-best injection resistance.
      ─ Decent on every axis.
      ─ 3.1s latency suits non-real-time.

   2. INTERACTIVE / LIVE             google/gemini-2.5-flash
      ─ 1.4s latency.
      ─ Perfectly deterministic (only model in our set).
      ─ ⚠️ Do NOT feed user-supplied or adversarial content.
        Wrap with a sanitizer or use deepseek-chat instead.

   3. PRIVACY / OFFLINE / EU         mistral:7b via Ollama
      ─ $0 cost, runs on your hardware.
      ─ Perfect multilingual (en/es/tr/ru/zh/ja all 5.00).
      ─ Tied-best injection resistance.
      ─ ⚠️ Pair with downstream verification —
        worst hallucination floor (2.80).
      ─ 30s/call latency rules out interactive use.
      ─ RAM: ~4.4GB active — leaves apps alone on 16GB+.

   4. FREE FALLBACK / DEV            nvidia/nemotron-nano-9b:free
      ─ $0 cloud (no setup).
      ─ 4.00 stage-1 quality.
      ─ 10s+ latency, batch-only.

   5. WHEN HALLUCINATION FLOOR       deepseek-chat-v3.1
      MATTERS MOST                   ─ Highest refusal score (4.80).
                                     ─ Cheap ($0.009).
                                     ─ Weak inject (2.75) — avoid
                                       on adversarial content.
```

## What got cut (and why)

```
   Cloud, eliminated at stage 0 (returned empty):
   ─ tencent/hunyuan-large
   ─ x-ai/grok-2-1212
   ─ mistralai/mistral-large-2411  (reborn, scored 4.60, didn't make top 5)
   ─ z-ai/glm-4.6                  (reborn, scored 4.60, didn't make top 5)

   Local, eliminated at stage 0:
   ─ qwen2.5:3b           empty
   ─ nemotron-mini:4b     empty

   Cloud, mid-pack at high cost (bad value):
   ─ google/gemini-2.5-pro     4.40 at 10x flash cost
   ─ cohere/command-r-plus     4.40 at 8x peer cost
   ─ amazon/nova-pro-v1        3.80, weakest survivor

   Local, slow without proportional quality gain:
   ─ qwen3:8b      4.40 at 111s/call — reasoning model, not worth it
   ─ phi4 (14B)    4.40 at 77s/call  — 3B versions match it
   ─ llama3.1:8b   4.40 at 43s/call  — llama3.2:3b matches at 2.6s
```

## Recommended deployment in a2web

```
   a2web settings:

   # Default (private workloads, cost-optimized):
   A2WEB_LLM_PROVIDER=openrouter
   A2WEB_LLM_MODEL=microsoft/phi-4

   # Live interactive:
   A2WEB_LLM_PROVIDER=openrouter
   A2WEB_LLM_MODEL=google/gemini-2.5-flash

   # Privacy / EU / offline (requires Ollama running):
   A2WEB_LLM_PROVIDER=ollama
   A2WEB_LLM_MODEL=mistral:7b
   # Plus: enable downstream answer-verification for hallucination tax.
```

## Methodology + provenance

```
   Stage 0     1 URL × 28 models, no judge → 22 survived
   Stage 1     5 URLs × 28 (cached cells skip) → top 5
   Stage 2     20 URLs × 5 final
   Reliability inject (5×5), hallucinate (5×5), language (8×5),
               determinism (5×3 runs × top 3)

   Provider routing:
     OpenRouter   model name contains "/"      cloud
     Ollama       model name without "/"       local

   Judge        claude-sonnet-4-6 via OS session (free against subscription)
   Total spend  ~$2-3 OpenRouter for extraction
                ~$15 Sonnet for ~100 judge calls (subscription billable)
   Total wall   ~90 min including pulls
```
