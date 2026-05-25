## Context

v0.20 (shipped one commit before this change) added an `affordances` field to `AskResponse` carrying page typing + content shapes + follow-up questions, alongside the existing `next_links`. Implementation followed the catalog model: always emit a full payload of typing-and-routing metadata.

After shipping, three exploration spikes compared the catalog model against alternative shapes:

- `eval/spikes/router_shape_v1.py` (4 URLs) — silent-when-complete router emits empty arrays when its answer is self-contained; −32% cost.
- `eval/spikes/router_shape_v2_stress.py` (5 stressed URLs designed to force partial answers) — Haiku self-assessment of partiality held on obvious-gap cases (3/3 correctly identified as `none`), but the permissive router prompt dropped into prose on HN front-page, producing a parse-fail where the rigid catalog held. Caveat: a too-silent router is brittle under JSON discipline.
- `eval/spikes/surface_eval_v1.py` (10 research-realistic URLs) — adding a singular `shape` field and a soft-cap "context decides count" instruction yielded −11.7% cost, zero obvious-filler follow-ups, zero parse failures, and reliable `shape` picks across all 10 pages. Exposed: rich pages (MDN, wiki, HN-front) where the silent router lost useful drilldowns.

The router-shape envelope in this proposal is the synthesis: omit-empty conditional fields like `_prune_wire`, axis-decomposed typing (no enum drift), JSON-rigid prompt (no prose fallback), and soft "context decides count" rather than hard caps.

Two constraints carry forward from existing architecture:
- **Cache-prefix byte-stability invariant** (v0.19) — the cache_prefix portion of the prompt template must be byte-identical to `EXTRACT_CACHEABLE_V1` so cross-call cache hits work on Anthropic + claude-agent-sdk paths.
- **`_prune_wire` envelope discipline** (v0.14) — omit-empty serializer on response models. The new fields must integrate with this helper, not bypass it.

## Goals / Non-Goals

**Goals:**
- Replace `AskResponse.affordances` with 7 explicit fields (3 required + 4 conditional via `_prune_wire`).
- Tighter, axis-decomposed `structural_form` / `genre` / `obstacle` enums — no synonym drift, no confusable-cluster workaround needed.
- Singular `shape` field replacing the `shapes[]` multi-pick.
- New `discussion` shape value for high-signal thread pages.
- Behavioral routing signal (presence of `try_url` ≈ "I think there's somewhere better") rather than a model self-rated `completeness` flag.
- Prompt tail ~40% smaller than v0.20 (~520 vs 853 tokens).
- Memory-isolation hardening on the claude_code provider (`mcp_servers={}`, `strict_mcp_config=True`, `agents={}`) to close the leak observed in surface eval v1.
- Replaces, doesn't coexist with, the v0.20 affordances surface.

**Non-Goals:**
- Structured-answer mode (auto-shape `answer: str | list | dict`). Defer to a future `extract` tool with consumer-supplied schema.
- Confidence scores on the model's self-rating. `page_kind_confidence` not resurrected unless a real consumer asks; if so, `debug=True`-only.
- Multi-axis tagging (`tags: list[str]`). The two-axis decomposition + obstacle is sufficient.
- Listing-record extraction shape. `record_extract` already owns listings; the router-shape is for the non-record path.
- Live-network output-benchmark A/B. User-triggered, runs after merge.

## Decisions

### D1 — Two-axis typing (structural_form + genre + obstacle) instead of monolithic page_kind

**Decision:** Replace v0.20's 29-value `page_kind` enum with three orthogonal fields:
- `structural_form: Literal[...]` — required, 9 values, what the page IS structurally.
- `genre: Literal[...] | None` — optional, 7 values, what the page is ABOUT.
- `obstacle: Literal[...] | None` — optional, 4 values, page-level failure mode.

**Why:** The 29-value enum had close synonyms (`news` vs `news-article`, `package` vs `package-page`) causing model drift across runs. v0.20 added confusable-cluster rules A-G in the prompt to disambiguate, costing ~150 tail tokens. The axis decomposition removes the synonym problem entirely: `news` (genre) and `article` (structural) can't compete — they're on different axes.

