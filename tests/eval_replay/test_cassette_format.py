"""Cassette serialization round-trips losslessly and stays diff-readable."""

from __future__ import annotations

from a2web.packages.http_fetch import FetchOutcome, FetchVerdict
from eval._capture.cassette import parse_exchanges, serialize_exchanges


def _outcome(url: str, body: bytes, *, ct: str = "text/html", status: int = 200) -> FetchOutcome:
    return FetchOutcome(
        body=body,
        content_type=ct,
        status_code=status,
        final_url=url,
        headers={"content-type": ct, "server": "test"},
        verdict=FetchVerdict.ok,
    )


def test_utf8_body_round_trips_and_is_plain_text() -> None:
    url = "https://example.com/a"
    html = b"<html><body><h1>Hello</h1><p>Plain readable body.</p></body></html>"
    text = serialize_exchanges({url: _outcome(url, html)})

    # Body is stored as plain text for a human-readable bless diff.
    assert "body-encoding: utf-8" in text
    assert "<h1>Hello</h1>" in text

    parsed = parse_exchanges(text)
    assert parsed[url].body == html
    assert parsed[url].headers["server"] == "test"
    assert parsed[url].verdict is FetchVerdict.ok


def test_binary_body_falls_back_to_base64() -> None:
    url = "https://example.com/img"
    blob = bytes(range(256))  # not valid utf-8
    text = serialize_exchanges({url: _outcome(url, blob, ct="image/png")})
    assert "body-encoding: base64" in text
    assert parse_exchanges(text)[url].body == blob


def test_multiple_exchanges_keyed_by_url() -> None:
    a = "https://archive.org/cdx?q=1"
    b = "https://web.archive.org/snap"
    text = serialize_exchanges({a: _outcome(a, b"cdx-rows"), b: _outcome(b, b"<html>snap</html>")})
    parsed = parse_exchanges(text)
    assert set(parsed) == {a, b}
    assert parsed[a].body == b"cdx-rows"


def test_verdict_and_conditional_hit_preserved() -> None:
    url = "https://example.com/404"
    o = FetchOutcome(body=b"", content_type="", status_code=404, final_url=url, verdict=FetchVerdict.not_found)
    parsed = parse_exchanges(serialize_exchanges({url: o}))
    assert parsed[url].verdict is FetchVerdict.not_found
    assert parsed[url].status_code == 404
