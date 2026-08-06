## Context

`build_ask_response` (`src/a2web/fetcher_response.py`) sets two fields from the same source, `fr.content_md`, under overlapping conditions:

```python
# ~line 1002
thin_content = fr.content_md if (empty_confirmed or has_hint(op_hints, "content_thin")) else None
# ~line 1039
content_md = fr.content_md if include_content else ""
```

When both conditions hold — a thin/empty-confirmed outcome AND `include_content=True` — the wire carries the identical string twice under two different keys. `thin_content` exists per ADR-0015 to guarantee the body reaches the wire on these outcomes specifically because `query` withholds content by default; once `content_md` is already present, that guarantee is already satisfied by another field.

The `ask-response` spec currently makes this an explicit requirement ("its presence SHALL NOT depend on `include_content`"), so this is a requirement change, not just a code fix.

## Goals / Non-Goals

**Goals:**
- Eliminate the duplicate body on the wire when `include_content=True` coincides with a thin/empty-confirmed outcome.
- Preserve the existing guarantee for the default (`include_content=False`) case exactly as-is.
- Cover both trigger paths that set `thin_content`: the `content_thin` hint path (`thin_unverified`/`empty_unverified`) and the promoted-`ok` corroborated-empty path.
- Update ADR-0015 and the `ask-response` spec so the contract is stated, not just implemented.

**Non-Goals:**
- No change to `FetchResponse`/`fetch_raw` — it has no `thin_content` field, unaffected.
- No change to when `content_md` itself is populated (`include_content` semantics untouched).
- No change to the `content_thin` / `content_empty` operator hints — they still fire independently of this guard.
- No wire type change, no new field, no tool signature change.

## Decisions

**D1 — Guard condition: presence, not equality.** Omit `thin_content` when `content_md` is truthy (non-empty) on the built response, rather than comparing the two strings. The two are populated from the same source (`fr.content_md`) so they can't diverge in practice; guarding on presence is simpler, matches the existing presence-guard pattern the module already documents (models.py's `_prune_wire` fixes), and doesn't need a value comparison that would be meaningless if content_md were ever truncated differently in the future.

**D2 — Apply the same guard to both trigger paths.** The `empty_confirmed` (promoted-ok) case and the `content_thin` hint case both currently set `thin_content = fr.content_md` unconditionally. Considered treating `empty_confirmed` differently since it's the "wire-only, never cached" synthetic-answer case — but the reason `thin_content` exists there is identical (let the caller verify the synthetic "no results" answer against the real body when the body was otherwise withheld). If `content_md` is already on the wire via `include_content=True`, the caller already has that verification path. No reason found to special-case it — same guard, single implementation site.

**D3 — Where the guard lives.** Apply it at the point `thin_content` is assigned (`fetcher_response.py:1002`), reading the already-computed `content_md` opt-in state (`include_content`) directly rather than introducing a new intermediate flag. Since `content_md`'s value is `fr.content_md if include_content else ""`, the guard condition is equivalent to `not include_content` — implement it as reading `include_content` for clarity (the field being empty vs. absent is not itself the semantic being guarded against; the opt-in flag is the actual cause).

## Risks / Trade-offs

- **[Risk] A caller that unconditionally reads `thin_content` on a `content_thin` hint, without checking `content_md`, silently gets nothing when it previously got the duplicate.** → Mitigation: spec and ADR both state the new contract explicitly ("check `content_md` first; `thin_content` is a fallback"); this is the intended behavior — the caller already has the body via `content_md`.
- **[Risk] Widening scope by touching the `empty_confirmed` path could interact with the "never cached" rule for promoted-empty responses.** → Mitigation: the guard only changes wire presence of `thin_content`, not caching behavior; the promoted-empty response was already excluded from cache before this change and remains so — no code path here touches `cache.py`.

## Migration Plan

No migration — this is a same-deploy, same-version wire behavior change gated purely on call parameters. No data model change, no staged rollout needed. Land the code + spec + ADR changes together.

## Open Questions

None outstanding — D1–D3 above resolve the design questions raised during exploration (a2web-y5m).
