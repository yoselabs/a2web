"""The `next_links` judge must not reward filtering the product forbids.

ADR-0012 is a first-class product invariant: a2web shapes and relays content, it
never ranks, filters, hides, or crowns by a criterion of its own. On a listing,
the onward-link index is supposed to be the page's items — including the ones a
reader would find dull.

The bench's `next_links` judge was scoring against the opposite rule. Measured on
2026-08-01 (`eval/runs/2026-08-01_152218/trace/gh-trending-best/a2web_extract/`),
it marked the set down to 3 because it "pollutes coverage with clearly off-topic
entries like SimplifyJobs/Summer2027-Internships (an internship list, not a repo
to adopt) and paperswithbacktest/awesome-systematic-trading (a curated list, not
a project)".

Both were on GitHub trending that day. a2web relayed them, which is precisely
what ADR-0012 requires — so **an a2web that obeyed its own invariant could not
score full marks on this axis**, and one that quietly editorialised would have
scored better. An eval that rewards violating the spec is worse than no eval:
it applies steady pressure in the wrong direction, and every run repeats it.

Second defect, same prompt: scoring item merit means scoring THAT DAY'S page, so
the axis moved with whatever happened to trend overnight rather than with any
change to a2web. That is the noise documented in
`eval/findings_2026-08-01-noise-floor.md`.

This test pins the corrected framing. It asserts on the prompt text because the
prompt IS the mechanism — there is no cheaper witness for "what is this judge
told to reward", and the failure mode is someone tightening the wording later
and silently restoring the old incentive.
"""

from __future__ import annotations

from a2web.llm_eval.bench_judge import _NEXT_LINKS_TEMPLATE

_PROMPT = _NEXT_LINKS_TEMPLATE.lower()


def test_the_prompt_is_actually_being_read() -> None:
    """Non-vacuity: an empty or renamed template would satisfy every `in` below.

    `"x" not in ""` is True, so the negative assertions in particular would all
    pass over nothing.
    """
    assert len(_NEXT_LINKS_TEMPLATE) > 400, "the template is far shorter than expected — is this still the prompt?"
    assert "{task}" in _NEXT_LINKS_TEMPLATE
    assert "{next_links}" in _NEXT_LINKS_TEMPLATE


def test_the_judge_is_told_not_to_grade_individual_item_merit() -> None:
    """THE regression. The judge must not penalise a faithfully relayed item."""
    assert "not whether each linked item is individually worthwhile" in _PROMPT, (
        "the prompt no longer forbids grading individual item merit — this is the clause that stops the axis rewarding ADR-0012 violations"
    )
    assert "faithfully" in _PROMPT
    assert "filtering" in _PROMPT


def test_the_judge_is_told_the_system_may_not_filter_or_rank() -> None:
    """The reason for the rule, not just the rule — a judge given only a
    prohibition tends to route around it."""
    assert "required to relay" in _PROMPT
    assert "forbidden" in _PROMPT


def test_the_judge_is_told_it_cannot_see_todays_page() -> None:
    """The noise half: grading against today's content makes the axis unreadable."""
    assert "today" in _PROMPT
    assert "cannot see" in _PROMPT


def test_the_judge_still_scores_composition() -> None:
    """Anti-vacuity of a different kind: the axis must still measure SOMETHING.

    Stripping the content-grading incentive without leaving a positive criterion
    would turn this into an axis that cannot distinguish a good set from a bad
    one — which scores well on "no longer wrong" and badly on "still useful".
    """
    for criterion in ("drill-down targets", "chrome", "coverage"):
        assert criterion in _PROMPT, f"the prompt no longer asks about {criterion!r} — the axis measures nothing"


def test_the_fabrication_amnesty_survives_because_the_judge_is_blind() -> None:
    """Deliberately NOT inverted, against `close-guards-that-read-green` §6.5.

    That task says to invert "never assume it is fabricated" because the clause
    disarms ADR-0014. The premise is "once it can verify" — and this judge is
    handed the task string and the rendered block and nothing else. It has no
    page, so it cannot check whether a URL was on one. Telling a blind judge to
    suspect fabrication buys guesses, not verification, and guesses on this axis
    are exactly what the rest of this file is about removing.

    ADR-0014 is deterministic — every emitted URL traceable to an anchor on the
    fetched page — and belongs in a check that can read the page. Asserted here
    so the clause is not "fixed" without that check existing first.
    """
    assert "never assume it is fabricated" in _PROMPT
    assert "existence is checked elsewhere" in _PROMPT
