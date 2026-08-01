"""Capture the MCP wire surface through a real client against the real server.

**One layer, one rule: if a byte does not come out of `fastmcp.Client`
against `build_mcp_server(build_app())`, it is not a contract byte.**

This exists because the older `tests/contracts/test_contracts.py` snapshots
cannot serve as a migration gate — they pass vacuously across a substrate
change, for three independent reasons:

1. `client.call_wire` reads `structured_content` and *re-formats* it through
   `format_response(value, descriptor.format_hint)`, a path that can only
   yield the `tsv` / `page-tsv` / `json` plans — never the `envelope` plan
   production actually uses. It measures a path the wire does not take.
2. `compute_schema` is an a2kit-private reimplementation of schema
   derivation. Its output has titles and no descriptions; the live wire has
   descriptions and no titles. Different artifacts.
3. Nothing covered tool descriptions, annotations, `_meta`, the error
   envelope, or the log-notification stream.

**Do not reach for `a2kit.testing.client` here.** It calls
`server.enable(tags={"_meta"})` on construction (`a2kit/packages/testing/
client.py:96`), re-enabling tools production hides via
`server.disable(tags={"_meta"})`. A surface captured through it is not the
surface agents see. We build the server ourselves — `build_mcp_server(app)`
with no `code_mode` override consults `config.mcp.code_mode` (a2web: False)
and applies the `_meta` disable internally, so it is production-exact.

**Determinism comes from freezing the clock, never from scrubbing raw
bytes.** Scrubbing inside a frozen string is precisely how a real diff
hides: a substitution that turns `total_ms=469` into `total_ms=<volatile>`
would equally mask an encoder that dropped the field's neighbours. So
`freeze_clocks` pins `time.perf_counter` and `datetime.now`, and
normalization is confined to `structured_content`.
"""

from __future__ import annotations

import contextlib
import datetime as _datetime_mod
import difflib
import json
import os
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from a2web.server import build_mcp_server

WIRE_DIR = Path(__file__).parent / "wire"
DELTAS_PATH = Path(__file__).parent / "DELTAS.md"


#: Set to a reason slug to accept a wire change. Writes the new golden AND
#: appends the diff to DELTAS.md under that slug. A re-bless with no slug is
#: rejected when goldens exist — that is the whole point of the two phases.
def _validated_accept_slug() -> str | None:
    """The re-bless reason, rejected unless it is actually a reason.

    Any truthy value rewrote all 12 goldens. `A2WEB_ACCEPT_WIRE_DELTA=1` — a
    plausible slip when reaching for a flag — silently re-blessed the entire
    agent-facing wire contract and wrote "1" into DELTAS.md as the
    justification. The gate's whole design is "an unexplained re-bless is
    rejected"; a value that explains nothing must be treated as unexplained.

    So: kebab-case, at least two words, no bare booleans or digits. This cannot
    tell a real reason from a well-formed lie — nothing can — but it does stop
    the accidental blanket accept, which is the failure that actually happens.
    """
    raw = os.environ.get("A2WEB_ACCEPT_WIRE_DELTA")
    if raw is None:
        return None
    slug = raw.strip()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", slug) or slug in _REJECTED_SLUGS:
        raise RuntimeError(
            f"A2WEB_ACCEPT_WIRE_DELTA={raw!r} is not a reason.\n"
            "Re-blessing rewrites the surface installed agents consume, so the slug is\n"
            "recorded in tests/contracts/DELTAS.md as the justification. Use kebab-case\n"
            "with at least two words, e.g. `severity-column-union-fix`.\n"
            "Rejected: bare digits, booleans, and single words."
        )
    return slug


#: Values that parse as slugs but say nothing.
_REJECTED_SLUGS = frozenset({"yes-yes", "true-true", "accept-it", "do-it", "just-do-it"})

ACCEPT_SLUG = _validated_accept_slug()

#: The instant every captured response is pinned to.
FROZEN_INSTANT = _datetime_mod.datetime(2026, 1, 1, 0, 0, 0, tzinfo=_datetime_mod.UTC)


class _FrozenDatetime(_datetime_mod.datetime):
    """`datetime` with a pinned `now()`; everything else inherited."""

    @classmethod
    def now(cls, tz: Any = None) -> _datetime_mod.datetime:  # type: ignore[override]
        return FROZEN_INSTANT if tz is not None else FROZEN_INSTANT.replace(tzinfo=None)


