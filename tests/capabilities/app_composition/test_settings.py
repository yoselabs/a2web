"""Settings tests — zero-config + YAML + env override + secret rule."""

from __future__ import annotations

from pathlib import Path

import pytest

import a2web.settings as settings_mod
from a2web.settings import AppSettings


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point HOME at an empty dir and clear A2WEB_* env to start clean."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("A2WEB_CONFIG", raising=False)
    monkeypatch.delenv("A2WEB_STEALTH", raising=False)
    monkeypatch.delenv("A2WEB_JINA_KEY", raising=False)
    settings_mod.get_settings.cache_clear()


def test_zero_config_defaults() -> None:
    """No file, no env vars — `AppSettings()` constructs with defaults."""
    s = AppSettings()
    assert s.stealth is False
    assert s.diagnostics_default == "off"
    assert s.proxies == {}
    assert s.jina_key == ""


def test_yaml_overrides_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """YAML at `$A2WEB_CONFIG` overrides defaults."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("stealth: true\ndiagnostics_default: brief\n")
    monkeypatch.setenv("A2WEB_CONFIG", str(cfg))

    s = AppSettings()
    assert s.stealth is True
    assert s.diagnostics_default == "brief"


def test_env_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`A2WEB_STEALTH=true` env beats YAML `stealth: false`."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("stealth: false\n")
    monkeypatch.setenv("A2WEB_CONFIG", str(cfg))
    monkeypatch.setenv("A2WEB_STEALTH", "true")

    s = AppSettings()
    assert s.stealth is True


def test_jina_key_env_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`jina_key` set in YAML is ignored; only env populates it."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("jina_key: should-be-ignored\n")
    monkeypatch.setenv("A2WEB_CONFIG", str(cfg))

    s = AppSettings()
    assert s.jina_key == ""

    monkeypatch.setenv("A2WEB_JINA_KEY", "from-env")
    s2 = AppSettings()
    assert s2.jina_key == "from-env"


def test_default_yaml_path_used_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`~/.a2web/config.yaml` is read when no `$A2WEB_CONFIG` is set."""
    home_cfg_dir = tmp_path / ".a2web"
    home_cfg_dir.mkdir()
    (home_cfg_dir / "config.yaml").write_text("stealth: true\n")

    s = AppSettings()
    assert s.stealth is True


def test_get_settings_is_cached() -> None:
    s1 = settings_mod.get_settings()
    s2 = settings_mod.get_settings()
    assert s1 is s2
