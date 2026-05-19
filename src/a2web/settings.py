"""Global a2web configuration — single optional YAML file plus env vars.

Precedence (highest first):
1. `A2WEB_*` environment variables (e.g. `A2WEB_STEALTH=true`).
2. YAML file at `$A2WEB_CONFIG` (when set), otherwise `~/.a2web/config.yaml`.
3. Hard-coded defaults.

Secrets (`jina_key`) are env-only — a YAML-set value is ignored. The fetch
tool MUST work zero-config; absence of both file and env vars is the
expected default.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_ENV_REF_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _resolve_env_refs(value: str) -> str:
    """Replace `${VAR}` with `os.environ[VAR]`; leave literal on miss."""

    def _sub(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), match.group(0))

    return _ENV_REF_RE.sub(_sub, value)


class ProxyEntry(BaseModel):
    """One proxy in the pool. `${ENV_VAR}` references in `url` are resolved at load."""

    url: str
    region: str = "unknown"
    kind: Literal["datacenter", "residential", "mobile"] = "datacenter"

    @field_validator("url", mode="after")
    @classmethod
    def _resolve_env(cls, value: str) -> str:
        return _resolve_env_refs(value)


class RouteRule(BaseModel):
    """One row of the proxy-routing table; first match wins."""

    host: str | None = None
    tier: str | None = None
    proxy: str = "direct"
    proxy_required: bool = False
    fallback: list[str] = Field(default_factory=list)


def _resolve_yaml_path() -> Path | None:
    override = os.environ.get("A2WEB_CONFIG")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    default = Path.home() / ".a2web" / "config.yaml"
    return default if default.is_file() else None


class _YamlSourceWithoutSecrets(YamlConfigSettingsSource):
    """YAML source that drops fields the user must supply via env only."""

    EXCLUDE: ClassVar[frozenset[str]] = frozenset({"jina_key", "github_token"})

    def __call__(self) -> dict[str, Any]:
        data = super().__call__()
        for key in self.EXCLUDE:
            data.pop(key, None)
        return data


class AppSettings(BaseSettings):
    """Global a2web settings loaded from env + YAML file.

    The model carries the default proxy-pool, route table, cache TTLs, and
    diagnostics defaults. Tools never receive this object directly in PR1;
    PR2 wires it through `AppState` for tier dispatch.
    """

    model_config = SettingsConfigDict(
        env_prefix="A2WEB_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    default_ua: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    stealth: bool = False

    proxies: dict[str, ProxyEntry] = Field(default_factory=dict)
    routes: list[RouteRule] = Field(default_factory=list)

    cache_ttl_static_h: int = 168
    cache_ttl_article_h: int = 24
    cache_ttl_live_m: int = 5

    diagnostics_default: Literal["off", "brief", "full"] = "off"
    live_only_hosts: list[str] = Field(default_factory=lambda: ["reddit.com", "news.ycombinator.com"])

    jina_key: str = ""
    jina_deny_hosts: list[str] = Field(default_factory=list)

    github_token: str = ""

    browser_enabled: bool = True
    browser_max_pool: int = 4
    browser_idle_timeout_s: int = 300
    browser_page_budget_s: int = 30

    # v0.10: hosts known to be JS-heavy CSR apps. When the gate sees a
    # thin browser-tier response (<1KB) from one of these hosts, it
    # downgrades to length_floor so escalation continues. Combined with
    # the seed list at fetcher._JS_HEAVY_HOSTS_SEED.
    js_heavy_hosts_extra: list[str] = Field(default_factory=list)

    # v0.3: Twitter / X handler via Nitter rotation. Empty list = handler
    # effectively disabled (`matches` returns False) so the orchestrator
    # falls through to raw + browser tiers as before. Public Nitter
    # instances rotate/die constantly — keep this empty until the operator
    # commits to a maintained list.
    nitter_instances: list[str] = Field(default_factory=list)

    # v0.4/v0.7: LLM-backed extraction. Activated by the `ask=` param on
    # the fetch tool. As of v0.7 the SDKs are baseline deps — no extra
    # install needed. Default model matches Claude Code's WebFetch
    # sub-call (research/123).
    #
    # `auto`         — prefer ClaudeCodeProvider if `claude-agent-sdk` + the
    #                  `claude` CLI are available (uses the OS session, no
    #                  API key needed); fall back to AnthropicProvider.
    # `anthropic`    — direct Anthropic Messages API; requires API key.
    # `claude-code`  — Claude Code OS session via `claude-agent-sdk` only.
    llm_provider: Literal["auto", "anthropic", "claude-code"] = "auto"
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_api_key_env: str = "ANTHROPIC_API_KEY"
    extraction_max_chars: int = 100_000  # matches WebFetch's BD_ constant
    extraction_cache_ttl_s: int = 900  # matches WebFetch's sg5 (15 min)

    # v0.7: when true, only the `ask` tool is exposed on the MCP/CLI
    # surface — `fetch_raw` is hidden. Forces calling agents through the
    # cheap server-side Haiku extractor for cost discipline. Stop-gap
    # toggle until a2kit absorbs proper per-tool selection upstream
    # (see docs/history/A2KIT_FEEDBACK_v0.39.md).
    ask_only: bool = False

    # v0.8: opt-in browser cookie source. Default `none` keeps the subsystem
    # inert — no resource construction, no DB access, no Keychain prompts.
    # `chrome` is macOS-only in v0.8; Linux/Windows deferred. `firefox`
    # reads `cookies.sqlite` directly (plaintext, no Keychain).
    cookie_source: Literal["none", "chrome", "firefox"] = "none"
    cookie_profile: str = "Default"
    cookie_stale_after_hours: int = 24

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_path = _resolve_yaml_path()
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if yaml_path is not None:
            sources.append(_YamlSourceWithoutSecrets(settings_cls, yaml_file=yaml_path))
        return tuple(sources)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Process-wide cached settings accessor for downstream PRs."""
    return AppSettings()
