"""`detect_gated_sections` — the DOM predicate (ADR-0020 design.md D1-D4).

Positive case driven against a CAPTURED page (`tests/fixtures/captured/`), not
a hand-written stand-in (AGENTS.md: fixtures are captured, never the oracle for
parser-matches-live-site). Negative cases are synthetic — they assert the
predicate does NOT fire on shapes that would trip a naive "label + number"
text heuristic, which is the false-positive class design.md D2/D3 name
explicitly (cart/notification badges, price, rating, pager).
"""

from __future__ import annotations

from pathlib import Path

from a2web.gated_sections import detect_gated_sections

_FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "captured" / "hepsiburada_carraro_gravel_g2_tabs.html"


def _fixture_html() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_the_captured_page_really_states_a_qa_count() -> None:
    """Recapture-sanity: if this fails, the fixture no longer represents the
    live page's markup and must be recaptured, not patched around."""
    assert 'aria-controls="QuestionAnswers"' in _fixture_html()
    assert 'aria-label=" Soru Cevap 4"' in _fixture_html()


def test_detects_the_gated_qa_tab_with_its_stated_count() -> None:
    digest = detect_gated_sections(_fixture_html())
    labels = {e.label: e.stated_count for e in digest.entries}
    assert labels["Soru Cevap"] == 4


def test_does_not_flag_the_currently_active_tab() -> None:
    """The Description tab is selected and populated — never a gate."""
    digest = detect_gated_sections(_fixture_html())
    labels = {e.label for e in digest.entries}
    assert "Ürün Açıklaması" not in labels  # noqa: RUF001


def test_does_not_flag_an_inactive_but_already_populated_tab() -> None:
    """The Reviews panel is `display:none` (inactive) but already carries real
    rendered text once style/script noise is excluded — the exact case that
    would trip a naive 'display:none = gated' heuristic. Ground-truth verified
    live: 573 chars of real review prose survive script/style stripping."""
    digest = detect_gated_sections(_fixture_html())
    labels = {e.label for e in digest.entries}
    assert "Değerlendirmeler" not in labels


def test_flags_every_other_empty_panel_tab() -> None:
    digest = detect_gated_sections(_fixture_html())
    labels = {e.label for e in digest.entries}
    assert labels >= {"Hepsitaksit", "Kredi Kart Taksitleri", "Alışveriş Kredisi", "İptal ve İade Koşulları"}  # noqa: RUF001


def test_handles_are_stable_and_one_indexed_in_document_order() -> None:
    digest = detect_gated_sections(_fixture_html())
    handles = [e.handle for e in digest.entries]
    assert handles == list(range(1, len(handles) + 1))
    assert digest.entries[0].label == "Soru Cevap"


def test_render_produces_a_closed_menu_block() -> None:
    digest = detect_gated_sections(_fixture_html())
    rendered = digest.render()
    assert rendered.startswith("## gated sections")
    assert "{{1}} Soru Cevap (4)" in rendered


def test_resolve_returns_the_section_for_a_known_handle() -> None:
    digest = detect_gated_sections(_fixture_html())
    resolved = digest.resolve(1)
    assert resolved is not None
    assert resolved.label == "Soru Cevap"


def test_resolve_drops_an_unknown_handle_rather_than_guessing() -> None:
    digest = detect_gated_sections(_fixture_html())
    assert digest.resolve(999) is None


# ─── Negative controls — the false-positive class design.md names ─────────


def test_cart_badge_inside_nav_is_excluded() -> None:
    html = """
    <nav role="nav">
      <button role="tab" aria-controls="cart-panel" aria-label=" Sepet 3">Sepet<span>3</span></button>
    </nav>
    <div id="cart-panel"></div>
    """
    assert detect_gated_sections(html).entries == ()


def test_notification_badge_inside_nav_is_excluded() -> None:
    html = """
    <div role="nav">
      <button role="tab" aria-controls="notif-panel" aria-label=" Bildirimler 12">Bildirimler</button>
    </div>
    <div id="notif-panel"></div>
    """
    assert detect_gated_sections(html).entries == ()


def test_plain_price_rating_pager_text_is_not_a_control() -> None:
    """Price / rating / pager text is never a `role=tab` or `<details>`
    control in the first place — excluded structurally, not by content."""
    html = "<div>Fiyat 1.299,00 TL</div><div>Değerlendirme Puanı 4,5</div><div>Sayfa 1 / 7</div>"  # noqa: RUF001
    assert detect_gated_sections(html).entries == ()


def test_tab_with_no_aria_controls_is_skipped_not_guessed() -> None:
    html = '<button role="tab" aria-label="Mystery 9">Mystery</button>'
    assert detect_gated_sections(html).entries == ()


def test_populated_details_with_open_is_not_a_gate() -> None:
    html = '<details open><summary>Soru Cevap (4)</summary><p>Real answer text here</p></details>'
    assert detect_gated_sections(html).entries == ()


def test_empty_details_without_open_is_a_gate() -> None:
    html = "<details><summary>Soru Cevap (4)</summary></details>"
    digest = detect_gated_sections(html)
    assert len(digest.entries) == 1
    assert digest.entries[0].label == "Soru Cevap"
    assert digest.entries[0].stated_count == 4


def test_tab_whose_panel_is_entirely_absent_from_the_dom_is_a_gate() -> None:
    html = '<button role="tab" aria-controls="missing" aria-label=" Yorumlar 12">Yorumlar</button>'
    digest = detect_gated_sections(html)
    assert digest.entries == (digest.entries[0],)
    assert digest.entries[0].stated_count == 12


def test_a_tab_with_no_trailing_count_is_still_detected() -> None:
    html = '<button role="tab" aria-controls="missing" aria-label=" Hepsitaksit ">Hepsitaksit</button>'
    digest = detect_gated_sections(html)
    assert len(digest.entries) == 1
    assert digest.entries[0].label == "Hepsitaksit"
    assert digest.entries[0].stated_count is None


def test_markdown_only_body_yields_no_gate() -> None:
    """The declared coverage limit (design.md D4): a tier whose retrieved body
    is markdown carries no `role=tab`/`<details>` markup to inspect at all —
    the detector must not manufacture a gate it cannot evidence."""
    markdown_body = "# Product\n\nSoru Cevap 4\n\nDetails here.\n"
    assert detect_gated_sections(markdown_body).entries == ()


def test_no_controls_at_all_yields_an_empty_falsy_digest() -> None:
    digest = detect_gated_sections("<div>hello world</div>")
    assert digest.entries == ()
    assert bool(digest) is False
