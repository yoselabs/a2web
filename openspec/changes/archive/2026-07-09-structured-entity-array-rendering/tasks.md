## 1. Fix the list-of-dicts rendering gap

- [x] 1.1 In `src/a2web/domain.py::_single_entity_md`, extend the `isinstance(val, list)` branch: when list elements are dicts (not just scalars), flatten each dict element (reusing `_scalar_kv` per-entry, same rule as the existing single-nested-dict branch) into its own sub-line under the parent key, instead of silently producing an empty joined string.
- [x] 1.2 Add a defensive cap on the number of rendered array entries (design D3 — `_ENTITY_ARRAY_CAP = 10`).
- [x] 1.3 Confirmed the existing scalar-list path (`keywords: [...]`) is untouched via `test_scalar_list_fields_are_unaffected`.

## 2. Test coverage

- [x] 2.1 Added `tests/architecture/test_json_entity_array_rendering.py::test_array_of_contact_points_renders_each_entry_distinctly` — an `Organization` with an array `contactPoint` of 2 entries; asserts both entries' `telephone`/`email`/`contactType` values are present and distinguishable.
- [x] 2.2 Added `test_oversized_contact_point_array_is_capped` — 25-entry array renders exactly 10.
- [x] 2.3 Confirmed via `tests/architecture/test_json_entity_render_is_default_keep.py` (unchanged, still passing) that the fix doesn't regress the single-object case; also covered by the new `LocalBusiness`/`Organization`/`ContactPoint`-dispatch path already in `_ld_json_to_markdown`.

## 3. Verification

- [x] 3.1 Run `make check` (lint + ty + test, coverage ≥85%).
- [x] 3.2 No `make bench` run needed (design: this doesn't touch LLM prompt instructions, only the `content`/menu text fed to the extractor) — skipped, consistent with quota constraint.
- [ ] 3.3 Optional live probe (free, no LLM): fetch a real page known to carry an array `contactPoint` (or construct a local HTML fixture) via `fetch_raw`/the escalation ladder directly, and confirm the rendered `content_candidates` entry now contains all contact entries. Not done this session — optional, unit coverage already exercises the exact code path.