**Why these specific enums:**
- `structural_form` values picked by collapsing v0.20's enum onto structural-shape boundaries (article, thread, listing, reference, tutorial, changelog, code, product, media, other). `spa` dropped — it's a *technical detail* (page needs JS), not a structural type; once browser tier resolves the page, it's a regular article/listing/thread.
- `genre` values picked to cover the realistic discriminators downstream agents care about (news vs encyclopedia vs spec vs paper vs personal opinion vs official docs vs community UGC). Omitted on pages where none clearly applies.
- `obstacle` values preserved from v0.20's obstacle subset — these are operationally important (cache-discipline, retry decisions).

**Alternatives considered:**
- Keep v0.20's 29-value enum + cluster rules. Rejected: the rules cost prompt tokens for ambiguity the tighter enum eliminates by construction.
- Single `page_kind` enum reduced to 15 values. Rejected: still has synonym drift on news vs article vs blog, and loses the "topic vs structure" distinction.
- Multi-axis `tags: list[str]`. Rejected: open-ended lists trigger schema drift in Haiku (validated in research thread); closed enums on each axis are more reliable.

### D2 — Drop `content_value` and `completeness`

**Decision:** Remove both as wire fields.

**Why:** Both are paraphrased by signals already present:
- `content_value: low` ≈ `ask_here` empty + content-kind `structural_form` (the model has nothing more useful to ask about this URL).
- `content_value: high` ≈ `ask_here` populated.
- `completeness: complete` ≈ `try_url` empty (model has no better URL to suggest).
- `completeness: none` ≈ `obstacle` populated OR `try_url` populated + answer starts with "no answer found".

The most reliable signal is *behavioral* (whether the model emitted suggestions), not self-rated. Self-ratings have a confidence bias — the model that confidently labels a wrong page kind also confidently rates an incomplete answer as complete. Behavioral signal can't be falsified the same way.

**Alternatives considered:** Keep `completeness` as a debug-only field. Rejected: same reliability concern; we're not adding fields that downstream agents shouldn't trust as primary signals.

### D3 — Singular `shape` instead of `shapes[]` multi-pick

**Decision:** Replace `affordances.shapes: list[AffordanceShape]` with `shape: Literal[...]` (one value, required, 7 values including new `discussion`).

**Why:** `shapes[]` was multi-pick in v0.20 (a page can have a table AND a list AND code). Surface eval v1 showed: agents don't branch on combinations, they branch on the *primary* shape. The list form added per-call tokens (per-item structured object) for marginal downstream value. Singular `shape` with `mixed` as the fallback covers the combinatorial case.

**Why add `discussion`:** Surface eval v1 showed `mixed` was too vague for thread pages (HN item, reddit, lobste, blog-with-comments) — these are a recurring, high-signal shape worth a dedicated label. They're not just "prose plus comments"; the comment tree IS the primary content for many questions.

**Alternatives considered:**
- Keep `shapes[]` but cap at 1 by prompt. Rejected: doesn't save tokens, doesn't move semantics.
- Use `primary_shape` + `secondary_shapes: list`. Rejected: same complexity, same downstream-branch question.

### D4 — Behavioral routing signal (omit-empty arrays) instead of explicit completeness flag

**Decision:** No `completeness` field. Routing intent is encoded by the *presence and content* of `ask_here` / `try_url`. Empty arrays are omitted by `_prune_wire`.

**Why:** Per D2 — behavioral signal is more honest than self-rating. Also: the omit-empty discipline matches v0.14's `_prune_wire` pattern, so the helper extends without a new code path.

**Wire shape:**
```json
// Full answer, nothing more to suggest:
{"answer": "...", "structural_form": "article", "shape": "prose"}

// Partial — model has follow-ups but no better URL:
{"answer": "...", "structural_form": "reference", "shape": "mixed",
 "ask_here": ["..."]}

// Failed — paywall, suggesting archive:
{"answer": "no body, paywalled", "structural_form": "article", "shape": "prose",
 "genre": "news", "obstacle": "paywalled",
 "try_url": [{"url": ".../archive/...", "reason": "Wayback before paywall"}]}
```

### D5 — Soft cap ("context decides count, 3 good 5 great, up to 10 fine on rich pages, [] on simple")

**Decision:** Phrase the suggestion-count guidance as a target range, not a hard cap.

