"""The `a2web` command line — Typer commands DERIVED from the MCP tools.

a2kit generated this surface from the `App`. The sunset replaced the App, so
a2web owns the derivation now. It stays a *derivation* rather than a
hand-written parallel CLI for one reason: a hand-written one drifts. A flag
renamed on a tool but not on its command is a bug nothing catches, and the CLI
had no tests at all before `tests/contracts/cli/`.

**Why deriving is safe here, and was not under a2kit.** a2kit had to guess
which parameters were wire-facing, because its container silently swallowed any
parameter whose type it could resolve (design D1 — registering a provider for
`str` would have eaten every `url`). Sunset design D1 removed that partition:
a tool's parameter list *is* its wire schema, so `inspect.signature` is total
and unambiguous. Every `--flag` below is a tool parameter, and every tool
parameter is a `--flag`.

The descriptions are not duplicated either — `Annotated[T, pydantic.Field(
description=…)]` on the tool becomes `typer.Option(help=…)` here, so the MCP
schema and `--help` cannot disagree.

**What is deliberately NOT carried over from a2kit's CLI** (the goldens in
`tests/contracts/cli/` record the old behaviour; `DELTAS.md` records each
decision):

- `--format [auto|json|tsv|page-tsv]` — formatter surface that left with a2kit.
  `auto` emitted plain JSON on every a2web tool anyway; three of the four
  values were unreachable.
- `--json` — was byte-identical to the default on both web tools. A no-op flag.
- `schema` / `list-tools` / `code` / `_meta` — framework introspection, not
  product. `code` died with code-mode in FastMCP 4.8.
- The 50k output cap. a2kit exported `truncate()` with `DEFAULT_MAX_CHARS =
  50_000` but **never called it**, so the cap never fired and no observed
  behaviour depends on it. Adding one now would be a new behaviour, and a bad
  one: these commands emit a single JSON document, so slicing at N characters
  yields unparseable JSON — the failure mode is a caller's `json.loads`
  crashing on output that looks fine in a terminal. If output size ever needs
  bounding, bound a *field* before encoding, not the encoded string.
"""

from __future__ import annotations

import asyncio
import enum
import inspect
import json
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin

import typer
from lean_wire import dump_model_for_wire
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from . import __version__
from .components import Components, build_components
from .settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["build_cli", "field_to_typer_annotation", "main"]

#: Which command group each MCP tool lands in. A LITERAL table, for the same
#: reason `wire._TSV_FIELDS` is literal: the command tree is a contract the user
#: types, not something to re-derive from tool names. a2kit inferred it from
#: router slugs, which is why renaming a router would have silently moved a
#: command. A tool missing from this table is a hard error at build time
#: (`_assert_table_covers_tools`) rather than a command that quietly vanishes.
_TOOL_GROUPS: dict[str, tuple[str, str]] = {
    # tool name -> (group, command name)
    "query": ("web", "query"),
    "fetch_raw": ("web", "fetch_raw"),
    "cookies_refresh": ("cookies", "refresh"),
    "report_feedback": ("feedback", "report"),
}

_GROUP_HELP: dict[str, str] = {
    "web": "Fetch and query web pages.",
    "cookies": "Manage the local browser-cookie mirror.",
    "feedback": "Report your own feedback on a fetch (add-agent-invoked-feedback-tool).",
}


class Transport(enum.StrEnum):
    """Transports `serve` accepts. The two FastMCP transports a2web is tested on."""

    stdio = "stdio"
    http = "http"


def field_to_typer_annotation(annotation: Any) -> Any:
    """Rewrite `Annotated[T, pydantic.FieldInfo]` → `Annotated[T, typer.Option]`.

    Vendored from a2kit's `packages/cli/_field_to_typer.py` (54 lines) with one
    deliberate change, below. Lifting `FieldInfo.description` into
    `typer.Option(help=…)` is what keeps `--help` and the MCP tool schema from
    disagreeing: they are the same string.

    Other `FieldInfo` settings (constraints, validators) are left on the
    annotation. Typer does not honour them, but the tool body is still the
    pydantic-validated one, so a `min_length=1` violation is caught there.

    **The change:** a2kit returned the annotation unchanged when it was not
    `Annotated`, which made bare-typed params render as positional Arguments
    while annotated siblings rendered as Options — the shape of a parameter's
    *annotation* decided the shape of the *CLI*. Everything is an Option here.
    """
    if get_origin(annotation) is None or not hasattr(annotation, "__metadata__"):
        return Annotated[annotation, typer.Option()]

    args = get_args(annotation)
    base = args[0]
    description: str | None = None
    for meta in args[1:]:
        if isinstance(meta, FieldInfo) and meta.description:
            description = meta.description
            break

    if description is not None:
        return Annotated[base, typer.Option(help=description)]
    return Annotated[base, typer.Option()]


