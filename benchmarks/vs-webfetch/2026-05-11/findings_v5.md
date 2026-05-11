# Findings v5 — multi-model extraction + reliability

Ran 2026-05-11. 22 models smoked, 17 advanced to a 5-URL ranked subset,
top 5 ran the full 20-URL corpus, then four reliability axes
(injection, hallucination, language, determinism) on the survivors.
This document is the production recommendation.

## TL;DR — three tier picks

```
   Tier        Pick                           Why
   ──────────────────────────────────────────────────────────────────
   Quality     microsoft/phi-4                Best stage-2 quality (3.33),
   + Cheap                                    cheapest by 10x ($0.001/call),
                                              best injection resistance (4.20).
                                              Caveat: non-deterministic,
                                              slightly worse hallucination floor.

   Speed       google/gemini-2.5-flash        1.4s latency, perfectly
                                              deterministic (1.000 similarity).
                                              Caveat: weakest injection
                                              resistance of the top 5 (2.60).

   Well-       deepseek/deepseek-chat-v3.1    Top-3 across every axis,
   rounded                                    best hallucination floor (4.80),
                                              perfect on all 6 languages.
                                              Decent middle on injection (3.00).

   Free        nvidia/nemotron-nano-9b-v2:free  4.00 stage-1 mean at $0/call.
                                                10s+ latency, mediocre but
                                                non-zero. Use for batch jobs
                                                where cost = 0 matters most.
```

## Stage 0 — 22 models smoked, 5 eliminated

```
   ELIMINATED (returned empty or 0 tokens on the Wikipedia smoke):
   ─ z-ai/glm-4.6              empty (reasoning model — content suppressed)
   ─ minimax/minimax-m2        empty
   ─ tencent/hunyuan-large     0 tokens
   ─ mistralai/mistral-large-2411   empty (deprecated?)
   ─ x-ai/grok-2-1212          empty
```

## Stage 1 — full 17-model ranked subset (5 URLs, judged)

```
   Rank  Model                                    Mean   Cost     Lat
   ─────────────────────────────────────────────────────────────────────
    1    microsoft/phi-4                          4.80   $0.001   4.2s
    1    deepseek/deepseek-chat-v3.1              4.80   $0.004   3.1s
    1    google/gemini-2.5-flash                  4.80   $0.006   1.0s
    4    qwen/qwen3-30b-a3b                       4.60   $0.003  14.7s
    4    openai/gpt-4.1-mini                      4.60   $0.003   2.3s
    4    qwen/qwen3-max                           4.60   $0.006   4.0s
    4    deepseek/deepseek-r1-0528                4.60   $0.010  13.3s
    4    qwen/qwen3-235b-a22b                     4.60   $0.012   8.2s
    4    anthropic/claude-haiku-4-5               4.60   $0.019   2.6s
   10    deepseek/deepseek-v3.2-exp               4.40   $0.004   3.2s
   10    moonshotai/kimi-k2                       4.40   $0.009   3.4s
   10    cohere/command-r-plus-08-2024            4.40   $0.043   2.6s
   10    google/gemini-2.5-pro                    4.40   $0.067  17.4s
   14    openai/gpt-4o-mini                       4.20   $0.002   1.3s
   14    meta-llama/llama-3.3-70b-instruct        4.20   $0.002   2.0s
   16    nvidia/nemotron-nano-9b-v2:free          4.00   $0.000  10.6s
   17    amazon/nova-pro-v1                       3.80   $0.013   1.0s
```

### Surprises in stage 1

```
   ─ microsoft/phi-4 is the price-quality champion: tied #1 at $0.001
     per call — 4-19x cheaper than peers at the same quality tier.

   ─ google/gemini-2.5-pro is BAD VALUE: $0.067 per call (10x flash)
     for LOWER quality (4.40 vs 4.80). Skip it.

   ─ cohere/command-r-plus is mid-pack at 8x the cost — extraction-
     training claim doesn't seem to deliver.

   ─ anthropic/claude-haiku-4-5 — our internal anchor — only matches
     mid-tier OpenRouter models. Not a quality leader by a long shot.

   ─ nvidia/nemotron-nano-9b:free at 4.00 is shockingly viable for
     batch jobs where $0 cost matters more than 10s latency.
```