**Why:** v1 spike's hard "≤3" caused the model to over-trim on rich pages (MDN array reference would naturally suggest 4-7 method drilldowns; the cap forced it to pick 2-3 and lose useful coverage). v0.20's "exactly 5" caused obvious-filler. The middle ground: "3 good, 5 great, up to 10 fine, [] for simple". Lets question + content shape decide.

**Risk:** without a hard cap, the model could in theory emit 20 items on a wiki page. Surface eval v1 showed Haiku self-regulates well with soft guidance — no run emitted more than the catalog baseline. Hard cap remains in the model layer (`max_tokens=1024`) as a safety net.

### D6 — `EXTRACT_ROUTER_V1` template, byte-identical `cache_prefix` to `EXTRACT_CACHEABLE_V1`

**Decision:** New template `EXTRACT_ROUTER_V1` replaces `EXTRACT_WITH_AFFORDANCES_V1`. The `cache_prefix_template` must be byte-identical to `EXTRACT_CACHEABLE_V1.cache_prefix_template` (matches the v0.20 design decision).

**Why:** Cache-prefix byte stability is the cross-call cache discipline. Anthropic prompt caching and claude-agent-sdk's internal cache both key on the prefix. Page content lives in the cache_prefix; system + tail carry the router-shape instructions. If `cache_prefix` drifts, cross-call cache hits stop on every URL re-asked with a different question.

**Tail content (~520 tokens):**
- 1 short paragraph framing the answer-first instruction
- 9-value `structural_form` enum with one-line per value
- 7-value `shape` enum with one-line per value
- 7-value `genre` enum + "omit when none applies" rule
- 4-value `obstacle` enum + "omit when no obstacle" rule
- `ask_here` rule (obvious-filler cut, soft cap)
- `try_url` rule (Q-conditioned reason requirement, soft cap)
- One JSON envelope example showing omit-empty pattern

**Drops from v0.20 tail (~333 token savings):**
- Cluster rules A-G (~150 tokens) — no synonyms to disambiguate.
- `content_value` rules (~80 tokens) — field removed.
- `page_kind_confidence` decision rules (~30 tokens) — field removed.
- `affordances.reasoning` field (~10 tokens).
- Multiple JSON examples consolidated to one (~60 tokens).

**Alternatives considered:**
- Reuse `EXTRACT_WITH_AFFORDANCES_V1` with a feature flag. Rejected: dual-mode prompts are a maintenance hazard, and the content drift is large enough that two templates communicate intent better.
- Build the tail dynamically per kwarg (request_routing, request_typing, etc.). Rejected: combinatorial explosion of cache_prefix variants; better to have one canonical router template.

### D7 — Memory-isolation hardening on claude_code provider (folded into same release)

**Decision:** Add `mcp_servers={}`, `strict_mcp_config=True`, `agents={}` to `ClaudeAgentOptions` in `claude_code.py`. Surface `num_turns` from `ResultMessage.raw` for paranoid verification.

**Why:** Surface eval v1 observed user-memory contamination in a catalog HN response ("Which posts would appeal most to Denis's known interests…"). The existing opt-outs (`setting_sources=[]`, `skills=[]`, `disable-slash-commands`) cover CLAUDE.md / skills / slash-commands. The leak path was MCP servers loaded by the host Claude Code CLI (`hub_memory_recall` and similar). The SDK doesn't auto-disable host CLI's MCP config.

**Why fold into this release:** The leak surfaced during the surface eval that motivated this refactor. Shipping the prompt change without the isolation fix would leave a known production data-exfil risk on the surface that downstream agents read. They land together or not at all.

**Alternatives considered:** Separate change for isolation. Rejected: artificial sequencing; both fixes touch the same code path and same test gates; one CHANGELOG entry is clearer than two adjacent ones.

### D8 — Clean replace, no coexistence path

**Decision:** v0.20's `affordances` field is removed entirely. No deprecation alias. No dual-mode `Extractor.extract(request_affordances= OR request_routing=)`.

**Why:** External consumers of v0.20 = the user's own Claude Code MCP install only (v0.20 shipped this morning, never propagated past the local install). Breakage radius is one consumer who'll run `make install-global` after the merge. Coexistence would burn maintenance budget for no real-world benefit.

