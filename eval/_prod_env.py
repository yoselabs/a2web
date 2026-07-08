"""Run a command with the a2web MCP server's env applied — production-parity bench.

The output benchmark reads secrets (e.g. `A2WEB_ZYTE_KEY`) from the environment,
but those live only in the installed MCP server's config
(`~/.claude.json` -> `mcpServers.a2web.env`), NOT in a developer shell. A keyless
bench falsely flags Zyte-served hosts (Reddit and friends) as blocked, so it
under-reports real reliability. This shim merges that env into the child process
and `exec`s the real command, so:

  * the bench sees exactly the keys production sees (end-to-end parity), and
  * no secret ever appears on a command line or in a `make` variable (the env is
    passed to `execvpe`, never as argv) -- so it won't leak into `ps`/`--debug`.

The caller's own environment always wins (an explicit `A2WEB_ZYTE_KEY=...` on the
command line overrides the config), and a missing file/key degrades to a plain
keyless run. Usage: `python eval/_prod_env.py <cmd> [args...]`.
"""

from __future__ import annotations

import json
import os
import sys

_MCP_CONFIG = os.path.expanduser("~/.claude.json")
_SERVER = "a2web"


def _mcp_env() -> dict[str, str]:
    """Env dict declared for the a2web MCP server, or empty on any absence/error."""
    try:
        with open(_MCP_CONFIG, encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        return {}
    entry = servers.get(_SERVER)
    if not isinstance(entry, dict):
        return {}
    env = entry.get("env")
    if not isinstance(env, dict):
        return {}
    return {str(k): str(v) for k, v in env.items() if v is not None}


def main() -> None:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: python eval/_prod_env.py <cmd> [args...]\n")
        raise SystemExit(2)
    merged = dict(os.environ)
    applied: list[str] = []
    for key, value in _mcp_env().items():
        if key not in merged:  # caller's env wins
            merged[key] = value
            applied.append(key)
    if applied:
        sys.stderr.write(f"[prod-env] applied from MCP config: {', '.join(sorted(applied))}\n")
    # execvpe (no shell) is deliberate: the merged env — including secrets — is
    # passed as the env argument, never as argv, so it can't leak into `ps`.
    os.execvpe(sys.argv[1], sys.argv[1:], merged)  # noqa: S606


if __name__ == "__main__":
    main()
