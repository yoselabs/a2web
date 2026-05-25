## Why

The v0.20 affordances surface on `ask` (shipped one commit ago) treats the model as a catalog: emit page typing, shapes, follow-up questions, and ranked links as separate fields, always populated. Three exploration spikes (`router_shape_v1`, `router_shape_v2_stress`, `surface_eval_v1`) showed that:

1. The catalog wastes tokens on rich-page typing and obvious follow-ups (5 follow-ups, 5 next_links, 3 shapes per call even when the answer is complete and self-contained).
2. The `affordances.page_kind` 29-value enum has synonym drift (`news` vs `news-article`, `package` vs `package-page`) — the cluster-rules workaround costs ~150 tail tokens for ambiguity that disappears with a tighter, axis-decomposed enum.
3. `content_value` is paraphrased by the presence/absence of suggestion arrays + the obstacle kinds — keeping it costs 80 tail tokens for no agent-decision change.
4. The model can pick `shape` reliably with a single closed value; the `shapes[]` list (multi-pick) bloats the envelope and rarely changes downstream behavior.

The result of the exploration is a router-shape envelope: same Haiku call, ~40% smaller tail prompt, omit-empty conditional fields, axis-decomposed typing, and behavioral routing signals (presence of `try_url` ≈ "I think there's somewhere better"). Surface eval v1 measured −11.7% cost across 10 research-realistic URLs with zero parse failures and zero obvious-filler follow-ups, while the `shape` field picked the right value on all 10 pages.

## What Changes

**BREAKING** — `AskResponse` wire format changes. Direct supersedes `add-affordances-to-ask` (archived in same release). No external consumers depend on v0.20 yet besides the local Claude Code MCP install.

- **NEW** `ask` response fields (7):
  - `answer: str` — required, unchanged semantics. Enumeration questions put the list in here as compact markdown.
  - `structural_form: Literal["article","thread","listing","reference","tutorial","changelog","code","product","media","other"]` — required, 9 values, no synonyms. Replaces `page_kind`. `spa` dropped (technical detail, not structure — `tier=browser` already signals it).
  - `shape: Literal["prose","records","key-value","code","table","discussion","mixed"]` — required, 7 values. New `discussion` value for thread-style pages (HN item, reddit, lobste, blog-with-comments). Folds in `affordances.shapes[]` (was multi-pick list, now singular).
  - `genre: Literal["news","encyclopedia","spec","paper","personal","official","community"] | None` — optional, omitted via `_prune_wire` when no value clearly applies. Captures "what the page is ABOUT" orthogonal to `structural_form`.
  - `obstacle: Literal["paywalled","blocked","empty","error"] | None` — optional, omitted on healthy pages. Replaces the obstacle subset of v0.20's `page_kind`.
  - `ask_here: list[str]` — optional, omitted when `[]`. Same-URL re-asks. Quality-filtered: emit ONLY questions whose answer requires reading the body, never obvious-from-title-or-byline questions.
  - `try_url: list[NextUrl]` — optional, omitted when `[]`. Different-URL re-asks where each entry has `{url, reason}` with question-conditioned reasons. Context decides count (3 good, 5 great, up to 10 fine on rich pages, [] on simple ones).

- **REMOVED** v0.20 fields:
  - `affordances` field on `AskResponse` (and the entire `AffordancesPayload` pydantic + boundary type).
  - `affordances.page_kind` (29-value enum) — replaced by `structural_form` + `genre` + `obstacle`.
  - `affordances.page_kind_confidence` — model self-rating that agents rarely act on; resurrect under `debug=True` only if a real consumer asks.
  - `affordances.content_value` — paraphrased by presence-of-`ask_here` and `obstacle`.
  - `affordances.shapes: list[AffordanceShape]` — folded into singular `shape: str`.
  - `affordances.follow_up_questions` — renamed `ask_here` with obvious-filler prompt rule.
  - `affordances.reasoning` — model uses a one-liner in `answer`, not a separate field.

- **REPLACED** prompt template:
  - `EXTRACT_WITH_AFFORDANCES_V1` (853 tail tokens) → `EXTRACT_ROUTER_V1` (~520 tail tokens, −40%). `cache_prefix` stays byte-identical to `EXTRACT_CACHEABLE_V1` (load-bearing — cross-call cache discipline depends on it).
  - Drops confusable-cluster rules A-G (tighter enum has no synonyms to disambiguate, so nothing to disambiguate).
  - Adds soft-cap phrasing for `ask_here` / `try_url` ("context decides count, 3 good 5 great").
  - Adds obvious-filler rule for `ask_here` ("answer must require reading the body").

- **RENAMED** API:
  - `Extractor.extract(request_affordances=)` → `Extractor.extract(request_routing=)`.
  - `WebRouter.ask(include_affordances=True)` → `WebRouter.ask(include_routing=True)`.
  - `FetchContext.affordances` → `FetchContext.routing`.
  - `_project_affordances` → `_project_routing`.
  - Boundary type file `packages/llm_extract/affordances.py` → `packages/llm_extract/router_payload.py`.

- **NEW** memory isolation hardening (folded into same release — surfaces during the surface eval HN response leak):
  - `claude_code.py` provider options gain `mcp_servers={}` (disable all MCP servers regardless of host CLI config), `strict_mcp_config=True` (fail-closed on MCP drift), `agents={}` (disable preset subagents).
  - Surface `num_turns` from `ResultMessage.raw` for paranoid verification (always 1 with existing `max_turns=1` cap; surfacing makes the invariant assertable).

## Capabilities

### New Capabilities

(none — this is a refactor of existing capabilities)

### Modified Capabilities

- `ask-response`: response envelope replaces `affordances` field with seven router-shape fields (3 required + 4 conditional via `_prune_wire`).
- `extraction`: LLM extraction surface adopts `EXTRACT_ROUTER_V1` template; `Extractor.extract` kwarg renamed `request_routing`; boundary type replaced; MCP isolation hardened on the claude_code provider.

## Impact

- **Wire format breaking** for any consumer of the v0.20 `ask` response — but external blast radius is the user's own Claude Code MCP install only. `make install-global` needs to run after merge.
- **Code surface**: 7 files modified (prompts.py, extractor.py, fetcher.py, fetcher_response.py, models.py, routers.py, llm_resource.py) + boundary type rename + claude_code.py isolation fields. Tests follow the same rename (`test_affordances_*` → `test_router_*`).
- **Cost** drops ~10-12% per `ask` call (eval v1 measured −11.7%). Prompt tail drops ~40% (~520 vs 853 tokens).
- **No new dependencies**. Same Haiku call, same DI shape, same `_prune_wire` envelope-discipline helper.
- **Contracts**: `tests/contracts/{ask_debug.json,tool_schemas.json}` re-bless required (template name + new fields + new tool kwarg).
- **CHANGELOG**: v0.21.0 supersedes the v0.20.0 affordances surface. Note in the entry that the affordances surface was a one-day stepping-stone — design refined through three exploration spikes after shipping.
- **BACKLOG**: closes the affordances item; opens `extract` tool with consumer-supplied schema (deferred structured-answer mode); opens `page_kind_confidence` resurrection if a real consumer asks.
