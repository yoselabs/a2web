"""Affordances JSON-envelope parser tests (v0.20).

Guards the `_split_answer_and_affordances` helper in the Extractor:

  - Well-formed content-page payload parses into a full AffordancesPayload
  - Well-formed obstacle-page payload (no content_value / shapes / follow_ups)
    parses with `content_value=None` and empty tuples
  - Malformed JSON returns (text-as-given, None) — graceful degrade
  - ```json fences are tolerated
  - Missing required fields (page_kind, page_kind_confidence) return None
"""

from __future__ import annotations

import json

from a2web.packages.llm_extract import AffordancesPayload
from a2web.packages.llm_extract.extractor import _split_answer_and_affordances


def _content_page_envelope() -> str:
    return json.dumps(
        {
            "extracted_answer": "This article describes Rust's borrow checker.",
            "page_kind": "encyclopedia",
            "page_kind_confidence": "high",
            "reasoning": "Substantial Wikipedia article with citations and code examples.",
            "content_value": "high",
            "shapes": [
                {"label": "timeline", "where": "History section", "size": "medium"},
                {"label": "code", "where": "Syntax section", "size": "large"},
            ],
            "follow_up_questions": [
                "How does the borrow checker prevent memory safety errors?",
                "What companies have adopted Rust in production?",
            ],
        }
    )


def _obstacle_page_envelope() -> str:
    return json.dumps(
        {
            "extracted_answer": "The page returns a 404 error.",
            "page_kind": "error",
            "page_kind_confidence": "high",
            "reasoning": "HTTP 404 with 'Page not found' headline.",
        }
    )


def test_content_page_parses_full_payload() -> None:
    answer, payload = _split_answer_and_affordances(_content_page_envelope())
    assert answer == "This article describes Rust's borrow checker."
    assert payload is not None
    assert payload.page_kind == "encyclopedia"
    assert payload.page_kind_confidence == "high"
    assert payload.content_value == "high"
    assert len(payload.shapes) == 2
    assert payload.shapes[0].label == "timeline"
    assert payload.shapes[1].label == "code"
    assert len(payload.follow_up_questions) == 2


def test_obstacle_page_parses_with_defaults() -> None:
    answer, payload = _split_answer_and_affordances(_obstacle_page_envelope())
    assert answer == "The page returns a 404 error."
    assert payload is not None
    assert payload.page_kind == "error"
    assert payload.content_value is None
    assert payload.shapes == ()
    assert payload.follow_up_questions == ()


def test_obstacle_payload_with_stray_shapes_still_omits_them() -> None:
    """An obstacle page that DID emit shapes/follow_ups should still be
    interpreted with envelope discipline — shapes are dropped because
    page_kind is in the obstacle set. The parser enforces this."""
    payload_text = json.dumps(
        {
            "extracted_answer": "Captcha wall.",
            "page_kind": "blocked",
            "page_kind_confidence": "high",
            "reasoning": "Cloudflare interstitial.",
            "content_value": "low",
            "shapes": [{"label": "list", "where": "stray", "size": "small"}],
            "follow_up_questions": ["should not appear"],
        }
    )
    _, payload = _split_answer_and_affordances(payload_text)
    assert payload is not None
    assert payload.page_kind == "blocked"
    assert payload.content_value is None
    assert payload.shapes == ()
    assert payload.follow_up_questions == ()


def test_json_fence_tolerated() -> None:
    fenced = "```json\n" + _content_page_envelope() + "\n```"
    answer, payload = _split_answer_and_affordances(fenced)
    assert payload is not None
    assert payload.page_kind == "encyclopedia"
    assert answer.startswith("This article")


def test_bare_fence_tolerated() -> None:
    """A fence with no language tag still works."""
    fenced = "```\n" + _content_page_envelope() + "\n```"
    _, payload = _split_answer_and_affordances(fenced)
    assert payload is not None
    assert payload.page_kind == "encyclopedia"


def test_malformed_json_returns_none_payload() -> None:
    """Parse failure leaves payload None and returns the original text.
    Caller still gets a usable extraction; affordances are best-effort."""
    text = "Just plain text, no JSON anywhere."
    answer, payload = _split_answer_and_affordances(text)
    assert answer == text
    assert payload is None


def test_partial_json_returns_none() -> None:
    text = '{"extracted_answer": "Hi", "page_kind": "encyclopedia"'  # missing closing brace
    answer, payload = _split_answer_and_affordances(text)
    assert answer == text
    assert payload is None


def test_missing_extracted_answer_returns_none() -> None:
    payload_text = json.dumps({"page_kind": "encyclopedia", "page_kind_confidence": "high"})
    answer, payload = _split_answer_and_affordances(payload_text)
    assert payload is None
    # Falls back to returning the original text (caller can still salvage).
    assert answer == payload_text


def test_missing_page_kind_returns_answer_but_no_payload() -> None:
    payload_text = json.dumps(
        {
            "extracted_answer": "An answer.",
            "page_kind_confidence": "high",
        }
    )
    answer, payload = _split_answer_and_affordances(payload_text)
    assert answer == "An answer."
    assert payload is None


def test_shape_with_non_string_label_is_dropped() -> None:
    """Defensive: malformed shape entries are silently dropped, payload survives."""
    payload_text = json.dumps(
        {
            "extracted_answer": "OK.",
            "page_kind": "encyclopedia",
            "page_kind_confidence": "high",
            "reasoning": "",
            "content_value": "medium",
            "shapes": [
                {"label": "list", "where": "top", "size": "small"},
                {"label": 42, "where": "x", "size": "y"},  # bad label type
                {"missing_label": "yes"},
            ],
            "follow_up_questions": ["good question", 99, ""],
        }
    )
    _, payload = _split_answer_and_affordances(payload_text)
    assert payload is not None
    assert len(payload.shapes) == 1
    assert payload.shapes[0].label == "list"
    # Non-string + empty follow-ups dropped.
    assert payload.follow_up_questions == ("good question",)


def test_affordances_payload_is_frozen_dataclass() -> None:
    """Defensive: the boundary type must be immutable."""
    p = AffordancesPayload(
        page_kind="encyclopedia",
        page_kind_confidence="high",
        reasoning="",
    )
    try:
        p.page_kind = "tampered"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("AffordancesPayload must be frozen")
