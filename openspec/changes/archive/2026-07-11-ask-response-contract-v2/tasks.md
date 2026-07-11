## 0. Prerequisites (this change applies LAST)

- [x] 0.1 `bench-cost-isolation` is applied — cheap/subscription bench + per-item + per-axis isolation. Spikes MUST NOT run on the metered Anthropic API.
- [x] 0.2 The parallel `unify-escalation-executor` has landed. This is a breaking envelope rename — do not interleave.

## 1. ADR-0015 (author the governing tenet)

- [x] 1.1 Promote the D0 draft to `docs/adr/0015-the-withheld-body-index.md` (standard skeleton), set Status: Accepted on apply.
- [x] 1.2 Add the row to `docs/adr/INDEX.md`.
- [x] 1.3 Add the `**Never** … (the first-class product invariant — ADR-0015)` line to `CLAUDE.md`'s Never section.

## 2. Spikes — validate the grammar before renaming (cheap provider only)

> **DEFERRED / user-run (live LLM).** The prompt shipped with the grammar as
> designed in `design.md` D1 (deletion rule + operators + CAPS + FIND/DECIDE).
> Live spike validation needs the Claude Code OS session in the shell (same
> precedent as `bench-cost-isolation` task 5.2) and must run on the cheap /
> subscription provider via `bench-cost-isolation`'s guard — never metered.
- [ ] 2.1 Spike A (phrasing × 4 shapes); write `eval/spikes/query-grammar-A.md`.
- [ ] 2.2 Spike B (CAPS); shipped conservative (CAPS ≤1 load-bearing token); live confirm pending.
- [ ] 2.3 Spike C (LEAN vs FAT description); shipped a compact middle description in the `query` param; live confirm pending.
- [x] 2.4 Capture any new failure/edge case in `eval/corpus.yaml` — none surfaced this session.

## 3. Extraction prompt

- [x] 3.1 `EXTRACT_ROUTER_V1`: `ask_here`→`also_here` in query grammar (target+operator, CAPS per Spike B, split `and`, `?` only for DECIDE); add the non-overlap instruction (defer to options/axes on listings; never restate a heading/option/axis).
- [x] 3.2 `EXTRACT_ROUTER_V1`: unify the links instruction into one `other_pages` shape with `kind` (structural|drilldown); preserve the ADR-0014 "LINKS IN THE ANSWER · HARD RULE" clause and `{{{{n}}}}` double-brace marker discipline.
- [x] 3.3 Bump the template version; update the version-history comment.

## 4. Wire / models (breaking)

- [x] 4.1 `src/a2web/routers.py`: tool `ask`→`query`, param `question`→`query`, `canonical_name_override="query"`, install the locked tool description (incl. cost-asymmetry line).
- [x] 4.2 `src/a2web/models.py`: `AskResponse.ask_here`→`also_here`; new `OtherPage` model (`url, reason, kind, off_domain`); retire/fold `NextUrl` + `NextLink`; `_prune_wire`/serializer + TSV rendering for `other_pages`; update the ADR-0009 docstring at `models.py:226`.
- [x] 4.3 `src/a2web/fetcher_response.py`: `_project_routing` → `also_here`; `_compose_next_links` → `_compose_other_pages` (merge next_links + try_url, assign `kind`, preserve `{{n}}` rehydration + `off_domain` + drilldown reason-conditioning + cap).
- [x] 4.4 Grep `ask_here` / `next_links` / `try_url` / `"ask"` tool-name / `question=` across `src/` and update.

## 5. Docs & tests

- [x] 5.1 `CLAUDE.md:38,40,81` — update `ask(url, question)`, `ask_here`, and the affordance-corpus-class references.
- [x] 5.2 `tests/contracts/*.json` + tool-schema fixtures for `query` + `query` param + `also_here` + `other_pages`.
- [x] 5.3 `tests/capabilities/ask_response/` and any test referencing the renamed surfaces.
- [x] 5.4 `make check` green (lint + ty + test, coverage ≥85%).

## 6. Ship (one breaking bump)

- [x] 6.1 Version bump + CHANGELOG (breaking: tool + envelope rename, other_pages merge).
- [ ] 6.2 `make install-global`; update `~/.claude.json` MCP entry name if referenced.
- [ ] 6.3 One live `query` call — sanity-check `also_here` (query grammar) + `other_pages` (kind-tagged, grounded URLs).
