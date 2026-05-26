# ADR-0001 — Structural prevention over vigilance

**Status:** Accepted
**Date:** 2026-05-26
**Supersedes:** —
**Superseded by:** —

## Context

The 2026-05-26 explore session (transcript in conversation memory; spike artefacts at `scripts/spike_typed_funnel_wobble.py` and the deleted `tach.toml` / `.importlinter` probes) audited a2web at v0.23 for coupling and discipline-drift smells. Four parallel axis-specialised agents cross-confirmed three problem classes:

1. **Discipline bypass.** Rules declared in `CLAUDE.md` ("Four canonical sites today" go through `wobble.apply_policy`) are silently violated. The biggest LLM-JSON parse site in the codebase — `extractor._split_answer_and_routing` (78 LoC) — hand-rolls `json.loads` + `isinstance` checks and never emits the `llm_wobble` event the discipline mandates.

2. **Plugin-surface drift.** Six "extension point" surfaces (tiers, handlers, LLM providers, LDD sinks, wobble policies, eval systems) drifted into three different shapes for *registration*, *configuration delivery*, and *unavailability handling*. Each new surface re-discovers the pattern. Concrete cost: `llm_resource.py:78` reaches past `providers/__init__.py` to import concrete provider classes directly; `cookie_jar.py:37` reaches past `cookie_store/__init__.py` likewise.

3. **Doc rot.** `CLAUDE.md` claims "Four canonical sites today" — in reality two go through the discipline, two hand-roll. Rules expressed as English prose rot the moment the next contributor's edits diverge.

