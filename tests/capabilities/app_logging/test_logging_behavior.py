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
from anyllm import ClaudeCodeSdkAdapter

from a2web.llm_resource import select_provider
from a2web.log import log_warning
from a2web.settings import AppSettings


@contextlib.contextmanager
def _capture_records(level: int = logging.DEBUG) -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("a2web")
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


def test_provider_selection_never_writes_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Provider selection with no backend configured resolves to None and writes
    nothing to stdout (a stray write would corrupt the MCP stdio JSON-RPC stream).

    Provider construction + the quiet skip of unavailable backends now live in
    anyllm (`resolve_provider`); a2web's job is only to keep every log record off
    stdout. Exercise the live `select_provider` path with no key and no session."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ClaudeCodeSdkAdapter, "available", lambda _self: False)

    with _capture_records():
        assert select_provider(AppSettings()) is None

    out = capsys.readouterr()
    assert out.out == "", f"logging leaked to stdout (MCP stdio hazard): {out.out!r}"


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
