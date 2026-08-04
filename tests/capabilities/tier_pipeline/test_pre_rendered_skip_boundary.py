"""What the `pre_rendered` skip may and may not skip.

`_phase_extract` returns early when a tier installed pre-rendered markdown. That
skip exists for ONE reason: a tier that already produced markdown must not pay
trafilatura a second time. It was written around `extract_markdown`, and it also
skipped everything textually below it — including two parsers that have nothing
to do with trafilatura:

    _run_extraction_escalation   json_in_html + record_mine
    _phase_listing_completeness  the ADR-0009 sufficiency check

Four consumers lost their input on every browser / archive / paid / handler
fetch: the extractor's candidate menu collapsed to one item (ADR-0005), the link
digest's gate became unsatisfiable so `other_pages` could never be emitted,
`listing_partial` could never fire on a browser-served listing — the population
most likely to BE a truncated infinite-scroll listing, since that is what forced
the browser — and the option shelf stayed empty.

This is the second half of a fix. `restore-links-on-pre-rendered-tiers` closed
the `fc.links` half at this same early return and was measured NOT to make
`other_pages` reachable (`eval/runs/post-link-fix`, 2026-07-28: both target
cells still `unscored`). Hence `test_the_links_are_already_there` below — it
pins the previous fix as the PREMISE of these, so a future failure here is
never misread as that defect returning.

Both halves of the boundary are asserted in one module on purpose. Splitting
them invites a future edit to satisfy the ladder assertions by deleting the
branch, which would silently reintroduce the double trafilatura pass the skip
exists to prevent. `test_the_trafilatura_pass_is_still_skipped` starts green and
must STAY green.

Offline: a fixture of known shape driven through the real `_phase_extract`.
No network, no LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from content_extract import extract_markdown

from a2web.fetcher import FetchContext, FetchInputs, FetchResources, _build_link_digest, _phase_extract
from a2web.tiers import Rendered

_BASE_URL = "https://example.org/list/recent"

#: Records the fixture genuinely carries. The non-vacuity floor for every count
#: assertion below — "not None" passes on a single stray record, which is
#: exactly the shape of a guard that reads as coverage while providing none.
_RECORD_COUNT = 12

#: The advertised total, so listing-completeness has a numeric oracle to find.
#: Deliberately far above `_RECORD_COUNT` — a partial listing, unambiguously.
_ADVERTISED_TOTAL = 240


def _card(i: int) -> str:
    return (
        '<article class="prd">'
        f'<h2 class="title"><a href="/abs/10{i:02d}">Paper number {i} on scaling and transformers</a></h2>'
        f'<div class="au"><span class="name">Author {i}</span></div>'
        f'<div class="ab">A summary sentence for entry {i} that is long enough to matter.</div>'
        "</article>"
    )


_LISTING_HTML = (
    "<html><head><title>Recent submissions</title></head><body>"
    "<h1>Recent submissions</h1>"
    '<div class="grid">' + "".join(_card(i) for i in range(1, _RECORD_COUNT + 1)) + "</div>"
    f"<p>Showing {_RECORD_COUNT} of {_ADVERTISED_TOTAL} results</p>"
    '<a href="/list?skip=12">Next page</a>'
    "</body></html>"
)


async def _pre_rendered_fetch() -> FetchContext:
    """A fetch as a pre-rendering tier leaves it, driven through the real phase.

    The `Rendered` payload is built from the canonical extractor exactly as
    `tiers/browser.py` builds it, rather than hand-assembled — a hand-built
    payload would be a double of the thing under test and could not witness a
    change to it.
    """
    extracted = await extract_markdown(_LISTING_HTML, _BASE_URL)
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=False,
        ),
        resources=FetchResources(
            sqlite=None,
        ),
        url=_BASE_URL,
        final_url=_BASE_URL,
        body=_LISTING_HTML.encode("utf-8"),
        content_type="text/html",
        pre_rendered_payload=Rendered(
            content_md=extracted.content_md,
            title=extracted.title,
            byline=extracted.byline,
            headings=list(extracted.headings),
            links=list(extracted.links),
        ),
    )
    await _phase_extract(fc)
    return fc


def test_the_fixture_is_record_shaped() -> None:
    """Non-vacuity floor: the fixture must genuinely carry what we count.

    Without this, a fixture emptied by an escaping slip reads as a passing
    guard for every assertion that depends on its shape.
    """
    from record_mine import extract_records

    rs = extract_records(_LISTING_HTML, base_url=_BASE_URL)
    assert rs is not None and len(rs.records) == _RECORD_COUNT, (
        f"the fixture yields {0 if rs is None else len(rs.records)} record(s), expected "
        f"{_RECORD_COUNT}. Fix the fixture or the constant — do not weaken the assertions "
        "that depend on it."
    )


@pytest.mark.asyncio
async def test_the_links_are_already_there() -> None:
    """PREMISE, not a claim of this change.

    `restore-links-on-pre-rendered-tiers` made this true. It is asserted here so
    that a failure in the tests below is unambiguously the ladder gate and never
    the link gate — the two defects sit six lines apart and the first was
    already mistaken for the whole story once.
    """
    fc = await _pre_rendered_fetch()

    assert fc.links, (
        "no links on the pre-rendered path. That is the EARLIER defect "
        "(restore-links-on-pre-rendered-tiers), not this one — fix that first, "
        "or the assertions below are testing the wrong gate."
    )


@pytest.mark.asyncio
async def test_the_structured_ladder_runs_on_the_pre_rendered_path() -> None:
    """A tier that produced markdown has NOT already run record detection."""
    fc = await _pre_rendered_fetch()

    sources = [c.source for c in fc.content_candidates]
    assert "record_synth" in sources, (
        f"the candidate menu is {sources or '[]'} — no record_synth. The escalation ladder "
        "did not run, so the extractor sees prose only (ADR-0005 menu of one), the digest "
        "gate can never pass, and the option shelf is empty."
    )
    assert sources[0] == "trafilatura", (
        f"the baseline candidate is missing or misordered: {sources}. The pre-rendered "
        "markdown must seed the menu in the same fixed source order as the raw path."
    )


@pytest.mark.asyncio
async def test_the_link_digest_is_reachable_on_the_pre_rendered_path() -> None:
    """The whole point: `other_pages` becomes emittable off the raw tier.

    The gate itself is unchanged and deliberately so — it requires a structured
    candidate as a pre-LLM stand-in for `structural_form ∈ {product, listing}`,
    which is what `link-affordances` requires so prose articles pay nothing.
    The gate was never the defect; it was starved.
    """
    fc = await _pre_rendered_fetch()

    digest = _build_link_digest(fc)
    assert digest is not None and digest.entries, (
        "no link digest on a listing-shaped pre-rendered page. With links present "
        "(asserted above) the only remaining gate is the structured candidate — so the "
        "escalation ladder is still being skipped."
    )


@pytest.mark.asyncio
async def test_listing_sufficiency_is_checked_on_the_pre_rendered_path() -> None:
    """ADR-0009's sufficiency axis, on the population most likely to need it.

    An infinite-scroll listing is precisely what forces a browser fetch, and a
    browser-served truncated sample was being returned as a confident complete
    answer.
    """
    fc = await _pre_rendered_fetch()

    assert fc.record_count == _RECORD_COUNT, (
        f"record_count is {fc.record_count}, expected {_RECORD_COUNT}. Listing "
        "completeness has no progress metric, so listing_partial can never fire on any "
        "pre-rendered tier."
    )
    assert fc.regex_oracle_total == _ADVERTISED_TOTAL, (
        f"the numeric oracle is {fc.regex_oracle_total}, expected {_ADVERTISED_TOTAL} — "
        "_phase_listing_completeness did not run, so a truncated sample is indistinguishable "
        "from the whole listing."
    )


def test_every_pre_rendered_install_goes_through_one_copy() -> None:
    """`Rendered`'s fields are copied onto the context in exactly ONE place.

    There were three — `_phase_extract`, `_escalate_browser`, `_escalate_paid` —
    and they disagreed. `links` was added to one, so the fix meant to make
    `other_pages` reachable did nothing on any page that reached the browser by
    ESCALATION rather than by winning the tier loop. That is the common path: a
    handler wins, the gate says `length_floor`, the browser escalates. Measured
    on `arxiv.org/list/cs.CL/recent` after the first fix shipped: `fc.links == 0`.

    The guard written for that fix could not see this, because it tested the
    extraction seam and not the install. This one tests the install, which is
    why it is a source-shape assertion rather than a behavioural one — a
    behavioural test passes as soon as the ONE path it exercises is correct, and
    that is exactly the failure being prevented.
    """
    import ast
    import inspect
    from pathlib import Path

    import a2web.fetcher as fetcher_mod

    source = Path(inspect.getsourcefile(fetcher_mod) or "").read_text(encoding="utf-8")
    tree = ast.parse(source)

    #: What a copy of the block looks like: three or more `fc.<f> = <src>.<f>`
    #: assignments in a row, same-named field, same source object. Matching the
    #: BLOCK rather than a single line is deliberate — `fc.content_md =
    #: extract_result.content_md` on the raw path is a legitimate one-off, and a
    #: per-line rule flags it while a block rule does not.
    _COPY_FLOOR = 3
    _HELPER = "_install_rendered_fields"

    #: The fields `Rendered` carries. A block copying three or more of THESE is a
    #: pre-rendered install. Transport blocks (`body`/`content_type`/`final_url`
    #: from a tier result) share the shape but not the subject — the escalation
    #: paths must set those themselves, which is why the helper deliberately
    #: does not.
    _RENDERED_FIELDS = frozenset({"content_md", "title", "byline", "headings", "links"})

    #: Source variables allowed to copy the same field set, and WHY. A table
    #: rather than a loosened rule, so the exemption is a visible reviewed edit.
    #:
    #: `extract_result` is `content_extract.ExtractedContent`, the raw path's
    #: canonical extraction output — a DIFFERENT type that additionally carries
    #: `published`, which `Rendered` has no field for. Folding it into the helper
    #: would either drop `published` on the raw path or add a field to `Rendered`
    #: that no tier can fill. It is the source the pre-rendered payloads are
    #: derived FROM, not another copy of them.
    _COPY_EXEMPT: frozenset[str] = frozenset({"extract_result"})

    def _copied_field(stmt: ast.stmt) -> tuple[str, str] | None:
        """`(source_var, field)` when stmt is `fc.X = src.X`, else None."""
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            return None
        target, value = stmt.targets[0], stmt.value
        if not (isinstance(target, ast.Attribute) and isinstance(value, ast.Attribute)):
            return None
        if target.attr != value.attr:
            return None
        src = ast.unparse(value.value)
        return (src, target.attr)

    offenders: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef) or func.name == _HELPER:
            continue
        for parent in ast.walk(func):
            body = getattr(parent, "body", None)
            if not isinstance(body, list):
                continue
            run_src: str | None = None
            run: list[str] = []
            for stmt in [*body, ast.Pass()]:
                got = _copied_field(stmt)
                if got is not None and (run_src is None or got[0] == run_src):
                    run_src, _ = got
                    run.append(got[1])
                    continue
                rendered_hits = [f for f in run if f in _RENDERED_FIELDS]
                if len(rendered_hits) >= _COPY_FLOOR and run_src not in _COPY_EXEMPT:
                    offenders.append(f"{func.name} — {run_src}: {'/'.join(run)}")
                run_src, run = (got[0], [got[1]]) if got is not None else (None, [])

    assert not offenders, (
        "a pre-rendered payload's fields are copied onto the context outside "
        f"`{_HELPER}`:\n  " + "\n  ".join(sorted(set(offenders))) + "\n\n"
        "That duplication is how `links` came to be carried on one install path and "
        "dropped on the other three, which made the previous fix a no-op on every "
        "page that reached the browser by escalation. Route it through the helper — "
        "there must be exactly one line to get wrong."
    )
    assert _HELPER in source, (
        f"`{_HELPER}` is gone, so this guard is asserting the absence of copies for "
        "a reason that no longer holds — it would pass vacuously on a codebase that "
        "had reverted to inline assignment via some other shape."
    )


@pytest.mark.asyncio
async def test_the_trafilatura_pass_is_still_skipped() -> None:
    """The half of the boundary that must NOT move.

    This starts green and stays green. If it ever fails, the skip was widened
    into a deletion and every pre-rendering tier is now paying trafilatura
    twice — the cost `pre_rendered` exists to avoid.
    """
    fc = await _pre_rendered_fetch()

    steps = [d.step for d in fc.diagnostics]
    assert "extract" not in steps, (
        f"an `extract` diagnostic row appeared: {steps}. The pre-rendered branch ran the "
        "trafilatura content pass, which the tier had already paid for."
    )
    assert fc.content_md, "the pre-rendered markdown was lost while narrowing the skip"
