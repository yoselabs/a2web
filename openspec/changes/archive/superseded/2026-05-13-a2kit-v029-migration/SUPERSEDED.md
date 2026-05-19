# Superseded

This change targeted a2kit v0.28.0 → v0.29.1 and was drafted on 2026-05-13.

Within hours of drafting, a2kit shipped three more breaking releases (v0.30.0, v0.31.0, v0.32.0) on the same day. Key impacts:

- **v0.30.0 reversed the docstring `Args:` auto-pull** that this change's Step 4 targeted. The 3 guard rails (pydocstyle convention, completeness test, CLAUDE.md note) became moot.
- **v0.31.0** removed `a2kit.Param`, removed `@app.on_startup/@on_shutdown` (replaced by `lifespan=`), required `slug`/`tools` ClassVars on `Router`, and reshaped `A2KitMeta`.
- **v0.32.0** trimmed the top-level `a2kit.*` namespace 22 → 10 names, requiring an import audit.

The migration plan was rewritten as `openspec/changes/2026-05-13-a2kit-v032-migration/` targeting v0.32.0 directly. The Step 1 (ambient ctx), Step 2 (async-singleton resources), and Step 3 (TestClient.override) work survived unchanged into the new proposal. Step 4 (docstring pull) was dropped; new steps were added for Param→pydantic.Field, Router contract, lifespan migration, and import-path audit.

Kept here for archaeology — not for execution.
