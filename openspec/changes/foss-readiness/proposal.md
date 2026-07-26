## Why

`yoselabs/a2web` and `yoselabs/shelf` are already public GitHub repos under
Apache-2.0 — but the a2web tree still reads like a personal workspace that
happens to be public, not a project a stranger can adopt:

- **No LICENSE file.** `pyproject.toml` declares `license = "Apache-2.0"` and
  `authors = [{name = "Denis Tomilin"}]`, but there is no license text at the
  repo root. The grant is *asserted in metadata, not delivered* — the first thing
  a FOSS consumer (or GitHub's own license detector) looks for is missing.
- **`CLAUDE.md` leaks the operator's environment.** It is a public, checked-in
  file, yet it carries absolute `/Users/iorlas/…` paths, pointers into a private
  knowledge base (`~/Documents/Knowledge/Projects/120-a2web/`, `handover.md`), a
  personal `~/.claude.json` MCP-config snippet, and a `## Deployment — remote-first
  (Shen)` section naming the operator's private gateway and `mcp.shen.iorlas.net`.
- **Personal identifiers scattered thin** through shipping docs — `Shen`,
  `iorlas`, the personal host, absolute home paths — in ADRs, `BACKLOG.md`,
  `CHANGELOG.md`, a spike note, and a couple of eval/benchmark fixtures.
- **No public front door.** `README.md` is not oriented to a newcomer: what
  a2web is, the two tools, how to install (git pin / GHCR image), a quickstart,
  `A2WEB_*` config, the contributor gate, a license section.

This is a presentation-and-hygiene gap, not a code problem. The only `src/`
occurrences of any personal term are the generic noun "homelab" in two comments
(`fetcher.py`, `events/types.py`) describing a legitimate deploy workaround — not
personal identifiers. Secrets are already env-only (`A2WEB_*`). What's missing is
the last mile between "my working copy" and "FOSS a project."

## What Changes

Scope fixed by owner decision (2026-07-27): **public repo + git/container
install** — the ~15 shelf git-deps stay as-is (both repos are public and
installable; **no PyPI track**); **genericize `CLAUDE.md` in place** (no
public/private split); **keep internal history** as honest engineering record
(strip identifiers only, do not relocate or delete).

- **Add a root `LICENSE`** (Apache-2.0 full text, copyright "Denis Tomilin"),
  matching the declared metadata so the grant is real and GitHub detects it.
- **De-personalize `CLAUDE.md` in place**: replace `/Users/iorlas/…` with generic
  placeholders (`<repo>`, `$HOME`), drop or genericize the private-K design-doc
  pointers, and rewrite the Deployment section from Shen specifics to a generic
  "build the `Dockerfile` image, publish to a registry, run it behind any HTTP MCP
  gateway" (no named gateway, no personal host, no personal MCP-config snippet).
- **Personal-identifier sweep** across shipping docs (`README.md`, `docs/adr/*`,
  `BACKLOG.md`, `CHANGELOG.md`, `docs/history/*`, spike notes) and eval/benchmark
  fixtures: remove `Shen`, `iorlas`, `mcp.shen.iorlas.net`, and absolute home
  paths — keeping the generic word "homelab" where it is genuinely generic (a
  self-hosted box), not a personal reference.
- **`README.md` as the public front door**: one-paragraph what-and-why, the two
  tools (`query` primary, `fetch_raw` fallback), install (git tag pin + `docker
  pull` the GHCR image), a 60-second quickstart (run + one `query` call), config
  via `A2WEB_*`, the `make check` contributor gate, and a license section/badge.
- **Confirm-only secrets audit**: assert the `A2WEB_*` env-only posture holds and
  no key material, token, or personal credential sits in the tree or git history
  reachable from `main` (spot-check, not a history rewrite).
- **Optional structural guard**: a `no-personal-strings` test that scans the
  shipping tree for a denylist (`iorlas`, `mcp.shen.iorlas.net`, `/Users/`) and
  fails on reappearance — **with an anti-vacuity floor** asserting it scanned ≥N
  files (per the repo's own "never add a guard that can pass on an empty walk"
  rule). Scoped to exclude `openspec/changes/archive/**` and regenerable artifacts.
- **Reconcile the deferred `optional-remote-only-deployment` change**, which this
  session already partly executed (local `uv tool uninstall a2web` done; the MCP
  config already points at the remote HTTP endpoint; the CLAUDE.md deploy-section
  reframe landed in `f824ba6`). Mark its completed tasks or fold the remainder in.

## Impact

- **Docs and metadata only** — no `src/` behavior change, no wire/envelope/tier
  change, no new dependency. `make check` (and its ≥85% coverage floor) is
  unaffected except by the optional new guard test.
- The **shelf git-deps are explicitly in-bounds as-is**: a public consumer
  installs a2web from a git tag or pulls the GHCR image, and the transitive shelf
  pins resolve from the public `yoselabs/shelf`. A future PyPI publish would need
  those packages on PyPI (direct-URL git deps are rejected by PyPI) — recorded as
  a **non-goal / BACKLOG item**, not undertaken here.
- Owner-directed history (`LESSONS_LEARNED.md`, `docs/history/A2KIT_FEEDBACK_*`)
  **stays**; only bare personal identifiers inside it are genericized. It is real
  engineering provenance and harmless once de-identified.
- **Non-goals**: PyPI publication; splitting `CLAUDE.md` public/private;
  relocating or deleting engineering history or benchmarks; changing the
  deployment *mechanism* (that is `optional-remote-only-deployment`); rewriting git
  history (the audit is confirm-only unless it finds a real secret).
