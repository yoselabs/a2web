"""The report_feedback nudge (openspec `add-agent-invoked-feedback-tool`, design D1).

Direct unit tests against `_with_feedback_nudge` — pure function, no fetch,
no network.
"""

from __future__ import annotations

from a2web.fetcher_response import _with_feedback_nudge
from a2web.hints import OperatorHint
from a2web.models import Confidence


def test_warning_hint_gets_nudge_appended_to_its_fix() -> None:
    hint = OperatorHint(code="content_thin", message="Thin page.", fix="Retry the fetch.", severity="warning")
    result = _with_feedback_nudge([hint], Confidence.medium)

    assert len(result) == 1
    assert result[0].code == "content_thin"
    assert "Retry the fetch." in result[0].fix
    assert "report_feedback(subject=..., note=...)" in result[0].fix


def test_critical_hint_gets_nudge_appended_not_a_new_hint() -> None:
    hint = OperatorHint(code="try_user_browser", message="Walled.", fix="Open a browser.", severity="critical")
    result = _with_feedback_nudge([hint], Confidence.low)

    assert len(result) == 1  # no new hint added — appended to the existing one


def test_hint_with_no_fix_gets_nudge_as_the_whole_fix() -> None:
    hint = OperatorHint(code="content_guidance", message="Context.", severity="warning")
    result = _with_feedback_nudge([hint], Confidence.high)

    assert "report_feedback(subject=..., note=...)" in (result[0].fix or "")


def test_low_confidence_with_no_hint_synthesizes_one_info_hint() -> None:
    result = _with_feedback_nudge([], Confidence.low)

    assert len(result) == 1
    assert result[0].code == "report_feedback_available"
    assert result[0].severity == "info"
    assert "report_feedback(subject=..., note=...)" in (result[0].fix or "")


def test_high_confidence_no_hint_stays_untouched() -> None:
    result = _with_feedback_nudge([], Confidence.high)

    assert result == []


def test_medium_confidence_no_hint_stays_untouched() -> None:
    """Only `low` triggers the confidence-only branch — `medium` is not an
    atypical-enough deviation on its own (design D1: bounded, not `always`)."""
    result = _with_feedback_nudge([], Confidence.medium)

    assert result == []


def test_info_only_hints_do_not_host_the_nudge_but_low_confidence_still_synthesizes_one() -> None:
    """An info-severity hint (e.g. content_guidance) is not a "host" for the
    nudge — only warning/critical are — but low confidence alone still
    triggers the standalone hint."""
    info_hint = OperatorHint(code="content_guidance", message="Context.", severity="info")
    result = _with_feedback_nudge([info_hint], Confidence.low)

    assert len(result) == 2
    assert result[0].fix is None or "report_feedback(" not in (result[0].fix or "")
    assert result[1].code == "report_feedback_available"


def test_idempotent_when_a_hint_is_already_nudged() -> None:
    """build_ask_response re-derives hints from build_response's output,
    which may already carry the nudge — a second call must not double-append."""
    hint = OperatorHint(
        code="try_user_browser",
        message="Walled.",
        fix="Open a browser. If this doesn't answer what you needed, call report_feedback(subject=..., note=...) to report it.",
        severity="critical",
    )
    result = _with_feedback_nudge([hint], Confidence.low)

    assert result[0].fix.count("report_feedback(") == 1


def test_idempotent_when_the_standalone_hint_is_already_present() -> None:
    from a2web.hints import report_feedback_available_hint

    already = report_feedback_available_hint()
    result = _with_feedback_nudge([already], Confidence.low)

    assert len(result) == 1  # not duplicated
