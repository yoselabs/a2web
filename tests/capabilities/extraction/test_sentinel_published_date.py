"""a2web-7bj.9: a bare Jan-1 `published` date is a copyright-footer/schema
sentinel, not a genuine first-published date — `_phase_extract` drops it
rather than shipping a confidently wrong value (I0269: dhl.com shipped
`2018-01-01`, gumruk.dhl.com.tr shipped `2000-01-01`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from a2web.decision_log import ObservationKind
from a2web.fetcher.comprehension.extract import _ExtractResult, _is_sentinel_date, _phase_extract
from a2web.fetcher.context import FetchContext, FetchInputs, FetchResources
from a2web.models import Verdict

_HTML = "<html><body><p>Some page content long enough to extract.</p></body></html>"


def _fc() -> FetchContext:
    fc = FetchContext(
        inputs=FetchInputs(
            started_at=datetime.now(UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
        ),
        resources=FetchResources(sqlite=None),
        url="https://example.org/page",
        final_url="https://example.org/page",
        body=_HTML.encode("utf-8"),
        content_type="text/html",
    )
    fc.observe(kind=ObservationKind.tier_outcome, source="raw", verdict=Verdict.ok)
    return fc


@pytest.mark.parametrize("d", [date(2000, 1, 1), date(2018, 1, 1), date(1999, 1, 1)])
def test_is_sentinel_date_flags_any_year_on_jan_1(d: date) -> None:
    assert _is_sentinel_date(d)


@pytest.mark.parametrize("d", [date(2026, 3, 15), date(2026, 1, 2), date(2025, 12, 1)])
def test_is_sentinel_date_leaves_other_dates_alone(d: date) -> None:
    assert not _is_sentinel_date(d)


@pytest.mark.asyncio
@pytest.mark.protects("spec:extraction", "Requirement: A bare Jan-1 published date is treated as no date")
async def test_phase_extract_drops_a_jan_1_published_date(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_extract_markdown(html: str, url: str) -> _ExtractResult:
        del html, url
        return _ExtractResult(
            content_md="some content",
            title="A title",
            byline=None,
            published=date(2000, 1, 1),
            headings=[],
            links=[],
            score=None,
        )

    monkeypatch.setattr("a2web.fetcher.comprehension.extract.extract_markdown", _fake_extract_markdown)

    fc = _fc()
    await _phase_extract(fc)

    assert fc.published is None


@pytest.mark.asyncio
@pytest.mark.protects("spec:extraction", "Requirement: A bare Jan-1 published date is treated as no date")
async def test_phase_extract_keeps_a_genuine_published_date(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_extract_markdown(html: str, url: str) -> _ExtractResult:
        del html, url
        return _ExtractResult(
            content_md="some content",
            title="A title",
            byline=None,
            published=date(2026, 3, 15),
            headings=[],
            links=[],
            score=None,
        )

    monkeypatch.setattr("a2web.fetcher.comprehension.extract.extract_markdown", _fake_extract_markdown)

    fc = _fc()
    await _phase_extract(fc)

    assert fc.published == date(2026, 3, 15)
