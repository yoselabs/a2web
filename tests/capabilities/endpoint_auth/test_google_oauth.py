"""Config-gated Google OAuth on the HTTP MCP endpoint (google-oauth-endpoint-auth).

a2kit is auth-agnostic on the MCP surface (ADR 0010): the provider is a FastMCP
object handed to `serve_process(mcp_options={"auth": …})`, not an AuthSpec. These
tests pin the gating + provider construction without a live OAuth handshake (that
needs a real GCP client + public URL — operator-verified).
"""

from __future__ import annotations

from typing import Any

import pytest

from a2web import server
from a2web.server import build_google_provider, serve_http_main
from a2web.settings import _SECRET_FIELDS, AppSettings

_FULL = {
    "google_client_id": "cid.apps.googleusercontent.com",
    "google_client_secret": "secret",
    "google_base_url": "https://a2web.example.com",
}


# --------------------------------------------------------------------- #
# Provider construction + gating
# --------------------------------------------------------------------- #


def _clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every auth var, prefixed and bare, from the process environment.

    Without this the "unconfigured" assertions read whatever the developer's
    shell happens to carry — and one of them now RAISES on a bare var, so an
    unrelated `GOOGLE_CLIENT_ID` in the environment would fail the suite.
    """
    for name in server._AUTH_ENV_FIELDS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(f"A2WEB_{name}", raising=False)


def test_unconfigured_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """No A2WEB_GOOGLE_CLIENT_ID → None → endpoint stays open (ship behind Tailscale/LAN)."""
    _clear_auth_env(monkeypatch)
    assert build_google_provider(AppSettings()) is None


# --------------------------------------------------------------------- #
# The unprefixed-env security defect
# --------------------------------------------------------------------- #


def test_unprefixed_auth_env_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE regression: bare vars must never yield a silently open endpoint.

    `env_prefix="A2WEB_"` + `extra="ignore"` means a bare `GOOGLE_CLIENT_ID`
    reaches nothing. Before 2026-08-01 this returned `None` and the server came
    up ANONYMOUS while every operator-visible signal said authenticated — and
    a2web's own README carried the bare spelling in a copy-pasteable
    `docker run` block, so it was a mistake the project taught.
    """
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_BASE_URL", "https://a2web.example.com")

    with pytest.raises(ValueError, match="WITHOUT the A2WEB_ prefix") as caught:
        build_google_provider(AppSettings())

    message = str(caught.value)
    assert "A2WEB_GOOGLE_CLIENT_ID" in message, "the error must name the CORRECT spelling, not just the wrong one"
    assert "UNAUTHENTICATED" in message


def test_unprefixed_check_does_not_fire_on_a_correct_deployment(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Anti-vacuity, and a real false-positive risk.

    A correctly-prefixed deployment that also carries an unrelated bare
    `GOOGLE_CLIENT_ID` (another tool's, a CI runner's) must still boot. The
    guard fires only on the unambiguous case: no prefixed var set, some bare
    one set.
    """
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "some-other-tools-client")
    monkeypatch.setenv("A2WEB_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("A2WEB_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("A2WEB_GOOGLE_BASE_URL", "https://a2web.example.com")
    monkeypatch.setenv("A2WEB_OAUTH_CACHE_DIR", str(tmp_path))

    settings = AppSettings()
    assert settings.google_client_id == "cid.apps.googleusercontent.com", "the prefixed var is the one that wins"
    assert build_google_provider(settings) is not None


def test_nothing_configured_at_all_still_serves_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must not turn "no auth wanted" into a boot failure.

    Serving open behind Tailscale/LAN is a supported deployment; only a
    *mistaken* configuration is an error.
    """
    _clear_auth_env(monkeypatch)
    assert build_google_provider(AppSettings()) is None


def test_fully_configured_builds_provider(tmp_path: Any) -> None:
    from fastmcp.server.auth.providers.google import GoogleProvider

    provider = build_google_provider(AppSettings(**_FULL, oauth_cache_dir=str(tmp_path)))
    assert isinstance(provider, GoogleProvider)


def test_partial_config_missing_secret_fails_loud() -> None:
    """CLIENT_ID without SECRET → loud ValueError (never silently serve open)."""
    with pytest.raises(ValueError, match="GOOGLE_CLIENT_SECRET"):
        build_google_provider(AppSettings(google_client_id="cid", google_base_url="https://x.example"))


def test_partial_config_missing_base_url_fails_loud() -> None:
    with pytest.raises(ValueError, match="GOOGLE_BASE_URL"):
        build_google_provider(AppSettings(google_client_id="cid", google_client_secret="secret"))


def test_encryption_wraps_the_store(tmp_path: Any) -> None:
    """An oauth_encryption_key wraps the token store in Fernet-at-rest (free — the
    provider still constructs)."""
    from fastmcp.server.auth.providers.google import GoogleProvider

    provider = build_google_provider(
        AppSettings(**_FULL, oauth_cache_dir=str(tmp_path), oauth_encryption_key="pass-phrase-123"),
    )
    assert isinstance(provider, GoogleProvider)


# --------------------------------------------------------------------- #
# Secrets are env-only (dropped from YAML)
# --------------------------------------------------------------------- #


def test_google_secrets_excluded_from_yaml() -> None:
    exclude = _SECRET_FIELDS
    assert {"google_client_secret", "google_jwt_signing_key", "oauth_encryption_key"} <= exclude


# --------------------------------------------------------------------- #
# serve_http_main path selection (no socket bound; seam mocked)
# --------------------------------------------------------------------- #


def _capture_serve(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub `FastMCP.run`; return the captured server + kwargs.

    Post-sunset there is no `serve_process` to intercept — `serve_http_main`
    builds the FastMCP server and calls `.run()` on it directly. Stubbing
    `.run` is what keeps this from binding a real socket and blocking the
    suite forever, which is exactly what happened the first time it was run
    against the new entrypoint.
    """
    captured: dict[str, Any] = {}
    from fastmcp import FastMCP

    def _fake_run(self: FastMCP, **kw: Any) -> None:
        captured["server"] = self
        captured.update(kw)

    monkeypatch.setattr(FastMCP, "run", _fake_run)
    return captured


def test_serve_unconfigured_passes_no_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "get_settings", lambda: AppSettings())
    captured = _capture_serve(monkeypatch)
    serve_http_main()
    assert captured["transport"] == "http"
    # Open endpoint, unchanged: no auth provider reached the server.
    assert captured["server"].auth is None


def test_serve_configured_injects_google_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from fastmcp.server.auth.providers.google import GoogleProvider

    monkeypatch.setattr(server, "get_settings", lambda: AppSettings(**_FULL, oauth_cache_dir=str(tmp_path)))
    captured = _capture_serve(monkeypatch)
    serve_http_main()
    assert isinstance(captured["server"].auth, GoogleProvider)


def test_serve_host_port_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "get_settings", lambda: AppSettings())
    monkeypatch.setenv("A2WEB_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("A2WEB_HTTP_PORT", "9001")
    captured = _capture_serve(monkeypatch)
    serve_http_main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9001
