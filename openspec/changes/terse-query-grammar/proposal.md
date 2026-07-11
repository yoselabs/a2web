## Why

The `ask` tool's self-suggested follow-ups (`ask_here: list[str]`) are emitted as full, hedged questions — "Are there any community discussions or issues in the Home Assistant forum about Multitek intercom integration challenges?". Two problems:

1. **They read as prose, not intent.** The load-bearing part of a follow-up is its *target* (the noun you want) plus its *discriminator* (a contrast, a qualifier, a list). The rest — "Are there any…", "Do any reviews mention…", the re-named entity you are already looking at — is scaffolding that carries no information but costs output tokens on every `ask` call and dilutes the signal the next fetch is steered by.
2. **Naive compression to keywords is lossy.** Dropping to a bare noun-bag ("Multitek Apple Home connection issues") destroys the *fork* ("Apple-Home-specific vs all platforms?"), the *qualifier* ("OFFICIAL troubleshooting"), and hides *compounds* (an `and`-joined double question). Keywords are lossless only for list-shaped questions.

The reconciliation: a follow-up is a **query**, not a question — defined by what you *delete* (the verb frame, the already-known entity), keeping the target and the one operator that discriminates. This leans entirely on priors the model already has (natural language + Google-search grammar), so the tool description stays tiny — no invented DSL.

The primary cost lever is not the query string's own tokens (negligible) — it is fetch hit-rate: a concrete, precisely-scoped follow-up lands the answer in one proxy fetch instead of two. The proxy fetch is the scarce cost (a wasted jina fetch costs more than every suggestion string combined).

## What Changes

- **Rename the tool `ask` → `query` and its `question` param → `query`** (full cascade — decided this session). `fetch_raw` / `refresh` unaffected. The `canonical_name_override` pin moves from `ask` to `query`.
- **Rename the `ask_here` response field → `refine`** — a list of same-URL follow-up **queries** (not questions). `refine` keeps the locality that a flat `queries` would lose.
- **Define the query grammar** (see `design.md`): a *deletion rule*, not additive syntax. Drop the verb frame and the already-known entity; keep the target noun(s) + the discriminating operator (`,` list · `vs` contrast · `/` alternatives · `CAPS` the one word that decides). Keep a `?` only when asking `query` to *judge*, not to *find*. If a follow-up needs `and`, it is two queries — split it.
- **Update the extraction router prompt** so the model emits `refine` items in query grammar (concise target + operator), replacing the current full-question instruction for `ask_here`.
- **Rewrite the tool description** to teach the grammar in ≤ ~50 words (strawmen in `design.md`), and prescribe the query shape for the caller's own `query` input too.
- **Validate before shipping via the query-grammar spikes** (A: does terseness cost extraction fidelity; B: does CAPS emphasis help; C: lean vs fat tool description). The spikes depend on the cheap-bench work in the sibling `bench-cost-isolation` change — do not run them on the metered API.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `ask-response`: the tool renames `ask` → `query` / `question` → `query`; the `ask_here` wire field renames to `refine` and its content contract changes from "questions" to "query-grammar strings".
- `extraction`: the `EXTRACT_ROUTER_V1` instruction for follow-up suggestions changes from full questions to query-grammar (target + operator, CAPS the decider, split compounds).

## Impact

- **BREAKING (MCP + parsers):** tool name `ask` → `query`, param `question` → `query`, response field `ask_here` → `refine`. Breaks installed MCP clients, `~/.claude.json` config, `canonical_name_override` pins, and any envelope parser. Gated behind the parallel feature landing; apply as a deliberate version bump + `make install-global`.
- `src/a2web/routers.py` — tool + param rename, `canonical_name_override`, description.
- `src/a2web/models.py` — `AskResponse` field `ask_here` → `refine`; serializer/prune wiring.
- `src/a2web/packages/llm_extract/prompts.py` — router prompt follow-up instruction.
- `src/a2web/fetcher_response.py` — `_project_routing` field mapping.
- `openspec/specs/ask-response/spec.md`, `openspec/specs/extraction/spec.md` — deltas.
- Tests referencing `ask` tool name / `ask_here` field — to be located and updated during apply.
- Validation is spike-driven (see `design.md`), NOT a full `make bench` run on metered API.
