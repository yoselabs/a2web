# Findings — a2web vs WebFetch, 2026-05-11

Grouped by pre-registered hypotheses (H1–H5) then "unplanned discoveries."
Each finding cites slug(s); see `results.tsv` for the numbers and `runs/<slug>/` for raw evidence.

---

## H1 — Links should default to `false`, opt-in via param. **CONFIRMED with one caveat.**

C_content_only scored **≥ A_full on 17 of 20 URLs**, with median **83% token savings**.
The `links` field alone accounts for **49% of total payload tokens across the corpus**.

Per-URL evidence (judge A → judge C, links tokens):

| Slug              | A | C | links toks | links count |
|-------------------|---|---|------------|-------------|
| pypi-page         | 5 | 5 | **10,391** | 287         |
| gh-trending       | 3 | 0 | **25,464** | 1,142       |  ← exception
| notion-public     | 5 | 5 | 7,990      | 395         |
| hn-front          | 4 | 4 | 4,529      | 197         |
| mdn-fetch-api     | 5 | 5 | 4,516      | 193         |
| vercel-blog       | 5 | 5 | 3,301      | 173         |
| stripe-docs       | 5 | 5 | 1,627      | 83          |
| linear-marketing  | 5 | 5 | 1,226      | 69          |
| habr (non-eng)    | 5 | 5 | 1,073      | 43          |
| medium-post       | 1 | 1 | 1,002      | 26          |

**Caveat: `gh-trending` is the only URL where links earned their keep** — the task ("list 5 trending repos") inherently needs link anchors, and C scored 0 vs A scored 3. This is a real signal: "list-extraction" tasks against aggregator pages do need link structure.

**Recommendation:** default `include_links=false`. Provide either (a) a separate `links` tool/param, or (b) a `mode="list_extraction"` toggle, or (c) site-handler tier-0 that returns structured items (handlers for HN/Reddit/GitHub already do this — extend to PyPI / npm / GitHub trending).

## H2 — Links should be categorized (nav / footer / inline / external) and only inline returned by default. **CONFIRMED (qualitatively).**

Eyeballing `runs/hn-front/a2web_raw.json`: each story has ~6 link entries (`anchor`, `from?site=`, `user?id=`, time, `hide?id=`, `comments`). Of those, only the story URL and the comments URL are content-bearing — 4 of 6 per story are UI noise.

PyPI's 287 links are mostly version-history dropdowns + sidebar nav.
gh-trending's 1,142 links are massively redundant (every repo has 4-5 redundant entries).

**Recommendation:** if links stay in the default response, classify them at extraction time: `{role: "primary"|"nav"|"meta"|"footer"}` and let downstream agents filter cheaply. Even cheaper: when site handlers exist, *prefer their structured output* and don't synthesize a links array from the DOM at all.

## H3 — Headings cheap enough to keep on. **WEAKLY CONFIRMED.**

`headings` tokens are tiny (median ~14 tokens, max 501 on Vercel/PyPI). B (drops links, keeps headings + diagnostics) vs C (content only) showed only **0.05 points difference** in mean judge score (3.20 vs 3.15). Headings don't earn their keep on this corpus, but they're cheap enough that the call is aesthetic.

**Recommendation:** keep headings; reconsider once the corpus includes more long-form documents where ToC would matter.

## H4 — `narrative` + `operator_hints` matter mostly on failures. **CONFIRMED.**

Tokens: `narrative` is 7-14 tokens per response (trivial). `operator_hints` is non-zero only on failures.

**Recommendation:** keep both. They're cheap, and operator_hints is the actionable failure surface.

## H5 — `diagnostics` carry their weight. **REJECTED for default; KEEP for debug mode.**

`diagnostics` is **~190 tokens on every response** (3,754 tokens total across the 20 URLs, ~3% of total). The diagnostic trace is debugging gold but the downstream agent rarely consumes it.

**Recommendation:** move `diagnostics` behind a `debug=true` flag, or return a compact one-line summary by default (`tier=raw verdict=ok 708ms`) and the full trace only when requested.

---

## Unplanned discoveries

### 🔴 `fit_md` is currently pure duplicate tax — 19% of total payload

