"""Cassette format — freeze and replay one egress request/response.

A *cassette* is the frozen world for one corpus case: every external
interaction the pipeline made (raw HTTP, jina, archive, the rendered
browser DOM, the LLM call) serialized to plain, diff-readable files under
`<case>/inputs/`. Replay re-runs the *real* orchestrator, gate, and tier
ladder above these frozen egress points — only the egress is canned.

This module owns serialization for the HTTP egress (`raw.http` and any
sibling `*.http` files), keyed by the exact URL passed to
`http_fetch.fetch_bytes`. The browser and LLM egresses are plain files
(`rendered.html`, `llm/<key>.json`) read directly by their cassette
overrides in the replay harness.

Body bytes are stored as UTF-8 text when they decode cleanly (so HTML
diffs are human-readable for the bless review); otherwise base64, marked
by the `body-encoding` header. Multiple exchanges may share one file,
separated by `_EXCHANGE_SEP`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from a2web.packages.http_fetch import FetchOutcome, FetchVerdict

# Sentinel separating exchanges within a single `.http` file. Chosen to be
# vanishingly unlikely in a real body; the writer falls back to base64 for
# any body that nonetheless contains it.
_EXCHANGE_SEP = "\n===== a2web-cassette-exchange =====\n"
_HEADERS_MARK = "--- headers ---"
_BODY_MARK = "--- body ---"
_REQUEST_PREFIX = ">>> GET "


class CassetteError(ValueError):
    """Malformed cassette file."""


@dataclass(slots=True)
class _Exchange:
    """One frozen HTTP egress — the request URL plus its `FetchOutcome`."""

    url: str
    outcome: FetchOutcome


def _decode_body(body: bytes) -> tuple[str, str]:
    """Return (encoding, text). UTF-8 when clean and sentinel-free, else base64."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return "base64", base64.b64encode(body).decode("ascii")
    if _EXCHANGE_SEP in text or text.startswith(_REQUEST_PREFIX):
        return "base64", base64.b64encode(body).decode("ascii")
    return "utf-8", text


def _serialize_exchange(ex: _Exchange) -> str:
    o = ex.outcome
    encoding, body_text = _decode_body(o.body)
    lines = [
        f"{_REQUEST_PREFIX}{ex.url}",
        f"status: {o.status_code}",
        f"verdict: {o.verdict.value}",
        f"content-type: {o.content_type}",
        f"final-url: {o.final_url}",
        f"conditional-hit: {'true' if o.conditional_hit else 'false'}",
        f"body-encoding: {encoding}",
        _HEADERS_MARK,
    ]
    for key, value in o.headers.items():
        lines.append(f"{key}: {value}")
    lines.append(_BODY_MARK)
    header_block = "\n".join(lines)
    return f"{header_block}\n{body_text}"


def _parse_exchange(chunk: str) -> _Exchange:
    if not chunk.startswith(_REQUEST_PREFIX):
        raise CassetteError(f"exchange does not start with {_REQUEST_PREFIX!r}")
    # Split on the marker line (not marker+trailing-newline) so an empty
    # body/headers block — where the next section starts immediately — still
    # parses. The serializer writes exactly one `\n` after each marker as the
    # separator, so stripping a single leading newline is lossless.
    body_split = chunk.split(f"\n{_BODY_MARK}", 1)
    if len(body_split) != 2:
        raise CassetteError(f"exchange missing {_BODY_MARK!r} marker")
    head, body_text = body_split
    if body_text.startswith("\n"):
        body_text = body_text[1:]

    head_split = head.split(f"\n{_HEADERS_MARK}", 1)
    if len(head_split) != 2:
        raise CassetteError(f"exchange missing {_HEADERS_MARK!r} marker")
    meta_block, headers_block = head_split
    if headers_block.startswith("\n"):
        headers_block = headers_block[1:]

    meta_lines = meta_block.splitlines()
    url = meta_lines[0][len(_REQUEST_PREFIX) :]
    meta: dict[str, str] = {}
    for line in meta_lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    headers: dict[str, str] = {}
    for line in headers_block.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        headers[key.strip()] = value.strip()

    encoding = meta.get("body-encoding", "utf-8")
    body = base64.b64decode(body_text) if encoding == "base64" else body_text.encode("utf-8")

    return _Exchange(
        url=url,
        outcome=FetchOutcome(
            body=body,
            content_type=meta.get("content-type", ""),
            status_code=int(meta.get("status", "0")),
            final_url=meta.get("final-url", url),
            headers=headers,
            verdict=FetchVerdict(meta.get("verdict", "ok")),
            conditional_hit=meta.get("conditional-hit", "false") == "true",
        ),
    )


def serialize_exchanges(exchanges: dict[str, FetchOutcome]) -> str:
    """Serialize a URL→FetchOutcome map to one `.http` file body."""
    return _EXCHANGE_SEP.join(_serialize_exchange(_Exchange(url=url, outcome=o)) for url, o in exchanges.items())


def parse_exchanges(text: str) -> dict[str, FetchOutcome]:
    """Parse a `.http` file body into a URL→FetchOutcome map.

    Newlines are structural (they delimit an empty body), so the text is
    NOT newline-stripped; a `make eval-capture` writes the serializer output
    verbatim. A trailing file newline only ever adds a harmless trailing
    newline to the last body.
    """
    if not text.strip():
        return {}
    out: dict[str, FetchOutcome] = {}
    for chunk in text.split(_EXCHANGE_SEP):
        ex = _parse_exchange(chunk)
        out[ex.url] = ex.outcome
    return out
