"""Reddit's Atom body is extracted with a DOM, not a greedy regex.

`_atom_body_markdown` pulled the authored body out of the `<content>` HTML with
`re.search(r'<div class="md">(.*)</div>', ...)`. Its own comment conceded the
assumption — *"Reddit's rendered md never nests `<div>`, so the greedy match
closes on the md div itself"* — which is a claim about Reddit's renderer that
a2web cannot enforce and that fails SILENTLY when it stops holding.

It does not hold for a sibling. A `<div>` AFTER the body (a footer, an embed)
makes `.*` run past the md div's closer to the LAST `</div>` on the fragment,
swallowing whatever sits between. The caller gets site chrome presented as the
author's words, with nothing to indicate it.

The architecture guard bans the regex; this asserts the behaviour, so the
replacement cannot regress into something that merely satisfies the guard.
"""

from __future__ import annotations

from a2web.handlers.reddit import _atom_body_markdown

_BODY = "Real body text"
_NOISE = "FOOTER NOISE"


def test_a_sibling_div_is_not_swallowed() -> None:
    """THE case the greedy regex got wrong (verified against it before replacing)."""
    fragment = f'<!-- SC_OFF --><div class="md"><p>{_BODY}</p></div><div class="footer">{_NOISE}</div><!-- SC_ON -->'

    out = _atom_body_markdown(fragment)

    assert _BODY in out
    assert _NOISE not in out, "site chrome reached the caller as the author's words"


def test_a_nested_div_inside_the_body_survives() -> None:
    """The other direction: real nested content must not be truncated.

    A blockquote containing a `<div>` is ordinary Reddit markup. A fix that
    switched the regex to non-greedy would pass the test above and silently
    cut every quoted block short here.
    """
    fragment = '<!-- SC_OFF --><div class="md"><blockquote><div>quoted</div></blockquote><p>after</p></div><!-- SC_ON -->'

    out = _atom_body_markdown(fragment)

    assert "quoted" in out
    assert "after" in out


def test_the_sc_markers_never_reach_the_markdown() -> None:
    """`to_markdown` renders HTML comments as TEXT — verified, not assumed.

    So dropping them is real work, not incidental: left in, the reader sees a
    literal "SC_OFF" at the top of every Reddit post body.
    """
    out = _atom_body_markdown(f'<!-- SC_OFF --><div class="md"><p>{_BODY}</p></div><!-- SC_ON -->')

    assert "SC_OFF" not in out and "SC_ON" not in out
    assert out.strip() == _BODY


def test_the_thumbnail_table_is_still_excluded() -> None:
    """The behaviour the md-div selection existed for in the first place."""
    fragment = f'<!-- SC_OFF --><table><tr><td>THUMB</td></tr></table><div class="md"><p>{_BODY}</p></div><!-- SC_ON -->'

    out = _atom_body_markdown(fragment)

    assert _BODY in out
    assert "THUMB" not in out


def test_a_body_with_no_md_div_still_renders() -> None:
    """Anti-vacuity: the fallback path must not silently return empty.

    A comment (t1) entry has no wrapper div. If the selector missing meant
    "nothing", every comment body would vanish — an empty answer that reads as
    a page with no content.
    """
    out = _atom_body_markdown("<p>A comment body with no wrapper</p>")

    assert "A comment body with no wrapper" in out
