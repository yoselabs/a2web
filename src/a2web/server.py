"""a2web server entrypoint — `a2kit.App` composition.

No `connections_cli` — a2web has no per-instance connection concept. Global
configuration is loaded from a single optional YAML file plus env vars; see
`a2web.settings`.
"""

from __future__ import annotations

import a2kit

from .routers import WebRouter
from .state import register_state

app = register_state(a2kit.App("a2web").add_router(WebRouter()))


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
