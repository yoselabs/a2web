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
from a2web.settings import AppSettings, _YamlSourceWithoutSecrets

_FULL = {
    "google_client_id": "cid.apps.googleusercontent.com",
    "google_client_secret": "secret",
    "google_base_url": "https://a2web.example.com",
}


# --------------------------------------------------------------------- #
# Provider construction + gating
# --------------------------------------------------------------------- #


def test_unconfigured_returns_none() -> None:
    """No GOOGLE_CLIENT_ID → None → endpoint stays open (ship behind Tailscale/LAN)."""
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
    exclude = _YamlSourceWithoutSecrets.EXCLUDE
    assert {"google_client_secret", "google_jwt_signing_key", "oauth_encryption_key"} <= exclude


# --------------------------------------------------------------------- #
# serve_http_main path selection (no socket bound; seam mocked)
# --------------------------------------------------------------------- #


def _capture_serve(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the runtime build + serve_process; return the captured kwargs."""
    captured: dict[str, Any] = {}
    import a2kit.packages.serve as serve_mod
    import a2kit.runtime as rt_mod

    monkeypatch.setattr(rt_mod, "build", lambda app: app)
    monkeypatch.setattr(rt_mod, "apply_selection", lambda runtime, sel: ("runtime", sel))

    def _fake_serve(runtime: Any, **kw: Any) -> None:
        captured["runtime"] = runtime
        captured.update(kw)

    monkeypatch.setattr(serve_mod, "serve_process", _fake_serve)
    return captured


def test_serve_unconfigured_passes_no_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "get_settings", lambda: AppSettings())
    captured = _capture_serve(monkeypatch)
    serve_http_main()
    assert captured["transport"] == "http"
    assert captured["mcp_options"] is None  # open endpoint, unchanged
    assert captured["runtime"] == ("runtime", ["surface=mcp"])


def test_serve_configured_injects_google_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from fastmcp.server.auth.providers.google import GoogleProvider

    monkeypatch.setattr(server, "get_settings", lambda: AppSettings(**_FULL, oauth_cache_dir=str(tmp_path)))
    captured = _capture_serve(monkeypatch)
    serve_http_main()
    assert isinstance(captured["mcp_options"]["auth"], GoogleProvider)


def test_serve_host_port_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "get_settings", lambda: AppSettings())
    monkeypatch.setenv("A2WEB_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("A2WEB_HTTP_PORT", "9001")
    captured = _capture_serve(monkeypatch)
    serve_http_main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9001