Research lobes covered Python layer-enforcement tooling (`import-linter`, `Tach`, `pytest-archon`), cross-language analogues (Shopify Packwerk's per-package manifests + `package_todo.yml` ratchet, Stripe Sorbet's per-file strictness opt-in), funnel patterns (Alexis King's "Parse, don't validate"; Glyph Lefkowitz's "Opaque Types in Python", May 2026), and plugin uniformity (pluggy, Dagster Components GA Oct 2025, Litestar DI, Datasette plugin manifests).

Two tooling spikes ran apples-to-apples on 2026-05-26:

- **Tach** (Rust binary, `[[interfaces]]` model) caught 38 violations in ~30s, including the precise `llm_resource.py:78` smell *plus* one we missed in the audit (`block_detector → packages.escalation` cross-package coupling). Auto-grandfathering via `tach sync` is a one-line bootstrap.
- **import-linter** (pure Python, mature since 2019) caught the cross-package smell with a minimal contract but cannot naturally express "this module's `__init__.py` is the only public surface, everything else is private" — our dominant rule shape. The `forbidden` contract requires enumerating every private submodule per package.

## Decision

Adopt a **three-pattern stack** that targets each class structurally:

```
                  ┌────────────────────────────┐
                  │  Architectural fitness     │
                  │  functions (CI)            │
                  │  — Tach for boundaries     │
                  │  — pytest-archon for       │
                  │    AST / call-site rules   │
                  └────┬───────────────────┬───┘
                       │ enforces          │ enforces
                       ▼                   ▼
       ┌─────────────────────────┐  ┌──────────────────────┐
       │  Typed funnels          │  │  Plugin manifests    │
       │  — Wobbled NewType      │  │  — PluginManifest[T] │
       │  — private _internal    │  │  — Unavailable result│
       │  — Recipe A             │  │  — capability tokens │
       │     (Glyph 2026)        │  │     before registry  │
       └─────────────────────────┘  └──────────────────────┘
              kills Class 1               kills Class 2
              (bypass)                    (drift)

   Defense in depth: tests catch what types miss;
                     types catch what review misses.
```

**Pattern 1 — Typed funnel.** Each "discipline" is exported as the only legitimate constructor of an opaque `NewType`. Downstream code is typed to accept the `NewType`. Bypass becomes a type error at edit time under `ty` / `pyright`. The first instance lands on `wobble.parse_with_policy` per change `wobble-typed-funnel`.

**Pattern 2 — Plugin manifests.** Each extension-point surface declares one file per plugin exporting a `MANIFEST = PluginManifest(...)` constant. App boot reflects on manifests, calls each factory with sliced `AppSettings`, and drops anything returning `Unavailable` *before it reaches the registry*. Collapses registration, configuration delivery, and unavailability into one shape. Migration sequenced by drift severity per change `unify-plugin-manifests` (providers first).

**Pattern 3 — Architectural fitness functions.** Two complementary tools:
- **Tach** for declarative package-boundary + public-interface enforcement (`[[interfaces]]` per package; everything not exposed is private).
- **pytest-archon** for AST-level / call-site rules (e.g. "only `wobble/` may call `json.loads` inside `packages/llm_extract/`"; "no `dict[str, Any]` field on internal dataclasses"; "tools must return pydantic, not `str`").

Existing hand-rolled `tests/test_packages_independence.py` is the template; it becomes one of several archon rules. The Packwerk-style ratchet (snapshot today's violations, fail CI on new violations) is provided by `tach sync` for boundary rules and by `pytest-archon`'s standard pytest skip/xfail mechanisms for AST rules.

## Consequences

**Positive**

- Each declared invariant is mechanically enforced. CLAUDE.md "Never" lines shrink to a pointer at the fitness-function file.
- New parse sites and new plugin surfaces fall into the established shape automatically; bypass requires the contributor to disable a test, which is visible in review.
- The patterns compose with `a2kit` — if the discipline ever needs to migrate into the framework, the in-tree `PluginManifest` + `Wobbled` shapes absorb cleanly.

**Negative / accepted cost**

- One new build-time tool (Tach, Rust binary, mitigated by `uvx`). One new dev dependency (pytest-archon).
- One-time grandfathering of ~30 existing layer violations via `tach.toml` (Pattern 3 bootstrap).
- A two-to-three-week migration window for the plugin manifest pattern (Pattern 2), staged one surface at a time.
- LARP boundary explicitly avoided: phantom-types / beartype / `Result[T, E]` monads are **not adopted** for a2web. They would be reconsidered only if `wobble` migrates into `a2kit` as a public library primitive (library contracts can't depend on consumer CI).

**Rejected alternatives**

- **`import-linter` over Tach.** Caught the cross-package smell but cannot express our dominant "private-by-default" rule without enumerating every private submodule per package. Acceptable second choice if Rust-binary dep is intolerable.
- **pytest-archon only (no Tach).** Workable but every layering rule becomes hand-rolled AST. Saves one tool at the cost of per-rule effort. Pattern 3 explicitly chooses *defense in depth*: Tach for boundaries, archon for AST.
- **Pluggy or `importlib.metadata.entry_points()` for plugin manifests.** Both target ecosystem-scale third-party plugin discovery. a2web's surfaces are all first-party in-tree; the maturity gain doesn't outweigh the conceptual overhead.
- **Phantom-types / beartype for runtime funnel enforcement.** Runtime tax not justified at our O(per-fetch) call rate when CI tests + ty already gate at PR time. Reconsider if the funnel migrates into `a2kit`.
- **Returns / `Result[T, E]` monads.** Solves a different problem (explicit error propagation), not bypass discipline. Existing `WobbleSkip` + closed-enum verdicts already cover explicit-error needs.

## Implementation

Three openspec changes execute this ADR:

1. **`wobble-typed-funnel`** — Pattern 1 proof. Lands `parse_with_policy` + `Wobbled` NewType, migrates the four canonical sites, adds the `json.loads`-ban archon rule. Smallest blast radius.
2. **`arch-fitness-functions-bootstrap`** — Pattern 3 bootstrap. Installs Tach + pytest-archon, runs `tach sync` to grandfather existing violations, adds the initial archon rules.
3. **`unify-plugin-manifests`** — Pattern 2 rollout. Defines `PluginManifest` + `Unavailable`, migrates surfaces one per session (providers → eval systems → sinks → handlers → tiers), each migration retires one bespoke `_ensure()` / `no_match=True` / `unavailable_lazy(...)` site.

Order is load-bearing: Pattern 1 lands the typed-funnel idiom; Pattern 3 provides the fitness-function harness that all subsequent rules depend on; Pattern 2 is the longest migration and benefits from both prior patterns being in place.

## References

- Alexis King, "Parse, don't validate" (2019) — <https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/>
- Glyph Lefkowitz, "Opaque Types in Python" (2026-05) — <https://blog.glyph.im/2026/05/opaque-types-in-python.html>
- Shopify, "Enforcing Modularity with Packwerk" — <https://shopify.engineering/enforcing-modularity-rails-apps-packwerk>
- Neal Ford et al., *Building Evolutionary Architectures* (2nd ed., 2023)
- Dagster Components GA (2025-10) — <https://docs.dagster.io/>
- import-linter — <https://import-linter.readthedocs.io/>
- Tach — <https://github.com/tach-org/tach>
- pytest-archon — <https://github.com/jwbargsten/pytest-archon>
- a2web explore-session findings (this conversation, 2026-05-26)
