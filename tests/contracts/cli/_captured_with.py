"""Capture the a2kit-generated CLI surface as goldens for the sunset Phase 5 gate.

Run from THIS worktree (detached at d2dc5d8 — the last commit that still has a
working a2kit CLI). Writes JSON goldens to the path given as argv[1].

The CLI is driven in-process via `a2kit.run(app, argv)` with the raw tier
stubbed, so no network is touched and the output is deterministic.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path

os.environ["COLUMNS"] = "100"
os.environ["A2WEB_CACHE_DIR"] = str(Path(__file__).parent / ".capture-cache")
os.environ["TERM"] = "dumb"
os.environ["NO_COLOR"] = "1"

import a2kit  # noqa: E402

from a2web.server import app  # noqa: E402
from a2web.tiers import REGISTRY, TierResult  # noqa: E402

# --- Determinism ------------------------------------------------------- #
# Three things vary run-to-run and none of them are CLI contract:
#   1. `fetched_at` in the content_md wrapper (wall clock),
#   2. the extractor's answer (a live LLM call — capture #1 actually spent
#      quota and produced prose that would never reproduce),
#   3. argv[0], which in-process capture reports as this script.
# Freeze all three so a golden diff means "the CLI changed".
import datetime as _dt  # noqa: E402

import a2web.fetcher_response as _fr  # noqa: E402

_FROZEN = _dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=_dt.UTC)
_real_wrap = _fr._wrap_content_md
_fr._wrap_content_md = lambda md, *, source, fetched_at: _real_wrap(md, source=source, fetched_at=_FROZEN)

from a2web.packages.llm_extract.extractor import ExtractionResult, Extractor  # noqa: E402

_ANSWER = "Frozen capture answer: adaptive fetching keeps the caller's context small."


async def _stub_extract(self: object, **kwargs: object) -> ExtractionResult:
    del self, kwargs
    return ExtractionResult(
        answer=_ANSWER,
        model="stub-model",
        template_name="stub-template",
        prompt_tokens=100,
        completion_tokens=20,
        latency_ms=7,
    )


Extractor.extract = _stub_extract  # type: ignore[method-assign]

_BODY = (
    b"<html><head><title>Capture Fixture</title></head><body><main>"
    b"<h2>Section One</h2>"
    + b"<p>Adaptive web fetching keeps the caller's context small.</p>" * 20
    + b'<a href="https://example.org/next">Next page</a>'
    b"</main></body></html>"
)


class _RawStub:
    """A raw tier that always wins, so no escalation is ever warranted."""

    name = "raw"

    async def fetch(self, url: str, **kwargs: object) -> TierResult:
        del kwargs
        return TierResult(body=_BODY, content_type="text/html", status_code=200, final_url=url)


REGISTRY["raw"] = _RawStub()

#: (slug, argv). Every command the CLI exposes that the sunset intends to keep,
#: plus --help at every level and one bad-flag error.
CASES: list[tuple[str, list[str]]] = [
    ("help_root", ["--help"]),
    ("help_web", ["web", "--help"]),
    ("help_web_query", ["web", "query", "--help"]),
    ("help_web_fetch_raw", ["web", "fetch_raw", "--help"]),
    ("help_health", ["health", "--help"]),
    ("help_serve", ["serve", "--help"]),
    ("web_fetch_raw", ["web", "fetch_raw", "--url", "https://example.org/x"]),
    ("web_fetch_raw_json", ["web", "fetch_raw", "--url", "https://example.org/x", "--json"]),
    (
        "web_fetch_raw_links",
        ["web", "fetch_raw", "--url", "https://example.org/x", "--include-links"],
    ),
    ("web_query", ["web", "query", "--url", "https://example.org/x", "--query", "topic"]),
    (
        "web_query_debug",
        ["web", "query", "--url", "https://example.org/x", "--query", "topic", "--debug"],
    ),
    (
        "web_query_include_content",
        ["web", "query", "--url", "https://example.org/x", "--query", "topic", "--include-content"],
    ),
    ("err_bad_flag", ["web", "fetch_raw", "--url", "https://example.org/x", "--nope"]),
    ("err_missing_url", ["web", "fetch_raw"]),
    ("err_unknown_command", ["nosuchcommand"]),
]


#: Wall-clock measurements. Their PRESENCE is contract (`--debug` must emit
#: them); their VALUES are not. Scrubbed to a marker so a golden diff means the
#: CLI changed rather than that the machine was busy.
_TIMING_RE = re.compile(
    r'"(started_at|total_ms|dur_ms|t_ms|latency_ms|elapsed_ms)":\s*("[^"]*"|[0-9.]+)'
)


def _normalize(text: str) -> str:
    """Erase capture-harness artifacts and wall-clock noise — neither is contract.

    In-process capture reports `argv[0]` as this script, so Click's usage lines
    read `capture_cli.py` where a real invocation reads `a2web`.
    """
    text = text.replace("capture_cli.py", "a2web")
    return _TIMING_RE.sub(r'"\1":<scrubbed>', text)


def run_case(argv: list[str]) -> dict[str, object]:
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            a2kit.run(app, argv)
    except SystemExit as exc:
        code = int(exc.code or 0)
    except BaseException as exc:  # noqa: BLE001 - capturing today's behaviour, warts included
        code = -1
        err.write(f"\n<<UNCAUGHT {type(exc).__name__}: {exc}>>\n")
    return {
        "argv": argv,
        "exit_code": code,
        "stdout": _normalize(out.getvalue()),
        "stderr": _normalize(err.getvalue()),
    }


def main() -> None:
    dest = Path(sys.argv[1])
    dest.mkdir(parents=True, exist_ok=True)
    for slug, argv in CASES:
        result = run_case(argv)
        (dest / f"{slug}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(f"{slug}: exit={result['exit_code']} out={len(str(result['stdout']))}b", file=sys.__stderr__)


if __name__ == "__main__":
    main()
