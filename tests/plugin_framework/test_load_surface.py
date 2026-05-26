"""Unit tests for `a2web._plugin.load_surface`."""

from __future__ import annotations

import pytest

from a2web._plugin import PluginManifest, Unavailable, load_surface
from a2web.settings import AppSettings

from ._fixture_surface.widget_alpha import Widget


@pytest.fixture
def settings() -> AppSettings:
    return AppSettings()


def test_load_surface_returns_available_plugins_only(settings: AppSettings) -> None:
    registry = load_surface(
        "tests.plugin_framework._fixture_surface", Widget, settings
    )
    assert set(registry) == {"alpha", "beta"}
    assert registry["alpha"].name == "alpha"
    assert registry["beta"].name == "beta"


def test_load_surface_skips_unavailable_silently(settings: AppSettings) -> None:
    registry = load_surface(
        "tests.plugin_framework._fixture_surface", Widget, settings
    )
    assert "gamma" not in registry


def test_load_surface_skips_utility_modules(settings: AppSettings) -> None:
    registry = load_surface(
        "tests.plugin_framework._fixture_surface", Widget, settings
    )
    assert "_utility" not in registry
    assert "utility" not in registry


def test_plugin_manifest_is_frozen() -> None:
    def factory(_s: AppSettings) -> object | Unavailable:
        return object()

    m = PluginManifest(name="x", protocol=object, factory=factory)
    with pytest.raises((AttributeError, TypeError)):
        m.name = "y"  # type: ignore[misc]


def test_unavailable_is_named_tuple() -> None:
    u = Unavailable("missing api key")
    assert u.reason == "missing api key"
    assert u[0] == "missing api key"
