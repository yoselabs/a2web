"""The capability specs may not describe the retired a2kit framework.

a2kit was retired on 2026-07-22 (`archive/.../sunset-a2kit-dependency`); a2web
now composes on `fastmcp.FastMCP` directly. The `reconcile-specs-post-sunset`
change rewrote every `openspec/specs/*/spec.md` requirement that still narrated
the dead framework into its FastMCP-direct mechanism. This guard is the floor
that keeps them from drifting back — a spec that resurrects `a2kit.App` /
`app.provide` / `WebRouter` / a DI container is describing software that does
not exist, which is worse than an out-of-date comment: the spec is the contract
a future change reads to know what to preserve.

**Why the denylist is CONCEPT terms, not just the literal `a2kit`.** The literal
`a2kit` alone is insufficient, and we know this concretely: `app-state` was the
single most a2kit-bound spec in the tree (`register_state`, `WebRouter.fetch`
DI-kwarg, `has_provider`) yet carried *zero* literal `a2kit` tokens — a
literal-only guard would wave it straight through. The dead framework leaves
its fingerprints in its vocabulary (`WebRouter`, `register_state`,
`bootstrap_state`, `add_router`, `has_provider`, `ToolContext`,
`canonical_name_override`, `app.provide`, `EventBus`), so those are what we ban.

**Why `structlog` is NOT on the denylist.** `structlog` is a *live ban term* —
`request-log` and `app-logging` requirements say "never a bypassing `structlog`
logger". Denylisting it here would fire on the very requirement that forbids it,
which is the "golden proves change, not correctness" hazard turned on the
guard's own denylist: the guard would punish a spec for correctly describing the
rule.

**The one allowlisted survivor** is the `app-logging` requirement whose subject
*is* the retirement — it factually names the removed `a2kit.ldd` API to reinforce
that the subsystem is gone. The allowlist is requirement-scoped (not file-scoped),
and `test_allowlisted_requirement_still_exists` fails if that requirement is ever
renamed or removed, so the exemption cannot outlive the thing it exempts (per the
CLAUDE.md "every accepted-delta table needs a test the delta is still real" rule).
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPECS_ROOT = _REPO_ROOT / "openspec" / "specs"

# Floor: there are ~42 capability specs today. Set well below that so ordinary
# deletions don't trip it, well above zero so a broken root does.
_MIN_SPEC_FILES = 30

# a2kit literals + the concept vocabulary that marks the dead framework even
# when the word "a2kit" is absent. Each is distinctive enough to match as a
# plain substring (CamelCase / snake_case / dotted) without word-boundary games.
_DENY_TERMS = (
    "a2kit",
    "app.provide",
    "EventBus",
    "ToolContext",
    "WebRouter",
    "register_state",
    "bootstrap_state",
    "add_router",
    "has_provider",
    "canonical_name_override",
)

# Requirement-scoped exemption: the one requirement whose *subject* is the
# retirement, so it legitimately names the removed `a2kit.ldd` API.
_ALLOWED = frozenset(
    {
        ("app-logging", 'No retired "LDD" terminology in live code'),
    }
)

_REQ_HEADER = re.compile(r"^### Requirement:\s*(?P<title>.+?)\s*$", re.MULTILINE)


def _spec_files() -> list[Path]:
    assert _SPECS_ROOT.is_dir(), (
        f"specs root does not exist: {_SPECS_ROOT}\n"
        "The guard cannot walk a tree that isn't there — fix the path, do not "
        "let the test pass by finding nothing."
    )
    paths = sorted(_SPECS_ROOT.rglob("spec.md"))
    assert len(paths) >= _MIN_SPEC_FILES, (
        f"spec walk over {_SPECS_ROOT} found {len(paths)} file(s), expected at "
        f"least {_MIN_SPEC_FILES}. The root moved or the tree shrank below the "
        "floor — an empty walk makes this guard pass vacuously."
    )
    return paths


def _requirements(text: str) -> list[tuple[str, str]]:
    """Split a spec into (requirement_title, body) chunks.

    Prose before the first `### Requirement:` (Purpose, the `## Requirements`
    header) is returned under the sentinel title `""` so it is still scanned —
    a2kit residue in a Purpose block is exactly as wrong as in a requirement.
    """
    matches = list(_REQ_HEADER.finditer(text))
    chunks: list[tuple[str, str]] = []
    if not matches:
        return [("", text)]
    if matches[0].start() > 0:
        chunks.append(("", text[: matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append((m.group("title"), text[m.start() : end]))
    return chunks


def test_no_a2kit_vocabulary_in_specs() -> None:
    violations: list[str] = []
    for path in _spec_files():
        capability = path.parent.name
        for title, body in _requirements(path.read_text()):
            if (capability, title) in _ALLOWED:
                continue
            hits = sorted({term for term in _DENY_TERMS if term in body})
            if hits:
                where = f"{capability} :: {title or '<preamble>'}"
                violations.append(f"{where}: {', '.join(hits)}")

    assert not violations, (
        "Retired-a2kit vocabulary reappeared in capability specs. These specs "
        "describe software that no longer exists — rewrite to the FastMCP-direct "
        "mechanism (see the archived `sunset-a2kit-dependency` change):\n  "
        + "\n  ".join(violations)
    )


def test_allowlisted_requirement_still_exists() -> None:
    """The exemption must name a real requirement, or it rots into a blind spot."""
    titles_by_capability: dict[str, set[str]] = {}
    for path in _spec_files():
        titles_by_capability.setdefault(path.parent.name, set()).update(
            title for title, _ in _requirements(path.read_text()) if title
        )
    for capability, title in _ALLOWED:
        assert title in titles_by_capability.get(capability, set()), (
            f"allowlist entry ({capability!r}, {title!r}) names a requirement "
            "that no longer exists — remove the stale exemption so the guard "
            "stops carrying a dead allowance."
        )