CLAUDE.md already notes: *"`pruning_filter` (fit_md) is gone in v0.2 — the model carries `fit_md: str | None` for forward-compat, populated only if a future filter ships."* Reality check: **`fit_md == content_md` on 14 of 20 fetches**, contributing **23,893 duplicate tokens** to the corpus total. The 6 fetches where they differ are all *failed* fetches with empty content.

**Recommendation:** **don't populate `fit_md` with `content_md`** when no filter ran. Return `None`/omit. Saves ~19% of total tokens immediately. Trivial code change.

### 🔴 a2web's browser tier fired 0/20 times

`from_browser: False` across the entire corpus, including Reddit, X (Twitter), Linear, LWN, t.co — where raw failed and the gate had a real opportunity to escalate.

Looking at status flags:
- Reddit: status=failed, tier=raw — but no browser dispatch
- X: status=failed, tier=raw — but no browser dispatch
- Linear: status=failed but judge says content was fine (gate FP — see below)
- LWN: status=failed, tier=raw — no escalation

**Recommendation:** investigate why the gate's `suggested_tier="browser"` isn't being produced on these. Either (a) the gate's block_detector is misclassifying these as "thin content" rather than "blocked," skipping browser, or (b) the orchestrator's playbook doesn't route on `suggested_tier`. Either way, **a2web is shipping a browser tier it doesn't actually use** — a major capability gap vs. the architectural promise.

### 🟡 Gate false-positive on Linear

`linear-marketing` returned `status=failed` but the content was the real landing page (judge scored 5/5 on all 4 systems). The gate flagged it as failed when it wasn't.

**Recommendation:** audit `block_detector.py` against the Linear payload. Probably a heuristic threshold misfiring on JS-heavy but content-bearing pages.

### 🟢 a2web wins on Notion redirect

WebFetch returned a "REDIRECT DETECTED, please re-call" notice (judge scored 0 reached=false). a2web followed the 301 from `notion.so` → `notion.com` transparently and returned full content (judge scored 5).

This is a **real architectural win** for a2web — redirect handling is a stealth value-add WebFetch users don't realize they're missing.

### 🟢 Site handlers consistently produce smaller, higher-quality responses

| Slug              | Tier                       | A_full | judge |
|-------------------|----------------------------|--------|-------|
| arxiv-abstract    | site_handler:arxiv         | 1,501  | 5     |
| wikipedia-rust    | site_handler:wikipedia     | 21,705 | 3     |
| github-issue      | site_handler:github        | 1,052  | 5     |

(Wikipedia is the outlier because content_md itself is 10k — that's appropriate for a long article, not envelope bloat.)

Handlers add the most value on "structured but tier-1-eligible" sites — arxiv and github issue are 5/5 on tiny payloads.

**Recommendation:** prioritize adding handlers for **PyPI, npm, GitHub trending** — currently the worst envelope/value ratios in the corpus.

### ⚪ WebFetch loses on JS-rendered pages and aggregators, ties on clean HTML

Pages where WebFetch was meaningfully worse:
- **notion-public** (0 vs 5): redirect not followed
- **linear-marketing** (5 vs 5): tied actually (Linear surprisingly serves SSR content)
- **gh-trending** (3 vs 0 vs 0): WebFetch *won here* because its NL digest succeeded where a2web's content_md without links failed
- **npm-page** (0 vs 4): WebFetch hit 403, a2web got content

WebFetch's hidden strength: **its sub-model can extract a list-like answer from messy DOM where a2web's content_md is just nav text.** When a2web ships `mode="list_extraction"`, this advantage disappears.

### ⚪ Both tied on quality where pages were clean

arxiv, wikipedia, MDN, HN front page, GitHub issue, habr — both systems delivered correct answers. The difference there is purely token cost: a2web's full payload is 5-15× WebFetch's NL answer.

---

## False-positive lessons (process)

During the WebFetch phase I flagged a `<system-reminder>` block inside the habr.com WebFetch result as a "prompt injection." On re-verification it was the Claude Code harness's own task-tool reminder, rendered inside the tool-result envelope.

The mistake was instructive: even with full context, a careful reader misclassified harness signal as content. If a2web wants its downstream consumers to safely ingest scraped content alongside system messages, this argues for a **structural envelope** — e.g. wrapping the `content_md` field's value in something explicitly tagged (`<a2web:content>...</a2web:content>` or similar) so downstream agents can syntactically distinguish "page" from "system." Worth a BACKLOG entry.
