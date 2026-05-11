"""a2web in-tree microsofware — independent, replaceable, possibly publishable.

Every module under `packages/` follows the same contract:

1. **No imports from a2web domain code.** Modules here MUST NOT
   `from a2web.<x> import ...` where `<x>` is anything other than
   `a2web.packages.*` or `a2web.utils.*`. Boundary types are owned by the
   package itself, not borrowed from `a2web.models`.

2. **Replaceable.** Each package should be swappable with a third-party
   library without changing its callers' shape — only the import path.

3. **Self-contained.** Tests live next to or under each package and
   exercise only that package's public surface.

4. **Publish-ready.** Could be lifted to its own PyPI package tomorrow
   with no code changes inside `packages/<name>/`.

See `BACKLOG.md` "v0.5 simplification stages" for the staged migration.
"""
