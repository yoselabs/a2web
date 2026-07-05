"""`patchright` + `zendriver` are an OPTIONAL extra (`a2web[browser]`) — the slim
deploy container ships without them (deployable-container-ci image-slimming).

The browser tier is escalation-only; its absence must degrade GRACEFULLY, never
crash. This pins the gate the packaging split relies on: with the extra absent,
the backend manifests report `Unavailable` (via `find_spec`, cheap — no heavy
import) and `select_backend` raises `ResourceUnavailable` at the seam, which the
orchestrator catches to emit a loud `try_user_browser` hint (covered end-to-end
by `test_browser_unavailable_surfaces_operator_hint`).

Extra-absent is simulated by monkeypatching `importlib.util.find_spec` — the
engines are really installed in the dev env via the extra, so we can't uninstall
them.
"""

from __future__ import annotations

import importlib.util

import pytest

from a2web._manifests.browser_backends import patchright as patchright_manifest
from a2web._manifests.browser_backends import zendriver as zendriver_manifest
from a2web._plugin import Unavailable
from a2web.settings import AppSettings
from a2web.state import ResourceUnavailable, select_backend

_ENGINES = ("patchright", "zendriver")


def _hide_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `find_spec` report both browser engines absent."""
    real = importlib.util.find_spec

    def fake(name: str, package: str | None = None):
        if name in _ENGINES:
            return None
        return real(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake)


def test_patchright_manifest_unavailable_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_engines(monkeypatch)
    result = patchright_manifest._build(AppSettings())
    assert isinstance(result, Unavailable)
    assert "patchright" in result.reason


def test_zendriver_manifest_unavailable_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_engines(monkeypatch)
    result = zendriver_manifest._build(AppSettings())
    assert isinstance(result, Unavailable)
    assert "zendriver" in result.reason


def test_select_backend_degrades_not_crashes_when_extra_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """No engine installed → both manifests drop out → the named backend isn't in
    the registry → `ResourceUnavailable` (the graceful seam), NOT an ImportError."""
    _hide_engines(monkeypatch)
    with pytest.raises(ResourceUnavailable):
        select_backend(AppSettings())


def test_backends_available_when_extra_present() -> None:
    """Dev env has the extra installed → the fast rung selects (no launch here —
    construction is lazy)."""
    backend = select_backend(AppSettings())
    assert backend is not None
