# hotfix-fastmcp-error-envelope

Restore the MCP error envelope: a2kit v0.49.2 passes is_error= to fastmcp 3.2.4's ToolResult, which rejects it, destroying every typed error on both channels.