def _emit(result: object) -> None:
    """Write one compact JSON document to stdout.

    Compact separators are inherited contract, pinned by the goldens: scripts
    piping `a2web web query` into `jq` see the same bytes they always have.

    This dumps the model through its own wire serializer, so the CLI shows
    exactly what an MCP client's `structured_content` carries — the omit-empty
    pruning, the field tiers, the deviation rules. It does NOT apply
    `wire.encode_envelope`: the TSV blocks exist to save an LLM's tokens on the
    `content[0].text` channel, and a terminal is not that channel. That split
    matches a2kit's observed behaviour (`headings` came out as a JSON array,
    never TSV).
    """
    # `dump_model_for_wire`, not a bare `model_dump` — the shelf documents it as
    # the "single substrate helper for wire dumps", and its whole reason to
    # exist is that future wire-shaping lands in ONE place. A caller that keeps
    # its own `model_dump` beside the import does not receive that change, and
    # the divergence is invisible: both produce identical bytes today, which is
    # exactly why nothing would fail when they stop.
    payload = dump_model_for_wire(result) if isinstance(result, BaseModel) else result
    typer.echo(json.dumps(payload, separators=(",", ":"), default=str, ensure_ascii=False))


def _make_command(fn: Callable[..., Any], components: Components) -> Callable[..., None]:
    """Wrap an async tool function as a synchronous Typer command.

    The generated command carries the tool's own signature with each parameter
    re-annotated for Typer, so Typer sees real parameters rather than
    `**kwargs` — which is what makes `--help` complete and typo'd flags an
    error instead of a silent no-op.

    **Teardown is not optional here, it is what lets the process exit.** The
    command runs the tool and then unwinds the `ResourceScope` in the same
    event loop. Skipping it does not merely leak: `SqliteResource` runs an
    aiosqlite worker thread, and a non-daemon worker with no `close()` keeps
    the interpreter alive after the JSON has been printed — the command appears
    to succeed and then hangs forever. That was the first thing this CLI did.
    """
    hints = _resolved_hints(fn)
    signature = inspect.signature(fn)

    async def _run(kwargs: dict[str, Any]) -> Any:
        try:
            return await fn(**kwargs)
        finally:
            await components.aclose()

    def _command(**kwargs: Any) -> None:
        _emit(asyncio.run(_run(kwargs)))

    _command.__name__ = getattr(fn, "__name__", "command")
    _command.__doc__ = inspect.getdoc(fn)
    # Typer reads `__signature__` to build the options; setting it is the
    # documented way to give a `**kwargs` function a real parameter list.
    # `ty` does not model that attribute on a plain function object.
    _command.__signature__ = signature.replace(  # ty: ignore[unresolved-attribute]
        parameters=[
            # Typer cannot express keyword-only parameters, and the tools are
            # all keyword-only (`*,`). Presented as POSITIONAL_OR_KEYWORD; they
            # are still invoked by keyword above, so the tool sees what it
            # declared.
            param.replace(
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=field_to_typer_annotation(hints.get(name, param.annotation)),
            )
            for name, param in signature.parameters.items()
        ]
    )
    return _command


def _resolved_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    """`get_type_hints(include_extras=True)`, tolerating unresolvable names.

    `from __future__ import annotations` makes every annotation a string, so
    the `FieldInfo` metadata is invisible to `inspect.signature` alone — the
    descriptions would silently vanish from `--help` and nothing would fail.
    """
    import typing

    try:
        return typing.get_type_hints(fn, include_extras=True)
    except Exception:  # pragma: no cover - defensive; a bad annotation is a bug
        return {}


def _tool_function(tool: object) -> Callable[..., Any]:
    """The Python function behind a registered tool.

    `list_tools()` is typed as returning the base `Tool`; only `FunctionTool`
    carries `.fn`. Every a2web tool is registered via `@mcp.tool` on a function,
    so this always holds — but it holds by construction rather than by type, and
    the whole CLI is derived from it. A tool registered some other way (a proxy,
    a remote mount) would otherwise fail deep inside signature inspection with
    nothing pointing back to here.
    """
    fn = getattr(tool, "fn", None)
    if fn is None:
        raise RuntimeError(
            f"tool {getattr(tool, 'name', tool)!r} has no underlying function, so no CLI "
            "command can be derived from it. Give it an explicit command instead of "
            "listing it in `_TOOL_GROUPS`."
        )
    return fn