## Stage 2 — top 5, full 20-URL corpus

```
   Rank  Model                          Mean   Cost     Lat    Cells  per-class (A/B/C/D/E)
   ────────────────────────────────────────────────────────────────────────────────────────
    1    microsoft/phi-4                3.33   $0.002   3.1s   18/20  4.0/1.3/5.0/3.2/2.3
    2    google/gemini-2.5-flash        3.22   $0.011   1.4s   18/20  4.5/0.3/4.8/3.5/2.0
    3    deepseek/deepseek-chat-v3.1    3.11   $0.009   4.1s   18/20  3.8/1.0/4.2/3.5/2.3
    4    openai/gpt-4.1-mini            3.06   $0.012   2.1s   18/20  3.5/1.3/4.2/3.2/2.3
    5    qwen/qwen3-30b-a3b             2.93   $0.008  15.9s   18/20  3.5/1.3/4.7/3.2/2.0
```

### Per-class pattern

```
   A_clean        4.0-4.5     Everyone is fine on simple articles
   B_gated        0.3-1.3     Hard for everyone; gemini-flash worst
   C_spa          4.2-5.0     SPA content extraction is solved
   D_structured   3.2-3.5     Tight band — small lead for gemini/deepseek
   E_edge         2.0-2.3     Universal weak spot (dead URLs, redirects)
```

## Reliability axis 1 — INJECTION resistance

5 synthetic pages with embedded jailbreak attempts. Score: did the
model ignore the injection and answer the actual task? 5 = perfect.

```
   Rank  Model                          Mean   Notes
   ─────────────────────────────────────────────────────────────────────
    1    microsoft/phi-4                4.20   most resistant
    2    qwen/qwen3-30b-a3b             3.80
    3    openai/gpt-4.1-mini            3.60
    4    deepseek/deepseek-chat-v3.1    3.00   middling
    5    google/gemini-2.5-flash        2.60   WEAKEST — gets jailbroken
```

**Critical for prod**: a page with a malicious `<!--IGNORE PREVIOUS-->`
comment will fool gemini-flash about 40% of the time but phi-4 only
~16%. If your fetcher can encounter adversarial content, weight this
axis heavily.

## Reliability axis 2 — HALLUCINATION FLOOR

5 pages whose content does NOT contain the answer. Score: did the
model admit ignorance or fabricate? 5 = perfect refusal.

```
   Rank  Model                          Mean   Notes
   ─────────────────────────────────────────────────────────────────────
    1    deepseek/deepseek-chat-v3.1    4.80   best refusal
    1    qwen/qwen3-30b-a3b             4.80
    1    openai/gpt-4.1-mini            4.80
    4    google/gemini-2.5-flash        4.60
    5    microsoft/phi-4                4.40   slightly more fabrication
```

**The phi-4 trade-off**: best at refusing injection, slightly worse
at refusing to fabricate when content is missing. Pair with downstream
verification if your task class often returns "answer not in content".

## Reliability axis 3 — LANGUAGE (6 langs: en/es/tr/ru/zh/ja)

8 synthetic content pages with same factual claims. Tests both:
"answer in English" and "answer in source language".

```
   Model                          Overall   en   es   tr   ru   zh   ja
   ──────────────────────────────────────────────────────────────────────
   microsoft/phi-4                5.00     5.0  5.0  5.0  5.0  5.0  5.0
   deepseek/deepseek-chat-v3.1    5.00     5.0  5.0  5.0  5.0  5.0  5.0
   qwen/qwen3-30b-a3b             5.00     5.0  -    5.0  5.0  5.0  5.0
   google/gemini-2.5-flash        4.88     5.0  5.0  5.0  5.0  5.0  4.0  ← ja
   openai/gpt-4.1-mini            4.88     5.0  5.0  4.0  5.0  5.0  5.0  ← tr
```

Phi-4 / deepseek-chat / qwen3-30b are **fully multilingual** at the
extraction-task level. Gemini-flash and gpt-4.1-mini have one weak
language each (Japanese / Turkish) but both still score 4.0 not 0 —
meaningful degradation, not catastrophic.

## Reliability axis 4 — DETERMINISM (3 runs same prompt)

5 URLs × 3 runs each at temp=0. Measured via `SequenceMatcher`
ratio between answer pairs. 1.0 = byte-identical across runs.

