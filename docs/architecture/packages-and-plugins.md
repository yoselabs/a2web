# Packages and plugin manifests

Covers `src/a2web/packages/` (in-tree microsofware) and the shelf
`plugin_surface` + `src/a2web/_manifests/` plugin manifest framework.

## `src/a2web/packages/`

Modules under here MUST NOT import from `a2web.<domain>`. Boundary types are
owned by the package; domain-coupled wiring lives in `domain.py` /
`llm_resource.py` / `cache.py`. Current packages: `block_detector`,
`proxy_routing`, `escalation`, `structured_render` (structured-data →
markdown, lifted out of `domain.py` 2026-08-01; also owns `listing_rows`,
which returns the SAME rows behind the markdown so the wire index and the
body cannot describe different item sets, and `declared_subject_entity`,
which returns the page's own `(type, fields)` declaration — `_ENTITY_TYPES`
is GONE, an eight-name allowlist that rendered every other declared type as
nothing; `declaration_rate_v6` measured it dropping 4 of the 7 corpus pages
declaring anything subject-level, including a 74-field `ProductGroup`), and
`llm_extract/` (folder — multi-author surface with `extractor`, `judge`,
`prompts`, `errors`, `router_payload`, `wobble`).

`llm_extract/providers/`<!-- gone --> is GONE — promoted to the shelf as
`anyllm` and adopted back; the concrete adapters now come from
`anyllm[anthropic,openai,claude-code-sdk]` and a2web keeps only the
Extractor/Judge/prompts above them. `browser_backends/`<!-- gone --> is GONE
— promoted to the shelf as `any_browser` (2026-07-26); a2web keeps the
product half (`select_backend*` in `state.py`, manifest gating in
`_manifests/browser_backends/`, the fast/robust rung split, the
`RenderOutcome→Verdict/OperatorHint` mapping in `tiers/browser.py`). The
engine override env is now `ANY_BROWSER_EXECUTABLE_PATH`. Likewise
`llm_cost_guard` → shelf `anyllm.cost`, the extraction `cache` → shelf
`llm-cache`, and `content_extract`/`cookie_store`/`html_fragment`/`record_extract`
were promoted/retired earlier — see
`openspec/changes/archive/2026-07-27-shelf-sweep-promotions/`.

The boundary is enforced by `tach.toml` (`uv run tach check`, in `make arch`);
`tests/architecture/test_tach_covers_every_package.py` asserts its module
list and the real package tree stay the same set, because an UNLISTED
package silently gets no contract at all.

**LLM contract parsing.** Every site that parses LLM JSON funnels through
`packages/llm_extract/wobble.parse_with_policy` (object envelopes) or
`parse_list_with_policy` (JSON-array envelopes). The funnel owns
`json.loads` — enforced by `tests/architecture/test_json_loads_funnel.py`
over `packages/llm_extract/` AND `llm_eval/`. It returns an opaque `Wobbled`
NewType — downstream code typed as `Wobbled` cannot accept a hand-rolled
payload fabricated outside. Upstream-API `json.loads` elsewhere in `src/` is
deliberately out of scope: the funnel exists for model wobble, not for a
broken API response, which the tier verdict machinery already owns.
Per-field `WobblePolicy` (`STRICT` / `DERIVE` / `DEFAULT` / `SKIP`) tables
live centrally in `wobble/_policies.py` for static cases; tables that bind a
DERIVE callable (e.g. `_JUDGE_POLICY` referencing `_derive_reached`) stay
adjacent to the callable in their consumer module. Recovered wobbles fire
the single structured log key `llm_wobble`. Sites today: `judge.py`,
`bench_judge.py` (clarity + next_links), `extractor.py` (router-shape +
next_links), `fetcher_response.py::_project_routing` (pydantic-validate, not
JSON parse — emits `llm_wobble` on closed-enum violations).

## `_manifests/` plugin framework

Every extension surface converges on `PluginManifest[T]` + `Unavailable` +
`load_surface(...)` / `load_surface_sorted(...)` (Pattern 2 of ADR-0001).
Each plugin lives as a no-side-effects module under
`_manifests/<surface>/<name>.py` declaring `MANIFEST = PluginManifest(...)`.
Surfaces today: `eval_systems/` (webfetch_baseline, a2web_detail,
a2web_extract), `sinks/` (otel), `handlers/` (9 site handlers), `tiers/` (8
tiers — `archive`, `browser`, `browser_robust`, `firecrawl`, `jina`, `raw`,
`site_handler`, `zyte`), `browser_backends/` (patchright, zendriver,
camoufox-gated).

`llm_providers/`<!-- gone --> is GONE — the adapters were promoted to the
shelf as `anyllm` and `select_provider` calls `resolve_provider` directly,
so there is no manifest surface left; the directory holds no tracked files.

Adding a plugin = drop one file; `load_surface(...)` discovers it at boot,
drops `Unavailable` returns silently. Module-level side effects banned by
`tests/architecture/test_plugin_modules_only_declare_manifest.py`.
Package-side classes stay settings-free (microsofware-pure); domain wiring
lives in the manifest.

## Rules

- No `dict[str, Any]` on slotted dataclasses (allowlist gated) — `tests/architecture/test_no_dict_str_any_on_dataclasses.py`.
- Boundary dataclasses under `packages/` are frozen — `tests/architecture/test_boundary_dataclasses_are_frozen.py`. Does NOT pin `packages/*/__init__.py` `__all__` — that stays deliberately unguarded.
- Plugin manifest files in `_manifests/` have no module-level side effects — `tests/architecture/test_plugin_modules_only_declare_manifest.py`.
- Before promoting a new module to `packages/`: boundary types need design, and the seam may need conversion logic — ask first.
