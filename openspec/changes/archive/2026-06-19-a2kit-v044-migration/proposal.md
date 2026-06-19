# a2kit v0.43 → v0.44 migration

## Why

a2web is pinned to `a2kit==v0.43.0`. a2kit shipped **v0.44.0** (2026-06-17,
`add-internal-spoke`, ADR 0029). Unlike the v0.43 rollup — a 59-commit surface
migration (ADR-0028 App subclassing + ADR-0027 LDD-on-logging) — **v0.44 touches
nothing a2web consumes.** This change is a clean pin bump, recorded as a change
only because the repo tracks every a2kit migration and because the verification
(`make check` green on the new pin) is the real deliverable.

What v0.44 changed, and why each is a no-op for a2web:

| v0.44 change | Class | a2web exposure |
|---|---|---|
| Internal spoke — `serve --internal-uds`, `a2kit.TokenAuth`, `a2kit.spoke.client` (ADR 0029) | Added | **None.** Additive; a2web runs no sandboxed first-party jobs against a single-writer core. Not adopted (see design.md D-Spoke). |
| `serve --transport=http` now multiplexes MCP `/mcp` + REST `/api` | **BREAKING** | **None.** a2web serves over **stdio** (`a2kit.run(app)`, installed `args: ["serve"]`). stdio is explicitly unchanged. a2web never sets an http transport. |
| Removed `a2kit.packages.mcp.cli` / `build_serve_command` | **BREAKING** | **None.** Not imported anywhere in `src/`. |
| Removed `auth.build_api_key_middleware`; `AuthSpec` now requires `build_middleware()`; `AuthTarget` opened to `str` | **BREAKING** | **None.** a2web imports no `a2kit` auth surface (the `src/` "auth" grep hits are all domain prose). |
| `app.py` / `routers.py` / `tool.py` / `di/container.py` edits | Internal | **Docstring-only**, plus the di legacy methods (`register`/`resolve`/…) now raise `AttributeError` instead of `TypeError` — a2web already uses `provide`/`get`, never the legacy names. |

**LDD specifically:** `src/a2kit/log.py` is **byte-identical** between v0.43.0 and
v0.44.0 (`git diff --quiet` confirms). The only two LDD-token hits in the whole
v0.44 source diff are docstring deletions (`_LDD_STATE`, `LddState` → `log
state`). a2web's entire events layer — `await a2kit.log.info(...)` emit sites,
`OtelHandler(logging.Handler)`, the bench `LiveSink`, `app.log.add_handler(...)`
— needs **zero** touches. The LDD churn already happened in the v0.43 migration.

## What changes

### Front A — Pin bump (the whole functional change)

`pyproject.toml`:
```diff
-    "a2kit>=0.43,<1",
+    "a2kit>=0.44,<1",
 ...
-a2kit = { git = "https://github.com/yoselabs/a2kit.git", tag = "v0.43.0" }
+a2kit = { git = "https://github.com/yoselabs/a2kit.git", tag = "v0.44.0" }
```
Then `uv lock` (refresh `uv.lock` to the v0.44.0 commit) + `uv sync --all-extras`.

### Front B — Verify (the real deliverable)

`make check` (lint + ty + test, coverage ≥85%) must be green with no source
edits. Static analysis says it will: no consumed surface moved. If it goes red,
the failure surface is the finding and this proposal's no-op premise is wrong —
stop and re-scope.

### Front C — Docs

`CLAUDE.md` prose says "v0.43" / "a2kit v0.43 mediated" throughout. Update the
version references to v0.44. This is a cosmetic version-string sweep, **not** a
surface rewrite (the v0.43 surface description is still accurate — nothing a2web
uses changed). Add a `CHANGELOG.md` entry.

## Non-goals

- **No internal-spoke adoption.** a2web has no job-runner / single-writer core;
  the spoke is not a fit and the Constitution's magic-budget rule argues against
  pulling in unused surface. (design.md D-Spoke.)
- **No source edits** beyond the pin. If any are needed, the no-op premise is
  falsified and this becomes a different change.
- **No behavior change** to fetch / extraction / tiers / handlers / envelope.
- **No bench run by default** (design.md D-Bench) and **no feedback round by
  default** (design.md D-Feedback) — v0.44 gave a2web nothing to react to.

## Impact

- Affected files: `pyproject.toml`, `uv.lock`, `CLAUDE.md`, `CHANGELOG.md`.
  **No `src/` changes expected.**
- **No MCP contract change** — stdio transport and bare tool names
  (`ask`/`fetch_raw`/`refresh`) are untouched. Still requires
  `make install-global` + session restart so the installed binary picks up the
  new a2kit.
- **One spec delta** (`specs/app-composition/`): an ADDED, version-agnostic
  invariant — the MCP wire contract (stdio transport + bare tool names) SHALL
  survive a2kit substrate upgrades. This codifies, as a permanent gate on every
  future bump, the contract the v0.43 change pinned. No behavior change to fetch
  / extraction; it makes contract-preservation explicit rather than incidental.