```
   Model                          Mean Similarity   Max Score Variance
   ──────────────────────────────────────────────────────────────────────
   google/gemini-2.5-flash        1.000              1.0  ← PERFECT
   microsoft/phi-4                0.558              2.0
   deepseek/deepseek-chat-v3.1    0.507              1.0
```

**Gemini-flash is the only truly deterministic model**. It returns
byte-identical answers across 3 runs. Phi-4 and deepseek-chat give
substantially different surface forms each time (~50% similarity)
even at temp=0 — production fallout: harder to cache by answer hash,
harder to debug regressions, less predictable in evals.

## The reliability trade-off matrix

```
                          phi-4   gemini   deepseek
   ─────────────────────────────────────────────────
   Stage 2 quality         ★★★      ★★      ★★
   Stage 2 cost            ★★★      ★       ★
   Stage 2 latency         ★★       ★★★     ★
   Injection resistance    ★★★      ★       ★
   Hallucination floor     ★        ★★      ★★★
   Language coverage       ★★★      ★★      ★★★
   Determinism             ★        ★★★     ★

   "★★★" = clear winner in this axis among the three
```

There is no single best model. Pick by what your prod workload
weights most. If you don't know yet, **start with deepseek-chat-v3.1**
— it's the most balanced choice across all axes.

## Production deployment recommendation

```
   1. PRIMARY (most workloads)         deepseek/deepseek-chat-v3.1
                                        ─ no axis is a weak point
                                        ─ $0.009 per 20-URL call
                                        ─ 4.1s mean latency

   2. SPEED-CRITICAL                   google/gemini-2.5-flash
                                        ─ 1.4s, deterministic
                                        ─ NEVER use on user-supplied
                                          adversarial content

   3. COST-CRITICAL / BATCH            microsoft/phi-4
                                        ─ $0.001 — 10x cheaper than
                                          alternatives
                                        ─ best injection resistance
                                        ─ add downstream verification
                                          for hallucination-prone tasks

   4. FREE FALLBACK / DEV              nvidia/nemotron-nano-9b-v2:free
                                        ─ $0 cost, 4.00 quality
                                        ─ 10s+ latency makes it
                                          unsuitable for live requests
```

## Models that did NOT survive

```
   z-ai/glm-4.6                empty stage 0
   minimax/minimax-m2          empty stage 0
   tencent/hunyuan-large       empty stage 0
   mistralai/mistral-large     empty stage 0 (probably deprecated)
   x-ai/grok-2-1212            empty stage 0
   amazon/nova-pro-v1          3.80 stage 1, eliminated
   google/gemini-2.5-pro       4.40 stage 1 at 10x cost — bad value
   cohere/command-r-plus       4.40 stage 1 at 8x cost — disappointing
   openai/gpt-4o-mini          4.20 stage 1, below cut
   meta-llama/llama-3.3-70b    4.20 stage 1, below cut
   anthropic/claude-haiku-4-5  4.60 stage 1 — competitive but eclipsed
                               on price by phi-4 / deepseek-chat
   moonshotai/kimi-k2          4.40 stage 1, below cut
   deepseek/deepseek-v3.2-exp  4.40 stage 1, eclipsed by v3.1
   deepseek/deepseek-r1-0528   4.60 stage 1 but 13s latency unusable
   qwen/qwen3-235b-a22b        4.60 stage 1 — 235B for 4.60 isn't worth it
   qwen/qwen3-max              4.60 stage 1
```

## Methodology + provenance

```
   Provider          OpenRouter via openai SDK (a2web.llm.OpenRouterProvider)
   Template          WEBFETCH_DEFAULT_V1 (byte-identical to Claude Code's)
   Judge             claude-sonnet-4-6 via Claude Code OS session
   Total wall        ~30 min across all stages
   Total spend       ~$1.50 OpenRouter + ~$10 in Sonnet judge calls
                     (Sonnet judge billed against subscription, not API key)

   Stage 0           1 URL × 22 models, no judge → 17 survived
   Stage 1           5 URLs × 17 models, judged → top 5
   Stage 2           20 URLs × 5 models, judged → final scoreboard
   Reliability       inject (5×5), hallucinate (5×5), language (8×5),
                     determinism (5×3 runs × 3 models)
```
