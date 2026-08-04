"""An archived answer says how old it is.

`archive.py` has computed `snapshot_age_days` since the tier was written, set it
on `TierResult` — and NOTHING read it. The number reached the orchestrator's
doorstep and stopped, so a 2019 snapshot and a yesterday snapshot produced
byte-identical envelopes.

Why this is an ADR-0009 failure and not a missing nicety: the archive tier fires
*precisely because the live site walled us*. The caller asked about a page a2web
could not reach and is handed an answer anyway. `tier: archive` is on the wire,
but a tier name is not a date — and for the questions that drive someone to a
walled page (pricing, reviews, availability, "is this still true"), a stale
answer is a WRONG answer wearing a confident face.

Found by reading a bench envelope, not by a failing test: the
`walled-page-with-preceding-info-hint` cell answered *"Reviewers acknowledge
Salesforce's cost but emphasize value…"* from a Wayback snapshot of unknown age,
with nothing in the envelope to date it (`eval/runs/2026-08-01_132342/`).

Same "computed, then discarded" shape as arXiv's listing counts and the handler
`next_links` — the third this week.
"""

from __future__ import annotations

from datetime import date

import pytest

from a2web.hints import _ARCHIVE_STALE_DAYS, HINT_CODES, archive_snapshot_age_hint


def test_the_code_is_in_the_closed_vocabulary() -> None:
    """A hint whose code is undeclared cannot be matched by any agent."""
    assert "archive_snapshot_age" in HINT_CODES


def test_an_old_snapshot_warns_and_names_the_risk() -> None:
    """THE regression. Pre-fix this envelope was identical to a fresh one."""
    hint = archive_snapshot_age_hint(age_days=847, taken_at=date(2023, 4, 15))

    assert hint.severity == "warning"
    assert "2023-04-15" in hint.message, "the capture DATE must be stated"
    assert "847" in hint.message, "the age must be stated, not merely implied by a severity"
    assert "ARCHIVE SNAPSHOT" in hint.message
    assert "UNVERIFIED" in hint.message, "an old snapshot must name what not to trust"
    assert hint.fix


def test_a_fresh_snapshot_is_informational_not_alarming() -> None:
    """Anti-vacuity, and the calibration that makes the warning worth reading.

    A day-old snapshot is usually fine. Warning on every archive hit would train
    the caller to skip the hint, which costs every genuinely stale one that
    follows — the same false-positive economics as the `hn` partial-view note.
    """
    hint = archive_snapshot_age_hint(age_days=2, taken_at=date(2026, 7, 30))

    assert hint.severity == "info"
    assert "2 day" in hint.message
    assert "2026-07-30" in hint.message
    assert "UNVERIFIED" not in hint.message


@pytest.mark.parametrize(
    ("age", "expected"),
    [(_ARCHIVE_STALE_DAYS - 1, "info"), (_ARCHIVE_STALE_DAYS, "warning")],
)
def test_the_threshold_is_where_it_says_it_is(age: int, expected: str) -> None:
    """The boundary, so a refactor cannot shift it by one and go unnoticed."""
    assert archive_snapshot_age_hint(age_days=age).severity == expected


def test_the_age_reaches_the_response_builder() -> None:
    """The WIRING, not just the factory — and the reason this test exists.

    The factory alone proves nothing: `snapshot_age_days` was correctly computed
    and correctly stored for the tier's whole life, and the defect was that
    nobody read it. So this asserts the field is on `FetchContext` and that
    `fetcher_response`'s `ResponseContext` Protocol declares it.
    """
    import dataclasses

    from a2web.fetcher import FetchContext

    names = {f.name for f in dataclasses.fields(FetchContext)}
    assert "snapshot_age_days" in names, "the age never reaches the context that builds the response"

    from tests.architecture.test_response_context_slice import _protocol_members

    assert "snapshot_age_days" in _protocol_members(), "the response builder does not declare the age"


def test_a_non_archive_fetch_emits_nothing() -> None:
    """Anti-vacuity: a hint on every fetch is a hint on none of them.

    `snapshot_age_days` is `None` unless an archive install set it, and the
    builder is gated on that — a live page must not carry an archive warning.
    """
    import dataclasses

    from a2web.fetcher import FetchContext

    field = next(f for f in dataclasses.fields(FetchContext) if f.name == "snapshot_age_days")
    assert field.default is None, "the archive hint would fire on every fetch"


def test_the_date_leads_because_only_the_date_keeps() -> None:
    """An age decays the moment it is written; a date does not.

    "847 days old" is true when emitted and wrong thereafter — cached, logged,
    or pasted into a report it silently drifts. The calendar date stays true
    forever, so it is the fact and the age is the gloss. Wayback hands over
    `YYYYMMDDhhmmss` and a2web previously kept only the subtraction.
    """
    dated = archive_snapshot_age_hint(age_days=847, taken_at=date(2023, 4, 15))
    assert dated.message.index("2023-04-15") < dated.message.index("847")


def test_an_undatable_snapshot_still_reports_its_age() -> None:
    """archive.ph gives no timestamp, and a partial signal beats silence.

    Degrading to "about N days old" is honest; suppressing the hint because one
    field is missing would hide the fact that the answer is archived at all.
    """
    hint = archive_snapshot_age_hint(age_days=500, taken_at=None)
    assert "500 day" in hint.message
    assert hint.severity == "warning"


def test_the_snapshot_date_reaches_the_response_builder() -> None:
    """The wiring for the date, same reason as the age: storage is not delivery."""
    import dataclasses

    from a2web.fetcher import FetchContext

    names = {f.name for f in dataclasses.fields(FetchContext)}
    assert "snapshot_taken_at" in names

    from tests.architecture.test_response_context_slice import _protocol_members

    assert "snapshot_taken_at" in _protocol_members()
