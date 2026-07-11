"""Router-shape JSON-envelope parser tests (v0.21).

Guards the `_split_answer_and_routing` helper in the Extractor:

  - Well-formed healthy payload parses into a full RouterPayload
  - Healthy payload with no conditionals omits optional fields cleanly
  - Obstacle payload populates `obstacle` and typically `other_pages`
  - Malformed JSON returns (text-as-given, None) — graceful degrade
  - ```json fences are tolerated
  - Missing required fields (answer / structural_form / shape) returns None
  - Unknown enum values pass through at the boundary (pydantic mirror enforces)
"""

from __future__ import annotations

import json

from a2web.packages.llm_extract import OtherPageBoundary, RouterPayload
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
            "also_here": [
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
            "other_pages": [
                {"url": "https://archive.org/wayback/foo", "reason": "wayback snapshot before paywall"},
            ],
        }
    )


def test_healthy_payload_parses_full_shape() -> None:
    """The `genre` key in `_healthy_envelope()` is a stray key from a
    non-conforming/stale-prompt response — it's silently ignored (no `genre`
    field exists on `RouterPayload` to receive it), the rest of the envelope
    parses normally."""
    answer, payload = _routing(_healthy_envelope())
    assert answer.startswith("Rust's borrow checker")
    assert payload is not None
    assert payload.answer == answer
    assert payload.structural_form == "reference"
    assert payload.shape == "prose"
    assert not hasattr(payload, "genre")
    assert payload.obstacle is None
    assert len(payload.also_here) == 3
    assert payload.other_pages == ()


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
    assert payload.obstacle is None
    assert payload.also_here == ()
    assert payload.other_pages == ()


def test_also_here_only_payload() -> None:
    text = json.dumps(
        {
            "answer": "Discussion thread on Rust async.",
            "structural_form": "thread",
            "shape": "discussion",
            "also_here": ["Top critique?", "What did the OP reply to?"],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert payload.shape == "discussion"
    assert len(payload.also_here) == 2
    assert payload.other_pages == ()


def test_obstacle_payload_populates_obstacle_and_other_pages() -> None:
    answer, payload = _routing(_obstacle_envelope())
    assert payload is not None
    assert payload.obstacle == "paywalled"
    assert len(payload.other_pages) == 1
    assert isinstance(payload.other_pages[0], OtherPageBoundary)
    assert payload.other_pages[0].url == "https://archive.org/wayback/foo"
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


def test_other_pages_with_bad_entry_drops_only_that_entry() -> None:
    text = json.dumps(
        {
            "answer": "OK.",
            "structural_form": "article",
            "shape": "prose",
            "other_pages": [
                {"url": "https://good.example/", "reason": "good"},
                {"url": "", "reason": "empty url drops"},
                {"reason": "no url drops"},
                "not a dict",
            ],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert len(payload.other_pages) == 1
    assert payload.other_pages[0].url == "https://good.example/"


def test_other_pages_handle_parses_to_boundary_with_empty_url() -> None:
    """The digest path: `{handle, reason}` → boundary carrying the handle,
    url empty (the domain seam rehydrates it from the closed digest set)."""
    text = json.dumps(
        {
            "answer": "Reviews are on a separate page.",
            "structural_form": "product",
            "shape": "key-value",
            "other_pages": [
                {"handle": 3, "reason": "customer reviews live here"},
            ],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert len(payload.other_pages) == 1
    entry = payload.other_pages[0]
    assert entry.handle == 3
    assert entry.url == ""
    assert entry.reason == "customer reviews live here"


def test_other_pages_handle_wins_over_url_and_rejects_bool_handle() -> None:
    text = json.dumps(
        {
            "answer": "OK.",
            "structural_form": "product",
            "shape": "key-value",
            "other_pages": [
                {"handle": 2, "url": "https://ignored.example/", "reason": "prefer handle"},
                {"handle": True, "reason": "bool is not a handle — falls through, no url, drops"},
            ],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert len(payload.other_pages) == 1
    assert payload.other_pages[0].handle == 2
    assert payload.other_pages[0].url == ""


def test_also_here_drops_non_strings_and_empties() -> None:
    text = json.dumps(
        {
            "answer": "OK.",
            "structural_form": "article",
            "shape": "prose",
            "also_here": ["good question", "", 99, None],
        }
    )
    _, payload = _routing(text)
    assert payload is not None
    assert payload.also_here == ("good question",)


def test_router_payload_is_frozen_dataclass() -> None:
    p = RouterPayload(answer="x", structural_form="article", shape="prose")
    try:
        p.answer = "tampered"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RouterPayload must be frozen")


def test_next_url_boundary_is_frozen_dataclass() -> None:
    n = OtherPageBoundary(url="https://example.com", reason="r")
    try:
        n.url = "tampered"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("OtherPageBoundary must be frozen")


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
