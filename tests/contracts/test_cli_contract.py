"""The CLI contract gate — the hand-written Typer app vs the a2kit-generated one.

`tests/contracts/cli/*.json` froze the pre-sunset CLI at commit `d2dc5d8`
(see that directory's README for the capture method). This file replays the
same argv against the CLI a2web now owns and diffs the result.

**The gate is not "zero deltas" here, unlike the MCP wire.** The MCP surface is
consumed by installed agents that a2web cannot update, so the sunset's rule
there is that no byte moves. The CLI is consumed by a human at a terminal, and
the capture recorded several behaviours that were a2kit artifacts rather than
product — a no-op `--json`, a `--format` whose non-default values were
unreachable, framework-only `serve` flags. Reproducing those faithfully would
mean porting a2kit's mistakes into a2web's own code and maintaining them.

So every delta is *expected to be explained*: `_ACCEPTED` below names each one
and why, and anything not in that table fails. That keeps the useful property
of a golden gate (nothing changes silently) without pretending the old
behaviour was a specification.

Determinism matches the capture harness exactly — same stubbed tier, same
stubbed extractor, same frozen clock, same timing scrub. A drift here means the
CLI changed, not that the machine was busy.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from anyllm import ProviderName
from typer.testing import CliRunner

from a2web.cli import build_cli
from a2web.components import build_components
from a2web.tiers import REGISTRY, TierResult

CLI_DIR = Path(__file__).parent / "cli"

_BODY = (
    b"<html><head><title>Capture Fixture</title></head><body><main>"
    b"<h2>Section One</h2>"
    + b"<p>Adaptive web fetching keeps the caller's context small.</p>"
    * 20
    + b'<a href="https://example.org/next">Next page</a>'
    b"</main></body></html>"
)

_TIMING_RE = re.compile(r'"(started_at|total_ms|dur_ms|t_ms|latency_ms|elapsed_ms)":\s*("[^"]*"|[0-9.]+)')


class _RawStub:
    name = "raw"

    async def fetch(self, url: str, **kwargs: object) -> TierResult:
        del kwargs
        return TierResult(body=_BODY, content_type="text/html", status_code=200, final_url=url)


#: Deltas from the a2kit-generated CLI that are DELIBERATE. Keyed by golden
#: slug; the value says what changed and why. A golden that differs for a
#: reason not listed here fails — the table is the review surface.
_ACCEPTED: dict[str, str] = {
    "help_root": (
        "Command tree: `schema` / `list-tools` / `code` / `_meta` dropped as framework "
        "introspection (task 5.3); `version` added. Help text is a2web's own."
    ),
    "help_web": "Group help text is a2web's own; Typer 0.27 renders panels where a2kit's Typer did not.",
    "help_web_query": (
        "`--format` and `--json` dropped (a2kit formatter surface; --json was a no-op). "
        "`--link-roles` now shows its real description instead of a2kit's 'JSON value.'. "
        "`~95%%` -> `~95%` (wire delta `percent-escape-typo`)."
    ),
    "help_web_fetch_raw": "Same as help_web_query.",
    "help_health": "`health` is a2web's own probe now, not a2kit's aggregated one.",
    "help_serve": (
        "`--code-mode` / `--code-mode-allow-destructive` / `--compact` / `--tools` / "
        "`--select` / `--internal-uds` dropped — all described a2kit machinery. "
        "`--transport` / `--host` / `--port` survive."
    ),
    "err_bad_flag": "Typer 0.27 error rendering differs from a2kit's Typer; exit code 2 is unchanged.",
    "err_missing_url": "Same rendering difference; exit code 2 unchanged.",
    "err_unknown_command": "Same rendering difference; exit code 2 unchanged.",
    "web_fetch_raw_json": "`--json` was a no-op flag and is gone; the command now errors on it.",
}

#: Goldens whose STDOUT must match byte-for-byte. These are the payload cases —
#: the ones a script pipes into `jq`, where a changed byte is a broken caller.
_PAYLOAD_CASES = ["web_fetch_raw", "web_fetch_raw_links", "web_query", "web_query_debug", "web_query_include_content"]


def _golden(slug: str) -> dict[str, Any]:
    return json.loads((CLI_DIR / f"{slug}.json").read_text())


def _normalize(text: str) -> str:
    return _TIMING_RE.sub(r'"\1":<scrubbed>', text)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Pin exactly what `cli/_captured_with.py` pinned, for the same reasons.

    Stubbing `Extractor.extract` rather than injecting a fake extractor
    resource is deliberate: it is the seam the capture used, and a capture and
    its gate that stub at different depths are not comparing the same thing.

    The provider pin is the ONE thing the capture did not pin and should have.
    Stubbing `Extractor.extract` only takes effect once a provider was selected
    at all: with `auto` and no credentials, `select_provider` returns None and
    every `web query` golden degrades to an `llm_unavailable` payload instead.
    Pinning an OpenAI-compatible gateway with fake credentials makes selection
    succeed by construction — nothing is ever called, because the stub intercepts
    before any request — so these goldens exercise the CLI's rendering of a
    successful extraction, which is what they were captured to measure.

    **This is an ordinary explicit configuration, not a workaround.** It was
    written as one in 0.48.1, when the gate passed on a developer laptop with a
    Claude Code session and failed on a bare runner. That general defect now has
    a general mechanism — `tests/conftest.py::_hermetic_llm_env` makes the host's
    providers invisible to every test — so this pin no longer carries the weight
    of defending the suite; it only says which provider THESE goldens want.
    Keeping it is still correct and is not redundant with the fixture: the
    fixture guarantees no provider is ambiently available, which is exactly the
    state in which these goldens would degrade. The fixture removes the accident;
    this line supplies the intent.
    """
    monkeypatch.setenv("A2WEB_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("A2WEB_LLM_PROVIDER", ProviderName.OPENAI_COMPATIBLE.value)
    monkeypatch.setenv("OPENAI_API_KEY", "gate-stub-key-never-sent")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://gate.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "stub-model")
    monkeypatch.setitem(REGISTRY, "raw", _RawStub())

    import a2web.fetcher_response as fetcher_response
    from a2web.packages.llm_extract.extractor import ExtractionResult, Extractor

    frozen = datetime(2026, 1, 1, tzinfo=UTC)
    real_wrap = fetcher_response._wrap_content_md
    monkeypatch.setattr(
        fetcher_response,
        "_wrap_content_md",
        lambda md, *, source, fetched_at: real_wrap(md, source=source, fetched_at=frozen),
    )

    async def _stub_extract(self: object, **kwargs: object) -> ExtractionResult:
        del self, kwargs
        return ExtractionResult(
            answer="Frozen capture answer: adaptive fetching keeps the caller's context small.",
            model="stub-model",
            template_name="stub-template",
            prompt_tokens=100,
            completion_tokens=20,
            latency_ms=7,
        )

    monkeypatch.setattr(Extractor, "extract", _stub_extract)


def _invoke(argv: list[str]) -> tuple[int, str, str]:
    """Run one argv and return (exit_code, stdout, stderr).

    **stderr is not optional to compare.** Every error case in the capture has
    an empty stdout, so comparing stdout alone made the three of them match
    trivially — the gate would have reported "no drift" for an error surface it
    never looked at. `test_every_accepted_delta_is_real` caught exactly that.
    """
    result = CliRunner().invoke(build_cli(components=build_components()), argv, catch_exceptions=False)
    return result.exit_code, _normalize(result.stdout), _normalize(result.stderr)


def _matches(golden: dict[str, Any], observed: tuple[int, str, str]) -> bool:
    exit_code, stdout, stderr = observed
    return exit_code == golden["exit_code"] and stdout == _normalize(golden["stdout"]) and stderr == _normalize(golden["stderr"])


@pytest.mark.parametrize("slug", _PAYLOAD_CASES)
def test_payload_cases_match_the_pre_sunset_cli(slug: str) -> None:
    """The bytes a script parses must not have moved.

    These cases carry no accepted delta on purpose: the flags involved all
    survived the rewrite, so a difference here is a real regression in what
    `a2web web query | jq` produces.
    """
    golden = _golden(slug)
    exit_code, stdout, stderr = _invoke(golden["argv"])

    assert exit_code == golden["exit_code"], f"{slug}: exit code moved"
    assert stderr == _normalize(golden["stderr"]), f"{slug}: stderr moved"
    assert stdout == _normalize(golden["stdout"]), (
        f"CLI CONTRACT DRIFT in cli/{slug}.json.\n\n"
        "This is payload a caller may be piping into jq. If the change is deliberate, "
        "add it to `_ACCEPTED` with a reason and move the case out of _PAYLOAD_CASES."
    )


@pytest.mark.parametrize("slug", sorted(_ACCEPTED))
def test_every_accepted_delta_is_real(slug: str) -> None:
    """An accepted delta that stopped being a delta is stale bookkeeping.

    Without this, `_ACCEPTED` would accumulate entries describing differences
    that no longer exist, and the table would stop being a review surface.
    """
    golden = _golden(slug)
    assert not _matches(golden, _invoke(golden["argv"])), (
        f"{slug} is listed in _ACCEPTED but now matches the a2kit golden exactly. Remove the entry — the delta it documents is gone."
    )


def test_no_unlisted_deltas() -> None:
    """Every golden either matches or is explained. Nothing drifts unnoticed."""
    unexplained: list[str] = []
    for path in sorted(CLI_DIR.glob("*.json")):
        slug = path.stem
        if slug in _ACCEPTED:
            continue
        golden = _golden(slug)
        if not _matches(golden, _invoke(golden["argv"])):
            unexplained.append(slug)

    assert not unexplained, (
        f"CLI goldens drifted with no recorded reason: {unexplained}.\n\n"
        "Either fix the CLI, or add each slug to `_ACCEPTED` with the reason it "
        "differs from the a2kit-generated original."
    )


def test_goldens_are_not_vacuous() -> None:
    """The gate asserts on real captures, not an empty directory.

    Every architecture walk in this repo carries this assertion, for the reason
    `tests/architecture/_walk.py` records: a guard that passes by finding
    nothing is worse than no guard, because it reads as coverage.
    """
    goldens = list(CLI_DIR.glob("*.json"))
    assert len(goldens) >= 15, f"expected the full pre-sunset capture, found {len(goldens)} goldens"
    assert all(_golden(p.stem)["argv"] for p in goldens), "a golden with no argv captures nothing"
