"""Transport discipline: nothing under `tiers/` or `handlers/` hand-rolls a client.

`handlers/README.md` has carried this rule since the linux.do incident — a
handler forked its own `httpx.AsyncClient`, its unit tests monkeypatched that
fork's `.get`, and production silently served a Cloudflare anti-AI banner while
the suite stayed green. The rule was prose only, and `tiers/` was never covered
by it, which is exactly where it was being violated: `jina.py` hand-rolled a
client for the tier's whole life, and the cost was not hypothetical — it kept
jina outside `patch_fetch_bytes`, so the eval replay corpus made LIVE requests
to `r.jina.ai` on every CI run while advertising "replay refuses to hit the
network".

So: the rule is a test now, over both directories.

The two paid tiers are a DECIDED exception, not an oversight, and the reason is
recorded in `docs/architecture/transport-discipline.md`. Each must name itself
here with its reason, so an exception is a sentence someone wrote rather than a
silence someone did not notice.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._walk import walked_files

_SRC = Path(__file__).resolve().parents[2] / "src" / "a2web"
_SCOPED = ("tiers", "handlers")

#: module stem -> why it may hold its own client.
#:
#: Both POST to an authenticated vendor JSON API; `fetch_bytes` is GET-only. The
#: decision NOT to widen it turns on what routing through it would actually buy,
#: which on inspection is nothing or less than nothing: TLS impersonation is
#: pointless against an API you authenticate to; both tiers explicitly discard
#: `proxy_url` because the vendor owns egress; conditional GET does not apply to
#: a POST; and the generic `FetchVerdict` has NO member for `paid_auth_error`,
#: so the shared closed enum would actively LOSE the 401/402/403 distinction
#: that ADR-0009 names by name. The one real gain was the circuit breaker, and
#: that is taken directly via `_paid.paid_api_breaker`.
_EXEMPT: dict[str, str] = {
    "zyte": "POSTs to api.zyte.com; needs paid_auth_error, which FetchVerdict lacks",
    "firecrawl": "POSTs to api.firecrawl.dev; needs paid_auth_error, which FetchVerdict lacks",
}

_BANNED_MODULES = {"httpx", "curl_cffi"}


def _imported_transport_modules(tree: ast.AST) -> set[str]:
    """Top-level transport packages this module imports, by any spelling."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BANNED_MODULES:
                    found.add(root)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _BANNED_MODULES:
                found.add(root)
    return found


def _candidates() -> list[Path]:
    files: list[Path] = []
    for package in _SCOPED:
        files.extend(walked_files(_SRC / package, minimum=5))
    return files


def test_no_tier_or_handler_hand_rolls_a_transport() -> None:
    violations: list[str] = []
    for path in _candidates():
        imported = _imported_transport_modules(ast.parse(path.read_text(encoding="utf-8")))
        if not imported:
            continue
        if path.stem in _EXEMPT:
            continue
        rel = path.relative_to(_SRC)
        violations.append(f"{rel} imports {sorted(imported)}")

    assert not violations, (
        "hand-rolled transport under tiers/ or handlers/:\n  "
        + "\n  ".join(violations)
        + "\nRoute it through `http_fetch.fetch_bytes`, or add it to `_EXEMPT` with a reason. "
        "The seam matters beyond the tier: `patch_fetch_bytes` is what makes the eval replay "
        "corpus offline, and a client it cannot see turns a replay into a live fetch."
    )


def test_every_exemption_is_still_a_real_exception() -> None:
    """An exemption that stopped describing a real import reads as a decision.

    If a paid tier were later routed through the primitive and the entry stayed,
    the allowlist would silently pre-authorise the next module to take that name.
    """
    stale: list[str] = []
    by_stem = {p.stem: p for p in _candidates()}
    for stem in _EXEMPT:
        path = by_stem.get(stem)
        if path is None:
            stale.append(f"{stem}: no such module under {_SCOPED}")
            continue
        if not _imported_transport_modules(ast.parse(path.read_text(encoding="utf-8"))):
            stale.append(f"{stem}: no longer imports a transport module — drop the exemption")
    assert not stale, "stale transport exemptions:\n  " + "\n  ".join(stale)


def test_the_exempt_tiers_still_take_the_breaker_they_opted_into() -> None:
    """The exemption was granted on the strength of ONE compensating control.

    `_EXEMPT`'s reason says the breaker "is taken directly via
    `_paid.paid_api_breaker`". If that call disappeared, the exemption's
    justification would evaporate while the exemption itself stayed — the exact
    shape of an allowlist entry that reads as coverage while providing none.
    """
    for stem in _EXEMPT:
        source = (_SRC / "tiers" / f"{stem}.py").read_text(encoding="utf-8")
        assert "paid_api_breaker" in source, f"{stem}.py is exempt from fetch_bytes but no longer takes a breaker"
