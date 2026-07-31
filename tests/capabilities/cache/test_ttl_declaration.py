"""Cache TTL comes from the producer's declaration, not a content-type guess.

`_ttl_for` read only the content type: `html` → 24h, everything else → 168h. A
handler serving an upstream API returns `application/json` or
`application/atom+xml`, so every handler-served discussion thread, issue list and
listing was cached for SEVEN DAYS — the freshest surfaces in the product held the
longest, and a `query` against a live thread could be answered from a week-old
body with nothing on the wire to say so.

The content type genuinely cannot decide this. `application/json` from the GitHub
issues API is a live discussion; `application/json` from a CDN may be a static
asset. Only the producer knows, so the producer declares and the heuristic
remains as the fallback for the generic HTTP tiers, which have nothing better.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from a2web.fetcher import _ttl_for
from a2web.settings import AppSettings

_HANDLERS = Path(__file__).resolve().parents[3] / "src" / "a2web" / "handlers"

# The handlers that serve an upstream API rather than a fetched HTML page.
_API_HANDLERS = ("arxiv", "github", "hn", "reddit", "discourse", "habr", "v2ex")


@pytest.mark.parametrize("content_type", ["application/json", "application/atom+xml"])
def test_a_declared_live_response_is_not_cached_for_a_week(content_type: str) -> None:
    """THE regression: pre-fix both of these returned 168 hours."""
    settings = AppSettings()
    ttl = _ttl_for(content_type, settings, volatility="live")

    assert ttl == settings.cache_ttl_live_m * 60
    assert ttl < 3600, f"a live API response cached for {ttl / 3600:.0f}h"


def test_a_static_asset_still_gets_the_long_ttl() -> None:
    """Anti-vacuity: the fix must not collapse every TTL to the short one."""
    settings = AppSettings()
    assert _ttl_for("image/png", settings, volatility="static") == settings.cache_ttl_static_h * 3600
    # And an undeclared non-html body still takes the heuristic's long TTL —
    # that is the correct default for the generic tiers, which know nothing.
    assert _ttl_for("image/png", settings) == settings.cache_ttl_static_h * 3600


def test_the_heuristic_survives_as_the_fallback() -> None:
    """Generic HTTP tiers declare nothing and must keep their old behaviour."""
    settings = AppSettings()
    assert _ttl_for("text/html", settings) == settings.cache_ttl_article_h * 3600
    assert _ttl_for(None, settings) == settings.cache_ttl_static_h * 3600


def test_ttl_for_reads_settings_directly_not_through_getattr() -> None:
    """A settings rename must be a type error, not a silent literal fallback.

    `_ttl_for` took `settings_obj: object` and read
    `getattr(settings_obj, "cache_ttl_article_h", 24)`. That duplicated every
    default and would have kept serving the literal through a rename — the
    setting would look wired while being dead.
    """
    source = (Path(__file__).resolve().parents[3] / "src" / "a2web" / "fetcher.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_ttl_for")

    getattrs = [n for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr"]
    assert not getattrs, "a defaulted getattr on settings hides a rename behind a literal"

    annotation = func.args.args[1].annotation
    assert isinstance(annotation, ast.Name) and annotation.id == "AppSettings", "settings must be typed, or a rename is not a type error"


@pytest.mark.parametrize("handler", _API_HANDLERS)
def test_every_api_handler_declares_its_volatility(handler: str) -> None:
    """Structural: a handler added without a declaration silently gets 7 days.

    Checked per successful return rather than per file, because a handler with
    several `TierResult` returns can easily have the declaration on one of them.
    """
    source = (_HANDLERS / f"{handler}.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    ok_returns = 0
    undeclared = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "TierResult"):
            continue
        kwargs = {k.arg: k.value for k in node.keywords if k.arg}
        verdict = kwargs.get("verdict")
        is_ok = isinstance(verdict, ast.Attribute) and verdict.attr == "ok"
        if not is_ok:
            continue  # a failure result is never cached
        ok_returns += 1
        if "volatility" not in kwargs:
            undeclared += 1

    assert ok_returns > 0, f"non-vacuous: no successful TierResult found in {handler}.py"
    assert undeclared == 0, (
        f"{handler}.py has {undeclared} successful TierResult return(s) with no `volatility` — "
        "an upstream API response with no declaration falls back to the content-type "
        "heuristic and is cached for 168 hours."
    )
