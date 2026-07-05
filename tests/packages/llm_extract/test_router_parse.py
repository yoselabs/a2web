"""Router-shape JSON-envelope parser tests (v0.21).

Guards the `_split_answer_and_routing` helper in the Extractor:

  - Well-formed healthy payload parses into a full RouterPayload
  - Healthy payload with no conditionals omits optional fields cleanly
  - Obstacle payload populates `obstacle` and typically `try_url`
  - Malformed JSON returns (text-as-given, None) — graceful degrade
  - ```json fences are tolerated
  - Missing required fields (answer / structural_form / shape) returns None
  - Unknown enum values pass through at the boundary (pydantic mirror enforces)
"""

from __future__ import annotations

import json

from a2web.packages.llm_extract import NextUrlBoundary, RouterPayload
from a2web.packages.llm_extract.extractor import _RoutingResult, _split_answer_and_routing
from a2web.packages.llm_extract.wobble import unwrap


def _routing(text: str) -> tuple[str, RouterPayload | None]:
    """Unwrap the funnel's Wobbled<_RoutingResult> to the legacy (str, RouterPayload | None) shape."""
    answer, wobbled = _split_answer_and_routing(text)
    if wobbled is None:
        return answer, None
    result: _RoutingResult = unwrap(wobbled)
    return answer, result.payload


def _healthy_envelope() -> str:
    return json.dumps(
        {
            "answer": "Rust's borrow checker prevents data races at compile time.",
            "structural_form": "reference",
            "shape": "prose",
            "genre": "encyclopedia",
            "ask_here": [
                "Which lifetime annotations require explicit syntax?",
                "How does &mut interact with NLL?",
                "When did the 2018 edition land borrow checker changes?",
            ],
        }
    )


def _obstacle_envelope() -> str:
    return json.dumps(
        {
            "answer": "The article is behind a paywall.",
            "structural_form": "article",
            "shape": "prose",
            "obstacle": "paywalled",
            "try_url": [
                {"url": "https://archive.org/wayback/foo", "reason": "wayback snapshot before paywall"},
            ],
        }
    )


def test_healthy_payload_parses_full_shape() -> None:
    answer, payload = _routing(_healthy_envelope())
    assert answer.startswith("Rust's borrow checker")
    assert payload is not None
    assert payload.answer == answer
    assert payload.structural_form == "reference"
    assert payload.shape == "prose"
    assert payload.genre == "encyclopedia"
    assert payload.obstacle is None
    assert len(payload.ask_here) == 3
    assert payload.try_url == ()


def test_minimal_payload_omits_optionals() -> None:
    text = json.dumps(
        {
            "answer": "A short article about widgets.",
            "structural_form": "article",
            "shape": "prose",
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert payload.genre is None
    assert payload.obstacle is None
    assert payload.ask_here == ()
    assert payload.try_url == ()


def test_ask_here_only_payload() -> None:
    text = json.dumps(
        {
            "answer": "Discussion thread on Rust async.",
            "structural_form": "thread",
            "shape": "discussion",
            "ask_here": ["Top critique?", "What did the OP reply to?"],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert payload.shape == "discussion"
    assert len(payload.ask_here) == 2
    assert payload.try_url == ()


def test_obstacle_payload_populates_obstacle_and_try_url() -> None:
    answer, payload = _routing(_obstacle_envelope())
    assert payload is not None
    assert payload.obstacle == "paywalled"
    assert len(payload.try_url) == 1
    assert isinstance(payload.try_url[0], NextUrlBoundary)
    assert payload.try_url[0].url == "https://archive.org/wayback/foo"
    assert answer.startswith("The article")


def test_json_fence_tolerated() -> None:
    fenced = "```json\n" + _healthy_envelope() + "\n```"
    _, payload = _routing(fenced)
    assert payload is not None
    assert payload.structural_form == "reference"


def test_bare_fence_tolerated() -> None:
    fenced = "```\n" + _healthy_envelope() + "\n```"
    _, payload = _routing(fenced)
    assert payload is not None
    assert payload.shape == "prose"


def test_malformed_json_returns_none_payload() -> None:
    text = "Just plain text, no JSON anywhere."
    answer, payload = _routing(text)
    assert answer == text
    assert payload is None


def test_partial_json_returns_none() -> None:
    text = '{"answer": "Hi", "structural_form": "article"'  # missing closing brace
    answer, payload = _routing(text)
    assert answer == text
    assert payload is None


def test_missing_answer_returns_none() -> None:
    text = json.dumps({"structural_form": "article", "shape": "prose"})
    answer, payload = _routing(text)
    assert payload is None
    assert answer == text


def test_missing_structural_form_returns_answer_but_no_payload() -> None:
    text = json.dumps({"answer": "An answer.", "shape": "prose"})
    answer, payload = _routing(text)
    assert answer == "An answer."
    assert payload is None


def test_missing_shape_returns_answer_but_no_payload() -> None:
    text = json.dumps({"answer": "An answer.", "structural_form": "article"})
    answer, payload = _routing(text)
    assert answer == "An answer."
    assert payload is None


def test_unknown_enum_values_pass_through_at_boundary() -> None:
    """The boundary type is loose; closed-enum enforcement is the pydantic
    mirror's job at the seam (see test_router_wire.py)."""
    text = json.dumps(
        {
            "answer": "Something.",
            "structural_form": "blog-post",  # not in the 9-value set
            "shape": "diagram",  # not in the 7-value set
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert payload.structural_form == "blog-post"
    assert payload.shape == "diagram"


def test_try_url_with_bad_entry_drops_only_that_entry() -> None:
    text = json.dumps(
        {
            "answer": "OK.",
            "structural_form": "article",
            "shape": "prose",
            "try_url": [
                {"url": "https://good.example/", "reason": "good"},
                {"url": "", "reason": "empty url drops"},
                {"reason": "no url drops"},
                "not a dict",
            ],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert len(payload.try_url) == 1
    assert payload.try_url[0].url == "https://good.example/"


def test_ask_here_drops_non_strings_and_empties() -> None:
    text = json.dumps(
        {
            "answer": "OK.",
            "structural_form": "article",
            "shape": "prose",
            "ask_here": ["good question", "", 99, None],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert payload.ask_here == ("good question",)


def test_router_payload_is_frozen_dataclass() -> None:
    p = RouterPayload(answer="x", structural_form="article", shape="prose")
    try:
        p.answer = "tampered"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RouterPayload must be frozen")


def test_next_url_boundary_is_frozen_dataclass() -> None:
    n = NextUrlBoundary(url="https://example.com", reason="r")
    try:
        n.url = "tampered"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("NextUrlBoundary must be frozen")


# --------------------------------------------------------------------- #
# Robustness: object present but not the whole payload (model-agnostic parse)
# --------------------------------------------------------------------- #


def test_trailing_next_links_fence_is_recovered() -> None:
    """DeepSeek pattern: a valid router object followed by a separate
    ```next_links``` fence. The funnel extracts the leading object instead of
    dumping raw JSON into the answer."""
    text = _healthy_envelope() + '\n\n```next_links\n[{"anchor":"x","url":"https://e/"}]\n```'
    answer, payload = _routing(text)
    assert payload is not None
    assert answer.startswith("Rust's borrow checker")
    assert "structural_form" not in answer
    assert "```" not in answer


def test_trailing_prose_after_object_is_recovered() -> None:
    text = _healthy_envelope() + "\n\nNote: some extra prose the model appended."
    answer, payload = _routing(text)
    assert payload is not None
    assert answer.startswith("Rust's borrow checker")
