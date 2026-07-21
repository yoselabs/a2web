"""The typed error envelope on the MCP wire — two pieces, and both are required.

**Why it cannot be one middleware.** FastMCP masks a plain exception escaping a
tool body *before* any middleware sees it: the middleware receives a generic
`ToolError` with the original long gone, so there is nothing left to build an
envelope from. The exception has to be converted at the tool boundary, while
its `__cause__` chain is still intact.

So:

1. `guard_tool` wraps each tool body. A non-`AppError` is quarantined into
   `UnexpectedDefect` (a bug is a bug, and the wire says so); the typed error
   is then raised as `ToolError(prose) from exc`, which FastMCP renders into
   `content[0].text` with `isError: true`.
2. `TypedErrorEnvelopeMiddleware` catches that `ToolError` on the way out,
   recovers the typed error from `__cause__`, and returns a
   `ToolResult(is_error=True)` carrying the prose in `content` and
   `{"error": envelope}` in `structured_content`.

The two channels deliberately do not overlap: prose for the model, envelope for
machine consumers. Do not "unify" them — the prose is what an agent reads to
decide what to do next, and the envelope is what a caller parses.

`ToolResult(is_error=True)` requires fastmcp >= 3.4; on 3.2/3.3 the keyword is
silently ignored and every error serves as a success. That floor is pinned in
`pyproject.toml`.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from a2effect import AppError
from a2effect.defect import quarantine
from fastmcp.exceptions import FastMCPError, ToolError
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from mcp.types import TextContent

__all__ = ["TypedErrorEnvelopeMiddleware", "format_error_prose", "guard_tool"]

_T = TypeVar("_T")

#: Human-readable label per error kind. Transcribed from a2kit's
#: `_CORE_KIND_LABELS`; the strings are wire contract (they open
#: `content[0].text` on every failure) and are pinned by the error goldens.
_KIND_LABELS: dict[str, str] = {
    "input": "Input error",
    "auth": "Authentication required",
    "policy": "Not allowed",
    "infra": "Service unavailable",
    "bug": "Internal error",
}


def _kind_label(kind: str) -> str:
    """Label for `kind`, resolving extension kinds through their base."""
    label = _KIND_LABELS.get(kind)
    if label is not None:
        return label
    from a2effect.errors import _KIND_EXTENSIONS

    ext = _KIND_EXTENSIONS.get(kind)
    return _KIND_LABELS[ext.base] if ext is not None else kind.capitalize()


def format_error_prose(exc: AppError) -> str:
    """Render an `AppError` to the fixed prose form.

        {KindLabel} ({Type}): {message}

        Hint: {hint}

    The `Hint:` block is omitted entirely when there is no hint.
    """
    cls = type(exc)
    label = cls.kind_label if cls.kind_label is not None else _kind_label(cls.kind)
    head = f"{label} ({cls.__name__}): {exc}"
    return f"{head}\n\nHint: {exc.hint}" if exc.hint else head


def guard_tool(fn: Callable[..., Awaitable[_T]]) -> Callable[..., Awaitable[_T]]:
    """Convert an escaping exception into the wire's typed error form.

    A `FastMCPError` the author raised deliberately passes through unwrapped —
    re-encoding it would double-wrap a message that is already wire-shaped.
    """

    @functools.wraps(fn)
    async def _guarded(*args: Any, **kwargs: Any) -> _T:
        try:
            return await fn(*args, **kwargs)
        except FastMCPError:
            raise
        except AppError as exc:
            raise ToolError(format_error_prose(exc)) from exc
        except Exception as exc:
            defect = quarantine(exc)
            raise ToolError(format_error_prose(defect)) from defect

    return _guarded


class TypedErrorEnvelopeMiddleware(Middleware):
    """Attach `{"error": envelope}` to `structured_content` on typed failures."""

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        try:
            return await call_next(context)
        except ToolError as err:
            cause = err.__cause__
            if not isinstance(cause, AppError):
                raise
            return ToolResult(
                content=[TextContent(type="text", text=str(err))],
                structured_content={"error": cause.to_envelope_dict()},
                is_error=True,
            )
