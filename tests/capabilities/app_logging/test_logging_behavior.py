"""Behavioral guarantees of the single managed logging channel.

Covers: (1) provider load never writes to stdout — the MCP-stdio JSON-RPC
safety property; (2) a resolved-fallback miss (`anthropic` unavailable while
`claude-code` resolves) is recorded at DEBUG only, so it is silent at default
`wire_level`/`stderr_sink`; (3) a2web emit obeys the `a2kit` logger's level —
the lever `LogConfig.enabled=false` / `level` pulls.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator

import pytest

from a2web._plugin import load_surface
from a2web.log import log_warning
from a2web.packages.llm_extract import Provider
from a2web.settings import AppSettings


@contextlib.contextmanager
def _capture_records(level: int = logging.DEBUG) -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("a2kit")
    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prev = logger.level
    logger.setLevel(level)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)


def test_provider_load_never_writes_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Loading the provider surface without an API key emits `plugin_unavailable`
    for anthropic — and writes nothing to stdout (would corrupt MCP stdio)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with _capture_records():
        load_surface("a2web._manifests.llm_providers", Provider, AppSettings())

    out = capsys.readouterr()
    assert out.out == "", f"logging leaked to stdout (MCP stdio hazard): {out.out!r}"


def test_provider_fallback_miss_is_debug_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The anthropic-unavailable fact is recorded at DEBUG (silent at default
    wire/stderr levels) — never at INFO+ that would read as a failure."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with _capture_records() as records:
        load_surface("a2web._manifests.llm_providers", Provider, AppSettings())

    unavailable = [r for r in records if r.getMessage() == "plugin_unavailable"]
    anthropic = [r for r in unavailable if getattr(r, "a2kit_fields", {}).get("name") == "anthropic"]
    assert anthropic, "expected a plugin_unavailable record for anthropic without an API key"
    assert all(r.levelno == logging.DEBUG for r in anthropic), "fallback miss must be DEBUG, not INFO+"


def test_emit_obeys_a2kit_logger_level() -> None:
    """a2web emit is governed by the `a2kit` logger level — the lever
    `LogConfig.enabled=false` pulls (disabled level → record dropped)."""
    # Disabled level above WARNING: a warning emit is suppressed.
    with _capture_records(level=logging.CRITICAL + 10) as records:
        log_warning("plugin_unavailable", name="anthropic")
    assert records == [], "emit should be suppressed when the a2kit logger level disables it"

    # Normal level: the same emit is captured on the managed channel.
    with _capture_records(level=logging.DEBUG) as records:
        log_warning("plugin_unavailable", name="anthropic")
    assert [r.getMessage() for r in records] == ["plugin_unavailable"]
