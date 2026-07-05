# a2web — slim networked MCP server image (deployable-container-ci).
#
# Runs `a2web serve --transport=http --select surface=mcp`: MCP under /mcp, plus
# a transport-native GET /health liveness route (a2kit ships it at the parent
# root). Multi-stage: a builder resolves the venv (needs git + uv), and a clean
# runtime layer copies only the venv + source — no git, no uv, no build caches.
# Runs as a non-root user; keeps the sqlite HTTP cache on a volume-backable /data.
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
#   docker build -t a2web .                                            # slim
#   docker build --build-arg INSTALL_BROWSER=true -t a2web-browser .   # +browser
#   docker run --rm -p 8000:8000 -v a2web-cache:/data \
#     -e OPENAI_API_KEY=... -e OPENAI_BASE_URL=... -e OPENAI_MODEL=... a2web
#   # MCP:    http://localhost:8000/mcp   liveness: http://localhost:8000/health

# Pinned to the uv that produced uv.lock, for a reproducible resolve.
FROM ghcr.io/astral-sh/uv:0.10.12 AS uv

# ---- builder: resolve the venv into /app/.venv (git for the a2kit git-dep) ---
FROM python:3.12-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
ARG INSTALL_CLAUDE_CODE=false
ARG INSTALL_BROWSER=false

# Layer 1: dependencies only (cached across source edits). --no-install-project
# resolves the venv from the frozen lockfile without the app itself. Extras are
# opt-in: --extra browser adds patchright + zendriver; --extra claude-code the SDK.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
      $( [ "$INSTALL_BROWSER" = "true" ] && echo "--extra browser" ) \
      $( [ "$INSTALL_CLAUDE_CODE" = "true" ] && echo "--extra claude-code" )

# Layer 2: application source + the project install.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
      $( [ "$INSTALL_BROWSER" = "true" ] && echo "--extra browser" ) \
      $( [ "$INSTALL_CLAUDE_CODE" = "true" ] && echo "--extra claude-code" )

# ---- runtime: slim, glibc, shell+curl for HEALTHCHECK; no git, no uv ---------
FROM python:3.12-slim
# curl: HEALTHCHECK probe. ca-certificates: TLS to upstreams + LLM endpoints.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Same base as the builder → the venv's interpreter symlink
# (/app/.venv/bin/python → /usr/local/bin/python3.12) resolves here unchanged.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers \
    A2WEB_CACHE_DIR=/data \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Browser bake happens in the RUNTIME stage so --with-deps' apt system libs
# (fonts, libnss, libatk, ...) land in the shipped image, not a discarded
# builder. Chromium binaries go to PLAYWRIGHT_BROWSERS_PATH. Slim image skips it.
ARG INSTALL_BROWSER=false
RUN if [ "$INSTALL_BROWSER" = "true" ]; then patchright install --with-deps chromium; fi

# Non-root runtime. Only the sqlite cache dir needs to be app-writable.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown -R app:app /data
VOLUME /data

EXPOSE 8000
# Liveness against the LIVE serve process (not the CLI): the a2kit-served root
# /health returns 200 while the multiplex parent is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

USER app
ENTRYPOINT ["a2web"]
CMD ["serve", "--transport=http", "--host=0.0.0.0", "--port=8000", "--select", "surface=mcp"]
