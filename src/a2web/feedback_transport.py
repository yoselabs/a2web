"""OTLP/HTTP-logs POST mechanics for a2web's mechanical, pipeline-triggered
feedback reporting (`fetcher/pipeline.py`'s `_record_feedback` — a fetch
resolved a warning/critical `OperatorHint` or low confidence).

The agent-invoked `report_feedback` tool no longer lives here — it's the
shelf `mcp-feedback` package now (`adopt-shelf-mcp-feedback`), which owns
its own copy of this same POST shape. This module keeps its own copy for
the mechanical reporter because that payload (`hint_code`/`chain`/
`tier_used`/`confidence`) is fetch-pipeline-specific and out of the shelf
package's scope (`adopt-shelf-mcp-feedback` design D1).

Not the OTel SDK's Logs API: that API is marked unstable/private in the
Python SDK (`opentelemetry.sdk._logs`, underscore-prefixed) and its exporter
is synchronous (`requests`-based), which would need an `asyncio.to_thread`
bridge in this async-native codebase for no proven benefit over the
hand-rolled POST here (`unify-otel-telemetry-seam` design D1).
"""

from __future__ import annotations

import httpx

from .log import log_warning
from .settings import AppSettings


async def post_feedback_logs(
    settings: AppSettings,
    *,
    scope_name: str,
    resource_attrs: list[dict[str, object]],
    log_records: list[dict[str, object]],
) -> bool:
    """POST one OTLP/HTTP logs payload. No-op unless feedback reporting is
    fully configured. Never raises — a dead gateway must never surface as a
    caller-visible failure.

    Returns whether a send was ATTEMPTED (`feedback_enabled` + endpoint/key
    all present) — never whether it was actually delivered, which is
    invisible by design (best-effort, swallowed on failure) and stays that
    way for callers that don't need to distinguish "off" from "attempted".
    """
    if not settings.feedback_enabled or not settings.feedback_api_key or not settings.feedback_endpoint:
        return False
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": resource_attrs},
                "scopeLogs": [{"scope": {"name": scope_name}, "logRecords": log_records}],
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                settings.feedback_endpoint,
                json=payload,
                headers={"X-Api-Key": settings.feedback_api_key},
            )
    except (httpx.HTTPError, OSError) as exc:  # telemetry is best-effort — never break the caller
        log_warning("feedback_report_failed", error=str(exc))
    return True