def freeze_clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin every clock the response envelope reads.

    `time.perf_counter` is patched on the `time` module itself: every call
    site does `import time` then `time.perf_counter()`, resolving the
    attribute at call time, so one patch reaches all of them. Elapsed
    durations collapse to 0 — `narrative` becomes `raw -> ok (0ms)` rather
    than a wall-clock artifact.
    """
    monkeypatch.setattr(time, "perf_counter", lambda: 0.0)
    monkeypatch.setattr("a2web.fetcher.datetime", _FrozenDatetime)


@contextlib.asynccontextmanager
async def wire_client(server: Any = None, **client_kwargs: Any) -> AsyncIterator[Any]:
    """A real `fastmcp.Client` over the real production server assembly.

    Takes the FastMCP server itself now — before the sunset it took an
    `a2kit.App` and built the server here. Passing `None` builds the default
    production server, which is what every scenario wants.
    """
    from fastmcp import Client

    if server is None:
        server = build_mcp_server()
    async with Client(transport=server, **client_kwargs) as client:
        yield client


def capture(result: Any) -> dict[str, Any]:
    """Freeze a `CallToolResult` as the three things a caller can observe.

    `content[].text` is kept as an **opaque string** and is never
    `json.loads`-ed. The sidecar keys, the `"\\n"` empty-TSV markers and the
    TSV escaping exist only in the raw bytes; parsing and re-serializing
    would normalize away the exact differences this gate is built to catch.
    """
    return {
        "is_error": bool(result.is_error),
        "content": [{"type": block.type, "text": block.text} for block in result.content],
        "structured_content": normalize(result.structured_content),
    }


#: Keys carrying values no clock freeze can pin (uuids, environment state).
#:
#: `a2kit_elapsed_ms` (and its post-sunset successor `elapsed_ms`) is the call
#: scope's wall-clock age on the notification wire. It reads `time.monotonic`,
#: not the `perf_counter` this harness freezes, and patching `monotonic`
#: globally would also freeze the event loop's own clock — asyncio resolves
#: `loop.time()` through it, so every timeout in the process would stop firing.
#: Masking the VALUE still leaves the KEY visible in the golden, so a rename or
#: a removal of the field is a diff; only the unpinnable integer is hidden.
_VOLATILE_KEYS = frozenset({"trace_id", "a2kit_elapsed_ms", "elapsed_ms"})


def normalize(obj: Any) -> Any:
    """Replace unpinnable values — `structured_content` ONLY, never raw text."""
    if isinstance(obj, dict):
        return {k: ("<volatile>" if k in _VOLATILE_KEYS else normalize(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj


def _serialize(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _record_delta(name: str, slug: str, expected: str, actual: str) -> None:
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"{name}.json (before)",
            tofile=f"{name}.json (after)",
        )
    )
    header = "" if DELTAS_PATH.exists() else "# Wire contract deltas\n\nEvery accepted change to the MCP wire surface, with its reason.\n"
    with DELTAS_PATH.open("a") as fh:
        fh.write(f"{header}\n## `{slug}` — `{name}`\n\n```diff\n{diff}```\n")


def check_wire(name: str, payload: Any) -> None:
    """Compare against the golden, or accept the change under a reason slug."""
    path = WIRE_DIR / f"{name}.json"
    actual = _serialize(payload)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual)
        pytest.fail(f"wire golden {name}.json did not exist — created it. Re-run to verify, then commit it.")

    expected = path.read_text()
    if expected == actual:
        return

    if ACCEPT_SLUG:
        path.write_text(actual)
        _record_delta(name, ACCEPT_SLUG, expected, actual)
        return

    diff = "".join(difflib.unified_diff(expected.splitlines(keepends=True), actual.splitlines(keepends=True), "expected", "actual"))
    pytest.fail(
        f"WIRE CONTRACT DRIFT in wire/{name}.json.\n\n"
        "This is the surface installed agents consume. If the change is deliberate, accept it\n"
        "WITH A REASON so the diff lands in tests/contracts/DELTAS.md:\n\n"
        f"    A2WEB_ACCEPT_WIRE_DELTA=<reason-slug> uv run pytest {__file__}\n\n"
        "An unexplained re-bless is rejected by design — during the a2kit sunset the gate is\n"
        "'zero deltas', and a blanket bless would let the migration silently redefine the wire.\n\n"
        f"{diff}"
    )