**Migration steps documented in tasks.md.**

## Risks / Trade-offs

- **Risk:** Soft-cap on `try_url` causes the model to over-emit on rich pages (e.g., 15 wiki drilldowns).
  → **Mitigation:** Surface eval v1 measured Haiku self-regulates well; `max_tokens=1024` is the hard ceiling. If production data shows over-emission, hard cap re-introduced in a follow-up prompt iteration without breaking the field shape.

- **Risk:** Singular `shape` loses information for genuinely-mixed pages where two shapes matter (e.g., an API reference that is mostly prose but has critical tables).
  → **Mitigation:** `shape=mixed` is the fallback for this case. If consumers ask for sub-shapes, add `secondary_shape: ShapeLabel | None` as a non-breaking later iteration.

- **Risk:** `discussion` shape is too narrow — comment trees vary (HN flat-ish, reddit nested, lobste threaded, Disqus opaque).
  → **Mitigation:** Single label is intentionally coarse. Sub-discrimination (depth, count, nested-vs-flat) belongs in `ask_here`-conditioned questions, not the typing axis.

- **Risk:** Two-axis typing (form + genre) confuses Haiku in edge cases where the structural form has its own canonical genre (e.g., `changelog` is always `official`).
  → **Mitigation:** Tail-prompt examples will pre-pair the canonical cases. If model drifts, add prompt examples; do not collapse the axes back into one field.

- **Risk:** `_prune_wire` omit-empty discipline trips downstream parsers that assume the v0.20 shape (e.g., always expect `affordances`).
  → **Mitigation:** Documented BREAKING in CHANGELOG. The local Claude Code MCP install regenerates on `make install-global`. No external consumers.

- **Risk:** Memory-isolation hardening (D7) breaks legitimate MCP usage by a future consumer who wants their tools available to the Haiku call.
  → **Mitigation:** Future-feature — out of scope. Today the `ask` tool's Haiku call is pure extraction; no tool use is required (the existing `tools=[]`, `max_turns=1` already enforce this).

- **Trade-off:** The v0.20 affordances surface lives for one release cycle (one commit) before being superseded. This looks unstable from the outside. Internally: the affordances work was the stepping stone that exposed the right design through three spike runs. CHANGELOG entry will frame the supersession honestly.

## Migration Plan

1. Land prompt template `EXTRACT_ROUTER_V1` in `prompts.py` alongside `EXTRACT_WITH_AFFORDANCES_V1` (transient coexistence in the same file is fine — only one is wired up at a time).
2. Land boundary type `packages/llm_extract/router_payload.py` with `RouterPayload` frozen dataclass.
3. Update `Extractor.extract` to switch on `request_routing` instead of `request_affordances`. Old kwarg name removed in the same commit.
4. Update `LlmExtractorResource.extract` and `FetchContext.routing`. Old field removed.
5. Update `models.py`: drop `AffordancesPayload`, add `RouterPayload` pydantic + all literal types + `AskResponse` field swap. `_prune_wire` already handles the omit-empty pattern; just register the new optional fields.
6. Update `routers.py`: `WebRouter.ask(include_routing=True)` replaces `include_affordances`.
7. Update `fetcher_response.py`: `_project_routing` replaces `_project_affordances`.
8. Update `claude_code.py` with D7 isolation fields + `num_turns` surfacing.
9. Replace `tests/packages/llm_extract/test_affordances_parse.py` → `test_router_parse.py`. Replace `tests/capabilities/ask_response/test_affordances_wire.py` → `test_router_wire.py`. Update `test_prompt_cache_stability.py` for the new template name (existing assertions on byte-identity to base template still apply).
10. Re-bless `tests/contracts/{ask_debug.json, tool_schemas.json}`.
11. `make check` → all green (≥85% coverage gate).
12. CHANGELOG v0.21.0 entry: framed as a clean supersession; note the one-release lifespan honestly.
13. `make install-global` after merge to propagate to user's Claude Code MCP.
14. Re-run surface eval v1 against the new template; capture findings doc.
15. Output-benchmark A/B (`make bench`) — user-triggered, post-merge.
16. `openspec archive refactor-ask-to-router-shape`.

**Rollback:** Single commit revert. Affordances surface returns. No data migration (response shape only; no persisted state).
