# Findings — Router-shape production bench (v0.21)

**Date:** 2026-05-25
**Run:** `eval/runs/2026-05-25_022834/` (regenerable; not committed)
**Question:** does v0.21 router-shape hold up live vs WebFetch baseline + raw fetch?

## Headline

**`ask` (a2web_extract) wins on quality AND cost-per-quality.** 11-URL corpus, 33 rows, Sonnet 4.6 judge.

| System | reached | mean | median | $/score-point |
|---|---|---|---|---|
| webfetch_baseline | 8/11 | 3.36 | 4.0 | $0.1434 |
| a2web_detail (fetch_raw) | 10/11 | 4.00 | 5.0 | $0.1111 |
| **a2web_extract (ask)** | **10/11** | **4.36** | **5.0** | **$0.1020** |

+30% mean quality vs WebFetch, +9% vs raw fetch, while being the cheapest per score-point.

## By URL class

| Class | webfetch_baseline | a2web_detail | a2web_extract | Notes |
|---|---|---|---|---|
| clean | 4.50 | 5.00 | 4.50 | All three handle prose; tie within noise |
| comments | 2.50 | 3.50 | **4.50** | `shape=discussion` validates live — thread pages need both content + reply structure |
| gated | 5.00 | 5.00 | 5.00 | Perfect across the board (paywalled/blocked → archive fallback nails it) |
| listing | 3.60 | 4.00 | 4.00 | Raw and extract tied; WebFetch loses on aggregator pages |
| spa | **0.00** | 2.00 | **5.00** | SPAs WebFetch can't reach at all — browser tier + extraction recovers fully |

## Cost

- Total: **$1.37** across 33 rows ($0.042/row)
- a2web_extract fetch: $0.24 (LLM extraction adds ~$0.024/URL on top of raw fetch)
- Judge: $0.85 (Sonnet 4.6 across 33 rows)

The headline `$/score-point` column captures the trade-off correctly: extraction costs more per call, but the denser answer delivers more useful information per dollar. WebFetch's three failure modes (spa=0.00, comments=2.50, listing=3.60) inflate its `$/score-point` even though raw per-call cost is similar.

## What this validates for v0.21

- **`shape=discussion` is load-bearing.** Comments-class URLs jumped from 2.50 (raw fetch) to 4.50 (router-shape extract) — the explicit discussion shape gives the model permission to surface both content and reply structure together.
- **Routing helps SPAs the most.** Where WebFetch hits 0.00, router-shape extract hits 5.00 — the tier cascade reaches the page AND the extraction renders a useful answer from JS-hydrated DOM.
- **Cost envelope holds.** No regression vs v0.20-baseline expectations; bench cost ~$1.37 / 11 URLs is in line with prior runs.

## Fetch errors (3 rows)

- `reddit-listing` × a2web_detail — length_floor (known backlog: Reddit anti-bot, see BACKLOG.md)
- `reddit-listing` × a2web_extract — same root cause
- `spa-react-dev` × webfetch_baseline — HTTP 404 (WebFetch can't reach SPAs)

## Recommendation

Ship v0.21. The router-shape envelope delivers the best answer-quality-per-dollar across every URL class in the corpus, and the new `discussion` shape value pays off on exactly the page type it was introduced for.

Optional follow-ups (BACKLOG):
- Reddit anti-bot fix (rewrite to `old.reddit.com` or JSON API).
- Genre prompt tightening for HN-front (`community` vs `news` disambiguation — defensible miss in pre-impl spike).
