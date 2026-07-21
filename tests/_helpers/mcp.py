"""The in-process MCP test seam — what `a2kit.testing.client` used to be.

a2kit's client built the server, then let a test mutate the DI registry
(`app.provide(LlmExtractorResource, lambda: fake)`) to swap a resource. That
worked, but it could also silently do nothing: providing a key nothing resolved
was not an error, so a stale override in a test read as "the fake was used"
when in fact production code ran.

Here the substitution is a `Components` field. `dataclasses.replace` fails
loudly on a name that does not exist, so an override that stopped matching the
graph breaks the test instead of quietly disarming it.

`call_wire` returns the raw `content[0].text` — the string the agent actually
receives, envelope encoding and all. Tests that want the machine channel read
`result.structured_content` instead; they are different payloads on purpose.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
from collections.abc import AsyncIterator
from typing import Any

from fastmcp import Client

from a2web.components import Components, build_components
from a2web.lazy import lazy
from a2web.server import build_mcp_server
from a2web.settings import AppSettings, get_settings

__all__ = ["build_test_components", "call_text", "call_wire", "mcp_client"]


def build_test_components(
    *,
    settings: AppSettings | None = None,
    **overrides: Any,
) -> Components:
    """Build a `Components` with resources swapped for fakes.

    Each override is either a ready instance (wrapped as a `Lazy` thunk here)
    or an already-`Lazy` callable — the fetch pipeline cannot tell the
    difference, and tests should not have to care.
    """
    parts = build_components(settings=settings if settings is not None else get_settings())
    if not overrides:
        return parts
    wrapped = {name: (value if callable(value) else lazy(value)) for name, value in overrides.items()}
    return dataclasses.replace(parts, **wrapped)


@contextlib.asynccontextmanager
async def mcp_client(
    *,
    settings: AppSettings | None = None,
    components: Components | None = None,
    **client_kwargs: Any,
) -> AsyncIterator[Client]:
    """A real `fastmcp.Client` over the real production server assembly."""
    server = build_mcp_server(settings=settings, components=components)
    async with Client(transport=server, **client_kwargs) as client:
        yield client


async def call_wire(client: Client, tool: str, **kwargs: Any) -> str:
    """Call `tool`; return the MACHINE channel (`structured_content`) as JSON.

    This is the channel a2kit's `client.call_wire` reported, so the ~1350
    existing field-presence assertions keep meaning what they meant. It is the
    pruned model dump: a field absent here was empty.

    **It is not the whole wire.** `content[0].text` carries the same payload
    plus the TSV blocks and their `_<field>_format` discriminators, and an
    empty TSV field is *present-but-empty* there while it is *absent* here. A
    test that means to assert on what the agent reads must use `call_text`;
    asserting `"headings" not in call_wire(...)` says nothing about whether
    the agent sees a `headings` key.
    """
    result = await client.call_tool(tool, kwargs)
    return json.dumps(result.structured_content)


async def call_text(client: Client, tool: str, **kwargs: Any) -> str:
    """Call `tool` and return the agent-facing `content[0].text` string."""
    result = await client.call_tool(tool, kwargs)
    return result.content[0].text
