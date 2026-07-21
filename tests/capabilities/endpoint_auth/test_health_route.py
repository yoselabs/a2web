"""`GET /health` — the route the container HEALTHCHECK actually curls.

**Why this file exists.** a2kit's multiplex parent served `/health` for free,
so nothing in a2web ever asserted it. The sunset's Phase 4 replaced that parent
with `mcp.run(transport="http")` and the route vanished: the container went on
serving MCP perfectly while every 30s probe 404'd, which after `--retries=3`
marks it unhealthy and invites an orchestrator restart-loop on a healthy
process. 1212 tests passed through that change.

The probe was invisible to pytest because it lived in the Dockerfile. So this
test reads the path *out of the Dockerfile* rather than hardcoding it — editing
the HEALTHCHECK to a path the server does not serve fails here, and so does
removing the route.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from a2web.server import build_mcp_server

_DOCKERFILE = Path(__file__).resolve().parents[3] / "Dockerfile"

#: `CMD curl -fsS http://localhost:8000/health || exit 1`
_HEALTHCHECK_URL_RE = re.compile(r"curl\s+[-\w]*\s*(https?://[^\s|]+)")


def _healthcheck_path() -> str:
    match = _HEALTHCHECK_URL_RE.search(_DOCKERFILE.read_text())
    assert match is not None, (
        f"no `curl <url>` HEALTHCHECK found in {_DOCKERFILE}. If the container "
        "probe moved to another mechanism, retarget this test at it — do not "
        "delete it; an unprobed container is how Phase 4 shipped a 404."
    )
    return "/" + match.group(1).split("/", 3)[3]


def test_dockerfile_healthcheck_path_is_served() -> None:
    path = _healthcheck_path()
    with TestClient(build_mcp_server().http_app()) as client:
        response = client.get(path)

    assert response.status_code == 200, (
        f"the Dockerfile HEALTHCHECK curls {path}, which the server answered "
        f"with {response.status_code}. The container would be marked unhealthy "
        "while serving correctly."
    )
    assert response.json()["status"] == "ok"


def test_health_reports_degraded_rather_than_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """A probe must always answer. A 500 from a crashed handler is
    indistinguishable to Docker from a dead process, but it is a *different*
    operational story — so the failure path returns a 503 with a reason.
    """
    import a2web.server as server

    async def _boom(_sqlite: object) -> bool:
        raise RuntimeError("sqlite is wedged")

    monkeypatch.setattr(server, "check_sqlite", _boom)

    with TestClient(build_mcp_server().http_app()) as client:
        response = client.get(_healthcheck_path())

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert "wedged" in response.json()["detail"]