def _assert_table_covers_tools(tool_names: set[str]) -> None:
    missing = sorted(tool_names - set(_TOOL_GROUPS))
    if missing:
        raise RuntimeError(
            f"tools with no CLI placement: {missing}. Add them to "
            "`cli._TOOL_GROUPS`. A tool absent from the table would be reachable "
            "over MCP but invisible from the command line, which is exactly the "
            "silent drift deriving the CLI is meant to prevent."
        )


def build_cli(*, components: Components | None = None) -> typer.Typer:
    """Build the Typer app, deriving one command per registered MCP tool.

    `components` is the test seam, the same one `build_mcp_server` takes —
    stubbed tiers and fake extractors reach the CLI exactly the way they reach
    the MCP surface, so the CLI goldens exercise the real command bodies.

    Building the server here (rather than taking one) is deliberate: the CLI
    needs the *same* `Components` the tools closed over in order to tear it
    down after the command, and only the caller that built both can know they
    match.
    """
    from .server import build_mcp_server

    parts = components if components is not None else build_components()
    server = build_mcp_server(components=parts)
    app = typer.Typer(
        name="a2web",
        help="a2web — adaptive web fetching for AI agents.",
        no_args_is_help=True,
        add_completion=False,
    )
    groups: dict[str, typer.Typer] = {}

    tools = asyncio.run(server.list_tools())
    _assert_table_covers_tools({tool.name for tool in tools})

    for tool in tools:
        group_name, command_name = _TOOL_GROUPS[tool.name]
        if group_name not in groups:
            groups[group_name] = typer.Typer(help=_GROUP_HELP.get(group_name, ""), no_args_is_help=True)
            app.add_typer(groups[group_name], name=group_name)
        groups[group_name].command(name=command_name)(_make_command(_tool_function(tool), parts))

    _register_operational_commands(app)
    return app


def _register_operational_commands(app: typer.Typer) -> None:
    """`serve`, `health`, `version` — the commands with no MCP tool behind them."""

    @app.command()
    def serve(
        transport: Annotated[Transport, typer.Option(help="Transport to serve on.")] = Transport.stdio,
        host: Annotated[str, typer.Option(help="HTTP bind host.")] = "127.0.0.1",
        port: Annotated[int, typer.Option(help="HTTP bind port.")] = 8000,
    ) -> None:
        """Run the MCP server.

        `stdio` (the default) is what an MCP client spawns. `http` serves MCP
        under `/mcp` plus the `GET /health` readiness route the container
        probes.

        a2kit's `serve` carried `--code-mode`, `--compact`, `--tools`,
        `--select` and `--internal-uds`; all five described framework machinery
        that left with it. Its `--transport` was a free-form `TEXT`, so a typo
        reached FastMCP as an unknown transport at startup; the enum here makes
        it a parse error with the valid choices listed.
        """
        from .server import build_mcp_server

        server = build_mcp_server()
        if transport is Transport.stdio:
            server.run()
        else:
            server.run(transport=transport.value, host=host, port=port)

    @app.command()
    def health() -> None:
        """Run the readiness probe; exits non-zero when degraded.

        The same check `GET /health` serves, reachable without a running
        server — which is what makes it usable from a shell or a CI step.
        """
        from .components import build_components
        from .server import check_sqlite

        async def _probe() -> dict[str, Any]:
            parts = build_components()
            try:
                ok = await check_sqlite(await parts.sqlite())
            finally:
                await parts.aclose()
            return {"status": "ok" if ok else "degraded", "version": __version__}

        try:
            report = asyncio.run(_probe())
        except Exception as exc:
            _emit({"status": "error", "version": __version__, "detail": str(exc)})
            raise typer.Exit(code=1) from exc
        _emit(report)
        if report["status"] != "ok":
            raise typer.Exit(code=1)

    @app.command()
    def version() -> None:
        """Print the installed a2web version."""
        _emit({"version": __version__, "cookies_tool": get_settings().expose_cookies_tool})


def main() -> None:
    """Console-script entrypoint (`a2web`)."""
    build_cli()()
