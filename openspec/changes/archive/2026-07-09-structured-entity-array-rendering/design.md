## Context

Traced live during the `ask-extraction-token-tuning` exploration, in response to a concern about losing phone/email/contact facts: a2web's extraction escalation ladder (`_phase_extract` → `_escalate_via_json` → `json_to_markdown_rows` → `_single_entity_md`, `fetcher.py`/`domain.py`) already renders `LocalBusiness`/`Organization`/`ContactPoint` JSON-LD into the LLM's prompt content, per ADR-0004's "default-keep" philosophy (`extraction` capability spec, "JSON-LD single-entity rendering is default-keep, not an allowlist"). Verified working for the single-nested-object case:

```python
if isinstance(val, dict):
    inner = ", ".join(f"{k}={v}" for k, v in val.items() if _scalar_kv(k, v))
    if inner:
        lines.append(f"- **{key}:** {inner}")
```

But schema.org's own spec for `Organization.contactPoint` (and `LocalBusiness.address`, and others) explicitly permits either a single `ContactPoint` object or an **array** of them (`"contactPoint": [{...}, {...}]` — e.g. one for sales, one for support). The current list-value branch:

```python
elif isinstance(val, list):
    scalars = [str(v) for v in val if isinstance(v, (str, int, float)) and str(v)]
    joined = ", ".join(scalars)
    if joined and len(joined) <= _ENTITY_VALUE_CAP:
        lines.append(f"- **{key}:** {joined}")
```

...only keeps scalar list items. A list of `ContactPoint` dicts produces `scalars = []`, `joined = ""`, and the entire field is dropped — no error, no log, just silence. This is precisely the "unanticipated field silently lost" failure mode the requirement's docstring says it eliminates ("No fixed `interesting_keys` allowlist — an unanticipated answer-bearing field... is no longer silently lost") — it just didn't anticipate this particular shape.

## Goals / Non-Goals

**Goals:**
- When a JSON-LD entity field's value is a list of dicts, render each dict as its own flattened line (same one-level scalar flatten already applied to a single nested dict), so multi-entry `contactPoint`/`address`/similar fields survive into the LLM's prompt.
- Keep the existing scalar-list rendering path (`keywords: [...]`, `sameAs: [...]` when they're plain strings) completely unchanged — this is additive.
- Stay within `_single_entity_md`'s existing complexity budget — this is a small, local fix, not a rewrite.

**Non-Goals:**
- Deep (2+ level) recursion into arbitrarily nested structures — schema.org's practical nesting depth for these entity/answer types is shallow (one level under the array), and CLAUDE.md's magic-budget discipline argues against speculative generality here.
- Changing `is_answer_bearing` / `_ld_json_strong` / `_PREFERRED_LD_TYPES` (the shelf's `json_in_html` ranking/gating) — untouched, out of scope.
- Any wire/schema change — this is purely about what text reaches the LLM's prompt via `content_candidates`, never a response model field.

## Decisions

**D1 — Render each dict in a list-of-dicts as its own sub-line under the parent key, not a single flattened blob.** E.g.:

```
- **contactPoint:**
  - telephone=+1-800-555-0100, contactType=sales
  - telephone=+1-800-555-0200, contactType=support, email=support@example.com
```

rather than trying to cram all entries onto one line (which risks exceeding `_ENTITY_VALUE_CAP` and produces a harder-to-read wall of `k=v` pairs once entries are combined). Alternative considered: flatten all dicts into one comma-joined line like the existing scalar-list path — rejected, multi-entry contact info is exactly the case where losing the entry boundary (which number belongs to which department) would make the rendered text actively misleading, not just verbose.

**D2 — Reuse `_scalar_kv` for each per-entry flatten, unchanged.** No new filtering logic — same noise rules (`@`-prefixed keys, empty values) already govern the single-object case.

**D3 — Cap the number of rendered array entries defensively (e.g. 10), mirroring the existing `_ENTITY_VALUE_CAP` / `[:50]` caps elsewhere in this file (`_find_product_or_item_list`).** Guards against a pathological page with a huge `contactPoint` array bloating the prompt; real-world entity/answer schemas rarely have more than a handful of contact points.

## Risks / Trade-offs

- **[Risk] Prompt-content growth on pages with large entity arrays.** Mitigated by D3's cap; also bounded by the existing overall `max_content_chars` truncation downstream.
- **[Trade-off] This is additive complexity to an already-dense renderer function.** Accepted — the alternative (silently dropping real-world-common multi-entry contact data) is the worse failure mode per ADR-0009's "never tolerate a silent miss" floor, and the fix is small and localized.

## Migration Plan

1. Extend `_single_entity_md`'s list-value branch per D1-D3.
2. Add a fixture-level test: a `LocalBusiness` (or `Organization`) JSON-LD with an array `contactPoint` of 2+ entries, asserting the rendered markdown contains each entry's `telephone`/`email` distinctly.
3. Add architecture-level coverage alongside the existing `test_json_entity_render_is_default_keep.py` suite.
4. No bench run needed — this doesn't touch the LLM prompt's `system`/instruction text, only the `content`/menu it's given; existing `make check` coverage suffices.

## Open Questions

- Exact array-entry cap (D3) — 10 is a starting guess; not load-bearing enough to block on, adjust at implementation time if a real fixture suggests otherwise.
