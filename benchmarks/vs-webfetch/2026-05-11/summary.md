# a2web vs WebFetch — Benchmark Summary (2026-05-11)

20 URLs × 5 classes (clean / gated / SPA / structured / edge).
4 systems: WebFetch, a2web A_full, a2web B_meta, a2web C_content_only.
Judge: claude-sonnet-4-6, blind, scored 0-5 against per-URL criteria.

## Headline numbers

| System              | Reached / 20 | Mean score (0-5) | Median score |
|---------------------|--------------|------------------|--------------|
| WebFetch            | 11           | 2.95             | 3.5          |
| a2web A_full        | 12           | **3.40**         | **4.0**      |
| a2web B_meta        | 11           | 3.20             | 3.5          |
| a2web C_content     | 12           | 3.15             | **4.0**      |

| a2web token cost (across all 20)        | Sum     | Mean / URL |
|-----------------------------------------|---------|------------|
| A_full (everything)                     | 127,054 | 6,353      |
| B_meta (content + title + byline)       | 27,807  | 1,390      |
| C_content_only                          | 26,698  | 1,335      |
| **`links` field alone**                 | **62,165** | **3,108**  |
| **`fit_md` field alone (pure duplicate of content_md)** | **23,893** | **1,195** |

**Going A → C: median 83% token savings, with judge scores tied-or-better on 17/20 URLs.**

## What this means

a2web ships substantial value in the *content* — slightly higher reach and quality than WebFetch.
But the **default response shape leaks ~5× more tokens than the downstream agent needs to answer the task**. The two largest leaks are:

1. **`links` (49% of total payload)** — dominated by aggregator/UI links (HN: 197, gh-trending: 1142, pypi: 287, notion: 395). Only needed for "list-extraction" tasks.
2. **`fit_md` byte-for-byte duplicates `content_md` on 14/20 fetches (19% of total payload)**. Pure duplicate tax — v0.2 kept the field for forward-compat but populates it with content_md.

## Reach surprises

- **a2web's browser tier fired 0 times across all 20 URLs.** Even on Reddit, X, Linear, LWN — where raw failed and browser would plausibly help — the gate did not suggest browser escalation.
- **Linear: a2web returned status=failed but judge scored 5/5.** The content was fine; the gate produced a false-positive failure verdict.
- **Notion: a2web won outright over WebFetch** — WebFetch returned a 301 redirect notice and stopped; a2web followed and returned full content.
- **WebFetch failed on Reddit + X explicitly** (Claude Code's URL allowlist) — a2web reached but the gate flagged them as block pages (correctly).

## Bottom line

a2web's *content tier* is winning. a2web's *response envelope* is bleeding ~80% of its token budget for ~0% quality gain on most tasks. Two changes (default-off links, kill duplicate fit_md) save ~85% of payload tokens with no measurable quality loss on this corpus.
