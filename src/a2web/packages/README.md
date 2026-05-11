# `a2web.packages` — microsofware contract

Modules in `packages/` are **infrastructure**, not domain code. Each one:

- Imports nothing from `a2web.<domain>` — no `a2web.models`, `a2web.state`,
  `a2web.settings`, `a2web.fetcher`, etc.
- Owns its own boundary types (configs, return shapes, errors).
- Could be lifted to its own PyPI package without changing its internals.
- Is replaceable: callers depend on the import path, not the implementation.

If a candidate module needs anything from `a2web.<domain>`, it stays in the
domain root. Promote later when the dependency can be inverted via a
boundary type.

## Inventory

| Module | What it is | Status |
|---|---|---|
| `browser_pool.py` | Camoufox per-host LRU pool with idle eviction | shipped Stage 2a |
| `content_extract/` | Trafilatura wrapper + OG/JSON-LD metadata | deferred Stage 2b (needs ExtractedHeading/Link boundary types) |
| `http_cache/` | sqlite HTTP revalidation cache | deferred (needs CacheConfig boundary) |
| `block_detector/` | HTML body → closed-enum reason | deferred (returns Verdict; needs BlockReason boundary) |
| `proxy_routing/` | Route-by-(host, tier) + CB-backed pool | deferred (needs RouteTable boundary) |
| `llm_extract/` | Provider-agnostic Extractor + Judge | deferred (decide if shape is stable enough) |

## Rules enforced by lint

`ruff.lint.per-file-ignores` / `flake8-tidy-imports.banned-api` and a
`tests/test_packages_independence.py` invariant test together gate the
"no a2web-domain imports" contract.

## Discipline

When touching a package:

1. Keep the public surface in `__init__.py` (or the single-file module's
   own `__all__`). Don't leak internals.
2. Document the boundary types — what shape callers expect.
3. If you find yourself wanting to import something from `a2web.<domain>`,
   stop and ask whether the type should move into the package or whether
   the package belongs in the domain.

## Why "microsofware"?

Smaller than a microservice. Bigger than a function. Possibly publishable.
Could be a library or could just be cleanly factored code in our tree.
The label distinguishes infrastructure-flavored code from
domain-flavored code at a glance.
