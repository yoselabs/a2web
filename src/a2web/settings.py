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

# LLM provider selection mode. `auto` resolves via the preference order in
# `llm_resource.select_provider`; the concrete ids name a single backend.
# Declared once here so the field and the bench's selection boundary share it.
ProviderMode = Literal["auto", "anthropic", "claude-code", "openai_compatible"]

# Default Discourse-forum allowlist for `DiscourseHandler.matches()`. Shared
# between the `AppSettings.discourse_hosts` field default and the handler's
# no-settings fallback so the two never drift.
DEFAULT_DISCOURSE_HOSTS: tuple[str, ...] = ("linux.do", "meta.discourse.org")


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

    EXCLUDE: ClassVar[frozenset[str]] = frozenset(
        {
            "jina_key",
            "github_token",
            "zyte_key",
            "firecrawl_key",
            "google_client_secret",
            "google_jwt_signing_key",
            "oauth_encryption_key",
        }
    )

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

    # Paid last-resort fetch tiers (reddit-reachability-never-silent-miss).
    # Env-only secrets (`A2WEB_ZYTE_KEY` / `A2WEB_FIRECRAWL_KEY`); a YAML-set
    # value is dropped by `_YamlSourceWithoutSecrets`. Empty = the tier's
    # manifest returns `Unavailable` at boot, so the tier never registers and
    # zero-config fetches never incur cost. Dispatched out-of-band only after
    # the free/proxied ladder (raw → jina → browser → archive) is exhausted on
    # a wall verdict — never speculatively. A keyed-but-failing service surfaces
    # `paid_auth_error` loudly (bad key), never a silent downgrade.
    zyte_key: str = ""
    firecrawl_key: str = ""

    # listing-completeness Slice 2 — bounded scroll-to-complete. OFF by default:
    # enabling it lets a partial listing (parsed records short of the page's
    # advertised item oracle) escalate to ONE scrolling paid render, shifting the
    # common listing path from free-curl to paid egress — an operator's choice,
    # not a silent default. `listing_scroll_max` is the completeness ceiling:
    # above it (a broad search with thousands of hits) the response steers
    # (narrow the query) instead of scrolling. `listing_scroll_cap` bounds the
    # scroll actions per render.
    complete_listings: bool = False
    listing_scroll_max: int = 200
    listing_scroll_cap: int = 8

    # Reddit tier-arbitration policy (reddit-via-zyte). Governs whether the
    # Reddit handler routes threads eagerly through a paid tier (Zyte) for a
    # rich scored/nested comment sample, or stays on the keyless RSS channel:
    #   - "robustness" (default): keyed → old.reddit via Zyte raw mode (scored,
    #     nested, ~top-500), else RSS. Best answer; every read hits Zyte.
    #   - "privacy": never route Reddit through the third-party paid tier; RSS
    #     only (degraded, keyless, no third party sees the URL).
    # A future self-hosted browser rung slots in ahead of Zyte under the
    # "robustness" policy without changing this knob (design §5; deferred).
    reddit_tier_policy: Literal["robustness", "privacy"] = "robustness"

    browser_enabled: bool = True
    # Two browser rungs (browser-backend-bakeoff): the fast Chromium engine is
    # tried first (the `browser` tier); the robust CDP engine is escalated to
    # (the `browser_robust` tier) only when the fast render comes back
    # thin/blocked. See _manifests/browser_backends/ + _manifests/tiers/.
    browser_backend: str = "patchright"  # fast rung
    browser_backend_robust: str = "zendriver"  # robust rung (CDP)
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

    # Discourse-forum host allowlist for `DiscourseHandler`. Discourse runs on
    # arbitrary domains, so the handler claims a URL only when its host is
    # listed here (env `A2WEB_DISCOURSE_HOSTS`, or YAML). Defaults cover the
    # named targets; adding a forum is one config line, never code.
    discourse_hosts: list[str] = Field(default_factory=lambda: list(DEFAULT_DISCOURSE_HOSTS))

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
    llm_provider: ProviderMode = "auto"
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_api_key_env: str = "ANTHROPIC_API_KEY"
    # OpenAI-compatible backend — reads the OpenAI SDK's STANDARD env vars, not
    # custom a2web ones: `OPENAI_API_KEY` (key; presence gates availability and
    # derives the backend as the last-resort fallback), `OPENAI_BASE_URL`
    # (endpoint; unset → OpenAI proper, set for Gemini/DeepSeek/OpenRouter/
    # local), `OPENAI_MODEL` (model; else a host-keyed recommendation, else a
    # loud failure). Only this indirection is a2web-native: the NAME of the key
    # env var, defaulting to the standard `OPENAI_API_KEY` (override for e.g.
    # `OPENROUTER_API_KEY`). Secret stays env-only.
    #
    # Validating a custom model before you trust it in prod: run the output bench
    # through the backend and read the **data-contract axis as the pass/fail gate**
    # (a model that cannot emit valid router-shape JSON is disqualified regardless
    # of quality) —
    #   A2WEB_BENCH_PROVIDER=openai_compatible OPENAI_BASE_URL=… OPENAI_API_KEY=… \
    #   OPENAI_MODEL=… make bench
    # The committed reference sweep (`eval/model_benchmark/`, re-run every couple
    # of months) prescribes the current default; DeepSeek V4 Flash is the
    # cheapest backend that clears the contract at Haiku-class quality.
    llm_openai_api_key_env: str = "OPENAI_API_KEY"
    extraction_max_chars: int = 100_000  # matches WebFetch's BD_ constant
    extraction_cache_ttl_s: int = 900  # matches WebFetch's sg5 (15 min)

    # Exposure toggle for the local-only `cookies_refresh` tool. Default OFF:
    # a2web served as a network MCP server has no local browser to read cookies
    # from, so the tool is pointless (and mildly surprising) on a server — the
    # `CookiesRouter` is simply not registered. Flip to `true`
    # (`A2WEB_EXPOSE_COOKIES_TOOL=true`) when running serve LOCALLY and you want
    # the cookie mirror. Independent of the `[cookies]` extra: this controls
    # whether the tool is *exposed*; the extra controls whether it can *function*
    # (absent extra → the tool returns a loud "install a2web[cookies]" note).
    expose_cookies_tool: bool = False

    # v0.16: opt-in browser cookie source. Default `none` keeps the subsystem
    # inert — no resource construction, no DB access, no Keychain prompts.
    # Backed by the `[cookies]` extra (browser-cookie3): local-only, cross-browser
    # (Chrome / Chromium / Brave / Edge / Firefox / Safari / …). The Keychain
    # prompt fires only on `cookies_refresh`.
    cookie_source: Literal[
        "none",
        "chrome",
        "chromium",
        "brave",
        "edge",
        "firefox",
        "safari",
        "vivaldi",
        "opera",
        "opera_gx",
    ] = "none"
    cookie_profile: str = "Default"
    cookie_stale_after_hours: int = 24

    # Google OAuth on the HTTP MCP endpoint (env-only; a2kit `docs/patterns/mcp-auth.md`).
    # Unset → the endpoint stays open (ship behind Tailscale/LAN). Auth engages
    # only when the HTTP serve entrypoint (`a2web-serve`) sees all three of
    # client_id/secret/base_url set. Secrets are env-only (dropped from YAML).
    google_client_id: str = ""
    google_client_secret: str = ""
    # PUBLIC base URL of the deployment. FastMCP derives the OAuth redirect from
    # it, so it MUST be the externally-reachable URL (e.g. https://a2web.example.com),
    # NOT the bind host (0.0.0.0). Must match the GCP client's authorized redirect.
    google_base_url: str = ""
    google_required_scopes: list[str] = ["openid", "email"]
    # Stable JWT signing key (`openssl rand -hex 32`). Recommended: without it,
    # tokens can't be re-validated across a restart. Optional here (in-memory-ish
    # sessions until the persistent store is populated). Env-only.
    google_jwt_signing_key: str = ""
    # Persistent OAuth token store (fastmcp FileTreeStore). Default: <cache_dir>/oauth
    # on the volume, so sessions survive container restarts. No new dependency —
    # the store ships with fastmcp.
    oauth_cache_dir: str = ""
    # Optional Fernet passphrase to encrypt the token store at rest (cryptography
    # is already a dep, so this is free). Env-only. Unset → plaintext on the volume.
    oauth_encryption_key: str = ""

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
