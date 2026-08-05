"""The transport half of a retrieval result is written in ONE place.

`_install_rendered_fields` collapsed the CONTENT half in 2026-07 after a live
bug: `links` was added to one of four copies, so the fix meant to make
`other_pages` reachable did nothing on the common escalation path. Its docstring
then explicitly left the transport half alone — "the escalation paths set them
from their tier result" — which was true, and was the problem. Five paths set
those fields, in four orders, and `_install_gate_archive` omitted `status_code`
entirely.

`TierInstall` + `install()` is that half's single site now. This guard is what
keeps it single: a sixth path that assigns `fc.body` directly is a new copy, and
a new copy is how the first one happened.

Scoped to the fetcher tree — `fetcher.py` today, `fetcher/` after
`decompose-fetcher-into-files` — because that is where the pipeline writes
context. Response building reads these fields; it does not write them.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._walk import walked_files

_SRC = Path(__file__).resolve().parents[2] / "src" / "a2web"

#: The duplicated set. NOT every context field a tier touches — `etag`,
#: `last_modified`, the archive snapshot dates and a handler's measured counts
#: are genuinely per-source, and folding them into `TierInstall` would force it
#: to invent a clearing semantics (write `etag=None` from the browser path and a
#: conditional-request token acquired upstream disappears).
_TRANSPORT_FIELDS = frozenset({"body", "content_type", "final_url", "tier_used", "status_code", "pre_rendered_payload"})

#: The one writer, plus functions that may write because they ARE the seam.
_ALLOWED_WRITERS = {
    "install": "the chokepoint itself",
    # The 304 path reuses a CACHED body — no tier result exists to install, and
    # `status_code = 200` is a logical hit rather than anything a server said.
    # Routing it through `install` would additionally write `final_url`, which it
    # deliberately does not set today.
    #
    # This exemption was `_phase_tier_loop` until 2026-08-05, and the line above
    # said `decompose-fetcher-into-files` "gives it its own file
    # (`retrieval/conditional.py`)" — a prediction, written before the file
    # existed. §7 landed it, and this guard is what noticed: the move went red
    # here first, on the stale-exemption assertion below, before any behavioural
    # test had an opinion. An exemption naming a function that no longer writes
    # is how a guard comes to pre-authorise whatever takes that name next.
    "_reuse_cached_body": "the conditional-304 cache-reuse path — no tier result to install",
    # `RewriteUrl` retargets the fetch BEFORE any retrieval — `final_url` here is
    # "where we are about to look", not "where a tier landed". Found by this
    # guard on its first run, which is the argument for having it: a sixth writer
    # of the set was already there and nothing named it.
    "_dispatch_action": "URL rewrite retargets the fetch before retrieval",
    # Synthesizes a payload from a JSON body rather than installing a retrieval:
    # nothing was fetched at this point that is not already installed.
    "_phase_extract": "JSON-body synthesis writes `pre_rendered_payload` from content it just built",
}


def _fetcher_sources() -> list[Path]:
    single = _SRC / "fetcher.py"
    if single.exists():
        return [single]
    return walked_files(_SRC / "fetcher", minimum=5)


def _writes_in(node: ast.AST) -> set[str]:
    """Transport fields assigned on a context object inside `node`."""
    written: set[str] = set()
    for sub in ast.walk(node):
        targets: list[ast.expr] = []
        if isinstance(sub, ast.Assign):
            targets = list(sub.targets)
        elif isinstance(sub, ast.AugAssign | ast.AnnAssign):
            targets = [sub.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr in _TRANSPORT_FIELDS and isinstance(target.value, ast.Name):
                written.add(target.attr)
    return written


def _top_level_functions() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in _fetcher_sources():
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                found[node.name] = node
    return found


def test_only_the_chokepoint_writes_the_transport_half() -> None:
    functions = _top_level_functions()
    assert len(functions) > 40, f"only {len(functions)} fetcher functions found — the walk is not seeing the tree"

    violations: list[str] = []
    for name, node in functions.items():
        if name in _ALLOWED_WRITERS:
            continue
        written = _writes_in(node)
        if written:
            violations.append(f"{name} writes {sorted(written)}")

    assert not violations, (
        "the transport half is being written outside `install()`:\n  "
        + "\n  ".join(violations)
        + "\nBuild a `TierInstall` and call `install(fc, ...)`. This set was written by five "
        "functions in four different orders, one of them silently omitting `status_code`; "
        "a sixth copy is how that happened the first time."
    )


def test_the_chokepoint_writes_every_field_it_claims() -> None:
    """`TierInstall` naming a field it never assigns is worse than not having it.

    The caller would pass it, read the type as the contract, and the value would
    go nowhere — the shape of a wire field pruned at the serializer while every
    producer keeps filling it.
    """
    functions = _top_level_functions()
    assert "install" in functions, "`install` not found — the chokepoint moved or was renamed"
    assert _writes_in(functions["install"]) == _TRANSPORT_FIELDS, (
        "`install` no longer writes exactly the declared transport set: "
        f"writes {sorted(_writes_in(functions['install']))}, declared {sorted(_TRANSPORT_FIELDS)}"
    )


def test_every_exemption_still_writes_something() -> None:
    """A stale exemption silently pre-authorises the next function to take that name."""
    functions = _top_level_functions()
    stale = [
        f"{name}: {reason} — but it writes no transport field any more"
        for name, reason in _ALLOWED_WRITERS.items()
        if name != "install" and name in functions and not _writes_in(functions[name])
    ]
    missing = [name for name in _ALLOWED_WRITERS if name not in functions]
    assert not stale, "stale install exemptions:\n  " + "\n  ".join(stale)
    assert not missing, f"exempted functions that no longer exist: {missing}"
