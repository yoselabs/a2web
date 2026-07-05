# a2web — slim networked MCP server image (deployable-container-ci).
#
# Runs `a2web serve --transport=http --select surface=mcp`: MCP under /mcp, plus
# a transport-native GET /health liveness route (a2kit ships it at the parent
# root). The image bakes the patchright Chromium rung + its system libs so the
# browser tier never hits a runtime download on a read-only rootfs. It runs as a
# non-root user and keeps the sqlite HTTP cache on a volume-backable /data.
#
# Two heavy things are OUT of the slim image, each behind a build arg:
#   - the browser rung (patchright + zendriver + baked Chromium + its desktop
#     system-lib tree, ~1.35GB) — INSTALL_BROWSER=true. The tier is
#     escalation-only; when absent, browser sites degrade to a loud
#     `try_user_browser` hint (Zyte/Firecrawl still cover hard sites via API).
#   - the Claude Code OS-session backend (claude-agent-sdk, ~210MB) —
#     INSTALL_CLAUDE_CODE=true. The container's default LLM path is
#     OpenAI-compatible (DeepSeek).
#
#   docker build -t a2web .                                   # slim, ~600MB
#   docker build --build-arg INSTALL_BROWSER=true -t a2web-browser .   # ~1.9GB
#   docker run --rm -p 8000:8000 -v a2web-cache:/data \
#     -e OPENAI_API_KEY=... -e OPENAI_BASE_URL=... -e OPENAI_MODEL=... a2web
#   # MCP:    http://localhost:8000/mcp   liveness: http://localhost:8000/health

# Pinned to the uv that produced uv.lock, for a reproducible resolve.
FROM ghcr.io/astral-sh/uv:0.10.12 AS uv

FROM python:3.12-slim

# curl: HEALTHCHECK probe. ca-certificates: TLS to upstreams + LLM endpoints.
# git: a2kit is a git dependency (with a git-subdir `a2effect`), so uv needs git
# at resolve time. (Backlog: a multi-stage build could drop git from the runtime
# layer; kept single-stage here for simplicity.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

# Shared browser cache — both `patchright install` (build) and the launched
# browser (runtime) resolve here, so install location and launch location agree.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Layer 1: dependencies only (cached across source edits). --no-install-project
# resolves the venv from the frozen lockfile without the app itself.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Layer 2: the application source + the project install. Extras are opt-in:
# --extra browser adds patchright + zendriver; --extra claude-code adds the SDK.
COPY src ./src
ARG INSTALL_CLAUDE_CODE=false
ARG INSTALL_BROWSER=false
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
      $( [ "$INSTALL_BROWSER" = "true" ] && echo "--extra browser" ) \
      $( [ "$INSTALL_CLAUDE_CODE" = "true" ] && echo "--extra claude-code" )

# Bake the Chromium rung + every system lib a Chromium needs (fonts, libnss,
# libatk, ...) ONLY when the browser extra is installed. --with-deps runs apt as
# root here, so nothing is downloaded at runtime. Skipped for the slim image.
RUN if [ "$INSTALL_BROWSER" = "true" ]; then patchright install --with-deps chromium; fi

# Non-root runtime. The browser cache and the source tree stay root-owned and
# world-readable (read-only at runtime); only the sqlite cache dir needs to be
# writable by the app user.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown -R app:app /data
ENV A2WEB_CACHE_DIR=/data
VOLUME /data

EXPOSE 8000
# Liveness against the LIVE serve process (not the CLI): the a2kit-served root
# /health returns 200 while the multiplex parent is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

USER app
ENTRYPOINT ["a2web"]
CMD ["serve", "--transport=http", "--host=0.0.0.0", "--port=8000", "--select", "surface=mcp"]
