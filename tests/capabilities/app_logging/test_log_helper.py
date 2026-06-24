"""The sync emit helper (`a2web.log`) lands records on the `a2kit` logger with
the structured payload under `record.a2kit_fields` — field-shape-identical to
the async `a2kit.log.*` front door's synchronous half."""

from __future__ import annotations

import logging

import pytest

from a2web.log import log_debug, log_error, log_info, log_warning


@pytest.fixture
def captured() -> list[logging.LogRecord]:
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("a2kit")
    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prev_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


def test_log_warning_record_shape(captured: list[logging.LogRecord]) -> None:
    log_warning("plugin_unavailable", name="anthropic", reason="no key")

    assert len(captured) == 1
    record = captured[0]
    assert record.name == "a2kit"
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "plugin_unavailable"
    assert record.a2kit_fields == {"name": "anthropic", "reason": "no key"}


@pytest.mark.parametrize(
    ("fn", "levelno"),
    [
        (log_debug, logging.DEBUG),
        (log_info, logging.INFO),
        (log_warning, logging.WARNING),
        (log_error, logging.ERROR),
    ],
)
def test_each_level_emits_at_its_severity(
    captured: list[logging.LogRecord],
    fn: object,
    levelno: int,
) -> None:
    fn("event", k="v")  # type: ignore[operator]

    assert len(captured) == 1
    assert captured[0].levelno == levelno
    assert captured[0].a2kit_fields == {"k": "v"}


def test_no_fields_emits_empty_payload(captured: list[logging.LogRecord]) -> None:
    log_info("bare")

    assert captured[0].a2kit_fields == {}
