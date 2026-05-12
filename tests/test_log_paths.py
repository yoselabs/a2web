"""Log path resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from a2web.packages.ndjson_log import active_log_path, log_dir


def test_log_dir_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("A2WEB_LOG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert log_dir() == tmp_path / ".a2web" / "logs"


def test_log_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A2WEB_LOG_DIR", str(tmp_path / "custom"))
    assert log_dir() == tmp_path / "custom"


def test_active_log_path_uses_passed_now(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A2WEB_LOG_DIR", str(tmp_path))
    fixed = datetime(2026, 5, 9, tzinfo=UTC)
    assert active_log_path(fixed) == tmp_path / "fetches-2026-05-09.ndjson"
